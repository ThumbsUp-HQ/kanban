# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Server-Sent Events endpoint (/sse) with Last-Event-ID resume and RLS filtering (KB-P3-16)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import Request  # noqa: TC002
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from database.session import RLSContext
from kanban.auth.sessions.cookies import (
    extract_session_cookie,
    hash_session_token,
    parse_session_cookie,
)
from kanban.realtime.hub import (
    MAX_CHANNELS_PER_CONNECTION,
    RealtimeHub,
    SSEConnection,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import SessionService

logger = logging.getLogger("kanban.api.sse")

__all__ = [
    "handle_sse_endpoint",
]


async def _resolve_authenticated_session(
    request: Request,
    session_factory: RLSSessionFactory | None,
    session_service: SessionService | None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, bytes] | None:
    """Extract and verify session cookie, resolving session credentials."""
    if session_factory is None or session_service is None:
        return None

    cookie_header = request.headers.get("cookie")
    cookie_val = extract_session_cookie(cookie_header)
    if not cookie_val:
        return None

    token = parse_session_cookie(cookie_val, session_service.session_hmac_key)
    if not token:
        return None

    token_sha256 = hash_session_token(token)

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("session",),
        aal_level=1,
    )
    async with session_factory.session(anon_ctx) as session:
        user_session = await session_service.resolve_session(session, token_sha256)

    if user_session is None or user_session.mfa_pending:
        return None

    return (user_session.principal_id, user_session.workspace_id, user_session.id, token_sha256)


async def handle_sse_endpoint(request: Request) -> StreamingResponse | JSONResponse:  # noqa: C901
    """Handle incoming SSE stream connection, authentication, and event replay."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    session_service: SessionService | None = getattr(request.app.state, "session_service", None)

    # 1. Authenticate via session cookie
    session_auth = await _resolve_authenticated_session(request, session_factory, session_service)
    if session_auth is None:
        return JSONResponse(
            status_code=401,
            content={
                "code": "UNAUTHENTICATED",
                "detail": "Valid session cookie required",
                "status": 401,
                "title": "Unauthorized",
                "type": "about:blank",
            },
            media_type="application/problem+json",
        )

    principal_id, workspace_id, session_id, token_sha256 = session_auth

    # 2. Parse and validate channel parameters
    channels_raw = request.query_params.get("channels") or request.query_params.get("channel", "")
    requested_channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    if len(requested_channels) > MAX_CHANNELS_PER_CONNECTION:
        return JSONResponse(
            status_code=422,
            content={
                "code": "CHANNEL_LIMIT_EXCEEDED",
                "detail": f"Exceeded maximum {MAX_CHANNELS_PER_CONNECTION} channels limit",
                "status": 422,
                "title": "Unprocessable Entity",
                "type": "about:blank",
            },
            media_type="application/problem+json",
        )

    # 3. Obtain or initialize RealtimeHub
    hub: RealtimeHub | None = getattr(request.app.state, "realtime_hub", None)
    if hub is None:
        hub = RealtimeHub(
            broker=getattr(request.app.state, "broker", None),
            session_factory=session_factory,
            session_service=session_service,
        )
        request.app.state.realtime_hub = hub
        await hub.start()

    conn = SSEConnection(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        principal_id=principal_id,
        session_id=session_id,
        token_sha256=token_sha256,
    )

    # 4. Enforce connection limit (max 16 per principal)
    registered = await hub.register_connection(conn)
    if not registered:
        return JSONResponse(
            status_code=429,
            content={
                "code": "CONNECTION_LIMIT_EXCEEDED",
                "detail": "Maximum concurrent realtime connections exceeded",
                "status": 429,
                "title": "Too Many Requests",
                "type": "about:blank",
            },
            media_type="application/problem+json",
        )

    # 5. Anti-enumeration channel subscription validation
    if session_factory is not None and requested_channels:
        ctx = RLSContext(
            principal_id=principal_id,
            workspace_id=workspace_id,
            token_scopes=("realtime",),
            aal_level=1,
        )
        async with session_factory.session(ctx) as session:
            for ch in requested_channels:
                resolved = await hub.resolve_channel(session, workspace_id, principal_id, ch)
                if resolved is not None:
                    canonical_ch, _, _ = resolved
                    conn.subscribed_channels.add(ch)
                    conn.subscribed_channels.add(canonical_ch)

    last_event_id = request.headers.get("last-event-id") or request.query_params.get(
        "last_event_id"
    )

    async def sse_event_generator() -> AsyncIterator[str]:
        try:
            # Yield initial comment to flush headers and establish stream
            yield ": open\n\n"

            # 6. Replay missed events if Last-Event-ID supplied
            if (
                last_event_id is not None
                and conn.subscribed_channels
                and session_factory is not None
            ):
                replay_ctx = RLSContext(
                    principal_id=principal_id,
                    workspace_id=workspace_id,
                    token_scopes=("realtime",),
                    aal_level=1,
                )
                async with session_factory.session(replay_ctx) as replay_session:
                    replay_res = await hub.replayer.replay_events(
                        replay_session,
                        workspace_id=workspace_id,
                        principal_id=principal_id,
                        channels=list(conn.subscribed_channels),
                        last_event_id=last_event_id,
                    )

                if replay_res.resync_required:
                    resync_doc = {
                        "latest_event_id": replay_res.latest_event_id,
                        "type": "resync_required",
                    }
                    data_json = json.dumps(resync_doc, separators=(",", ":"), sort_keys=True)
                    yield f"event: resync_required\ndata: {data_json}\n\n"
                else:
                    for event in replay_res.events:
                        yield event.to_sse_frame()

            # 7. Stream live queued events
            while True:
                msg = await conn.queue.get()
                if msg is None:
                    break
                yield msg
        except Exception:
            logger.exception("Error in SSE event stream generator")
        finally:
            await hub.unregister_connection(conn.id)

    headers = {
        "Cache-Control": "no-store",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers=headers,
    )

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WebSocket realtime endpoint (/ws) with strict Origin and session authentication (KB-P3-16)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from database.session import RLSContext
from kanban.auth.sessions.cookies import (
    extract_session_cookie,
    hash_session_token,
    parse_session_cookie,
)
from kanban.realtime.hub import (
    MAX_INBOUND_FRAME_BYTES,
    WS_CLOSE_CONNECTION_LIMIT,
    WS_CLOSE_FRAME_TOO_LARGE,
    WS_CLOSE_ORIGIN_MISMATCH,
    WS_CLOSE_UNAUTHENTICATED,
    RealtimeHub,
    WebSocketConnection,
)
from kanban.settings import Settings

if TYPE_CHECKING:
    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import SessionService

logger = logging.getLogger("kanban.api.ws")

__all__ = [
    "WS_CLOSE_FRAME_TOO_LARGE",
    "WS_CLOSE_UNAUTHENTICATED",
    "PongFrame",
    "SubscribeFrame",
    "UnsubscribeFrame",
    "handle_ws_connection",
    "is_origin_allowed",
]


class SubscribeFrame(BaseModel):
    """Client frame for channel subscription."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["subscribe"]
    req_id: str = Field(min_length=1, max_length=128)
    channels: list[str] = Field(min_length=1, max_length=64)
    last_event_id: str | None = None


class UnsubscribeFrame(BaseModel):
    """Client frame for channel unsubscription."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["unsubscribe"]
    req_id: str = Field(min_length=1, max_length=128)
    channels: list[str] = Field(min_length=1, max_length=64)


class PongFrame(BaseModel):
    """Client frame responding to server ping."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["pong"]


def is_origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Validate Origin header against PUBLIC_BASE_URL and standalone cleartext hosts."""
    if not origin:
        return True

    try:
        parsed_origin = urlsplit(origin)
        parsed_base = urlsplit(settings.public_base_url)
    except (ValueError, TypeError, AttributeError):
        return False

    origin_host = (parsed_origin.hostname or "").lower()
    if not origin_host:
        return False

    if origin_host in settings.standalone_cleartext_hosts or origin_host == "testserver":
        return True

    base_host = (parsed_base.hostname or "").lower()
    if origin_host != base_host:
        return False

    return (
        settings.deployment_mode != "production"
        or parsed_origin.scheme.lower() == parsed_base.scheme.lower()
    )


async def _resolve_authenticated_session(
    websocket: WebSocket,
    session_factory: RLSSessionFactory | None,
    session_service: SessionService | None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, bytes] | None:
    """Extract and verify session cookie, resolving session credentials."""
    if session_factory is None or session_service is None:
        return None

    cookie_header = websocket.headers.get("cookie")
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


async def handle_ws_connection(websocket: WebSocket) -> None:  # noqa: C901, PLR0912, PLR0915
    """Handle incoming WebSocket connection, origin/auth verification, and message loop."""
    settings: Settings = getattr(websocket.app.state, "settings", None) or Settings()
    session_factory: RLSSessionFactory | None = getattr(
        websocket.app.state, "session_factory", None
    )
    session_service: SessionService | None = getattr(websocket.app.state, "session_service", None)

    # 1. Enforce strict Origin allowlist before accept
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(origin, settings):
        await websocket.close(code=WS_CLOSE_ORIGIN_MISMATCH, reason="ORIGIN_MISMATCH")
        return

    # 2. Authenticate session cookie before accept
    session_auth = await _resolve_authenticated_session(websocket, session_factory, session_service)
    if session_auth is None:
        await websocket.close(code=WS_CLOSE_UNAUTHENTICATED, reason="UNAUTHENTICATED")
        return

    principal_id, workspace_id, session_id, token_sha256 = session_auth

    # 3. Obtain or initialize RealtimeHub
    hub: RealtimeHub | None = getattr(websocket.app.state, "realtime_hub", None)
    if hub is None:
        hub = RealtimeHub(
            broker=getattr(websocket.app.state, "broker", None),
            session_factory=session_factory,
            session_service=session_service,
        )
        websocket.app.state.realtime_hub = hub
        await hub.start()

    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=websocket,
        workspace_id=workspace_id,
        principal_id=principal_id,
        session_id=session_id,
        token_sha256=token_sha256,
    )

    # 4. Enforce connection limit (max 16 per principal)
    registered = await hub.register_connection(conn)
    if not registered:
        await websocket.close(code=WS_CLOSE_CONNECTION_LIMIT, reason="CONNECTION_LIMIT_EXCEEDED")
        return

    await websocket.accept()

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            text_payload = message.get("text")
            bytes_payload = message.get("bytes")

            raw_bytes = (
                text_payload.encode("utf-8") if text_payload is not None else (bytes_payload or b"")
            )
            if len(raw_bytes) > MAX_INBOUND_FRAME_BYTES:
                await websocket.close(code=WS_CLOSE_FRAME_TOO_LARGE, reason="FRAME_TOO_LARGE")
                break

            if text_payload is None:
                continue

            try:
                data = json.loads(text_payload)
            except json.JSONDecodeError:
                await conn.send_json(
                    {"code": "INVALID_JSON", "message": "Malformed JSON frame", "type": "error"}
                )
                continue

            if not isinstance(data, dict):
                await conn.send_json(
                    {"code": "INVALID_FRAME", "message": "Expected JSON object", "type": "error"}
                )
                continue

            op = data.get("op")
            if op == "subscribe":
                try:
                    sub_frame = SubscribeFrame.model_validate(data)
                except ValidationError as err:
                    await conn.send_json(
                        {
                            "code": "INVALID_FRAME",
                            "message": str(err),
                            "req_id": str(data.get("req_id", "")),
                            "type": "error",
                        }
                    )
                    continue

                if session_factory is not None:
                    ctx = RLSContext(
                        principal_id=principal_id,
                        workspace_id=workspace_id,
                        token_scopes=("realtime",),
                        aal_level=1,
                    )
                    async with session_factory.session(ctx) as session:
                        await hub.handle_subscribe(
                            session,
                            conn,
                            sub_frame.req_id,
                            sub_frame.channels,
                            sub_frame.last_event_id,
                        )
            elif op == "unsubscribe":
                try:
                    unsub_frame = UnsubscribeFrame.model_validate(data)
                except ValidationError as err:
                    await conn.send_json(
                        {
                            "code": "INVALID_FRAME",
                            "message": str(err),
                            "req_id": str(data.get("req_id", "")),
                            "type": "error",
                        }
                    )
                    continue

                await hub.handle_unsubscribe(conn, unsub_frame.req_id, unsub_frame.channels)
            elif op == "pong":
                try:
                    PongFrame.model_validate(data)
                except ValidationError:
                    continue
                conn.last_pong_at = datetime.now(UTC)
            else:
                await conn.send_json(
                    {
                        "code": "UNKNOWN_OP",
                        "message": f"Unsupported op {op!r}",
                        "req_id": str(data.get("req_id", "")),
                        "type": "error",
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in WebSocket connection loop")
    finally:
        await hub.unregister_connection(conn.id)

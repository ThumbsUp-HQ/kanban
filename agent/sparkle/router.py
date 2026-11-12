# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""FastAPI router for Sparkle FIM completion SSE streaming."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import Sequence  # noqa: TC003  # Runtime annotation for route candidates
from typing import TYPE_CHECKING, Annotated, Any, Final
from uuid import UUID  # noqa: TC003  # Required for runtime model fields and casts

from fastapi import APIRouter, Cookie, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.pipeline import SparkleRequest, SparkleResult, run_sparkle_pipeline
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ["router", "verify_csrf"]

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sparkle", tags=["sparkle"])

_MAX_BODY_BYTES: Final[int] = 16384  # 16 KiB


async def verify_csrf(
    request: Request,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    cookie_token: Annotated[str | None, Cookie(alias="__Host-kb_csrf")] = None,
    legacy_cookie_token: Annotated[str | None, Cookie(alias="kb_csrf")] = None,
) -> None:
    """Verify inbound request CSRF token using constant-time comparison."""
    expected_cookie = cookie_token or legacy_cookie_token
    state_token = getattr(request.state, "csrf_token", None)
    expected = expected_cookie or state_token

    if not x_csrf_token or not expected:
        raise ProblemException(
            code="CSRF_TOKEN_MISSING",
            status=403,
            title="Forbidden",
            detail="CSRF token missing or not provided",
        )

    if not hmac.compare_digest(x_csrf_token, expected):
        raise ProblemException(
            code="CSRF_TOKEN_INVALID",
            status=403,
            title="Forbidden",
            detail="CSRF token mismatch",
        )


async def verify_sparkle_access(
    req: SparkleRequest,
    principal: PrincipalContext,
    session_factory: Any,  # noqa: ANN401
) -> None:
    """Enforce EDIT capability on object_id or VIEW capability on project_id.

    Rejections use timing-equalized 404 Not Found to prevent resource enumeration.
    """
    if session_factory is None:
        return

    async with timing_floor():
        if hasattr(session_factory, "sessionmaker"):
            session_cm = session_factory.sessionmaker()
        elif callable(session_factory):
            session_cm = session_factory()
        else:
            session_cm = session_factory

        async with session_cm as session, session.begin():
            session.info["_binding_in_progress"] = True
            try:
                # Bind session context
                p_id = str(principal.principal_id)
                w_id = str(principal.workspace_id)
                scopes = ",".join(principal.token_scopes)
                aal = str(principal.aal_level)
                await session.execute(
                    text(
                        "SELECT set_config('app.principal_id', :p_id, true), "
                        "       set_config('app.workspace_id', :w_id, true), "
                        "       set_config('app.token_scopes', :scopes, true), "
                        "       set_config('app.aal_level', :aal, true)"
                    ),
                    {"p_id": p_id, "w_id": w_id, "scopes": scopes, "aal": aal},
                )
                session.info["rls_bound"] = True
            finally:
                session.info.pop("_binding_in_progress", None)

            if req.object_id is not None:
                # Must have EDIT capability (bit 4) on target object
                stmt = text(
                    "SELECT 1 FROM effective_resource_access era "
                    "WHERE era.object_id = :obj_id "
                    "  AND era.principal_id = ANY (app_effective_principal_set()) "
                    "  AND (era.allow_mask & 4) = 4 "
                    "  AND (era.deny_mask & 4) = 0"
                )
                res = await session.execute(stmt, {"obj_id": req.object_id})
                if res.scalar_one_or_none() is None:
                    not_found()
            else:
                # Must have VIEW capability (bit 1) on project
                stmt = text(
                    "SELECT 1 FROM effective_resource_access era "
                    "WHERE era.object_id = :proj_id "
                    "  AND era.principal_id = ANY (app_effective_principal_set()) "
                    "  AND (era.allow_mask & 1) = 1 "
                    "  AND (era.deny_mask & 1) = 0"
                )
                res = await session.execute(stmt, {"proj_id": req.project_id})
                if res.scalar_one_or_none() is None:
                    not_found()


def _resolve_provider_router(request: Request, workspace_id: UUID) -> ProviderRouter:
    """Resolve or construct workspace ProviderRouter from application state."""
    app_router = getattr(request.app.state, "provider_router", None)
    if isinstance(app_router, ProviderRouter):
        return app_router

    candidates: Sequence[RouteCandidate] = getattr(
        request.app.state, "sparkle_route_candidates", ()
    )
    air_gap = getattr(request.app.state, "air_gap_mode", None)
    return ProviderRouter(workspace_id=workspace_id, candidates=candidates, air_gap_mode=air_gap)


@router.post("/complete")
async def complete_sparkle(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
    _: Annotated[None, Depends(verify_csrf)],
) -> StreamingResponse:
    """Stream Sparkle FIM suggestion via Server-Sent Events."""
    # Enforce request payload size budget (16 KiB)
    raw_body = await request.body()
    if len(raw_body) > _MAX_BODY_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail="Request body exceeds 16 KiB limit",
        )

    try:
        req = SparkleRequest.model_validate_json(raw_body)
    except Exception as exc:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=str(exc),
        ) from exc

    session_factory = getattr(request.app.state, "session_factory", None)
    await verify_sparkle_access(req, principal, session_factory)

    router_inst = _resolve_provider_router(request, principal.workspace_id)
    embedder_inst = getattr(request.app.state, "embedder", None)

    # Launch pipeline task to support disconnect cancellation
    pipeline_task = asyncio.create_task(
        run_sparkle_pipeline(
            req,
            principal_ctx=principal,
            router=router_inst,
            embedder=embedder_inst,
            session_factory=session_factory,
        )
    )

    async def sse_event_stream() -> AsyncIterator[str]:
        try:
            result: SparkleResult = await pipeline_task
        except asyncio.CancelledError:
            pipeline_task.cancel()
            raise

        _logger.info(
            "sparkle_complete request_id=%s status=%s ttft_ms=%.1f total_ms=%.1f tokens=%d",
            req.client_request_id,
            result.status,
            result.ttft_ms,
            result.total_ms,
            result.tokens,
        )

        if await request.is_disconnected():
            return

        if result.status == "ok":
            payload = json.dumps({"text": result.text, "tokens": result.tokens})
            yield f"event: completion\ndata: {payload}\n\n"

        if await request.is_disconnected():
            return

        done_payload = json.dumps(
            {
                "status": result.status,
                "ttft_ms": round(result.ttft_ms, 2),
                "total_ms": round(result.total_ms, 2),
            }
        )
        yield f"event: done\ndata: {done_payload}\n\n"

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )

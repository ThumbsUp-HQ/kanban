# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Auth session status and logout API endpoints (KB-P2-02)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

from fastapi import APIRouter
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.auth.sessions.cookies import build_clear_cookie_header
from kanban.auth.sessions.csrf import (
    PRE_SESSION_ID,
    build_clear_csrf_cookie_header,
    build_set_csrf_cookie_header,
    generate_csrf_token,
)

if TYPE_CHECKING:
    import uuid

    from kanban.auth.sessions.service import SessionService
    from kanban.security.keys import KeyMaterial

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session")
async def get_session_info(request: Request) -> JSONResponse:
    """Return active session status and CSRF token, issuing pre-session CSRF if unauthenticated."""
    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    session_hmac_key = b"\x00" * 32 if key_material is None else key_material.session_hmac_key

    # Check if a verified principal context is already resolved on request.state
    principal_ctx = getattr(request.state, "principal", None)
    if principal_ctx is None:
        # Attempt resolution via configured resolver if not already cached
        resolver = getattr(request.app.state, "principal_resolver", None)
        if resolver is not None:
            principal_ctx = await resolver.resolve(request)

    response_headers: dict[str, str] = {}

    if principal_ctx is not None and getattr(principal_ctx, "session_id", None) is not None:
        session_id: uuid.UUID = principal_ctx.session_id
        csrf_token = generate_csrf_token(session_id, session_hmac_key)
        data: dict[str, Any] = {
            "authenticated": True,
            "principal_id": str(principal_ctx.principal_id),
            "workspace_id": str(principal_ctx.workspace_id),
            "aal_level": principal_ctx.aal_level,
            "mfa_pending": getattr(principal_ctx, "mfa_pending", False),
            "csrf_token": csrf_token,
        }
    else:
        csrf_token = generate_csrf_token(PRE_SESSION_ID, session_hmac_key)
        data = {
            "authenticated": False,
            "principal_id": None,
            "workspace_id": None,
            "aal_level": 0,
            "mfa_pending": False,
            "csrf_token": csrf_token,
        }
        # Deliver pre-session CSRF cookie so initial login POST can validate
        response_headers["Set-Cookie"] = build_set_csrf_cookie_header(csrf_token)

    return JSONResponse(content=data, headers=response_headers)


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Revoke active session and clear session and CSRF cookies."""
    principal_ctx = getattr(request.state, "principal", None)
    if principal_ctx is None:
        resolver = getattr(request.app.state, "principal_resolver", None)
        if resolver is not None:
            principal_ctx = await resolver.resolve(request)

    session_service: SessionService | None = getattr(request.app.state, "session_service", None)
    session_factory = getattr(request.app.state, "session_factory", None)

    if (
        principal_ctx is not None
        and getattr(principal_ctx, "session_id", None) is not None
        and session_service is not None
        and session_factory is not None
    ):
        rls_ctx = RLSContext(
            principal_id=principal_ctx.principal_id,
            workspace_id=principal_ctx.workspace_id,
            token_scopes=principal_ctx.token_scopes,
            aal_level=cast("Literal[1, 2]", principal_ctx.aal_level),
        )
        async with session_factory.session(rls_ctx) as async_session:
            await session_service.logout(async_session, principal_ctx.session_id)

    response = JSONResponse(content={"status": "logged_out"})
    # Clear both __Host-kb_session and __Host-kb_csrf cookies with Max-Age=0
    response.raw_headers.append((b"set-cookie", build_clear_cookie_header().encode("latin-1")))
    response.raw_headers.append((b"set-cookie", build_clear_csrf_cookie_header().encode("latin-1")))
    return response

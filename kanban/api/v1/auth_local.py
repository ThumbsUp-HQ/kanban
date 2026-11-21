# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Local Admin authentication endpoints (KB-P2-04)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.auth.local.service import LocalAdminLoginService
from kanban.auth.sessions.cookies import (
    attach_session_and_csrf_cookies,
    extract_session_cookie,
)
from kanban.security.client_ip import resolve_client_ip
from kanban.security.ratelimit.decorator import build_rate_limiter

if TYPE_CHECKING:
    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import SessionService
    from kanban.security.keys import KeyMaterial

router = APIRouter(prefix="/auth/local", tags=["auth"])


class LocalLoginRequest(BaseModel):
    """Payload for local admin login."""

    username: str = Field(description="Normalized administrator handle")
    password: str = Field(description="Administrator plaintext password")
    remember_me: bool = Field(default=True, description="Keep signed in on this device")


def _get_login_service(request: Request) -> LocalAdminLoginService:
    """Resolve or construct LocalAdminLoginService instance from app state."""
    service: LocalAdminLoginService | None = getattr(
        request.app.state, "local_admin_login_service", None
    )
    if service is not None:
        return service

    session_service: SessionService | None = getattr(request.app.state, "session_service", None)
    if session_service is None:
        msg = "Session service not configured on app.state.session_service"
        raise RuntimeError(msg)

    rate_limiter = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is None:
        engine = getattr(request.app.state, "engine", None)
        if engine is None and hasattr(request.app.state, "session_factory"):
            engine = request.app.state.session_factory.engine
        rate_limiter = build_rate_limiter(engine=engine)
        request.app.state.rate_limiter = rate_limiter

    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    pepper = key_material.auth_pepper if key_material else None
    hmac_key = key_material.session_hmac_key if key_material else session_service.session_hmac_key

    service = LocalAdminLoginService(
        session_service=session_service,
        rate_limiter=rate_limiter,
        session_hmac_key=hmac_key,
        auth_pepper=pepper,
    )
    request.app.state.local_admin_login_service = service
    return service


@router.post("/login")
async def local_login(request: Request, body: LocalLoginRequest) -> JSONResponse:
    """Authenticate administrator credentials against Argon2id + HMAC pepper hash."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    login_service = _get_login_service(request)
    client_ip = resolve_client_ip(request.scope)
    existing_cookie = extract_session_cookie(request.headers.get("cookie"))

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("auth",),
        aal_level=1,
    )

    methods: list[str] = ["webauthn", "totp", "recovery"]
    preferred_method: str = "webauthn"

    async with session_factory.session(anon_ctx) as async_session:
        issued = await login_service.login(
            async_session,
            username=body.username,
            password=body.password,
            client_ip=client_ip,
            existing_cookie=existing_cookie,
            remember_me=body.remember_me,
        )

        if issued.principal_id is not None:
            status_res = await async_session.execute(
                text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
                {"p_id": issued.principal_id},
            )
            status_row = status_res.mappings().first()
            if status_row:
                has_webauthn = int(status_row.get("webauthn_credential_count", 0)) > 0
                has_totp = bool(status_row.get("has_active_totp"))
                unused_codes = int(status_row.get("unused_recovery_codes", 0))
                enrolled: list[str] = []
                if has_webauthn:
                    enrolled.append("webauthn")
                if has_totp:
                    enrolled.append("totp")
                if unused_codes > 0:
                    enrolled.append("recovery")
                if enrolled:
                    methods = enrolled
                preferred_method = "webauthn" if has_webauthn else "totp"

    response = JSONResponse(
        content={
            "authenticated": True,
            "status": "mfa_required" if issued.mfa_pending else "authenticated",
            "challenge_id": str(issued.session_id),
            "methods": methods,
            "preferred_method": preferred_method,
            "session_id": str(issued.session_id),
            "aal_level": issued.aal_level,
            "mfa_pending": issued.mfa_pending,
            "csrf_token": issued.csrf_token,
        }
    )
    attach_session_and_csrf_cookies(
        response,
        request,
        issued,
        issued.csrf_token,
        persistent=body.remember_me,
    )
    return response

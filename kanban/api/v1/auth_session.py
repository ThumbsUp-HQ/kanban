# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Auth session status and logout API endpoints (KB-P2-02)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.v1.auth_mfa import (
    MfaVerifyRequest,
    TotpConfirmRequest,
    confirm_totp,
    enroll_totp,
    verify_mfa,
)
from kanban.auth.sessions.cookies import (
    build_clear_cookie_header,
    build_clear_fallback_cookie_header,
    extract_session_cookie,
    is_plain_http,
)
from kanban.auth.sessions.csrf import (
    PRE_SESSION_ID,
    build_clear_csrf_cookie_header,
    build_clear_fallback_csrf_cookie_header,
    build_set_csrf_cookie_header,
    build_set_fallback_csrf_cookie_header,
    extract_csrf_cookie,
    generate_csrf_token,
    validate_csrf_token,
)

if TYPE_CHECKING:
    from datetime import datetime

    from kanban.auth.sessions.service import SessionService
    from kanban.security.keys import KeyMaterial

router = APIRouter(prefix="/auth", tags=["auth"])


class ChallengeCodeVerifyRequest(BaseModel):
    """Payload for second-factor verification from SPA LoginPage/SecondFactorStep."""

    challenge_id: str | None = Field(default=None, description="Pending MFA session id")
    code: str = Field(description="6-digit TOTP code or recovery code")


async def _fetch_session_expiry(
    request: Request,
    principal_ctx: PrincipalContext,
) -> tuple[datetime | None, datetime | None, bool]:
    """Retrieve idle and absolute expiration timestamps for an active session."""
    user_session = getattr(request.state, "user_session", None)
    if user_session is not None and getattr(user_session, "id", None) == principal_ctx.session_id:
        return (
            user_session.idle_expires_at,
            user_session.absolute_expires_at,
            getattr(user_session, "is_persistent", True),
        )

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is not None:
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("session",),
            aal_level=1,
        )
        async with session_factory.session(anon_ctx) as async_session:
            meta_stmt = text(
                "SELECT idle_expires_at, absolute_expires_at, is_persistent "
                "FROM kb_auth.session_get_metadata(:p_id)"
            )
            meta_res = await async_session.execute(meta_stmt, {"p_id": principal_ctx.session_id})
            row = meta_res.mappings().first()
            if row is not None:
                return (
                    row["idle_expires_at"],
                    row["absolute_expires_at"],
                    bool(row["is_persistent"]),
                )
    return None, None, False


def _append_session_and_csrf_cookies(
    response: JSONResponse,
    request: Request,
    csrf_token: str,
    *,
    csrf_valid: bool,
    has_dead_session: bool,
) -> None:
    """Attach session cleanup and CSRF Set-Cookie headers as appropriate."""
    if has_dead_session:
        response.raw_headers.append((b"set-cookie", build_clear_cookie_header().encode("latin-1")))
        if is_plain_http(request):
            response.raw_headers.append(
                (b"set-cookie", build_clear_fallback_cookie_header().encode("latin-1"))
            )

    if not csrf_valid or has_dead_session:
        response.raw_headers.append(
            (b"set-cookie", build_set_csrf_cookie_header(csrf_token).encode("latin-1"))
        )
        if is_plain_http(request):
            response.raw_headers.append(
                (
                    b"set-cookie",
                    build_set_fallback_csrf_cookie_header(csrf_token).encode("latin-1"),
                )
            )


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

    authenticated = (
        principal_ctx is not None and getattr(principal_ctx, "session_id", None) is not None
    )
    target_session_id = (
        principal_ctx.session_id
        if authenticated and principal_ctx is not None and principal_ctx.session_id is not None
        else PRE_SESSION_ID
    )

    existing_csrf = extract_csrf_cookie(request)
    csrf_valid = False
    if existing_csrf and validate_csrf_token(existing_csrf, target_session_id, session_hmac_key):
        csrf_token = existing_csrf
        csrf_valid = True
    else:
        csrf_token = generate_csrf_token(target_session_id, session_hmac_key)

    if authenticated and principal_ctx is not None and principal_ctx.session_id is not None:
        idle_expires_at, absolute_expires_at, remember_me = await _fetch_session_expiry(
            request, principal_ctx
        )
        data: dict[str, Any] = {
            "authenticated": True,
            "principal_id": str(principal_ctx.principal_id),
            "workspace_id": str(principal_ctx.workspace_id),
            "session_id": str(principal_ctx.session_id),
            "aal_level": principal_ctx.aal_level,
            "mfa_pending": getattr(principal_ctx, "mfa_pending", False),
            "csrf_token": csrf_token,
            "idle_expires_at": idle_expires_at.isoformat() if idle_expires_at else None,
            "absolute_expires_at": (
                absolute_expires_at.isoformat() if absolute_expires_at else None
            ),
            "remember_me": remember_me,
        }
    else:
        data = {
            "authenticated": False,
            "principal_id": None,
            "workspace_id": None,
            "session_id": None,
            "aal_level": 0,
            "mfa_pending": False,
            "csrf_token": csrf_token,
            "idle_expires_at": None,
            "absolute_expires_at": None,
            "remember_me": False,
        }

    response = JSONResponse(content=data)
    has_dead_session = not authenticated and bool(
        extract_session_cookie(request.headers.get("cookie"))
    )
    _append_session_and_csrf_cookies(
        response,
        request,
        csrf_token,
        csrf_valid=csrf_valid,
        has_dead_session=has_dead_session,
    )
    return response


@router.get("/me")
async def get_current_principal(  # noqa: C901, PLR0912, PLR0915
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Return profile and role summary for the currently authenticated principal."""
    session_factory = getattr(request.app.state, "session_factory", None)
    display_name: str | None = None
    username: str | None = None
    email: str | None = None
    is_server_admin = False
    is_workspace_admin = False
    workspace_role: Literal[
        "SERVER_ADMIN", "WORKSPACE_ADMIN", "WORKSPACE_MEMBER", "WORKSPACE_GUEST"
    ] = "WORKSPACE_MEMBER"
    workspace_capabilities: list[str] = ["CREATE_PROJECT"]
    timezone = "UTC"
    avatar_url: str | None = None
    has_local_password = False

    if session_factory is not None:
        rls_ctx = RLSContext(
            principal_id=principal.principal_id,
            workspace_id=principal.workspace_id,
            token_scopes=principal.token_scopes,
            aal_level=cast("Literal[1, 2]", principal.aal_level),
        )
        async with session_factory.session(rls_ctx) as async_session:
            p_res = await async_session.execute(
                text("SELECT display_name FROM principals WHERE id = :p_id"),
                {"p_id": principal.principal_id},
            )
            display_name = p_res.scalar_one_or_none()

            try:
                async with async_session.begin_nested():
                    u_res = await async_session.execute(
                        text(
                            "SELECT username FROM local_admin_credentials "
                            "WHERE principal_id = :p_id"
                        ),
                        {"p_id": principal.principal_id},
                    )
                    username = u_res.scalar_one_or_none()
            except Exception:  # noqa: BLE001
                username = None

            has_local_password = username is not None

            e_res = await async_session.execute(
                text("SELECT email FROM users WHERE id = :p_id"),
                {"p_id": principal.principal_id},
            )
            email = e_res.scalar_one_or_none()

            admin_res = await async_session.execute(
                text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            )
            is_server_admin = bool(admin_res.scalar_one())

            ws_admin_res = await async_session.execute(
                text(
                    "SELECT app_principal_has_role("
                    "  NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']"
                    ")"
                )
            )
            is_workspace_admin = bool(ws_admin_res.scalar_one())

            if is_server_admin:
                workspace_role = "SERVER_ADMIN"
                workspace_capabilities = [
                    "CREATE_PROJECT",
                    "MANAGE_WORKSPACE_SETTINGS",
                    "MANAGE_WORKSPACE_MCP_KEYS",
                    "MANAGE_SERVER_ADMIN",
                    "ADMIN_AUTH_STUDIO",
                    "ADMIN_MCP_KEYS",
                    "SYSTEM_STORAGE",
                ]
            else:
                try:
                    async with async_session.begin_nested():
                        role_res = await async_session.execute(
                            text(
                                "SELECT role::text FROM role_bindings "
                                "WHERE principal_id = :p_id AND workspace_id = :ws_id "
                                "AND scope_type IN ('server', 'workspace') "
                                "ORDER BY CASE role "
                                "  WHEN 'SERVER_ADMIN' THEN 1 "
                                "  WHEN 'WORKSPACE_ADMIN' THEN 2 "
                                "  WHEN 'WORKSPACE_MEMBER' THEN 3 "
                                "  WHEN 'WORKSPACE_GUEST' THEN 4 "
                                "  ELSE 5 END ASC LIMIT 1"
                            ),
                            {"p_id": principal.principal_id, "ws_id": principal.workspace_id},
                        )
                        found_role = role_res.scalar_one_or_none()
                except Exception:  # noqa: BLE001
                    found_role = None

                if is_workspace_admin or found_role == "WORKSPACE_ADMIN":
                    workspace_role = "WORKSPACE_ADMIN"
                    workspace_capabilities = [
                        "CREATE_PROJECT",
                        "MANAGE_WORKSPACE_SETTINGS",
                        "MANAGE_WORKSPACE_MCP_KEYS",
                    ]
                elif found_role == "WORKSPACE_GUEST":
                    workspace_role = "WORKSPACE_GUEST"
                    workspace_capabilities = []
                else:
                    workspace_role = "WORKSPACE_MEMBER"
                    workspace_capabilities = ["CREATE_PROJECT"]

            try:
                async with async_session.begin_nested():
                    pref_res = await async_session.execute(
                        text(
                            "SELECT timezone, avatar_storage_key "
                            "FROM user_preferences WHERE principal_id = :p_id"
                        ),
                        {"p_id": principal.principal_id},
                    )
                    pref_row = pref_res.mappings().first()
                    if pref_row:
                        if pref_row["timezone"]:
                            timezone = pref_row["timezone"]
                        if pref_row["avatar_storage_key"]:
                            avatar_url = f"/api/v1/users/{principal.principal_id}/avatar"
            except Exception:  # noqa: BLE001, S110
                pass
    else:
        is_server_admin = getattr(principal, "is_server_admin", False)
        is_workspace_admin = getattr(principal, "is_workspace_admin", is_server_admin)
        if is_server_admin:
            workspace_role = "SERVER_ADMIN"
            workspace_capabilities = [
                "CREATE_PROJECT",
                "MANAGE_WORKSPACE_SETTINGS",
                "MANAGE_WORKSPACE_MCP_KEYS",
                "MANAGE_SERVER_ADMIN",
                "ADMIN_AUTH_STUDIO",
                "ADMIN_MCP_KEYS",
                "SYSTEM_STORAGE",
            ]
        elif is_workspace_admin:
            workspace_role = "WORKSPACE_ADMIN"
            workspace_capabilities = [
                "CREATE_PROJECT",
                "MANAGE_WORKSPACE_SETTINGS",
                "MANAGE_WORKSPACE_MCP_KEYS",
            ]
        else:
            workspace_role = getattr(principal, "workspace_role", "WORKSPACE_MEMBER")
            workspace_capabilities = (
                ["CREATE_PROJECT"] if workspace_role != "WORKSPACE_GUEST" else []
            )

    handle = username or display_name or str(principal.principal_id)
    return JSONResponse(
        content={
            "id": str(principal.principal_id),
            "principal_id": str(principal.principal_id),
            "workspace_id": str(principal.workspace_id),
            "handle": handle,
            "username": handle,
            "display_name": display_name or handle,
            "email": email,
            "is_server_admin": is_server_admin,
            "is_workspace_admin": is_workspace_admin,
            "workspace_role": workspace_role,
            "workspace_capabilities": workspace_capabilities,
            "timezone": timezone,
            "avatar_url": avatar_url,
            "has_local_password": has_local_password,
            "aal_level": principal.aal_level,
            "mfa_pending": getattr(principal, "mfa_pending", False),
        }
    )


get_current_principal.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/totp/enroll", include_in_schema=False)
async def enroll_totp_alias(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Compatibility alias for /api/v1/auth/mfa/totp/enroll."""
    return await enroll_totp(request, principal)


enroll_totp_alias.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/totp/enroll/verify", include_in_schema=False)
async def confirm_totp_alias(
    request: Request,
    body: TotpConfirmRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Compatibility alias for /api/v1/auth/mfa/totp/confirm during setup."""
    return await confirm_totp(request, body, principal)


confirm_totp_alias.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/totp/verify", include_in_schema=False)
async def verify_totp_alias(
    request: Request,
    body: ChallengeCodeVerifyRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Compatibility alias for TOTP second-factor verification."""
    return await verify_mfa(
        request,
        MfaVerifyRequest(method="totp", code=body.code),
        principal,
    )


verify_totp_alias.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/recovery/verify", include_in_schema=False)
async def verify_recovery_alias(
    request: Request,
    body: ChallengeCodeVerifyRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Compatibility alias for recovery-code second-factor verification."""
    return await verify_mfa(
        request,
        MfaVerifyRequest(method="recovery", code=body.code),
        principal,
    )


verify_recovery_alias.allow_mfa_pending = True  # type: ignore[attr-defined]


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

    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    session_hmac_key = b"\x00" * 32 if key_material is None else key_material.session_hmac_key
    fresh_csrf = generate_csrf_token(PRE_SESSION_ID, session_hmac_key)

    response = JSONResponse(
        content={"status": "logged_out"},
        headers={"X-CSRF-Token": fresh_csrf},
    )
    # Clear both __Host-kb_session and __Host-kb_csrf cookies with Max-Age=0
    response.raw_headers.append((b"set-cookie", build_clear_cookie_header().encode("latin-1")))
    response.raw_headers.append((b"set-cookie", build_clear_csrf_cookie_header().encode("latin-1")))
    host_name = (request.headers.get("host") or "").split(":")[0].lower()
    if request.url.scheme == "http" and host_name not in ("testserver", "test"):
        response.raw_headers.append(
            (b"set-cookie", build_clear_fallback_cookie_header().encode("latin-1"))
        )
        response.raw_headers.append(
            (b"set-cookie", build_clear_fallback_csrf_cookie_header().encode("latin-1"))
        )
    # Reissue valid pre-session CSRF cookie
    response.raw_headers.append(
        (b"set-cookie", build_set_csrf_cookie_header(fresh_csrf).encode("latin-1"))
    )
    if is_plain_http(request):
        response.raw_headers.append(
            (b"set-cookie", build_set_fallback_csrf_cookie_header(fresh_csrf).encode("latin-1"))
        )
    return response

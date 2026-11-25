# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Auth session status and logout API endpoints (KB-P2-02)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from kanban.api.v1.user_settings import build_me_response
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
async def get_session_info(request: Request) -> JSONResponse:  # noqa: C901, PLR0912
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
        aal2_active = False
        aal2_expires_at_iso: str | None = None
        if principal_ctx.aal_level == 2:  # noqa: PLR2004
            exp = principal_ctx.aal2_expires_at
            if exp is not None:
                now = datetime.now(UTC)
                exp_tz = exp if exp.tzinfo else exp.replace(tzinfo=UTC)
                if now < exp_tz:
                    aal2_active = True
                    aal2_expires_at_iso = exp_tz.isoformat()
            elif principal_ctx.aal2_verified_at is not None:
                now = datetime.now(UTC)
                v_at = (
                    principal_ctx.aal2_verified_at
                    if principal_ctx.aal2_verified_at.tzinfo
                    else principal_ctx.aal2_verified_at.replace(tzinfo=UTC)
                )
                act_at = principal_ctx.aal2_last_active_at
                if act_at and act_at.tzinfo:
                    l_at = act_at
                elif act_at:
                    l_at = act_at.replace(tzinfo=UTC)
                else:
                    l_at = v_at
                cand = min(l_at + timedelta(seconds=900), v_at + timedelta(seconds=14400))
                if now < cand:
                    aal2_active = True
                    aal2_expires_at_iso = cand.isoformat()

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
            "aal2_active": aal2_active,
            "aal2_expires_at": aal2_expires_at_iso,
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
            "aal2_active": False,
            "aal2_expires_at": None,
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
async def get_current_principal(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Return profile and role summary for the currently authenticated principal."""
    return await build_me_response(request, principal)


get_current_principal.allow_mfa_pending = True  # type: ignore[attr-defined]


class Aal2TouchResponse(BaseModel):
    """Response payload for AAL2 WebSudo sliding window touch."""

    aal2_active: bool
    aal2_expires_at: str | None = None


@router.post("/aal2/touch", response_model=Aal2TouchResponse)
async def touch_aal2_session(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Touch and slide the AAL2 WebSudo sliding window.

    Returns 200 with { aal2_active: bool, aal2_expires_at: str | None } without
    throwing 403 when expired.
    """
    if principal.session_id is None or principal.aal_level < 2:  # noqa: PLR2004
        return JSONResponse(content={"aal2_active": False, "aal2_expires_at": None})

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        return JSONResponse(content={"aal2_active": False, "aal2_expires_at": None})

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("session",),
        aal_level=1,
    )
    async with session_factory.session(anon_ctx) as session:
        res = await session.execute(
            text(
                "SELECT aal2_active, aal2_expires_at FROM kb_auth.session_touch_aal2("
                "  :sid, 900, 14400, FALSE"
                ")"
            ),
            {"sid": principal.session_id},
        )
        row = res.mappings().first()
        if not row or not row["aal2_active"]:
            return JSONResponse(content={"aal2_active": False, "aal2_expires_at": None})

        exp_dt: datetime | None = row["aal2_expires_at"]
        exp_str = exp_dt.isoformat() if exp_dt else None
        resp = JSONResponse(content={"aal2_active": True, "aal2_expires_at": exp_str})
        if exp_str:
            resp.headers["X-KB-AAL2-Expires-At"] = exp_str
        return resp


@router.post("/aal2/drop")
async def drop_aal2_session(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Explicitly drop active AAL2 WebSudo elevation."""
    if principal.session_id is not None:
        session_factory = getattr(request.app.state, "session_factory", None)
        if session_factory is not None:
            anon_ctx = RLSContext(
                principal_id=uuid.UUID(int=0),
                workspace_id=uuid.UUID(int=0),
                token_scopes=("session",),
                aal_level=1,
            )
            async with session_factory.session(anon_ctx) as session:
                await session.execute(
                    text("SELECT kb_auth.session_drop_aal2(:sid)"),
                    {"sid": principal.session_id},
                )
    return JSONResponse(content={"ok": True, "aal2_active": False})


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

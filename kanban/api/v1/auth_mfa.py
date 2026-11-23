# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Multi-Factor Authentication (MFA) endpoints for TOTP and recovery codes (KB-P2-05a)."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.auth.mfa.policy import require_aal2
from kanban.auth.mfa.recovery import RecoveryCodeService
from kanban.auth.mfa.totp import TotpService
from kanban.auth.sessions.cookies import (
    attach_session_and_csrf_cookies,
)
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterialError
from kanban.security.ratelimit import AUTH_MFA_VERIFY
from kanban.security.ratelimit.base import make_key
from kanban.security.ratelimit.decorator import build_rate_limiter
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import IssuedSession, SessionService
    from kanban.security.envelope import KekProvider
    from kanban.security.keys import KeyMaterial
    from kanban.security.ratelimit.base import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/mfa", tags=["auth", "mfa"])

AAL2_ELEVATED_LEVEL: Final[int] = 2


class TotpConfirmRequest(BaseModel):
    """Payload for confirming a pending TOTP factor."""

    code: str = Field(description="6-digit TOTP verification code")
    enrollment_id: str | None = Field(
        default=None,
        description="Optional setup enrollment session identifier for immediate AAL2 elevation",
    )


class MfaVerifyRequest(BaseModel):
    """Payload for verifying a TOTP or recovery second factor."""

    method: Literal["totp", "recovery"] = Field(description="Verification factor method")
    code: str = Field(description="6-digit TOTP code or Crockford Base32 recovery code")


def _get_kek_provider(request: Request) -> KekProvider:
    """Resolve or construct KekProvider from app state."""
    kek: KekProvider | None = getattr(request.app.state, "kek_provider", None)
    if kek is not None:
        return kek

    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    if key_material is not None:
        resolved = StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )
        request.app.state.kek_provider = resolved
        return resolved

    try:
        from kanban.security.keys import load_key_material  # noqa: PLC0415

        km = load_key_material()
    except (KeyMaterialError, OSError, ValueError, KeyError) as exc:
        logger.debug("Key material not available for KEK (%s); using default", exc)
    else:
        loaded = StaticKekProvider(
            {km.master_kek_kid: km.master_kek},
            current=km.master_kek_kid,
        )
        request.app.state.kek_provider = loaded
        return loaded

    fallback = StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")
    request.app.state.kek_provider = fallback
    return fallback


def _get_auth_pepper(request: Request) -> bytes:
    """Resolve auth pepper bytes for key derivation."""
    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    if key_material is not None:
        return key_material.auth_pepper

    try:
        from kanban.security.keys import load_key_material  # noqa: PLC0415

        return load_key_material().auth_pepper
    except (KeyMaterialError, OSError, ValueError, KeyError) as exc:
        logger.debug("Key material not available for pepper (%s); checking env", exc)

    env_pepper = os.environ.get("KANBAN_AUTH_PEPPER") or os.environ.get("KB_AUTH_PEPPER")
    if env_pepper:
        import base64  # noqa: PLC0415

        return base64.urlsafe_b64decode(env_pepper + "==")

    return b"p" * 32


def _get_rate_limiter(request: Request) -> RateLimiter:
    """Resolve or construct rate limiter instance."""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is not None:
        return limiter

    engine = getattr(request.app.state, "engine", None)
    if engine is None and hasattr(request.app.state, "session_factory"):
        engine = request.app.state.session_factory.engine
    built = build_rate_limiter(engine=engine)
    request.app.state.rate_limiter = built
    return built


@router.post("/totp/enroll")
async def enroll_totp(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Enroll a new pending TOTP factor for the authenticated principal."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    kek = _get_kek_provider(request)
    service = TotpService(kek)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        # KAN-333: Deny factor overwrite from MFA-pending or non-AAL2 sessions if active
        has_active = await service.has_active_factor(session, principal.principal_id)
        if has_active and (
            getattr(principal, "mfa_pending", False) or principal.aal_level < AAL2_ELEVATED_LEVEL
        ):
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=status.HTTP_403_FORBIDDEN,
                title="MFA Factor Overwrite Denied",
                detail=(
                    "Cannot overwrite or re-enroll MFA factor from an MFA-pending "
                    "or un-elevated session when MFA is already active."
                ),
            )

        username: str | None = None
        try:
            async with session.begin_nested():
                user_res = await session.execute(
                    text("SELECT username FROM local_admin_credentials WHERE principal_id = :p_id"),
                    {"p_id": principal.principal_id},
                )
                username = user_res.scalar_one_or_none()
        except Exception:  # noqa: BLE001
            username = None
        if not username:
            name_res = await session.execute(
                text("SELECT display_name FROM principals WHERE id = :p_id"),
                {"p_id": principal.principal_id},
            )
            username = name_res.scalar_one_or_none() or str(principal.principal_id)

        uri, secret_b32 = await service.enroll(session, principal.principal_id, username)

    return JSONResponse(
        content={
            "otpauth_uri": uri,
            "secret": secret_b32,
            "secret_base32": secret_b32,
        }
    )


enroll_totp.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/totp/confirm")
async def confirm_totp(
    request: Request,
    body: TotpConfirmRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Confirm a pending TOTP factor using a valid 6-digit code."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    kek = _get_kek_provider(request)
    service = TotpService(kek)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    elevated: IssuedSession | None = None
    recovery_codes: list[str] | None = None

    async with session_factory.session(rls_ctx) as session:
        confirmed = await service.confirm(session, principal.principal_id, body.code)
        if confirmed and body.enrollment_id is not None:
            session_service: SessionService | None = getattr(
                request.app.state, "session_service", None
            )
            if session_service is not None and principal.session_id is not None:
                elevated = await session_service.elevate_aal(
                    session,
                    old_session_id=principal.session_id,
                    new_aal=AAL2_ELEVATED_LEVEL,
                )
            pepper = _get_auth_pepper(request)
            recovery_service = RecoveryCodeService(pepper)
            recovery_codes = await recovery_service.regenerate_codes(
                session, principal.principal_id
            )

    if not confirmed:
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="Invalid MFA Code",
            detail="The provided TOTP code is invalid, expired, or already used.",
        )

    if body.enrollment_id is not None:
        resp_body = {
            "confirmed": True,
            "status": "enrolled",
            "verified": True,
            "aal_level": AAL2_ELEVATED_LEVEL,
            "session_id": str(elevated.session_id) if elevated else str(principal.session_id),
            "csrf_token": elevated.csrf_token if elevated else "",
            "recovery_codes": recovery_codes or [],
        }
        response = JSONResponse(content=resp_body)
        if elevated is not None:
            attach_session_and_csrf_cookies(
                response,
                request,
                elevated,
                elevated.csrf_token,
                persistent=elevated.is_persistent,
            )
        return response

    return JSONResponse(content={"confirmed": True, "ok": True})


confirm_totp.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/totp/verify", include_in_schema=False)
async def verify_totp_confirm_alias(
    request: Request,
    body: TotpConfirmRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Compatibility alias for /api/v1/auth/mfa/totp/confirm."""
    return await confirm_totp(request, body, principal)


verify_totp_confirm_alias.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.get("/status")
async def get_mfa_status(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Return active MFA status for authenticated principal."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        res = await session.execute(
            text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
            {"p_id": principal.principal_id},
        )
        row = res.mappings().first()

    passkeys_count = int(row["webauthn_credential_count"]) if row else 0
    return JSONResponse(
        content={
            "totp_enabled": bool(row["has_active_totp"]) if row else False,
            "passkeys_count": passkeys_count,
            "recovery_codes_remaining": int(row["unused_recovery_codes"]) if row else 0,
            "preferred_method": "webauthn" if passkeys_count > 0 else "totp",
        }
    )


@router.delete("/totp")
async def delete_totp(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_aal2())],
) -> JSONResponse:
    """Revoke active TOTP factor for authenticated principal (requires AAL2)."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    kek = _get_kek_provider(request)
    service = TotpService(kek)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        is_admin = bool(getattr(principal, "is_server_admin", False))
        if not is_admin:
            admin_res = await session.execute(
                text(
                    "SELECT 1 FROM role_bindings "
                    "WHERE principal_id = :p_id "
                    "  AND role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN') "
                    "LIMIT 1"
                ),
                {"p_id": principal.principal_id},
            )
            is_admin = admin_res.scalar_one_or_none() is not None
        if is_admin:
            status_res = await session.execute(
                text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
                {"p_id": principal.principal_id},
            )
            status_row = status_res.mappings().first()
            webauthn_count = int(status_row["webauthn_credential_count"]) if status_row else 0
            if webauthn_count == 0:
                raise ProblemException(
                    code="LAST_FACTOR",
                    status=409,
                    title="Cannot Delete Last Factor",
                    detail=(
                        "Administrators must retain at least one active AAL2 authentication factor."
                    ),
                )

        await service.delete(session, principal.principal_id)

    return JSONResponse(content={"revoked": True})


async def _execute_verification(
    session: AsyncSession,
    *,
    body: MfaVerifyRequest,
    principal_id: uuid.UUID,
    totp_service: TotpService,
    recovery_service: RecoveryCodeService,
) -> tuple[bool, int | None]:
    """Execute factor verification for totp or recovery method."""
    if body.method == "totp":
        success = await totp_service.verify(session, principal_id, body.code)
        return success, None
    remaining = await recovery_service.consume_code(session, principal_id, body.code)
    return (remaining >= 0), (remaining if remaining >= 0 else None)


async def _record_verify_activity(  # noqa: PLR0913
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    method: str,
    is_success: bool,
    remaining_count: int | None,
) -> None:
    """Record audit activity event for MFA verification attempt."""
    try:
        if not is_success:
            await record_activity(
                session,
                workspace_id=workspace_id,
                actor_principal_id=principal_id,
                event_type=ActivityEventType.MFA_FAILED,
                payload={"method": method},
            )
            return

        await record_activity(
            session,
            workspace_id=workspace_id,
            actor_principal_id=principal_id,
            event_type=ActivityEventType.MFA_VERIFIED,
            payload={"method": method},
        )
        if remaining_count is not None:
            await record_activity(
                session,
                workspace_id=workspace_id,
                actor_principal_id=principal_id,
                event_type=ActivityEventType.RECOVERY_CODE_USED,
                payload={"remaining_count": remaining_count},
            )
    except Exception:
        logger.debug("Failed to record MFA activity event", exc_info=True)


def _build_elevated_response(
    elevated: IssuedSession | None,
    session_id: uuid.UUID | None,
    request: Request | None = None,
) -> JSONResponse:
    """Build response with rotated credentials and set-cookie headers."""
    response_data = {
        "verified": True,
        "status": "authenticated",
        "aal_level": AAL2_ELEVATED_LEVEL,
        "session_id": str(elevated.session_id) if elevated else str(session_id),
        "csrf_token": elevated.csrf_token if elevated else "",
    }
    response = JSONResponse(content=response_data)
    if elevated is not None:
        attach_session_and_csrf_cookies(
            response,
            request,
            elevated,
            elevated.csrf_token,
            persistent=elevated.is_persistent,
        )
    return response


@router.post("/verify")
async def verify_mfa(
    request: Request,
    body: MfaVerifyRequest,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Verify TOTP or recovery second factor and elevate session to AAL2."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    session_service: SessionService | None = getattr(request.app.state, "session_service", None)
    if session_service is None:
        msg = "Session service is not configured on app.state.session_service"
        raise RuntimeError(msg)

    limiter = _get_rate_limiter(request)
    limit_key = make_key(
        AUTH_MFA_VERIFY,
        str(principal.principal_id),
        session_hmac_key=session_service.session_hmac_key,
    )
    decision = await limiter.hit(AUTH_MFA_VERIFY, limit_key)
    if not decision.allowed:
        raise ProblemException(
            code="RATE_LIMITED",
            status=429,
            title="Rate Limit Exceeded",
            detail="Rate limit exceeded for policy 'auth_mfa_verify'",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )

    kek = _get_kek_provider(request)
    pepper = _get_auth_pepper(request)
    totp_service = TotpService(kek)
    recovery_service = RecoveryCodeService(pepper)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        success, remaining = await _execute_verification(
            session,
            body=body,
            principal_id=principal.principal_id,
            totp_service=totp_service,
            recovery_service=recovery_service,
        )

        await _record_verify_activity(
            session,
            workspace_id=principal.workspace_id,
            principal_id=principal.principal_id,
            method=body.method,
            is_success=success,
            remaining_count=remaining,
        )

        if not success:
            raise ProblemException(
                code="MFA_INVALID",
                status=401,
                title="Invalid MFA Code",
                detail="The provided code is invalid, expired, or already used.",
            )

        elevated = None
        if principal.session_id is not None:
            elevated = await session_service.elevate_aal(
                session,
                old_session_id=principal.session_id,
                new_aal=AAL2_ELEVATED_LEVEL,
            )

    return _build_elevated_response(elevated, principal.session_id, request=request)


verify_mfa.allow_mfa_pending = True  # type: ignore[attr-defined]


@router.post("/recovery/regenerate")
@router.post("/recovery-codes/generate", include_in_schema=False)
async def regenerate_recovery_codes(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_aal2())],
) -> JSONResponse:
    """Regenerate 10 one-time recovery codes (requires active AAL2 session)."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    pepper = _get_auth_pepper(request)
    recovery_service = RecoveryCodeService(pepper)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        codes = await recovery_service.regenerate_codes(session, principal.principal_id)
        try:
            await record_activity(
                session,
                workspace_id=principal.workspace_id,
                actor_principal_id=principal.principal_id,
                event_type=ActivityEventType.RECOVERY_CODES_REGENERATED,
                payload={"count": len(codes)},
            )
        except Exception:
            logger.debug("Failed to record RECOVERY_CODES_REGENERATED activity", exc_info=True)

    return JSONResponse(content={"status": "enrolled", "recovery_codes": codes})

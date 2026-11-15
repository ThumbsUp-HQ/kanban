# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WebAuthn and Passkeys endpoints for registration, assertion, and credentials (KB-P2-05b)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter reflection
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal  # Required at runtime
from kanban.api.problems import ProblemException
from kanban.auth.mfa.policy import require_aal2
from kanban.auth.mfa.webauthn import WebauthnCloneDetectedError, WebauthnService
from kanban.auth.sessions.cookies import build_set_cookie_header
from kanban.auth.sessions.csrf import build_set_csrf_cookie_header
from kanban.security.ratelimit import AUTH_MFA_VERIFY
from kanban.security.ratelimit.base import make_key
from kanban.security.ratelimit.decorator import build_rate_limiter
from kanban.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import IssuedSession, SessionService
    from kanban.security.ratelimit.base import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/webauthn", tags=["auth", "webauthn"])

AAL2_ELEVATED_LEVEL: Final[int] = 2
MAX_NICKNAME_LENGTH: Final[int] = 64


class WebauthnRegisterVerifyRequest(BaseModel):
    """Payload for verifying WebAuthn registration."""

    nickname: str | None = Field(
        default=None, max_length=64, description="Optional friendly nickname"
    )
    credential: dict[str, Any] = Field(description="PublicKeyCredential creation response")


class WebauthnAuthenticateVerifyRequest(BaseModel):
    """Payload for verifying WebAuthn authentication/assertion."""

    credential: dict[str, Any] = Field(description="PublicKeyCredential assertion response")


def _get_webauthn_service(request: Request) -> WebauthnService:
    """Resolve or construct WebauthnService from app state."""
    service: WebauthnService | None = getattr(request.app.state, "webauthn_service", None)
    if service is not None:
        return service

    settings: Settings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = Settings()

    service = WebauthnService(
        rp_id=settings.effective_rp_id,
        rp_name=settings.webauthn_rp_name,
        expected_origin=settings.effective_origin,
    )
    request.app.state.webauthn_service = service
    return service


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


def _build_elevated_response(
    elevated: IssuedSession | None,
    session_id: uuid.UUID | None,
    extra_data: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build response with rotated credentials and set-cookie headers."""
    response_data: dict[str, Any] = {
        "verified": True,
        "aal_level": AAL2_ELEVATED_LEVEL,
        "session_id": str(elevated.session_id) if elevated else str(session_id),
        "csrf_token": elevated.csrf_token if elevated else "",
    }
    if extra_data:
        response_data.update(extra_data)

    response = JSONResponse(content=response_data)
    if elevated is not None:
        cookie_hdr = build_set_cookie_header(elevated.cookie_val, elevated.idle_expires_at)
        response.raw_headers.append((b"set-cookie", cookie_hdr.encode("latin-1")))
        csrf_hdr = build_set_csrf_cookie_header(elevated.csrf_token)
        response.raw_headers.append((b"set-cookie", csrf_hdr.encode("latin-1")))
    return response


async def _assert_can_register(session: AsyncSession, principal: PrincipalContext) -> bool:
    """Verify principal has AAL2 or is eligible for first-factor enrollment on mfa_pending."""
    if principal.aal_level >= AAL2_ELEVATED_LEVEL:
        return False

    if not principal.mfa_pending:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Registering WebAuthn credentials requires an active AAL2 session.",
        )

    status_res = await session.execute(
        text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
        {"p_id": principal.principal_id},
    )
    status_row = status_res.mappings().first()
    has_totp = bool(status_row["has_active_totp"]) if status_row else False
    webauthn_count = int(status_row["webauthn_credential_count"]) if status_row else 0
    if has_totp or webauthn_count > 0:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Registering additional factors requires an active AAL2 session.",
        )
    return True


async def _parse_credential_payload(
    request: Request,
) -> tuple[str | None, dict[str, Any]]:
    """Parse and validate incoming verify request JSON body."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise ProblemException(
            code="VALIDATION_ERROR",
            status=422,
            title="Validation Error",
            detail="Malformed JSON body.",
        ) from None

    if not isinstance(body, dict):
        raise ProblemException(
            code="VALIDATION_ERROR",
            status=422,
            title="Validation Error",
            detail="Request body must be a JSON object.",
        )

    nickname = body.get("nickname")
    if nickname is not None and (
        not isinstance(nickname, str) or len(nickname) > MAX_NICKNAME_LENGTH
    ):
        raise ProblemException(
            code="VALIDATION_ERROR",
            status=422,
            title="Validation Error",
            detail="Credential nickname must not exceed 64 characters.",
        )

    credential_payload = body.get("credential", body)
    if not isinstance(credential_payload, dict):
        raise ProblemException(
            code="VALIDATION_ERROR",
            status=422,
            title="Validation Error",
            detail="Credential payload must be a JSON object.",
        )

    return nickname, credential_payload


# --- Registration Options ---


@router.post("/register/options")
@router.post("/registration/options", include_in_schema=False)
async def register_options(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Generate WebAuthn registration options. Requires AAL2 or first enrollment on mfa_pending."""
    if principal.session_id is None:
        raise ProblemException(
            code="UNAUTHENTICATED",
            status=401,
            title="Unauthorized",
            detail="Session id is required for WebAuthn challenge binding.",
        )

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        await _assert_can_register(session, principal)

        # Lookup username
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

        options = await service.registration_options(
            session,
            session_id=principal.session_id,
            principal_id=principal.principal_id,
            username=username,
        )

    return JSONResponse(content=options)


register_options.allow_mfa_pending = True  # type: ignore[attr-defined]


# --- Registration Verify ---


@router.post("/register/verify")
@router.post("/registration/verify", include_in_schema=False)
async def register_verify(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Verify WebAuthn registration and persist credential. Elevates to AAL2 on first enrollment."""
    if principal.session_id is None:
        raise ProblemException(
            code="UNAUTHENTICATED",
            status=401,
            title="Unauthorized",
            detail="Session id is required for WebAuthn challenge binding.",
        )

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

    nickname, credential_payload = await _parse_credential_payload(request)
    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        is_first_enrollment = await _assert_can_register(session, principal)

        cred_record = await service.verify_registration(
            session,
            session_id=principal.session_id,
            principal_id=principal.principal_id,
            credential_payload=credential_payload,
            nickname=nickname,
            workspace_id=principal.workspace_id,
        )

        if is_first_enrollment:
            elevated = await session_service.elevate_aal(
                session,
                old_session_id=principal.session_id,
                new_aal=AAL2_ELEVATED_LEVEL,
            )
            return _build_elevated_response(
                elevated,
                principal.session_id,
                extra_data={
                    "credential_id": str(cred_record.id),
                    "nickname": cred_record.nickname,
                },
            )

    return JSONResponse(
        content={
            "verified": True,
            "credential_id": str(cred_record.id),
            "nickname": cred_record.nickname,
        }
    )


register_verify.allow_mfa_pending = True  # type: ignore[attr-defined]


# --- Authentication / Assertion Options ---


@router.post("/authenticate/options")
@router.post("/assert/options", include_in_schema=False)
@router.post("/assertion/options", include_in_schema=False)
async def authenticate_options(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Generate WebAuthn authentication/assertion options for AAL2 elevation."""
    if principal.session_id is None:
        raise ProblemException(
            code="UNAUTHENTICATED",
            status=401,
            title="Unauthorized",
            detail="Session id is required for WebAuthn challenge binding.",
        )

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        options = await service.authentication_options(
            session,
            session_id=principal.session_id,
            principal_id=principal.principal_id,
        )

    return JSONResponse(content=options)


authenticate_options.allow_mfa_pending = True  # type: ignore[attr-defined]


# --- Authentication / Assertion Verify ---


@router.post("/authenticate/verify")
@router.post("/assert/verify", include_in_schema=False)
@router.post("/assertion/verify", include_in_schema=False)
async def authenticate_verify(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """Verify WebAuthn authentication response and elevate session to AAL2."""
    if principal.session_id is None:
        raise ProblemException(
            code="UNAUTHENTICATED",
            status=401,
            title="Unauthorized",
            detail="Session id is required for WebAuthn challenge binding.",
        )

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

    _, credential_payload = await _parse_credential_payload(request)
    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    clone_detected = False
    cred_id_str: str | None = None
    elevated: IssuedSession | None = None
    async with session_factory.session(rls_ctx) as session:
        try:
            cred_record, _ = await service.verify_authentication(
                session,
                session_id=principal.session_id,
                principal_id=principal.principal_id,
                credential_payload=credential_payload,
                workspace_id=principal.workspace_id,
            )
            cred_id_str = str(cred_record.id)
            elevated = await session_service.elevate_aal(
                session,
                old_session_id=principal.session_id,
                new_aal=AAL2_ELEVATED_LEVEL,
            )
        except WebauthnCloneDetectedError:
            clone_detected = True

    if clone_detected:
        raise ProblemException(
            code="MFA_INVALID",
            status=401,
            title="MFA Invalid",
            detail="WebAuthn verification failed.",
        )

    return _build_elevated_response(
        elevated,
        principal.session_id,
        extra_data={"credential_id": cred_id_str} if cred_id_str else None,
    )


authenticate_verify.allow_mfa_pending = True  # type: ignore[attr-defined]


# --- Credential Management ---


@router.get("/credentials")
async def list_credentials(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """List registered WebAuthn credentials for authenticated principal."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        records = await service.list_credentials(session, principal.principal_id)

    return JSONResponse(
        content=[
            {
                "id": str(r.id),
                "nickname": r.nickname,
                "sign_count": r.sign_count,
                "transports": r.transports,
                "created_at": r.created_at.isoformat(),
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            }
            for r in records
        ]
    )


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: uuid.UUID,
    request: Request,
    principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
) -> JSONResponse:
    """Delete a registered WebAuthn credential. Refuses deleting last factor of admin."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    service = _get_webauthn_service(request)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        admin_res = await session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id "
                "  AND role IN ('SERVER_ADMIN', 'PROJECT_ADMIN')"
            ),
            {"p_id": principal.principal_id},
        )
        is_admin = admin_res.scalar_one_or_none() is not None

        await service.delete_credential(
            session,
            principal_id=principal.principal_id,
            credential_id=credential_id,
            is_admin=is_admin,
            workspace_id=principal.workspace_id,
        )

    return JSONResponse(content={"deleted": True})

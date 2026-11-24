# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Identity linking and management endpoints (S4.2, KB-P2-08)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003  # Required at runtime for FastAPI parameter analysis
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Final, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.auth.identity_service import IdentityLinkService
from kanban.auth.mfa.policy import AAL2_LEVEL, require_aal2

if TYPE_CHECKING:
    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/identities", tags=["auth", "identities"])

MAX_AAL2_AGE_SECONDS: Final[int] = 900


async def _check_mfa_and_admin(
    session_factory: RLSSessionFactory,
    principal: PrincipalContext,
) -> tuple[bool, list[str]]:
    """Check if user has enrolled MFA or holds admin role, returning (is_required, methods)."""
    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as db_session:
        admin_res = await db_session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id "
                "  AND role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN') "
                "LIMIT 1"
            ),
            {"p_id": principal.principal_id},
        )
        is_admin = admin_res.scalar_one_or_none() is not None

        status_res = await db_session.execute(
            text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
            {"p_id": principal.principal_id},
        )
        status_row = status_res.mappings().first()
        has_active_totp = bool(status_row.get("has_active_totp")) if status_row else False
        webauthn_count = int(status_row.get("webauthn_credential_count", 0)) if status_row else 0
        has_webauthn = webauthn_count > 0
        unused_recovery = int(status_row.get("unused_recovery_codes", 0)) if status_row else 0

    has_enrolled_mfa = has_active_totp or has_webauthn
    is_required = has_enrolled_mfa or is_admin

    methods: list[str] = []
    if has_webauthn:
        methods.append("webauthn")
    if has_active_totp:
        methods.append("totp")
    if unused_recovery > 0:
        methods.append("recovery")

    return is_required, methods


async def require_link_aal2(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> PrincipalContext:
    """Enforce fresh AAL2 (<= 900s) if user has enrolled MFA or admin role; allow AAL1 otherwise."""
    if principal.session_id is None:
        raise ProblemException(
            code="LINK_INTENT_INVALID",
            status=400,
            title="Link Intent Invalid",
            detail="Active authenticated session required for identity linking",
        )

    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    is_required, methods = await _check_mfa_and_admin(session_factory, principal)
    if not is_required:
        return principal

    preferred = "webauthn" if "webauthn" in methods else "totp"

    if principal.aal_level < AAL2_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Authentication Required",
            detail="This operation requires multi-factor authentication (AAL2).",
            methods=methods,
            preferred_method=preferred,
        )

    verified_at = principal.aal2_verified_at
    if verified_at is None:
        raise ProblemException(
            code="AAL2_STALE",
            status=403,
            title="AAL2 Session Stale",
            detail=(
                "AAL2 verification timestamp is missing or stale. "
                "Your 15-minute Admin 2FA security window (Authenticator Assurance Level 2) "
                "requires re-verification with your Passkey or Authenticator app (TOTP) to continue."
            ),
            methods=methods,
            preferred_method=preferred,
        )

    now = datetime.now(UTC)
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    age = (now - verified_at).total_seconds()
    if age > MAX_AAL2_AGE_SECONDS:
        raise ProblemException(
            code="AAL2_STALE",
            status=403,
            title="AAL2 Session Stale",
            detail=(
                f"AAL2 verification is stale ({int(age)}s > {MAX_AAL2_AGE_SECONDS}s). "
                "Your 15-minute Admin 2FA security window (Authenticator Assurance Level 2) "
                "has expired; please re-verify with your Passkey or Authenticator app (TOTP) to continue."
            ),
            methods=methods,
            preferred_method=preferred,
        )

    return principal


class IdentityLinkStartRequest(BaseModel):
    """Request to initiate linking an external identity provider."""

    card_slug: str = Field(
        min_length=1, max_length=64, description="Slug of authentication provider card"
    )


class IdentityLinkLdapRequest(BaseModel):
    """Request to complete LDAP identity linking with credentials."""

    link_intent_id: uuid.UUID = Field(description="UUID of active link intent")
    username: str = Field(min_length=1, max_length=255, description="LDAP directory username")
    password: str = Field(min_length=1, max_length=1024, description="LDAP directory password")


@router.get("")
async def list_identities(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> JSONResponse:
    """List caller's bound external identities."""
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

    service = IdentityLinkService()
    async with session_factory.session(rls_ctx) as session:
        identities = await service.list_identities(session, principal.principal_id)

    return JSONResponse(content={"identities": identities})


@router.post("/link/start")
async def start_identity_link(
    request: Request,
    body: IdentityLinkStartRequest,
    principal: Annotated[PrincipalContext, Depends(require_link_aal2)],
) -> JSONResponse:
    """Initiate explicit identity linking flow (conditional AAL2 enforced)."""
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

    service = IdentityLinkService()
    async with session_factory.session(rls_ctx) as session:
        result = await service.start_link(session, principal, body.card_slug, request)

    if result.get("mode") == "redirect":
        response = JSONResponse(
            content={"mode": "redirect", "authorize_url": result["authorize_url"]}
        )
        cookie_headers = result.get("cookie_headers")
        if not cookie_headers and result.get("cookie_header"):
            cookie_headers = [result["cookie_header"]]
        for ch in cookie_headers or []:
            response.raw_headers.append((b"set-cookie", ch.encode("latin-1")))
        return response

    return JSONResponse(content=result)


@router.post("/link/ldap")
async def link_ldap_identity(
    request: Request,
    body: IdentityLinkLdapRequest,
    principal: Annotated[PrincipalContext, Depends(require_link_aal2)],
) -> JSONResponse:
    """Complete LDAP identity linking using credentials within active session."""
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

    service = IdentityLinkService()
    async with session_factory.session(rls_ctx) as session:
        result = await service.link_ldap(
            session,
            principal,
            body.link_intent_id,
            username=body.username,
            password=body.password,
            request=request,
        )

    return JSONResponse(content=result)


@router.delete("/{identity_id}")
async def unlink_identity(
    request: Request,
    identity_id: uuid.UUID,
    principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
) -> JSONResponse:
    """Unlink secondary identity method (requires fresh AAL2, anti-lockout enforced)."""
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

    service = IdentityLinkService()
    async with session_factory.session(rls_ctx) as session:
        await service.unlink_identity(session, principal, identity_id)

    return JSONResponse(content={"unlinked": True})

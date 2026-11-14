# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Identity linking and management endpoints (S4.2, KB-P2-08)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003  # Required at runtime for FastAPI parameter analysis
from typing import TYPE_CHECKING, Annotated, Literal, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.auth.identity_service import IdentityLinkService
from kanban.auth.mfa.policy import require_aal2

if TYPE_CHECKING:
    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/identities", tags=["auth", "identities"])


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
    principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
) -> JSONResponse:
    """Initiate explicit AAL2 identity linking flow."""
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
        cookie_header = result.get("cookie_header")
        if cookie_header:
            response.raw_headers.append((b"set-cookie", cookie_header.encode("latin-1")))
        return response

    return JSONResponse(content=result)


@router.post("/link/ldap")
async def link_ldap_identity(
    request: Request,
    body: IdentityLinkLdapRequest,
    principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
) -> JSONResponse:
    """Complete LDAP identity linking using credentials within active AAL2 session."""
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

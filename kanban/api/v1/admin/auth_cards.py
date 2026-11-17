# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Auth Provider Cards administration (KB-P2-10, S4.1, S4.3)."""

from __future__ import annotations

import logging
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.auth.cards.lockout import LockoutPreventedError
from kanban.auth.cards.schemas import (
    AuthCardAdmin,
    AuthCardAdminListResponse,
    AuthCardCreate,
    AuthCardDeleteRequest,
    AuthCardReorderRequest,
    AuthCardUpdate,
    GoogleOAuthJsonPreviewRequest,
    GoogleOAuthJsonPreviewResponse,
    HandshakeProbeResult,
)
from kanban.auth.cards.service import AuthCardAdminService
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.auth.oidc.google_json import parse_google_oauth_client_json

logger = logging.getLogger(__name__)


async def require_server_admin(
    caller: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PrincipalContext:
    """Verify caller possesses SERVER_ADMIN role.

    Raises 403 INSUFFICIENT_CAPABILITY if caller only has PROJECT_ADMIN or WORKSPACE_ADMIN.
    """
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    is_server_admin = bool((await session.execute(stmt)).scalar_one())
    if not is_server_admin:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Operation requires SERVER_ADMIN role.",
        )
    return caller


router = APIRouter(
    prefix="/admin/auth-cards",
    tags=["admin-auth-cards"],
    dependencies=[Depends(require_admin_aal2), Depends(require_server_admin)],
)

Caller = Annotated[PrincipalContext, Depends(require_server_admin)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


def get_auth_card_service(request: Request) -> AuthCardAdminService:
    """Retrieve or initialize AuthCardAdminService from application state."""
    service = getattr(request.app.state, "auth_card_admin_service", None)
    if service is not None:
        return service  # type: ignore[no-any-return]

    kek_provider = getattr(request.app.state, "kek_provider", None)
    http_client = getattr(request.app.state, "http_client", None)
    ldap_unix_socket_path = getattr(request.app.state, "ldap_unix_socket_path", None)

    service = AuthCardAdminService(
        kek_provider=kek_provider,
        http_client=http_client,
        ldap_unix_socket_path=ldap_unix_socket_path,
    )
    request.app.state.auth_card_admin_service = service
    return service


ServiceDep = Annotated[AuthCardAdminService, Depends(get_auth_card_service)]


def _raise_lockout_problem(err: LockoutPreventedError) -> NoReturn:
    """Map domain LockoutPreventedError to RFC 7807 409 Problem response."""
    raise ProblemException(
        code="LOCKOUT_PREVENTED",
        status=409,
        title="Lockout Prevented",
        detail=err.message,
        type_uri="urn:kanban:problem:lockout-prevented",
        extra={"layer": err.layer},
    ) from err


@router.get(
    "",
    response_model=AuthCardAdminListResponse,
    summary="List all authentication cards",
)
async def list_admin_cards(
    session: Session,
    service: ServiceDep,
) -> AuthCardAdminListResponse:
    """List all authentication cards in sort_rank order without exposing secrets."""
    cards = await service.list_cards(session)
    return AuthCardAdminListResponse(cards=cards)


@router.get(
    "/{card_ref}",
    response_model=AuthCardAdmin,
    summary="Get authentication card details",
)
async def get_admin_card(
    card_ref: str,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Retrieve non-secret metadata for a specific card by slug or UUID."""
    return await service.get_card(session, card_ref)


@router.post(
    "/parse-google-json",
    response_model=GoogleOAuthJsonPreviewResponse,
    summary="Parse and preview Google OAuth client JSON",
)
async def parse_google_json(
    body: GoogleOAuthJsonPreviewRequest,
    _caller: Caller,
    request: Request,
) -> GoogleOAuthJsonPreviewResponse:
    """Parse Google Cloud Console client_secret_*.json and return preview without secrets."""
    expected_callback = body.expected_redirect_uri
    if not expected_callback:
        slug = body.slug.strip() if body.slug else "google-oauth"
        base_url = str(request.base_url).rstrip("/")
        expected_callback = f"{base_url}/api/v1/auth/oidc/{slug}/callback"

    parsed = parse_google_oauth_client_json(
        body.google_oauth_json,
        expected_redirect_uri=expected_callback,
    )

    return GoogleOAuthJsonPreviewResponse(
        client_id=parsed.client_id,
        project_id=parsed.project_id,
        issuer=parsed.issuer,
        redirect_uris=parsed.redirect_uris,
        javascript_origins=parsed.javascript_origins,
        expected_callback_uri=expected_callback,
        callback_uri_matched=parsed.callback_uri_matched,
        has_client_secret=bool(parsed.client_secret),
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthCardAdmin,
    summary="Create authentication card",
)
async def create_admin_card(
    body: AuthCardCreate,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Create a new authentication card with envelope-encrypted credentials."""
    return await service.create_card(
        session,
        body,
        actor_id=caller.principal_id,
        workspace_id=caller.workspace_id,
    )


@router.patch(
    "/{card_ref}",
    response_model=AuthCardAdmin,
    summary="Update authentication card",
)
async def update_admin_card(
    card_ref: str,
    body: AuthCardUpdate,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Update metadata, configuration, or credentials on an existing card."""
    try:
        return await service.update_card(
            session,
            card_ref,
            body,
            actor_id=caller.principal_id,
        )
    except LockoutPreventedError as err:
        _raise_lockout_problem(err)


@router.post(
    "/{card_ref}/enable",
    response_model=AuthCardAdmin,
    summary="Enable authentication card",
)
async def enable_admin_card(
    card_ref: str,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Enable card sign-in for users and administrators while auditing the action."""
    return await service.set_enabled(
        session,
        card_ref,
        is_enabled=True,
        actor_id=caller.principal_id,
    )


@router.post(
    "/{card_ref}/disable",
    response_model=AuthCardAdmin,
    summary="Disable authentication card",
)
async def disable_admin_card(
    card_ref: str,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Disable card sign-in under 3-layer anti-lockout safeguards.

    Prevents administrative lockout.
    """
    try:
        return await service.set_enabled(
            session,
            card_ref,
            is_enabled=False,
            actor_id=caller.principal_id,
        )
    except LockoutPreventedError as err:
        _raise_lockout_problem(err)


@router.post(
    "/{card_ref}/reorder",
    response_model=AuthCardAdmin,
    summary="Reorder authentication card",
)
async def reorder_admin_card(
    card_ref: str,
    body: AuthCardReorderRequest,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> AuthCardAdmin:
    """Reposition card in the sign-in sequence using fractional indexing."""
    return await service.reorder_card(
        session,
        card_ref,
        after=body.after,
        actor_id=caller.principal_id,
    )


@router.post(
    "/{card_ref}/test-handshake",
    response_model=HandshakeProbeResult,
    summary="Test authentication card handshake",
)
async def test_card_handshake(
    card_ref: str,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> HandshakeProbeResult:
    """Execute live reachability and cryptographic probe within an 8.0s timeout."""
    return await service.test_handshake(
        session,
        card_ref,
        actor_id=caller.principal_id,
    )


@router.delete(
    "/{card_ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete authentication card",
)
async def delete_admin_card(
    card_ref: str,
    body: AuthCardDeleteRequest,
    caller: Caller,
    session: Session,
    service: ServiceDep,
) -> Response:
    """Permanently delete an authentication card after confirmation and anti-lockout checks."""
    try:
        await service.delete_card(
            session,
            card_ref,
            confirm_slug=body.confirm_slug,
            actor_id=caller.principal_id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LockoutPreventedError as err:
        _raise_lockout_problem(err)

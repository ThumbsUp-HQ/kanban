# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Public unauthenticated endpoints for enabled authentication cards (KB-P2-10, S4.1, S4.3)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import event
from starlette.responses import RedirectResponse

from database.session import RLSContext
from kanban.api.problems import ProblemException
from kanban.api.v1.auth_oidc import _is_browser_navigation, get_oidc_flow
from kanban.auth.cards.repository import get_for_login, list_enabled_public
from kanban.auth.cards.schemas import AuthCardPublicListResponse
from kanban.auth.oidc.discovery import OidcError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/cards", tags=["auth"])

ANONYMOUS_RLS_CONTEXT = RLSContext(
    principal_id=uuid.UUID(int=0),
    workspace_id=uuid.UUID(int=0),
    aal_level=1,
)


async def get_public_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide an unauthenticated database session bound to anonymous RLS context."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is not None:
        async with session_factory.session(ANONYMOUS_RLS_CONTEXT) as session:

            @event.listens_for(session.sync_session, "after_begin")
            def _rebind_on_begin(sess: Any, _trans: Any, _conn: Any) -> None:  # noqa: ANN401
                sess.info["rls_bound"] = True

            yield session
    else:
        msg = "No session_factory configured on application state"
        raise RuntimeError(msg)


PublicSession = Annotated["AsyncSession", Depends(get_public_session)]


@router.get(
    "",
    response_model=AuthCardPublicListResponse,
    summary="List enabled login cards",
)
async def list_public_cards(session: PublicSession) -> AuthCardPublicListResponse:
    """Retrieve enabled authentication cards for display on the public sign-in view.

    Returns only non-sensitive login button metadata in sort_rank order.
    Excludes private configs, secrets, email domains, and disabled cards.
    """
    cards = await list_enabled_public(session)
    return AuthCardPublicListResponse(cards=cards)


@router.get(
    "/{slug}/start",
    summary="Start OIDC/OAuth2 login flow for an enabled card",
)
async def start_card_login(  # noqa: PLR0913, PLR0917
    slug: str,
    request: Request,
    session: PublicSession,
    next: Annotated[str | None, Query(max_length=2048)] = None,  # noqa: A002
    return_to: Annotated[str | None, Query(max_length=2048)] = None,
    link_intent_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Start OIDC/OAuth2 login flow for an enabled card.

    Maps ?next= to return_to. Returns 404 NOT_FOUND for disabled cards or non-OIDC/OAuth2 kinds.
    """
    card = await get_for_login(session, slug)
    if card is None or not card.is_enabled or card.provider_kind.upper() not in ("OIDC", "OAUTH2"):
        logger.warning("OIDC start requested for missing/disabled card '%s'", slug)
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise ProblemException(
            code="NOT_FOUND",
            status=404,
            title="Card Not Found",
            detail=f"Enabled OIDC/OAuth2 authentication card '{slug}' not found.",
        )

    flow = get_oidc_flow(request)
    target_return = next if next is not None else return_to
    try:
        return await flow.start(
            session,
            slug,
            return_to=target_return,
            link_intent_id=link_intent_id,
            request=request,
        )
    except OidcError as err:
        logger.warning(
            "OIDC start protocol error on public card '%s': code=%s detail=%s",
            slug,
            err.code,
            err.message or err.code,
        )
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise ProblemException(
            code=f"OIDC_{err.code}",
            status=502
            if err.code in ("DISCOVERY_FAILED", "JWKS_FETCH_FAILED", "ISSUER_MISMATCH")
            else 400,
            title="OIDC Protocol Error",
            detail=err.message or err.code,
        ) from err
    except ProblemException as err:
        logger.warning(
            "OIDC start rejected on public card '%s': code=%s status=%d detail=%s",
            slug,
            err.code,
            err.status,
            err.detail,
        )
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise
    except Exception:
        logger.exception("Unexpected error starting login on public card '%s'", slug)
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise

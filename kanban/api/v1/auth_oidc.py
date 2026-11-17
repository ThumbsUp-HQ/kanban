# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC and OAuth2 authentication API endpoints (KB-P2-06)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request  # noqa: TC002
from starlette.responses import RedirectResponse, Response

from database.session import RLSContext
from kanban.api.problems import ProblemException
from kanban.auth.oidc.discovery import OidcError
from kanban.auth.oidc.flow import (
    BROWSER_BINDING_COOKIE_NAME,
    OidcFlow,
)
from kanban.security.keys import load_key_material

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from database.session import RLSSessionFactory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oidc", tags=["auth"])

ANONYMOUS_RLS_CONTEXT = RLSContext(
    principal_id=uuid.UUID(int=0),
    workspace_id=uuid.UUID(int=0),
    aal_level=1,
)


def _is_browser_navigation(request: Request) -> bool:
    """Return True if the request is a browser HTML navigation rather than an API call."""
    accept = request.headers.get("accept", "").lower()
    sec_fetch_mode = request.headers.get("sec-fetch-mode", "").lower()
    return "text/html" in accept or sec_fetch_mode == "navigate"


async def get_auth_session(request: Request) -> AsyncIterator[AsyncSession]:
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


def get_oidc_flow(request: Request) -> OidcFlow:
    """Retrieve or construct the OidcFlow service from application state."""
    flow = getattr(request.app.state, "oidc_flow", None)
    if flow is not None:
        return cast("OidcFlow", flow)

    key_material = getattr(request.app.state, "key_material", None)
    if key_material is None:
        key_material = load_key_material()

    flow = OidcFlow(
        key_material=key_material,
        jwks_cache=getattr(request.app.state, "jwks_cache", None),
        identity_resolver=getattr(request.app.state, "identity_resolver", None),
        session_service=getattr(request.app.state, "session_service", None),
        http_client=getattr(request.app.state, "http_client", None),
        public_origin=getattr(request.app.state, "public_origin", None),
    )
    request.app.state.oidc_flow = flow
    return flow


AuthSession = Annotated[AsyncSession, Depends(get_auth_session)]
FlowDep = Annotated[OidcFlow, Depends(get_oidc_flow)]


@router.get("/{slug}/start", summary="Start OIDC or OAuth2 login")
async def oidc_start(  # noqa: PLR0913, PLR0917
    slug: str,
    request: Request,
    session: AuthSession,
    flow: FlowDep,
    return_to: Annotated[str | None, Query(max_length=2048)] = None,
    link_intent_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Initialize authorization-code flow with PKCE S256 for an OIDC or OAuth2 card."""
    try:
        return await flow.start(
            session,
            slug,
            return_to=return_to,
            link_intent_id=link_intent_id,
            request=request,
        )
    except OidcError as err:
        logger.warning(
            "OIDC start protocol error for card '%s': code=%s detail=%s",
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
            "OIDC start rejected for card '%s': code=%s status=%d detail=%s",
            slug,
            err.code,
            err.status,
            err.detail,
        )
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise
    except Exception:
        logger.exception("Unexpected error in OIDC start for card '%s'", slug)
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise


@router.get("/{slug}/callback", summary="Callback endpoint for OIDC or OAuth2 login")
async def oidc_callback(  # noqa: PLR0913, PLR0917
    slug: str,
    request: Request,
    session: AuthSession,
    flow: FlowDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
    link_intent_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Handle IdP callback redirect, validate state and token, and establish session."""
    browser_binding = request.cookies.get(BROWSER_BINDING_COOKIE_NAME)
    try:
        return await flow.callback(
            session,
            slug,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
            browser_binding_cookie=browser_binding,
            request=request,
            link_intent_id=link_intent_id,
        )
    except OidcError as err:
        logger.warning(
            "OIDC callback protocol error for card '%s': code=%s detail=%s",
            slug,
            err.code,
            err.message or err.code,
        )
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise ProblemException(
            code=f"OIDC_{err.code}",
            status=502 if err.code in ("DISCOVERY_FAILED", "JWKS_FETCH_FAILED") else 400,
            title="OIDC Protocol Error",
            detail=err.message or err.code,
        ) from err
    except ProblemException as err:
        logger.warning(
            "OIDC callback rejected for card '%s': code=%s status=%d detail=%s",
            slug,
            err.code,
            err.status,
            err.detail,
        )
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise
    except Exception:
        logger.exception("Unexpected error in OIDC callback for card '%s'", slug)
        if _is_browser_navigation(request):
            return RedirectResponse(url="/login?error=1", status_code=302)
        raise

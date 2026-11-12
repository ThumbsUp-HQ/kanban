# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session cookie principal resolver and MFA guard dependencies (KB-P2-02)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.auth.sessions.cookies import (
    extract_session_cookie,
    hash_session_token,
    parse_session_cookie,
)

if TYPE_CHECKING:
    from database.session import RLSSessionFactory
    from kanban.auth.sessions.service import SessionService

__all__ = [
    "SessionCookieResolver",
    "require_full_session",
]


class SessionCookieResolver:
    """Principal resolver extracting, verifying, and resolving __Host-kb_session cookies."""

    def __init__(
        self,
        session_service: SessionService,
        session_factory: RLSSessionFactory,
    ) -> None:
        """Initialize resolver with SessionService and database session factory."""
        self._service = session_service
        self._session_factory = session_factory

    async def resolve(self, request: Request) -> PrincipalContext | None:
        """Extract and verify session cookie, resolving database session state."""
        cookie_header = request.headers.get("cookie")
        cookie_val = extract_session_cookie(cookie_header)
        if not cookie_val:
            return None

        # Verify HMAC signature and bounds (rejects without DB access on invalid signature)
        token = parse_session_cookie(cookie_val, self._service.session_hmac_key)
        if not token:
            return None

        token_sha256 = hash_session_token(token)

        # Query database to resolve session using an anonymous context
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("session",),
            aal_level=1,
        )
        async with self._session_factory.session(anon_ctx) as async_session:
            user_session = await self._service.resolve_session(async_session, token_sha256)

        if user_session is None:
            return None

        # Populate request.state for downstream middleware (e.g. CSRF)
        request.state.session_id = user_session.id
        request.state.mfa_pending = user_session.mfa_pending

        ctx = PrincipalContext(
            principal_id=user_session.principal_id,
            workspace_id=user_session.workspace_id,
            token_scopes=("session",),
            aal_level=user_session.aal_level,
            session_id=user_session.id,
            mfa_pending=user_session.mfa_pending,
            aal2_verified_at=user_session.aal2_verified_at,
        )
        request.state.principal = ctx
        return ctx


async def require_full_session(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> PrincipalContext:
    """Ensure principal does not have an incomplete MFA authentication state."""
    allow_mfa = getattr(request.state, "allow_mfa_pending", False)
    # Also inspect endpoint route tags or endpoint function attributes
    endpoint = request.scope.get("endpoint")
    if endpoint and getattr(endpoint, "allow_mfa_pending", False):
        allow_mfa = True

    if principal.mfa_pending and not allow_mfa:
        raise ProblemException(
            code="MFA_REQUIRED",
            status=403,
            title="Multi-Factor Authentication Required",
            detail="Session requires second-factor verification before accessing this resource.",
        )
    return principal

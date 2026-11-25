# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session cookie principal resolver and MFA guard dependencies (KB-P2-02)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.api.request_id import bind_request_log_user, format_log_actor
from kanban.auth.sessions.cookies import (
    extract_session_cookie,
    hash_session_token,
    parse_session_cookie,
)
from kanban.security.boundary import CredentialBoundary

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

    async def resolve(self, request: Request) -> PrincipalContext | None:  # noqa: C901
        """Extract and verify credentials with Bearer-first precedence."""
        auth_hdr = request.headers.get("authorization") or ""
        has_bearer_token = auth_hdr.lower().startswith("bearer ") and bool(auth_hdr[7:].strip())
        has_subject_token = bool(request.headers.get("x-kb-subject-token"))

        # Bearer-first precedence: If explicit token header is present, authenticate token FIRST.
        # Do NOT fall back to ambient browser session cookie if the token header is invalid!
        if has_bearer_token or has_subject_token:
            return await self._resolve_subject_token(request)

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
        request.state.user_session = user_session

        aal2_last_active_at = getattr(user_session, "aal2_last_active_at", None)
        aal2_expires_at: datetime | None = None
        if user_session.aal_level == 2 and user_session.aal2_verified_at:  # noqa: PLR2004
            active_at = aal2_last_active_at or user_session.aal2_verified_at
            now = datetime.now(UTC)
            if active_at.tzinfo is None:
                active_at = active_at.replace(tzinfo=UTC)
            verified_at = user_session.aal2_verified_at
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=UTC)
            idle_exp = user_session.idle_expires_at
            if idle_exp.tzinfo is None:
                idle_exp = idle_exp.replace(tzinfo=UTC)
            abs_exp = user_session.absolute_expires_at
            if abs_exp.tzinfo is None:
                abs_exp = abs_exp.replace(tzinfo=UTC)

            idle_cap = active_at + timedelta(seconds=900)
            abs_cap = verified_at + timedelta(seconds=14400)
            candidate = min(idle_cap, abs_cap, idle_exp, abs_exp)
            if now < candidate:
                aal2_expires_at = candidate

        request.state.aal2_expires_at = aal2_expires_at

        ctx = PrincipalContext(
            principal_id=user_session.principal_id,
            workspace_id=user_session.workspace_id,
            token_scopes=("session",),
            aal_level=user_session.aal_level,
            session_id=user_session.id,
            mfa_pending=user_session.mfa_pending,
            aal2_verified_at=user_session.aal2_verified_at,
            aal2_last_active_at=aal2_last_active_at,
            aal2_expires_at=aal2_expires_at,
            principal_type="USER",
            is_mcp_credential=False,
        )
        request.state.principal = ctx
        bind_request_log_user(
            request,
            format_log_actor(
                ctx.principal_id,
                agent_principal_id=ctx.agent_principal_id,
                mfa_pending=ctx.mfa_pending,
            ),
        )
        return ctx

    async def _resolve_subject_token(self, request: Request) -> PrincipalContext | None:
        """Resolve MCP API key, ephemeral token, or OAuth JWT from X-KB-Subject-Token or Bearer."""
        raw_token = request.headers.get("x-kb-subject-token")
        if not raw_token:
            auth_hdr = request.headers.get("authorization") or ""
            if auth_hdr.lower().startswith("bearer "):
                raw_token = auth_hdr[7:].strip()
        if not raw_token:
            return None

        from sqlalchemy import text  # noqa: PLC0415

        from kanban.security.mcp_keys import introspect_subject_token  # noqa: PLC0415

        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )
        async with self._session_factory.session(anon_ctx) as async_session:
            intro = await introspect_subject_token(async_session, raw_token)
            if not intro.active or intro.principal_id is None:
                return None
            scope_ws = request.headers.get("x-kb-scope-workspace")
            if scope_ws:
                scope_ws_clean = scope_ws.strip()
                target_ws: uuid.UUID | None = None
                try:
                    target_ws = uuid.UUID(scope_ws_clean)
                except ValueError:
                    resolved_ws = (
                        await async_session.execute(
                            text("SELECT resolve_workspace_by_slug_or_id(:ident)"),
                            {"ident": scope_ws_clean},
                        )
                    ).scalar_one_or_none()
                    if isinstance(resolved_ws, uuid.UUID):
                        target_ws = resolved_ws
                ws_id = target_ws if target_ws is not None else intro.workspace_id
            else:
                ws_id = intro.workspace_id

            if ws_id is None or ws_id == uuid.UUID(int=0):
                def_ws = (
                    await async_session.execute(text("SELECT get_default_workspace_id()"))
                ).scalar_one_or_none()
                ws_id = def_ws if def_ws is not None else uuid.UUID(int=0)

        is_ephemeral = (
            intro.token_kind == "ephemeral"  # noqa: S105
            or raw_token.startswith(("kb_agt_eph_", "kb_eat_"))
        )
        owner_kind = intro.owner_kind or (
            "agent" if intro.agent_principal_id or is_ephemeral else "user"
        )
        principal_type = owner_kind.upper()
        boundary = getattr(
            intro, "credential_boundary", None
        ) or CredentialBoundary.from_introspection(intro)
        ctx = PrincipalContext(
            principal_id=intro.principal_id,
            workspace_id=ws_id,
            token_scopes=tuple(intro.scopes or ()),
            aal_level=2 if intro.surface == "admin" else 1,
            agent_principal_id=intro.agent_principal_id,
            ephemeral_project_id=intro.project_id if is_ephemeral else None,
            read_only=is_ephemeral,
            scope_tier=intro.scope_tier,
            scoped_project_id=intro.project_id,
            principal_type=principal_type,
            is_mcp_credential=True,
            credential_boundary=boundary,
        )
        request.state.principal = ctx
        bind_request_log_user(
            request,
            format_log_actor(
                ctx.principal_id,
                agent_principal_id=ctx.agent_principal_id,
                mfa_pending=ctx.mfa_pending,
            ),
        )
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
            status=401,
            title="Multi-Factor Authentication Required",
            detail="Session requires second-factor verification before accessing this resource.",
        )
    return principal

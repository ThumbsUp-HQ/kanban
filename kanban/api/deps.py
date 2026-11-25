"""Principal authentication, context resolution, and RLS session dependencies (S3.3)."""

from __future__ import annotations

import hashlib
import uuid  # Required at runtime for dataclass field validation
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, cast

from fastapi import Depends
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis

from database.session import RLSContext
from kanban.api.problems import ProblemException
from kanban.api.request_id import bind_request_log_user, format_log_actor
from kanban.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory
    from kanban.security.boundary import CredentialBoundary


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """Resolved identity and capability context for an authenticated request."""

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    token_scopes: tuple[str, ...] = ()
    aal_level: int = 1
    session_id: uuid.UUID | None = None
    agent_principal_id: uuid.UUID | None = None
    ephemeral_project_id: uuid.UUID | None = None
    read_only: bool = False
    mfa_pending: bool = False
    aal2_verified_at: datetime | None = None
    aal2_last_active_at: datetime | None = None
    aal2_expires_at: datetime | None = None
    scope_tier: str | None = None
    scoped_project_id: uuid.UUID | None = None
    user_access_hash: bytes | None = None
    is_server_admin: bool = False
    principal_type: str | None = None
    is_mcp_credential: bool = False
    credential_boundary: CredentialBoundary | None = None

    def __post_init__(self) -> None:
        """Enforce AAL level bounds."""
        if self.aal_level not in (1, 2):
            msg = f"Invalid aal_level: {self.aal_level} (must be 1 or 2)"
            raise ValueError(msg)

        raw_scopes: object = self.token_scopes
        if not isinstance(raw_scopes, tuple):
            if not hasattr(raw_scopes, "__iter__"):
                msg = f"Token scopes must be an iterable (got {type(raw_scopes).__name__})"
                raise TypeError(msg)
            converted: tuple[object, ...] = tuple(raw_scopes)
            object.__setattr__(self, "token_scopes", converted)

    @property
    def is_agent_or_mcp_caller(self) -> bool:
        """Return True if caller is an AI agent, MCP client, or service principal."""
        if self.principal_type in ("AGENT", "SERVICE_PRINCIPAL", "agent", "service_principal"):
            return True
        if self.agent_principal_id is not None:
            return True
        if self.is_mcp_credential:
            return True
        return any(scope.startswith(("agent:", "docs:", "admin:")) for scope in self.token_scopes)


class PrincipalResolver(Protocol):
    """Protocol for resolving PrincipalContext from an inbound HTTP request."""

    async def resolve(self, request: Request) -> PrincipalContext | None:
        """Inspect request authentication state and resolve PrincipalContext, or None."""
        ...


class DenyAllResolver:
    """Default fail-closed resolver that denies all requests."""

    async def resolve(self, request: Request) -> PrincipalContext | None:
        """Deny resolution returning None unconditionally."""
        del request
        return None


async def get_principal(request: Request) -> PrincipalContext:
    """Resolve and enforce the authenticated principal context for the active request.

    S3.3: Client-supplied headers or query params are NEVER inspected for identity.
    Identity is resolved exclusively through verified cryptographic credentials via the
    configured PrincipalResolver on app.state.principal_resolver.
    """
    resolver: PrincipalResolver = getattr(
        request.app.state, "principal_resolver", DenyAllResolver()
    )
    principal = await resolver.resolve(request)

    if principal is None:
        raise ProblemException(
            code="AUTHENTICATION_REQUIRED",
            status=401,
            title="Authentication Required",
            detail=None,
        )

    bind_request_log_user(
        request,
        format_log_actor(
            principal.principal_id,
            agent_principal_id=principal.agent_principal_id,
            mfa_pending=principal.mfa_pending,
        ),
    )

    allow_mfa = getattr(request.state, "allow_mfa_pending", False)
    endpoint = request.scope.get("endpoint")
    if endpoint and getattr(endpoint, "allow_mfa_pending", False):
        allow_mfa = True

    path = request.url.path
    if path.startswith(("/api/v1/auth/mfa", "/api/v1/auth/webauthn", "/api/v1/mfa")) or path in (
        "/api/v1/auth/session",
        "/api/v1/auth/logout",
        "/api/v1/auth/totp/enroll",
        "/api/v1/auth/totp/enroll/verify",
        "/api/v1/auth/totp/verify",
        "/api/v1/auth/recovery/verify",
    ):
        allow_mfa = True

    if principal.mfa_pending and not allow_mfa:
        raise ProblemException(
            code="MFA_REQUIRED",
            status=401,
            title="Multi-Factor Authentication Required",
            detail="Session requires second-factor verification before accessing this resource.",
        )

    if principal.credential_boundary is not None:
        principal.credential_boundary.validate_request(request, principal.workspace_id)

    return principal


async def get_rls_session(
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> AsyncIterator[AsyncSession]:
    """Provide an RLS-bound database session inside an active transaction.

    Binds session context via SET LOCAL prior to statement execution, commits on normal
    completion, and rolls back on unhandled errors.
    """
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "RLS session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    target_ws_id = principal.workspace_id
    scope_ws = request.headers.get("x-kb-scope-workspace")
    if scope_ws:
        scope_ws_clean = scope_ws.strip()
        try:
            target_ws_id = uuid.UUID(scope_ws_clean)
        except ValueError:
            from sqlalchemy import text  # noqa: PLC0415

            lookup_ctx = RLSContext(
                principal_id=principal.principal_id,
                workspace_id=uuid.UUID(int=0),
                token_scopes=("auth",),
                aal_level=1,
            )
            async with session_factory.session(lookup_ctx) as lookup_session:
                res_ws = (
                    await lookup_session.execute(
                        text("SELECT resolve_workspace_by_slug_or_id(:ident)"),
                        {"ident": scope_ws_clean},
                    )
                ).scalar_one_or_none()
                if res_ws:
                    target_ws_id = res_ws

    if (
        principal.credential_boundary is not None
        and not principal.credential_boundary.allows_workspace(target_ws_id)
    ):
        raise ProblemException(
            code="CREDENTIAL_SCOPE_VIOLATION",
            status=403,
            title="Credential Scope Violation",
            detail=f"Workspace '{target_ws_id}' is outside allowed workspaces.",
        )

    user_access_hash = principal.user_access_hash
    if user_access_hash is None:
        scopes_str = ",".join(sorted(principal.token_scopes))
        raw = f"{principal.workspace_id}:{principal.principal_id}:{scopes_str}".encode()
        user_access_hash = hashlib.sha256(raw).digest()

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=target_ws_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
        agent_principal_id=principal.agent_principal_id,
        ephemeral_project_id=principal.ephemeral_project_id,
        read_only=principal.read_only or (principal.ephemeral_project_id is not None),
        user_access_hash=user_access_hash,
    )

    async with session_factory.session(rls_ctx) as session:
        yield session


def get_settings(request: Request) -> Settings:
    """Return the active platform settings from app state, or default."""
    settings = getattr(request.app.state, "settings", None)
    if isinstance(settings, Settings):
        return settings
    return Settings()


# Alias for backwards compatibility and clarity across dependencies
get_current_principal = get_principal

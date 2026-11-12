"""Principal authentication, context resolution, and RLS session dependencies (S3.3)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime for dataclass field validation
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, cast

from fastapi import Depends
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis

from database.session import RLSContext
from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.session import RLSSessionFactory


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """Resolved identity and capability context for an authenticated request."""

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    token_scopes: tuple[str, ...] = ()
    aal_level: int = 1
    session_id: uuid.UUID | None = None
    agent_principal_id: uuid.UUID | None = None
    mfa_pending: bool = False
    aal2_verified_at: datetime | None = None

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

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as session:
        yield session

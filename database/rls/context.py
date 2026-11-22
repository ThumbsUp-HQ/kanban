# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RLS session context management and PostgreSQL SET LOCAL binding."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "RLSContext",
    "RLSContextError",
    "RLSRoleViolationError",
    "UnboundRLSSessionError",
    "bind_rls_context",
]

_SCOPE_REGEX = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,63}$")


class RLSContextError(RuntimeError):
    """Base exception for RLS context and session binding violations."""


class UnboundRLSSessionError(RLSContextError):
    """Raised when an ORM query is attempted on a session lacking RLS context binding."""


class RLSRoleViolationError(RLSContextError):
    """Raised when the connected database role has SUPERUSER or BYPASSRLS privileges."""


@dataclass(frozen=True, slots=True)
class RLSContext:
    """Immutable security context bound to PostgreSQL session variables via SET LOCAL."""

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    token_scopes: tuple[str, ...] = ()
    aal_level: Literal[1, 2] = 1
    user_access_hash: bytes | str | None = None
    agent_principal_id: uuid.UUID | None = None
    ephemeral_project_id: uuid.UUID | None = None
    read_only: bool = False
    credential_workspaces: tuple[uuid.UUID, ...] | frozenset[uuid.UUID] = ()
    credential_projects: tuple[uuid.UUID, ...] | frozenset[uuid.UUID] = ()
    credential_capability_mask: int | None = None
    credential_boundary: Any = None

    def _validate_aal_and_scopes(self) -> None:
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
            raw_scopes = converted

        for scope in raw_scopes:
            if not isinstance(scope, str):
                msg = f"Token scope must be a string (got {type(scope).__name__})"
                raise TypeError(msg)
            if "," in scope or any(c.isspace() for c in scope) or not _SCOPE_REGEX.match(scope):
                msg = f"Invalid token scope: {scope!r}"
                raise ValueError(msg)

    def _normalize_credential_boundary(self) -> None:
        cb = self.credential_boundary
        if cb is not None:
            if not self.credential_workspaces and hasattr(cb, "workspace_allowlist"):
                ws_allow = cb.workspace_allowlist
                if ws_allow:
                    object.__setattr__(self, "credential_workspaces", tuple(ws_allow))
            if not self.credential_projects and hasattr(cb, "project_allowlist"):
                proj_allow = cb.project_allowlist
                if proj_allow:
                    object.__setattr__(self, "credential_projects", tuple(proj_allow))
            if self.credential_capability_mask is None and hasattr(cb, "capability_mask"):
                object.__setattr__(self, "credential_capability_mask", cb.capability_mask)

        ws_tuple: tuple[uuid.UUID, ...] = tuple(
            w if isinstance(w, uuid.UUID) else uuid.UUID(str(w))  # type: ignore[redundant-expr]
            for w in (self.credential_workspaces or ())
        )
        object.__setattr__(self, "credential_workspaces", ws_tuple)

        proj_tuple: tuple[uuid.UUID, ...] = tuple(
            p if isinstance(p, uuid.UUID) else uuid.UUID(str(p))  # type: ignore[redundant-expr]
            for p in (self.credential_projects or ())
        )
        object.__setattr__(self, "credential_projects", proj_tuple)

        if self.credential_capability_mask is not None:
            object.__setattr__(
                self,
                "credential_capability_mask",
                int(self.credential_capability_mask),
            )

    def __post_init__(self) -> None:
        """Validate aal_level, token scopes, and normalize credential boundary attributes."""
        self._validate_aal_and_scopes()
        self._normalize_credential_boundary()


async def bind_rls_context(session: AsyncSession, ctx: RLSContext) -> None:
    """Bind RLS session context variables using SET LOCAL within an active transaction."""
    if not session.in_transaction():
        msg = "bind_rls_context requires an active transaction"
        raise RLSContextError(msg)

    session.info["_binding_in_progress"] = True
    try:
        user_hash_val = ""
        if ctx.user_access_hash is not None:
            if isinstance(ctx.user_access_hash, bytes):
                user_hash_val = ctx.user_access_hash.hex()
            else:
                user_hash_val = str(ctx.user_access_hash)

        ws_list = (
            ",".join(str(w) for w in ctx.credential_workspaces) if ctx.credential_workspaces else ""
        )
        proj_list = (
            ",".join(str(p) for p in ctx.credential_projects) if ctx.credential_projects else ""
        )
        cap_mask_str = (
            str(ctx.credential_capability_mask)
            if ctx.credential_capability_mask is not None
            else ""
        )

        stmt = text(
            "SELECT set_config('app.principal_id', :principal_id, true), "
            "set_config('app.workspace_id', :workspace_id, true), "
            "set_config('app.token_scopes', :token_scopes, true), "
            "set_config('app.aal_level', :aal_level, true), "
            "set_config('app.user_access_hash', :user_access_hash, true), "
            "set_config('app.agent_principal_id', :agent_principal_id, true), "
            "set_config('app.ephemeral_project_id', :ephemeral_project_id, true), "
            "set_config('app.credential_workspaces', :credential_workspaces, true), "
            "set_config('app.credential_projects', :credential_projects, true), "
            "set_config('app.credential_capability_mask', :credential_capability_mask, true)"
        )
        params = {
            "principal_id": str(ctx.principal_id),
            "workspace_id": str(ctx.workspace_id),
            "token_scopes": ",".join(ctx.token_scopes),
            "aal_level": str(ctx.aal_level),
            "user_access_hash": user_hash_val,
            "agent_principal_id": (
                str(ctx.agent_principal_id) if ctx.agent_principal_id is not None else ""
            ),
            "ephemeral_project_id": (
                str(ctx.ephemeral_project_id) if ctx.ephemeral_project_id is not None else ""
            ),
            "credential_workspaces": ws_list,
            "credential_projects": proj_list,
            "credential_capability_mask": cap_mask_str,
        }
        await session.execute(stmt, params)
        if ctx.read_only:
            await session.execute(text("SET LOCAL TRANSACTION READ ONLY"))
        session.info["rls_bound"] = True
        session.info["rls_context"] = ctx
    finally:
        session.info.pop("_binding_in_progress", None)

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Immutable CredentialBoundary across REST Bearer auth (KB-SEC-04).

Enforces workspace/project allowlists, CIDR, capability mask, and tool scope.
"""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from starlette.requests import Request

    from kanban.security.mcp_keys import McpIntrospectionResult


class EmptyCapabilitySet(frozenset[Any]):
    """Empty capability set that compares equal to frozenset() and Capability.NONE (0)."""

    def __hash__(self) -> int:
        """Hash representation matches frozenset."""
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        """Compare equal to 0, Capability.NONE, or empty sets."""
        from kanban.security.permissions import Capability  # noqa: PLC0415

        if other is Capability.NONE:
            return True
        if other == 0:
            return True
        return super().__eq__(other)

    def __int__(self) -> int:
        """Integer representation is 0."""
        return 0


@dataclass(frozen=True, slots=True)
class CredentialBoundary:
    """Immutable boundary enforcing scoping, surface, CIDR, and capability invariants."""

    scope_tier: str = "workspace"
    surface: str = "agent"
    workspace_allowlist: frozenset[uuid.UUID] | Any = frozenset()
    project_allowlist: frozenset[uuid.UUID] | Any = frozenset()
    capability_mask: int = 255
    allowed_tools: frozenset[str] | Any = None
    allowed_cidrs: tuple[str, ...] | Any = ()
    execution_id: uuid.UUID | None = None
    has_aal2_provenance: bool = False

    def __post_init__(self) -> None:
        """Normalize attributes upon construction."""
        # Normalize scope_tier
        if self.scope_tier == "server":
            object.__setattr__(self, "scope_tier", "global")

        # Normalize workspace_allowlist
        if not isinstance(self.workspace_allowlist, frozenset):
            ws_set = frozenset(
                uuid.UUID(str(w)) if not isinstance(w, uuid.UUID) else w
                for w in (self.workspace_allowlist or ())
            )
            object.__setattr__(self, "workspace_allowlist", ws_set)

        # Normalize project_allowlist
        if not isinstance(self.project_allowlist, frozenset):
            proj_set = frozenset(
                uuid.UUID(str(p)) if not isinstance(p, uuid.UUID) else p
                for p in (self.project_allowlist or ())
            )
            object.__setattr__(self, "project_allowlist", proj_set)

        # Normalize allowed_tools
        if self.allowed_tools is not None and not isinstance(self.allowed_tools, frozenset):
            object.__setattr__(self, "allowed_tools", frozenset(self.allowed_tools))

        # Normalize allowed_cidrs
        if not isinstance(self.allowed_cidrs, tuple):
            object.__setattr__(
                self, "allowed_cidrs", tuple(str(c) for c in (self.allowed_cidrs or ()))
            )

    @classmethod
    def from_introspection(cls, intro: McpIntrospectionResult) -> CredentialBoundary:
        """Construct an immutable CredentialBoundary from an active introspection result."""
        scope_tier = intro.scope_tier or "workspace"
        if scope_tier == "server":
            scope_tier = "global"

        ws_set: set[uuid.UUID] = set()
        if intro.allowed_workspace_ids:
            ws_set.update(uuid.UUID(str(w)) for w in intro.allowed_workspace_ids)
        if intro.workspace_id and scope_tier in ("workspace", "project"):
            ws_set.add(uuid.UUID(str(intro.workspace_id)))
        workspace_allowlist = frozenset(ws_set)

        proj_set: set[uuid.UUID] = set()
        if intro.allowed_project_ids:
            proj_set.update(uuid.UUID(str(p)) for p in intro.allowed_project_ids)
        elif intro.allowed_projects:
            proj_set.update(uuid.UUID(str(p)) for p in intro.allowed_projects)
        if intro.project_id:
            proj_set.add(uuid.UUID(str(intro.project_id)))
        project_allowlist = frozenset(proj_set)

        cap_mask = intro.capability_mask if intro.capability_mask is not None else 255
        allowed_tools = frozenset(intro.allowed_tools) if intro.allowed_tools is not None else None
        allowed_cidrs = tuple(str(c) for c in (intro.allowed_cidrs or ()))

        # Verified AAL2 provenance: strictly for admin API keys
        has_aal2_provenance = (
            intro.surface == "admin" and intro.token_kind == "api_key"  # noqa: S105
        )

        raw_surface = intro.surface or "agent"
        surface_val: Literal["agent", "docs", "admin"] = (
            cast("Literal['agent', 'docs', 'admin']", raw_surface)
            if raw_surface in ("agent", "docs", "admin")
            else "agent"
        )
        tier_val: Literal["global", "workspace", "project"] = (
            cast("Literal['global', 'workspace', 'project']", scope_tier)
            if scope_tier in ("global", "workspace", "project")
            else "workspace"
        )

        return cls(
            scope_tier=tier_val,
            surface=surface_val,
            workspace_allowlist=workspace_allowlist,
            project_allowlist=project_allowlist,
            capability_mask=cap_mask,
            allowed_tools=allowed_tools,
            allowed_cidrs=allowed_cidrs,
            execution_id=intro.execution_id,
            has_aal2_provenance=has_aal2_provenance,
        )

    def allows_workspace(self, workspace_id: uuid.UUID | str | None) -> bool:
        """Check whether the workspace is permitted under this credential boundary."""
        if workspace_id is None:
            return True
        target = (
            uuid.UUID(str(workspace_id))
            if not isinstance(workspace_id, uuid.UUID)
            else workspace_id
        )
        if self.workspace_allowlist:
            return target in self.workspace_allowlist
        return self.scope_tier == "global"

    def allows_project(self, project_id: uuid.UUID | str | None) -> bool:
        """Check whether the project is permitted under this credential boundary."""
        if project_id is None:
            return True
        target = uuid.UUID(str(project_id)) if not isinstance(project_id, uuid.UUID) else project_id
        if self.project_allowlist:
            return target in self.project_allowlist
        return self.scope_tier != "project"

    def allows_ip(self, client_ip: str | None) -> bool:
        """Check whether the client IP address is allowed under the CIDR allowlist."""
        if not self.allowed_cidrs or not client_ip:
            return True
        try:
            ip = ipaddress.ip_address(client_ip)
            return any(
                ip in ipaddress.ip_network(cidr, strict=False) for cidr in self.allowed_cidrs
            )
        except ValueError:
            return False

    def effective_capabilities(self, rbac_caps: object) -> object:
        """Intersect RBAC capabilities with this boundary's capability mask."""
        from kanban.security.permissions import Capability, capabilities_to_names  # noqa: PLC0415

        if isinstance(rbac_caps, (Capability, int)):
            return Capability(int(rbac_caps) & self.capability_mask)

        if isinstance(rbac_caps, (set, frozenset, list, tuple)):
            items = list(rbac_caps)
            if not items:
                return frozenset()
            if isinstance(items[0], Capability):
                return frozenset(c for c in items if (int(c) & self.capability_mask) == int(c))
            allowed_names = set(capabilities_to_names(Capability(self.capability_mask)))
            return frozenset(str(c).upper() for c in items if str(c).upper() in allowed_names)

        return rbac_caps

    def validate_request(self, request: Request, workspace_id: uuid.UUID | None = None) -> None:
        """Validate request client IP, workspace, and surface restrictions."""
        # 1. CIDR validation
        if self.allowed_cidrs:
            from kanban.security.client_ip import resolve_client_ip  # noqa: PLC0415

            client_ip = resolve_client_ip(request.scope)
            if not self.allows_ip(client_ip):
                raise ProblemException(
                    code="CIDR_NOT_ALLOWED",
                    status=403,
                    title="CIDR Not Allowed",
                    detail=f"Client IP '{client_ip}' is outside allowed CIDRs.",
                )

        # 2. Workspace validation
        if workspace_id is not None and not self.allows_workspace(workspace_id):
            raise ProblemException(
                code="CREDENTIAL_SCOPE_VIOLATION",
                status=403,
                title="Credential Scope Violation",
                detail=f"Workspace '{workspace_id}' is outside allowed workspaces.",
            )

        # 3. Surface restrictions
        path = request.url.path
        method = request.method.upper()

        if path.startswith("/api/v1/admin") and self.surface != "admin":
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail=(
                    f"Credential with surface '{self.surface}' cannot invoke "
                    "administrative endpoints."
                ),
            )

        if self.surface == "docs" and method in ("POST", "PUT", "PATCH", "DELETE"):
            is_doc_path = path.startswith(("/api/v1/docs", "/api/v1/pages", "/api/v1/stickies"))
            if not is_doc_path:
                raise ProblemException(
                    code="INSUFFICIENT_SCOPE",
                    status=403,
                    title="Insufficient Scope",
                    detail=(
                        f"Docs surface credential cannot invoke mutation endpoints "
                        f"on non-doc resources ({path})."
                    ),
                )

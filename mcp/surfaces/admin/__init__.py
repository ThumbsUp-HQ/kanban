# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Admin surface tool registry and definitions (KB-P4-09a, KB-P4-09b, KB-P4-11 / S11.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.admin.audit_and_purge_object_links import (
    AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA,
    audit_and_purge_object_links,
)
from mcp.surfaces.admin.configure_workspace import (
    CONFIGURE_WORKSPACE_SCHEMA,
    configure_workspace,
    create_configure_workspace_tool,
)
from mcp.surfaces.admin.manage_access_policies import (
    MANAGE_ACCESS_POLICIES_SCHEMA,
    create_manage_access_policies_tool,
    manage_access_policies_tool,
)
from mcp.surfaces.admin.manage_auth_cards import (
    MANAGE_AUTH_CARDS_SCHEMA,
    create_manage_auth_cards_tool,
    manage_auth_cards,
)
from mcp.surfaces.admin.manage_principals_and_groups import (
    MANAGE_PRINCIPALS_AND_GROUPS_SCHEMA,
    create_manage_principals_and_groups_tool,
    manage_principals_and_groups_tool,
)
from mcp.surfaces.admin.override_ticket_provenance import (
    OVERRIDE_TICKET_PROVENANCE_SCHEMA,
    override_ticket_provenance,
)

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA",
    "CONFIGURE_WORKSPACE_SCHEMA",
    "MANAGE_ACCESS_POLICIES_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "MANAGE_PRINCIPALS_AND_GROUPS_SCHEMA",
    "OVERRIDE_TICKET_PROVENANCE_SCHEMA",
    "audit_and_purge_object_links",
    "build_admin_registry",
    "configure_workspace",
    "create_admin_registry",
    "create_manage_access_policies_tool",
    "create_manage_principals_and_groups_tool",
    "manage_access_policies_tool",
    "manage_auth_cards",
    "manage_principals_and_groups_tool",
    "override_ticket_provenance",
]


def build_admin_registry(client: KanbanApiClient | None = None) -> ToolRegistry:  # noqa: ARG001
    """Construct and return the admin surface ToolRegistry with official tools."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
    registry.register(create_manage_principals_and_groups_tool())
    registry.register(create_manage_access_policies_tool())
    registry.register(
        ToolSpec(
            name="override_ticket_provenance",
            description=(
                "Perform audited 'Created by' overrides, Hard WIP limit overrides, and "
                "unarchivals with a mandatory justification under PROJECT_ADMIN or SERVER_ADMIN."
            ),
            input_schema=OVERRIDE_TICKET_PROVENANCE_SCHEMA,
            surface=Surface.ADMIN,
            handler=override_ticket_provenance,
        )
    )
    registry.register(
        ToolSpec(
            name="audit_and_purge_object_links",
            description=(
                "Execute the 6-class Universal Object Graph Auditor, inspect flagged link "
                "snapshots, and purge audited entries with an immutable activity ledger record."
            ),
            input_schema=AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA,
            surface=Surface.ADMIN,
            handler=audit_and_purge_object_links,
        )
    )
    return registry


create_admin_registry = build_admin_registry

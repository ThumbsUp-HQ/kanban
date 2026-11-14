# Copyright 2026 Kanban Platform Contributors
"""Admin surface tool registry and definitions (KB-P4-09a, KB-P4-11, KB-P4-12 / S11.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

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
from mcp.surfaces.admin.destructive_lifecycle import (
    DESTRUCTIVE_LIFECYCLE_SCHEMA,
    create_destructive_lifecycle_tool,
    destructive_lifecycle,
)
from mcp.surfaces.admin.manage_auth_cards import (
    MANAGE_AUTH_CARDS_SCHEMA,
    create_manage_auth_cards_tool,
    manage_auth_cards,
)
from mcp.surfaces.admin.override_ticket_provenance import (
    OVERRIDE_TICKET_PROVENANCE_SCHEMA,
    override_ticket_provenance,
)

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ADMIN_TOOL_NAMES",
    "AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA",
    "CONFIGURE_WORKSPACE_SCHEMA",
    "DESTRUCTIVE_LIFECYCLE_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "OVERRIDE_TICKET_PROVENANCE_SCHEMA",
    "audit_and_purge_object_links",
    "build_admin_registry",
    "configure_workspace",
    "create_admin_registry",
    "destructive_lifecycle",
    "manage_auth_cards",
    "override_ticket_provenance",
]

ADMIN_TOOL_NAMES: Final[tuple[str, ...]] = (
    "configure_workspace",
    "manage_auth_cards",
    "override_ticket_provenance",
    "audit_and_purge_object_links",
    "destructive_lifecycle",
)


def build_admin_registry(client: KanbanApiClient | None = None) -> ToolRegistry:
    """Construct and return the admin surface ToolRegistry with official tools."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
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
    registry.register(create_destructive_lifecycle_tool(client))
    return registry


create_admin_registry = build_admin_registry

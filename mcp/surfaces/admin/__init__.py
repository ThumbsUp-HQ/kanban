# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Admin surface tool registry and definitions (KB-P4-11, S11.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.admin.audit_and_purge_object_links import (
    AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA,
    audit_and_purge_object_links,
)
from mcp.surfaces.admin.override_ticket_provenance import (
    OVERRIDE_TICKET_PROVENANCE_SCHEMA,
    override_ticket_provenance,
)

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "AUDIT_AND_PURGE_OBJECT_LINKS_SCHEMA",
    "OVERRIDE_TICKET_PROVENANCE_SCHEMA",
    "audit_and_purge_object_links",
    "build_admin_registry",
    "create_admin_registry",
    "override_ticket_provenance",
]


def build_admin_registry(client: KanbanApiClient | None = None) -> ToolRegistry:  # noqa: ARG001
    """Construct and return the admin surface ToolRegistry with official tools."""
    registry = ToolRegistry(Surface.ADMIN)

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

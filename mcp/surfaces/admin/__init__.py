# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP admin surface tool registry and definitions (KB-P4-09a / KB-P4-12 / S11.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mcp.registry import Surface, ToolRegistry
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

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "ADMIN_TOOL_NAMES",
    "CONFIGURE_WORKSPACE_SCHEMA",
    "DESTRUCTIVE_LIFECYCLE_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "build_admin_registry",
    "configure_workspace",
    "create_admin_registry",
    "destructive_lifecycle",
    "manage_auth_cards",
]

ADMIN_TOOL_NAMES: Final[tuple[str, ...]] = (
    "configure_workspace",
    "manage_auth_cards",
    "destructive_lifecycle",
)


def create_admin_registry(client: KanbanApiClient | None = None) -> ToolRegistry:
    """Construct frozen ToolRegistry containing official tools for /mcp/admin."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
    registry.register(create_destructive_lifecycle_tool(client))
    return registry


build_admin_registry = create_admin_registry

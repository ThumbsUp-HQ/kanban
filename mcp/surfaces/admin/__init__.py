# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP admin surface tool registry and definitions (KB-P4-09a / S11.4)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry
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

__all__ = [
    "CONFIGURE_WORKSPACE_SCHEMA",
    "MANAGE_ACCESS_POLICIES_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "MANAGE_PRINCIPALS_AND_GROUPS_SCHEMA",
    "configure_workspace",
    "create_admin_registry",
    "manage_access_policies_tool",
    "manage_auth_cards",
    "manage_principals_and_groups_tool",
]


def create_admin_registry() -> ToolRegistry:
    """Construct frozen ToolRegistry containing official tools for /mcp/admin."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
    registry.register(create_manage_principals_and_groups_tool())
    registry.register(create_manage_access_policies_tool())
    return registry

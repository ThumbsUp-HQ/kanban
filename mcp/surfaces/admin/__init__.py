# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP admin surface tool registry and definitions (KB-P4-09a / S11.4)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry
from mcp.surfaces.admin.architect_project import (
    ARCHITECT_PROJECT_SCHEMA,
    architect_project,
    create_architect_project_tool,
)
from mcp.surfaces.admin.configure_workspace import (
    CONFIGURE_WORKSPACE_SCHEMA,
    configure_workspace,
    create_configure_workspace_tool,
)
from mcp.surfaces.admin.manage_auth_cards import (
    MANAGE_AUTH_CARDS_SCHEMA,
    create_manage_auth_cards_tool,
    manage_auth_cards,
)
from mcp.surfaces.admin.manage_cycles_and_modules import (
    MANAGE_CYCLES_AND_MODULES_SCHEMA,
    create_manage_cycles_and_modules_tool,
    manage_cycles_and_modules,
)

__all__ = [
    "ARCHITECT_PROJECT_SCHEMA",
    "CONFIGURE_WORKSPACE_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "MANAGE_CYCLES_AND_MODULES_SCHEMA",
    "architect_project",
    "configure_workspace",
    "create_admin_registry",
    "manage_auth_cards",
    "manage_cycles_and_modules",
]


def create_admin_registry() -> ToolRegistry:
    """Construct frozen ToolRegistry containing official tools for /mcp/admin."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
    registry.register(create_architect_project_tool())
    registry.register(create_manage_cycles_and_modules_tool())
    return registry

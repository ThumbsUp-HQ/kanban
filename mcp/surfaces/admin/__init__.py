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
from mcp.surfaces.admin.manage_ai_and_agent_runners import (
    MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA,
    create_manage_ai_and_agent_runners_tool,
    manage_ai_and_agent_runners,
)
from mcp.surfaces.admin.manage_auth_cards import (
    MANAGE_AUTH_CARDS_SCHEMA,
    create_manage_auth_cards_tool,
    manage_auth_cards,
)

__all__ = [
    "CONFIGURE_WORKSPACE_SCHEMA",
    "MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA",
    "MANAGE_AUTH_CARDS_SCHEMA",
    "configure_workspace",
    "create_admin_registry",
    "manage_ai_and_agent_runners",
    "manage_auth_cards",
]


def create_admin_registry() -> ToolRegistry:
    """Construct frozen ToolRegistry containing official tools for /mcp/admin."""
    registry = ToolRegistry(Surface.ADMIN)
    registry.register(create_configure_workspace_tool())
    registry.register(create_manage_auth_cards_tool())
    registry.register(create_manage_ai_and_agent_runners_tool())
    return registry

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export manage_ai_and_agent_runners for MCP surfaces admin package (KB-P5-05b)."""

from __future__ import annotations

from mcp.admin.tools.manage_ai_and_agent_runners import (
    MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA,
    create_manage_ai_and_agent_runners_tool,
    manage_ai_and_agent_runners,
)

__all__ = [
    "MANAGE_AI_AND_AGENT_RUNNERS_SCHEMA",
    "create_manage_ai_and_agent_runners_tool",
    "manage_ai_and_agent_runners",
]

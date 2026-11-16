# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export of manage_cycles_and_modules MCP tool (KB-P5-19b, S11.4)."""

from mcp.surfaces.admin.manage_cycles_and_modules import (
    MANAGE_CYCLES_AND_MODULES_SCHEMA,
    create_manage_cycles_and_modules_tool,
    manage_cycles_and_modules,
)

__all__ = [
    "MANAGE_CYCLES_AND_MODULES_SCHEMA",
    "create_manage_cycles_and_modules_tool",
    "manage_cycles_and_modules",
]

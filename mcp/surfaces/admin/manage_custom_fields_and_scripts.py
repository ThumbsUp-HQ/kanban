# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export of manage_custom_fields_and_scripts MCP tool for surfaces.admin (KB-P5-13)."""

from mcp.admin.tools.manage_custom_fields_and_scripts import (
    MANAGE_CUSTOM_FIELDS_AND_SCRIPTS_SCHEMA,
    create_manage_custom_fields_and_scripts_tool,
    manage_custom_fields_and_scripts,
)

__all__ = [
    "MANAGE_CUSTOM_FIELDS_AND_SCRIPTS_SCHEMA",
    "create_manage_custom_fields_and_scripts_tool",
    "manage_custom_fields_and_scripts",
]

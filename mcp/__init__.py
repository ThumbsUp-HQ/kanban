# Copyright 2026 Kanban Platform Contributors
"""Model Context Protocol server exposing agent, docs, and admin surfaces."""

from __future__ import annotations

from mcp.app import create_mcp_app
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings

__version__: str = "0.0.0"

__all__ = [
    "KanbanApiClient",
    "KbMcpError",
    "McpErrorCode",
    "McpSettings",
    "Surface",
    "ToolRegistry",
    "ToolSpec",
    "create_mcp_app",
]

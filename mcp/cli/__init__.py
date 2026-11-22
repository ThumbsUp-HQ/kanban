# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Command-line interface for Kanban MCP tools, auth, and schema parity (KAN-48)."""

from __future__ import annotations

from mcp.cli.main import main, main_admin, main_agent, main_docs

__all__ = [
    "main",
    "main_admin",
    "main_agent",
    "main_docs",
]

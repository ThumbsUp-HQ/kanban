# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Admin surface registry re-exports and definitions (KB-P5-17b, S11.4)."""

from __future__ import annotations

from mcp.surfaces.admin import (
    ADMIN_TOOL_NAMES,
    build_admin_registry,
    create_admin_registry,
)

__all__ = [
    "ADMIN_TOOL_NAMES",
    "build_admin_registry",
    "create_admin_registry",
]

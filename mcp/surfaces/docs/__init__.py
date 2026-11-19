# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Isolated /mcp/docs surface registry and consolidated tools (S11.3, KB-P4-08, KAN-18)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mcp.registry import Surface, ToolRegistry
from mcp.surfaces.docs.create import create_docs_create_tool
from mcp.surfaces.docs.search import create_docs_search_tool
from mcp.surfaces.docs.update import create_docs_update_tool

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "DOCS_TOOL_NAMES",
    "build_docs_registry",
    "create_docs_registry",
]

DOCS_TOOL_NAMES: Final[tuple[str, ...]] = (
    "search",
    "create",
    "update",
)


def build_docs_registry(client: KanbanApiClient | None = None) -> ToolRegistry:
    """Construct, populate, and freeze the isolated /mcp/docs ToolRegistry."""
    registry = ToolRegistry(Surface.DOCS)
    registry.register(create_docs_search_tool(client))
    registry.register(create_docs_create_tool(client))
    registry.register(create_docs_update_tool(client))
    registry.freeze()
    return registry


create_docs_registry = build_docs_registry

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Isolated /mcp/docs surface registry and knowledge tools (S11.3, KB-P4-08)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mcp.registry import Surface, ToolRegistry
from mcp.surfaces.docs.link_knowledge import create_link_knowledge_tool
from mcp.surfaces.docs.manage_stickies import create_manage_stickies_tool
from mcp.surfaces.docs.promote_sticky_to_doc import create_promote_sticky_to_doc_tool
from mcp.surfaces.docs.read_doc import create_read_doc_tool
from mcp.surfaces.docs.search_knowledge import create_search_knowledge_tool
from mcp.surfaces.docs.upsert_doc import create_upsert_doc_tool

if TYPE_CHECKING:
    from mcp.internal_client import KanbanApiClient

__all__ = [
    "DOCS_TOOL_NAMES",
    "build_docs_registry",
    "create_docs_registry",
]

DOCS_TOOL_NAMES: Final[tuple[str, ...]] = (
    "search_knowledge",
    "read_doc",
    "upsert_doc",
    "manage_stickies",
    "promote_sticky_to_doc",
    "link_knowledge",
)


def build_docs_registry(client: KanbanApiClient | None = None) -> ToolRegistry:
    """Construct, populate, and freeze the isolated /mcp/docs ToolRegistry."""
    registry = ToolRegistry(Surface.DOCS)
    registry.register(create_search_knowledge_tool(client))
    registry.register(create_read_doc_tool(client))
    registry.register(create_upsert_doc_tool(client))
    registry.register(create_manage_stickies_tool(client))
    registry.register(create_promote_sticky_to_doc_tool(client))
    registry.register(create_link_knowledge_tool(client))
    registry.freeze()
    return registry


create_docs_registry = build_docs_registry


# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Agent surface tool registry and definitions (KB-P4-04)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.agent.read_ticket import READ_TICKET_SCHEMA, read_ticket
from mcp.surfaces.agent.search_tickets import SEARCH_TICKETS_SCHEMA, search_tickets

__all__ = [
    "READ_TICKET_SCHEMA",
    "SEARCH_TICKETS_SCHEMA",
    "create_agent_registry",
    "read_ticket",
    "search_tickets",
]


def create_agent_registry() -> ToolRegistry:
    """Construct and return the agent surface ToolRegistry with official tools."""
    registry = ToolRegistry(Surface.AGENT)
    registry.register(
        ToolSpec(
            name="search_tickets",
            description="Search tickets by text and structured filters under caller permissions.",
            input_schema=SEARCH_TICKETS_SCHEMA,
            surface=Surface.AGENT,
            handler=search_tickets,
        )
    )
    registry.register(
        ToolSpec(
            name="read_ticket",
            description=(
                "Read ticket details, markdown, links, comments, and activity at chosen LOD."
            ),
            input_schema=READ_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=read_ticket,
        )
    )
    return registry

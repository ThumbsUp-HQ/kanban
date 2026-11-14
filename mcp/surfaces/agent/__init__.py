# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Agent surface tool registry and definitions (KB-P4-04, KB-P4-05)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.agent.create_ticket import CREATE_TICKET_SCHEMA, create_ticket
from mcp.surfaces.agent.read_ticket import READ_TICKET_SCHEMA, read_ticket
from mcp.surfaces.agent.search_tickets import SEARCH_TICKETS_SCHEMA, search_tickets
from mcp.surfaces.agent.update_ticket import UPDATE_TICKET_SCHEMA, update_ticket

__all__ = [
    "CREATE_TICKET_SCHEMA",
    "READ_TICKET_SCHEMA",
    "SEARCH_TICKETS_SCHEMA",
    "UPDATE_TICKET_SCHEMA",
    "create_agent_registry",
    "create_ticket",
    "read_ticket",
    "search_tickets",
    "update_ticket",
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
    registry.register(
        ToolSpec(
            name="create_ticket",
            description=(
                "Create a single ticket or parent-child issue tree atomically with human names."
            ),
            input_schema=CREATE_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=create_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="update_ticket",
            description=(
                "Apply an atomic patch or append description under description ETag concurrency."
            ),
            input_schema=UPDATE_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=update_ticket,
        )
    )
    return registry

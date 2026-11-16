# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Agent surface tool registry and definitions (KB-P4-04, KB-P4-05, KB-P4-06)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.agent.add_comment import ADD_COMMENT_SCHEMA, add_comment
from mcp.surfaces.agent.begin_work import BEGIN_WORK_SCHEMA, begin_work
from mcp.surfaces.agent.complete_work import COMPLETE_WORK_SCHEMA, complete_work
from mcp.surfaces.agent.create_ticket import CREATE_TICKET_SCHEMA, create_ticket
from mcp.surfaces.agent.link_objects import LINK_OBJECTS_SCHEMA, link_objects
from mcp.surfaces.agent.read_ticket import READ_TICKET_SCHEMA, read_ticket
from mcp.surfaces.agent.search_tickets import SEARCH_TICKETS_SCHEMA, search_tickets
from mcp.surfaces.agent.transition_ticket import (
    TRANSITION_TICKET_SCHEMA,
    transition_ticket,
)
from mcp.surfaces.agent.update_ticket import UPDATE_TICKET_SCHEMA, update_ticket

__all__ = [
    "ADD_COMMENT_SCHEMA",
    "BEGIN_WORK_SCHEMA",
    "COMPLETE_WORK_SCHEMA",
    "CREATE_TICKET_SCHEMA",
    "LINK_OBJECTS_SCHEMA",
    "READ_TICKET_SCHEMA",
    "SEARCH_TICKETS_SCHEMA",
    "TRANSITION_TICKET_SCHEMA",
    "UPDATE_TICKET_SCHEMA",
    "add_comment",
    "begin_work",
    "complete_work",
    "create_agent_registry",
    "create_ticket",
    "link_objects",
    "read_ticket",
    "search_tickets",
    "transition_ticket",
    "update_ticket",
]


def create_agent_registry() -> ToolRegistry:
    """Construct frozen ToolRegistry containing official tools for /mcp/agent."""
    registry = ToolRegistry(Surface.AGENT)
    registry.register(
        ToolSpec(
            name="search_tickets",
            description="Search tickets.",
            input_schema=SEARCH_TICKETS_SCHEMA,
            surface=Surface.AGENT,
            handler=search_tickets,
        )
    )
    registry.register(
        ToolSpec(
            name="read_ticket",
            description="Read ticket.",
            input_schema=READ_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=read_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="create_ticket",
            description="Create ticket.",
            input_schema=CREATE_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=create_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="update_ticket",
            description="Update ticket.",
            input_schema=UPDATE_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=update_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="begin_work",
            description="Begin work.",
            input_schema=BEGIN_WORK_SCHEMA,
            surface=Surface.AGENT,
            handler=begin_work,
        )
    )
    registry.register(
        ToolSpec(
            name="transition_ticket",
            description="Transition ticket.",
            input_schema=TRANSITION_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=transition_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="complete_work",
            description="Complete work.",
            input_schema=COMPLETE_WORK_SCHEMA,
            surface=Surface.AGENT,
            handler=complete_work,
        )
    )
    registry.register(
        ToolSpec(
            name="add_comment",
            description="Add comment.",
            input_schema=ADD_COMMENT_SCHEMA,
            surface=Surface.AGENT,
            handler=add_comment,
        )
    )
    registry.register(
        ToolSpec(
            name="link_objects",
            description="Link objects.",
            input_schema=LINK_OBJECTS_SCHEMA,
            surface=Surface.AGENT,
            handler=link_objects,
        )
    )
    return registry

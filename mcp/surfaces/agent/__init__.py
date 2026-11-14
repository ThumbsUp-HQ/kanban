# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Agent surface tool registry and definitions (KB-P4-04)."""

from __future__ import annotations

from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.surfaces.agent.begin_work import BEGIN_WORK_SCHEMA, begin_work
from mcp.surfaces.agent.complete_work import COMPLETE_WORK_SCHEMA, complete_work
from mcp.surfaces.agent.read_ticket import READ_TICKET_SCHEMA, read_ticket
from mcp.surfaces.agent.search_tickets import SEARCH_TICKETS_SCHEMA, search_tickets
from mcp.surfaces.agent.transition_ticket import (
    TRANSITION_TICKET_SCHEMA,
    transition_ticket,
)

__all__ = [
    "BEGIN_WORK_SCHEMA",
    "COMPLETE_WORK_SCHEMA",
    "READ_TICKET_SCHEMA",
    "SEARCH_TICKETS_SCHEMA",
    "TRANSITION_TICKET_SCHEMA",
    "begin_work",
    "complete_work",
    "create_agent_registry",
    "read_ticket",
    "search_tickets",
    "transition_ticket",
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
            name="begin_work",
            description=(
                "Atomically assign caller, bind cycle, move to started state, and post plan."
            ),
            input_schema=BEGIN_WORK_SCHEMA,
            surface=Surface.AGENT,
            handler=begin_work,
        )
    )
    registry.register(
        ToolSpec(
            name="transition_ticket",
            description="Transition ticket to intermediate workflow state under gate evaluation.",
            input_schema=TRANSITION_TICKET_SCHEMA,
            surface=Surface.AGENT,
            handler=transition_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="complete_work",
            description="Verify blockers and QA gate, transition to completed, and log proof.",
            input_schema=COMPLETE_WORK_SCHEMA,
            surface=Surface.AGENT,
            handler=complete_work,
        )
    )
    return registry

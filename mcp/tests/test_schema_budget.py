# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Token budget audit for /mcp/agent tools schema (S11.1, KB-P4-07)."""

from __future__ import annotations

import json
from typing import Any

from mcp.surfaces.agent import create_agent_registry

EXPECTED_AGENT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_tickets",
        "read_ticket",
        "create_ticket",
        "update_ticket",
        "begin_work",
        "transition_ticket",
        "complete_work",
        "add_comment",
        "link_objects",
    }
)
MAX_AGENT_SCHEMA_BUDGET_TOKENS: int = 2200


def test_schema_budget_agent_tools() -> None:
    """Assert /mcp/agent tools/list JSON conforms to <= 2,200 token budget."""
    registry = create_agent_registry()
    specs = registry.list_specs()
    tool_names = {s.name for s in specs}

    assert tool_names == EXPECTED_AGENT_TOOL_NAMES, f"Mismatch in agent tools: {tool_names}"

    tools_list: list[dict[str, Any]] = [
        {
            "name": s.name,
            "description": s.description,
            "inputSchema": s.input_schema,
        }
        for s in specs
    ]
    raw_json = json.dumps({"tools": tools_list})
    approx_tokens = len(raw_json) // 4

    assert approx_tokens <= MAX_AGENT_SCHEMA_BUDGET_TOKENS, (
        f"Token budget exceeded: {approx_tokens} > {MAX_AGENT_SCHEMA_BUDGET_TOKENS}"
    )

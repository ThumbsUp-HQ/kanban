# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001
"""Feature unit and security tests for dynamic MCP capability stripping on untrusted taint (KAN-70).

Covers:
  1. tools/list before untrusted read contains all registered tools (read and mutating).
  2. Reading untrusted content propagates X-Kanban-Untrusted-Taint: 1 and marks session tainted.
  3. tools/list after untrusted read strips all mutating and linking tools.
  4. Attempting to call mutating tools pre-dispatch is rejected with UNTRUSTED_CONTENT_TAINT_ACTIVE.
  5. initialize advertises tools.listChanged = True for dynamic clients.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from starlette.responses import JSONResponse

from mcp.protocol import (
    InMemorySessionStore,
    McpProtocolHandler,
)
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings


def _create_mock_registry() -> ToolRegistry:
    """Create isolated registry containing standard agent tools."""
    registry = ToolRegistry(Surface.AGENT)

    async def _mock_read_ticket(args: dict[str, Any]) -> dict[str, Any]:
        ident = args.get("identifier", "KAN-1")
        if ident == "UNTRUSTED-1":
            return {
                "key": "KAN-99",
                "summary": "Untrusted Bug Report",
                "provenance_tier": "imported",
                "is_untrusted_content": True,
                "description_markdown": "Hostile prompt injection payload",
            }
        return {
            "key": "KAN-1",
            "summary": "Clean internal task",
            "provenance_tier": "trusted_member",
            "is_untrusted_content": False,
            "description_markdown": "Normal developer description",
        }

    async def _mock_create_ticket(args: dict[str, Any]) -> dict[str, Any]:
        return {"key": "KAN-100", "summary": args.get("summary", "")}

    async def _mock_update_ticket(args: dict[str, Any]) -> dict[str, Any]:
        return {"key": args.get("ticket_id", "KAN-1"), "summary": "updated"}

    async def _mock_search_tickets(_args: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"key": "KAN-1", "summary": "Search result"}]

    registry.register(
        ToolSpec(
            name="read_ticket",
            description="Read a ticket",
            input_schema={
                "type": "object",
                "properties": {"identifier": {"type": "string"}},
                "required": ["identifier"],
            },
            surface=Surface.AGENT,
            handler=_mock_read_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="create_ticket",
            description="Create a ticket",
            input_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
            surface=Surface.AGENT,
            handler=_mock_create_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="update_ticket",
            description="Update a ticket",
            input_schema={
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
            surface=Surface.AGENT,
            handler=_mock_update_ticket,
        )
    )
    registry.register(
        ToolSpec(
            name="search_tickets",
            description="Search tickets",
            input_schema={"type": "object"},
            surface=Surface.AGENT,
            handler=_mock_search_tickets,
        )
    )
    return registry


@pytest.fixture
def protocol_handler() -> McpProtocolHandler:
    """Fixture providing protocol handler with memory session store."""
    registry = _create_mock_registry()
    store = InMemorySessionStore()
    settings = McpSettings()
    return McpProtocolHandler(
        surface=Surface.AGENT,
        registry=registry,
        session_store=store,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_initialize_advertises_list_changed_capability(
    protocol_handler: McpProtocolHandler,
) -> None:
    """Initialize advertises tools.listChanged = True for dynamic MCP clients."""
    resp = await protocol_handler._handle_initialize(
        req_id=1,
        params={"clientInfo": {"name": "dynamic-agent-runner", "version": "2.0"}},
    )
    assert isinstance(resp, JSONResponse)
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["result"]["capabilities"]["tools"]["listChanged"] is True


@pytest.mark.asyncio
async def test_dynamic_taint_stripping_lifecycle(
    protocol_handler: McpProtocolHandler,
) -> None:
    """Test full capability stripping lifecycle upon reading untrusted content."""
    # 1. Initialize session
    session = protocol_handler.session_store.create_session(Surface.AGENT)
    session_id = session.session_id

    # 2. tools/list before untrusted read contains all registered tools
    list_resp_1 = protocol_handler._handle_tools_list(req_id=10, session_id=session_id)
    data_1 = json.loads(bytes(list_resp_1.body).decode("utf-8"))
    tools_1 = {t["name"] for t in data_1["result"]["tools"]}
    assert "create_ticket" in tools_1
    assert "update_ticket" in tools_1
    assert "read_ticket" in tools_1
    assert "search_tickets" in tools_1

    # 3. Read trusted ticket KAN-1 -> session remains untainted
    trusted_call = await protocol_handler._handle_tools_call(
        req_id=20,
        params={"name": "read_ticket", "arguments": {"identifier": "KAN-1"}},
        session_id=session_id,
    )
    assert trusted_call.headers.get("X-Kanban-Untrusted-Taint") is None
    sess_trusted = protocol_handler.session_store.get_session(session_id)
    assert sess_trusted is not None
    assert sess_trusted.tainted_by_untrusted is False

    # 4. Read untrusted ticket UNTRUSTED-1 -> triggers untrusted taint propagation
    untrusted_call = await protocol_handler._handle_tools_call(
        req_id=30,
        params={"name": "read_ticket", "arguments": {"identifier": "UNTRUSTED-1"}},
        session_id=session_id,
    )
    assert untrusted_call.headers.get("X-Kanban-Untrusted-Taint") == "1"
    sess_tainted = protocol_handler.session_store.get_session(session_id)
    assert sess_tainted is not None
    assert sess_tainted.tainted_by_untrusted is True

    # 5. tools/list after untrusted read strips mutating tools
    list_resp_2 = protocol_handler._handle_tools_list(req_id=40, session_id=session_id)
    data_2 = json.loads(bytes(list_resp_2.body).decode("utf-8"))
    tools_2 = {t["name"] for t in data_2["result"]["tools"]}
    assert "create_ticket" not in tools_2
    assert "update_ticket" not in tools_2
    assert "read_ticket" in tools_2
    assert "search_tickets" in tools_2

    # 6. Attempting to call mutating tool create_ticket is blocked pre-dispatch
    blocked_call = await protocol_handler._handle_tools_call(
        req_id=50,
        params={"name": "create_ticket", "arguments": {"summary": "Hostile task"}},
        session_id=session_id,
    )
    assert blocked_call.headers.get("X-Kanban-Untrusted-Taint") == "1"
    data_blocked = json.loads(bytes(blocked_call.body).decode("utf-8"))
    assert data_blocked["result"]["isError"] is True
    error_yaml = data_blocked["result"]["content"][0]["text"]
    parsed_err = yaml.safe_load(error_yaml)
    assert parsed_err["code"] == "UNTRUSTED_CONTENT_TAINT_ACTIVE"
    assert "blocked: session tainted by untrusted content" in parsed_err["message"]
    assert "human" in parsed_err["hint"].lower()

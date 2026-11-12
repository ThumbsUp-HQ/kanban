# Copyright 2026 Kanban Platform Contributors
"""Tests for isolated tool registry security and cross-surface isolation."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from mcp.errors import KbMcpError, McpErrorCode
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings


def test_case_2_registry_surface_validation_and_freeze() -> None:
    """Test Case 2: Registering mismatched surface raises ValueError; freeze raises RuntimeError."""
    agent_reg = ToolRegistry(Surface.AGENT)

    # 1. Mismatched surface raises ValueError
    admin_spec = ToolSpec(
        name="ping_admin",
        description="Admin tool",
        input_schema={"type": "object"},
        surface=Surface.ADMIN,
        handler=lambda _args: {"ok": True},
    )
    with pytest.raises(ValueError, match="does not match registry surface"):
        agent_reg.register(admin_spec)

    # 2. Matching surface registers successfully
    agent_spec = ToolSpec(
        name="custom_agent_tool",
        description="Agent tool",
        input_schema={"type": "object"},
        surface=Surface.AGENT,
        handler=lambda _args: {"result": "success"},
    )
    agent_reg.register(agent_spec)
    assert agent_reg.get("custom_agent_tool") is not None
    assert len(agent_reg.list_specs()) == 1

    # 3. Freeze prevents further registration
    agent_reg.freeze()
    assert agent_reg.is_frozen

    another_spec = ToolSpec(
        name="another_tool",
        description="Another",
        input_schema={"type": "object"},
        surface=Surface.AGENT,
        handler=lambda _args: {},
    )
    with pytest.raises(RuntimeError, match="registry for surface 'agent' is frozen"):
        agent_reg.register(another_spec)


@pytest.mark.asyncio
async def test_case_2_cross_surface_tool_call_isolation(
    mcp_client: httpx.AsyncClient,
) -> None:
    """Test Case 2: Cross-surface tool invocation returns isError: true with code NOT_FOUND."""
    # 1. Initialize on /mcp/agent
    init_agent = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert init_agent.status_code == 200
    sess_agent = init_agent.headers["mcp-session-id"]

    # 2. Invoke ping_admin on /mcp/agent -> NOT_FOUND
    call_admin_on_agent = await mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "ping_admin", "arguments": {}},
        },
        headers={"mcp-session-id": sess_agent},
    )
    assert call_admin_on_agent.status_code == 200
    res = call_admin_on_agent.json()["result"]
    assert res["isError"] is True
    err_text = res["content"][0]["text"]
    assert "code: NOT_FOUND" in err_text
    assert "ping_admin" in err_text

    # 3. Invoke ping_docs on /mcp/agent -> NOT_FOUND
    call_docs_on_agent = await mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ping_docs", "arguments": {}},
        },
        headers={"mcp-session-id": sess_agent},
    )
    assert call_docs_on_agent.status_code == 200
    res_docs = call_docs_on_agent.json()["result"]
    assert res_docs["isError"] is True
    assert "code: NOT_FOUND" in res_docs["content"][0]["text"]


@pytest.mark.asyncio
async def test_tool_handler_error_scenarios(
    mcp_client: httpx.AsyncClient,
) -> None:
    """Verify tool handlers raising KbMcpError or unexpected exception format cleanly."""
    # Obtain session
    init_resp = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert init_resp.headers["mcp-session-id"]

    settings = McpSettings(mode="standalone_inprocess")

    # Add custom tool to docs registry before freeze in a standalone app
    docs_reg = ToolRegistry(Surface.DOCS)

    def _failing_handler(_args: object) -> None:
        raise KbMcpError(McpErrorCode.VALIDATION_FAILED, "Invalid project ID", hint="Check ID")

    def _crash_handler(_args: object) -> None:
        msg = "Unexpected database failure"
        raise RuntimeError(msg)

    docs_reg.register(
        ToolSpec(
            name="fail_tool",
            description="Fails with KbMcpError",
            input_schema={"type": "object"},
            surface=Surface.DOCS,
            handler=_failing_handler,
        )
    )
    docs_reg.register(
        ToolSpec(
            name="crash_tool",
            description="Crashes with RuntimeError",
            input_schema={"type": "object"},
            surface=Surface.DOCS,
            handler=_crash_handler,
        )
    )
    docs_reg.freeze()

    store = InMemorySessionStore()
    sess = store.create_session(Surface.DOCS)
    handler = McpProtocolHandler(Surface.DOCS, docs_reg, store, settings)

    app = Starlette(routes=[Route("/mcp/docs", handler.handle_request, methods=["POST"])])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test KbMcpError handling
        resp_fail = await client.post(
            "/mcp/docs",
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "fail_tool", "arguments": {}},
            },
            headers={"mcp-session-id": sess.session_id},
        )
        assert resp_fail.status_code == 200
        res_fail = resp_fail.json()["result"]
        assert res_fail["isError"] is True
        text_fail = res_fail["content"][0]["text"]
        assert "code: VALIDATION_FAILED" in text_fail
        assert "Invalid project ID" in text_fail
        assert "hint: Check ID" in text_fail

        # Test unexpected exception handling -> INTERNAL error code
        resp_crash = await client.post(
            "/mcp/docs",
            json={
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "crash_tool", "arguments": {}},
            },
            headers={"mcp-session-id": sess.session_id},
        )
        assert resp_crash.status_code == 200
        res_crash = resp_crash.json()["result"]
        assert res_crash["isError"] is True
        text_crash = res_crash["content"][0]["text"]
        assert "code: INTERNAL" in text_crash
        assert "Unexpected database failure" in text_crash

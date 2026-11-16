# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for hierarchical MCP key narrowing and CIDR gating (KB-P4-14)."""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx
import pytest

from mcp.app import create_mcp_app
from mcp.auth import McpAuthMiddleware
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolRegistry, ToolSpec, create_placeholder_tool
from mcp.settings import McpSettings


def _generate_test_mcp_key(surface: Surface) -> str:
    prefix = {"agent": "kb_agt_", "docs": "kb_doc_", "admin": "kb_adm_"}[surface.value]
    rand = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    return f"{prefix}{rand}"


def _build_test_app(
    surface: Surface,
    mock_transport: httpx.AsyncBaseTransport,
) -> tuple[httpx.AsyncClient, ToolRegistry]:
    """Construct an MCP application with placeholder and test tools."""
    reg = ToolRegistry(surface)
    reg.register(create_placeholder_tool(surface))

    async def _write_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "created"}

    reg.register(
        ToolSpec(
            name="test_agent_write",
            description="Tool requiring agent:write scope",
            surface=surface,
            input_schema={"type": "object"},
            handler=_write_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    kanban_client = KanbanApiClient(settings, transport=mock_transport)

    kwargs: dict[str, Any] = {"settings": settings}
    if surface == Surface.AGENT:
        kwargs["agent_registry"] = reg
    elif surface == Surface.DOCS:
        kwargs["docs_registry"] = reg
    else:
        kwargs["admin_registry"] = reg

    base_app = create_mcp_app(**kwargs)
    middleware = McpAuthMiddleware(
        base_app,
        surface=surface,
        internal_client=kanban_client,
        settings=settings,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=middleware),
        base_url="http://testserver",
    )
    return client, reg


@pytest.mark.asyncio
async def test_disabled_tools_omitted_from_tools_list_and_blocked_on_call() -> None:
    """Verify disabled_tools are omitted in tools/list and rejected with INSUFFICIENT_SCOPE."""
    token = _generate_test_mcp_key(Surface.AGENT)

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read", "agent:write"],
                "scope_tier": "personal_user",
                "disabled_tools": ["ping_agent"],
                "allowed_tools": None,
            },
        )

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _reg = _build_test_app(Surface.AGENT, mock_transport)

    async with client:
        # Initialize
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        # tools/list should omit ping_agent because it is in disabled_tools
        list_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "Mcp-Session-Id": session_id},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert list_resp.status_code == 200
        tools = list_resp.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "ping_agent" not in tool_names
        assert "test_agent_write" in tool_names

        # tools/call for ping_agent should fail with INSUFFICIENT_SCOPE
        call_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "Mcp-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ping_agent", "arguments": {}},
            },
        )
        assert call_resp.status_code == 200
        data = call_resp.json()
        assert data.get("result", {}).get("isError") is True
        error_content = data["result"]["content"][0]["text"]
        assert "disabled_tools" in error_content or "disabled" in error_content


@pytest.mark.asyncio
async def test_allowed_tools_narrowing() -> None:
    """Verify allowed_tools narrows tools/list and rejects unlisted tools."""
    token = _generate_test_mcp_key(Surface.AGENT)

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read", "agent:write"],
                "scope_tier": "project",
                "disabled_tools": [],
                "allowed_tools": ["ping_agent"],
            },
        )

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _reg = _build_test_app(Surface.AGENT, mock_transport)

    async with client:
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        # tools/list should only include ping_agent
        list_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "Mcp-Session-Id": session_id},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert list_resp.status_code == 200
        tools = list_resp.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert tool_names == ["ping_agent"]

        # Calling test_agent_write should fail because it is not in allowed_tools
        call_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}", "Mcp-Session-Id": session_id},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "test_agent_write", "arguments": {}},
            },
        )
        assert call_resp.status_code == 200
        data = call_resp.json()
        assert data.get("result", {}).get("isError") is True
        error_content = data["result"]["content"][0]["text"]
        assert "allowed_tools" in error_content


@pytest.mark.asyncio
async def test_cidr_filtering_in_mcp_auth_middleware() -> None:
    """Verify McpAuthMiddleware enforces allowed_cidrs from introspection."""
    token = _generate_test_mcp_key(Surface.AGENT)

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read", "agent:write"],
                "scope_tier": "personal_user",
                "allowed_cidrs": ["192.168.1.0/24"],
            },
        )

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _reg = _build_test_app(Surface.AGENT, mock_transport)

    async with client:
        # 1. Denied IP
        denied_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "10.0.0.1",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert denied_resp.status_code == 403
        denied_json = denied_resp.json()
        assert denied_json["error"] == "KEY_CIDR_DENIED"

        # 2. Allowed IP
        allowed_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "192.168.1.55",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert allowed_resp.status_code == 200

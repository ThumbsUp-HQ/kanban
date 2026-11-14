# Copyright 2026 Kanban Platform Contributors
"""Tests for MCP Streamable HTTP JSON-RPC 2.0 protocol and session management."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from mcp.app import create_mcp_app
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings
from mcp.tests.conftest import record_http_exchange

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_case_1_positive_initialize_and_tools_list(
    mcp_client: httpx.AsyncClient,
) -> None:
    """Test Case 1: Positive initialize and tools/list on all 3 mounts."""
    surfaces = [
        (
            "/mcp/agent",
            "kanban-mcp-agent",
            ["search_tickets", "read_ticket", "create_ticket", "update_ticket"],
            "search_tickets",
            {"gate_status": "approved"},
            "gate history available",
        ),
        (
            "/mcp/docs",
            "kanban-mcp-docs",
            ["ping_docs"],
            "ping_docs",
            {},
            "ok: true",
        ),
        (
            "/mcp/admin",
            "kanban-mcp-admin",
            ["configure_workspace", "manage_auth_cards"],
            "configure_workspace",
            {"action": "help"},
            "configure_workspace",
        ),
    ]

    for (
        mount,
        expected_server_name,
        expected_tools,
        call_tool,
        call_args,
        expected_substr,
    ) in surfaces:
        # 1. Initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        resp = await mcp_client.post(mount, json=init_req)
        assert resp.status_code == 200
        session_id = resp.headers.get("mcp-session-id")
        assert session_id is not None
        assert len(session_id) > 20

        data = resp.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        result = data["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["serverInfo"]["name"] == expected_server_name
        assert result["capabilities"]["tools"]["listChanged"] is False

        headers = {"mcp-session-id": session_id}

        # 2. Ping
        ping_resp = await mcp_client.post(
            mount,
            json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
            headers=headers,
        )
        assert ping_resp.status_code == 200
        assert ping_resp.json()["result"] == {}

        # 3. Notification initialized
        notif_resp = await mcp_client.post(
            mount,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
        )
        assert notif_resp.status_code == 204

        # 4. Tools list
        tools_resp = await mcp_client.post(
            mount,
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            headers=headers,
        )
        assert tools_resp.status_code == 200
        tools_data = tools_resp.json()["result"]["tools"]
        tool_names = [t["name"] for t in tools_data]
        assert tool_names == expected_tools

        # 5. Tools call
        call_resp = await mcp_client.post(
            mount,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": call_tool, "arguments": call_args},
            },
            headers=headers,
        )
        assert call_resp.status_code == 200
        call_data = call_resp.json()["result"]
        assert call_data["isError"] is False
        assert len(call_data["content"]) == 1
        assert expected_substr in call_data["content"][0]["text"]

    # 6. Cross-surface tool call in test_protocol: call ping_admin on /mcp/agent -> NOT_FOUND
    # Also pass bearer and subject tokens with kb_ prefix to record verified transcript redaction
    agent_init = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 10, "method": "initialize"},
    )
    agent_sess = agent_init.headers["mcp-session-id"]
    token_val = "kb_agt_" + "abcdef0123456789" * 2
    subject_val = "kb_usr_" + "9876543210fedcba" * 2

    cross_call = await mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "ping_admin", "arguments": {}},
        },
        headers={
            "mcp-session-id": agent_sess,
            "authorization": f"Bearer {token_val}",
            "x-kb-subject-token": subject_val,
        },
    )
    assert cross_call.status_code == 200
    cross_data = cross_call.json()
    assert cross_data["result"]["isError"] is True
    assert "NOT_FOUND" in cross_data["result"]["content"][0]["text"]
    expected_msg = "Tool 'ping_admin' not found on surface 'agent'"
    assert expected_msg in cross_data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_case_3_protocol_negatives(
    mcp_client: httpx.AsyncClient,
) -> None:
    """Test Case 3: Protocol error codes and HTTP negative constraints."""
    mount = "/mcp/agent"

    # 1. Initialize to obtain a valid session id
    init_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    session_id = init_resp.headers["mcp-session-id"]
    valid_headers = {"mcp-session-id": session_id}

    # 2. JSON-RPC batch array rejected with 400
    batch_resp = await mcp_client.post(
        mount,
        json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
        headers=valid_headers,
    )
    assert batch_resp.status_code == 400
    assert "batching is not supported" in batch_resp.text

    # 3. Oversized payload > 1,048,576 bytes -> 413
    huge_data = "x" * (1_048_576 + 10)
    huge_resp = await mcp_client.post(
        mount,
        content=huge_data.encode("utf-8"),
        headers={"content-type": "application/json", **valid_headers},
    )
    assert huge_resp.status_code == 413

    # 4. Unknown method -> -32601
    unknown_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 2, "method": "nonexistent_method"},
        headers=valid_headers,
    )
    assert unknown_resp.status_code == 200
    assert unknown_resp.json()["error"]["code"] == -32601

    # 5. Bad JSON -> -32700
    bad_json_resp = await mcp_client.post(
        mount,
        content=b"{bad json",
        headers={"content-type": "application/json", **valid_headers},
    )
    assert bad_json_resp.status_code == 400
    assert bad_json_resp.json()["error"]["code"] == -32700

    # 6. Unsupported MCP-Protocol-Version -> 400
    bad_proto_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 3, "method": "ping"},
        headers={"mcp-protocol-version": "2024-11-05", **valid_headers},
    )
    assert bad_proto_resp.status_code == 400

    # 7. GET -> 405
    get_resp = await mcp_client.get(mount)
    assert get_resp.status_code == 405

    # 8. Unknown session id -> 404
    missing_session_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 4, "method": "ping"},
        headers={"mcp-session-id": "unknown_session_id_12345"},
    )
    assert missing_session_resp.status_code == 404

    # 9. Missing session id on non-initialize -> 404
    no_session_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 5, "method": "ping"},
    )
    assert no_session_resp.status_code == 404

    # 10. DELETE session terminates it -> 204, then reuse -> 404
    del_resp = await mcp_client.delete(mount, headers=valid_headers)
    assert del_resp.status_code == 204

    reuse_resp = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 6, "method": "ping"},
        headers=valid_headers,
    )
    assert reuse_resp.status_code == 404

    # 11. DELETE unknown session -> 404
    del_unknown_resp = await mcp_client.delete(
        mount,
        headers={"mcp-session-id": "unknown_session_id"},
    )
    assert del_unknown_resp.status_code == 404

    # 12. Invalid params for tools/call -> -32602
    init2 = await mcp_client.post(mount, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    sess2 = init2.headers["mcp-session-id"]

    inv_params = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": "not_dict"},
        headers={"mcp-session-id": sess2},
    )
    assert inv_params.json()["error"]["code"] == -32602

    inv_args = await mcp_client.post(
        mount,
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "ping_agent", "arguments": "str"},
        },
        headers={"mcp-session-id": sess2},
    )
    assert inv_args.json()["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_disallowed_origin_rejection() -> None:
    """Verify Origin header validation against allowed_origins (DNS-rebinding defense)."""
    settings = McpSettings(
        mode="standalone_inprocess",
        allowed_origins=["https://allowed.kanban.local"],
    )
    app = create_mcp_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Allowed origin passes
        resp_ok = await client.post(
            "/mcp/agent",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            headers={"origin": "https://allowed.kanban.local"},
        )
        assert resp_ok.status_code == 200

        # 2. Disallowed origin rejected with 403
        resp_bad = await client.post(
            "/mcp/agent",
            json={"jsonrpc": "2.0", "id": 2, "method": "initialize"},
            headers={"origin": "https://attacker.evil.com"},
        )
        assert resp_bad.status_code == 403


def test_case_4_session_store_capacity_and_idle_ttl() -> None:
    """Test Case 4: Eviction on 10,001st session and idle TTL expiry."""
    current_time = 1000.0

    def _clock() -> float:
        return current_time

    # 1. Max sessions capacity eviction
    store = InMemorySessionStore(ttl_s=3600.0, max_sessions=3, clock=_clock)
    s1 = store.create_session(Surface.AGENT)
    s2 = store.create_session(Surface.DOCS)
    s3 = store.create_session(Surface.ADMIN)

    assert store.get_session(s1.session_id) is not None
    assert store.get_session(s2.session_id) is not None
    assert store.get_session(s3.session_id) is not None

    # Creating 4th session evicts s1 (oldest)
    s4 = store.create_session(Surface.AGENT)
    assert store.get_session(s1.session_id) is None
    assert store.get_session(s2.session_id) is not None
    assert store.get_session(s3.session_id) is not None
    assert store.get_session(s4.session_id) is not None

    # 2. Idle TTL expiry at 3600s + 1
    # Advance time by 3600s -> still valid
    current_time += 3600.0
    assert store.get_session(s4.session_id) is not None

    # Advance time by 3601s -> expired
    current_time += 3601.0
    assert store.get_session(s4.session_id) is None


def test_case_6_transcript_redaction_unit(tmp_path: Path) -> None:
    """Test Case 6: Redaction asserts Authorization and Subject tokens are redacted."""
    transcript_file = tmp_path / "transcript.txt"

    token_secret = "kb_agt_" + "1234567890abcdef" * 2 + "12345678901"
    subject_secret = "kb_usr_" + "fedcba0987654321" * 2 + "09876543210"

    req = httpx.Request(
        "POST",
        "http://test/mcp/agent",
        headers={
            "authorization": f"Bearer {token_secret}",
            "x-kb-subject-token": subject_secret,
        },
        content=json.dumps({"token": token_secret}).encode("utf-8"),
    )
    resp = httpx.Response(
        200,
        headers={"x-token": token_secret},
        content=json.dumps({"echo": token_secret}).encode("utf-8"),
    )

    record_http_exchange(transcript_file, req, resp)

    content = transcript_file.read_text(encoding="utf-8")
    assert "kb_agt_***REDACTED***" in content
    assert "kb_usr_***REDACTED***" in content
    assert token_secret not in content
    assert subject_secret not in content


@pytest.mark.asyncio
async def test_protocol_additional_edge_cases(mcp_client: httpx.AsyncClient) -> None:
    """Verify PUT rejection, invalid method types, notifications, and non-dict tool results."""
    mount = "/mcp/agent"

    # 1. PUT -> 405
    put_resp = await mcp_client.put(mount)
    assert put_resp.status_code == 405

    # 2. Non-dict request -> -32600
    invalid_rpc = await mcp_client.post(
        mount,
        content=b'"just a string"',
        headers={"content-type": "application/json"},
    )
    assert invalid_rpc.status_code == 400
    assert invalid_rpc.json()["error"]["code"] == -32600

    # 3. Missing or non-str method -> -32600
    no_method = await mcp_client.post(mount, json={"jsonrpc": "2.0", "id": 1, "method": 123})
    assert no_method.status_code == 400
    assert no_method.json()["error"]["code"] == -32600

    # 4. Initialize to obtain session
    init_res = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    sess_id = init_res.headers["mcp-session-id"]

    # 5. Generic notification with id=None
    notif_res = await mcp_client.post(
        mount,
        json={"jsonrpc": "2.0", "method": "custom/notification"},
        headers={"mcp-session-id": sess_id},
    )
    assert notif_res.status_code == 204

    # 6. Store touch_session
    store = InMemorySessionStore()
    sess = store.create_session(Surface.AGENT)
    store.touch_session(sess.session_id)
    assert store.get_session(sess.session_id) is not None

    # 7. create_mcp_app default invocation
    app_default = create_mcp_app()
    assert app_default.state.settings is not None


@pytest.mark.asyncio
async def test_method_not_allowed_and_tool_result_types(mcp_client: httpx.AsyncClient) -> None:
    """Verify HTTP 405 on unsupported methods and various tool return types."""
    # GET returns 405 from protocol handler
    resp_get = await mcp_client.get("/mcp/agent")
    assert resp_get.status_code == 405
    assert "POST, DELETE" in resp_get.headers.get("allow", "")

    registry = ToolRegistry(Surface.AGENT)

    async def async_str_handler(_args: dict[str, Any]) -> str:
        return "raw string result"

    def awaitable_handler(_args: dict[str, Any]) -> object:
        async def _inner() -> str:
            return "awaitable result"

        return _inner()

    def int_handler(_args: dict[str, Any]) -> int:
        return 42

    registry.register(
        ToolSpec(
            name="async_str_tool",
            description="desc",
            input_schema={},
            handler=async_str_handler,
            surface=Surface.AGENT,
        )
    )
    registry.register(
        ToolSpec(
            name="awaitable_tool",
            description="desc",
            input_schema={},
            handler=awaitable_handler,
            surface=Surface.AGENT,
        )
    )
    registry.register(
        ToolSpec(
            name="int_tool",
            description="desc",
            input_schema={},
            handler=int_handler,
            surface=Surface.AGENT,
        )
    )
    registry.freeze()

    store = InMemorySessionStore()
    handler = McpProtocolHandler(
        Surface.AGENT,
        registry,
        store,
        McpSettings(mode="standalone_inprocess"),
    )
    app = Starlette(
        routes=[Route("/mcp/agent", handler.handle_request, methods=["POST", "DELETE", "PUT"])],
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # PUT reaches handler.handle_request line 180
        resp_put = await client.put("/mcp/agent")
        assert resp_put.status_code == 405
        assert resp_put.headers.get("allow") == "POST, DELETE"

        # Initialize
        init_res = await client.post(
            "/mcp/agent",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        sess_id = init_res.headers["mcp-session-id"]

        # Call async_str_tool
        call_res1 = await client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "async_str_tool", "arguments": {}},
            },
            headers={"mcp-session-id": sess_id},
        )
        assert call_res1.status_code == 200
        assert call_res1.json()["result"]["content"][0]["text"] == "raw string result"

        # Call awaitable_tool
        call_res2 = await client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "awaitable_tool", "arguments": {}},
            },
            headers={"mcp-session-id": sess_id},
        )
        assert call_res2.status_code == 200
        assert call_res2.json()["result"]["content"][0]["text"] == "awaitable result"

        # Call int_tool
        call_res3 = await client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "int_tool", "arguments": {}},
            },
            headers={"mcp-session-id": sess_id},
        )
        assert call_res3.status_code == 200
        assert call_res3.json()["result"]["content"][0]["text"] == "42"

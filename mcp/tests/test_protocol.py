# Copyright 2026 Kanban Platform Contributors
"""Tests for MCP Streamable HTTP JSON-RPC 2.0 protocol and session management."""

# ruff: noqa: SLF001, PLR0915, PLC0415, S106, FBT003
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from mcp.app import create_mcp_app
from mcp.errors import KbMcpError, McpErrorCode
from mcp.protocol import (
    InMemorySessionStore,
    McpProtocolHandler,
    _format_flag_val,
    _matches_schema_type,
)
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings
from mcp.surfaces.agent.create_ticket import _validate_tree_node
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
            [
                "search_tickets",
                "read_ticket",
                "create_ticket",
                "update_ticket",
                "begin_work",
                "transition_ticket",
                "complete_work",
                "add_comment",
                "link_objects",
            ],
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
            ["ping_admin"],
            "ping_admin",
            {},
            "ok: true",
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
        if mount == "/mcp/agent":
            assert result["instructions"] == (
                "Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' "
                "(or project='help' on create_ticket) for live project options. "
                "On create_ticket, set 'project' and optional 'parent' on the root object only; "
                "omit 'project' and 'parent' inside children[]."
            )
        else:
            assert "instructions" not in result

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


@pytest.mark.asyncio
async def test_protocol_helper_branches(mcp_client: httpx.AsyncClient) -> None:
    """Verify protocol helper branches for flag formatting, schema types, and session touch."""
    # 1. _format_flag_val fallback for custom object
    custom_obj = object()
    formatted = _format_flag_val(custom_obj)
    assert str(custom_obj) in formatted

    # 2. _matches_schema_type fallback for unknown type
    assert _matches_schema_type("val", "unknown_type_specifier") is True

    # 3. session_store touch nonexistent session
    store = InMemorySessionStore()
    store.touch_session("nonexistent_session_id")
    assert store.get_session("nonexistent_session_id") is None

    # 4. Initialize with raw non-bearer authorization header
    init_req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = await mcp_client.post(
        "/mcp/agent",
        json=init_req,
        headers={"Authorization": "RawApiKeyWithoutBearerPrefix"},
    )
    assert resp.status_code == 200

    # 5. _validate_tree_node with depth > _MAX_DEPTH
    with pytest.raises(KbMcpError) as exc:
        _validate_tree_node({"summary": "X"}, is_root=False, depth=7)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED
    assert "Tree depth (7)" in exc.value.message


@pytest.mark.asyncio
async def test_protocol_advanced_dispatch_branches(mcp_client: httpx.AsyncClient) -> None:
    """Verify delete session, ping, unknown method, header parsing, and session deletion."""
    # 1. Initialize to get session
    init_res = await mcp_client.post(
        "/mcp/agent",
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
    assert init_res.status_code == 200
    sid = init_res.headers["mcp-session-id"]

    # 2. Ping via tools dispatch
    ping_res = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        headers={"mcp-session-id": sid},
    )
    assert ping_res.status_code == 200
    assert ping_res.json()["result"] == {}

    # 3. Unknown method
    unknown_res = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 3, "method": "unknown/method"},
        headers={"mcp-session-id": sid},
    )
    assert unknown_res.status_code == 200
    assert unknown_res.json()["error"]["code"] == -32601

    # 4. Header X-KB-Scopes and X-KB-AAL-Level invalid int
    call_headers = {
        "mcp-session-id": sid,
        "X-KB-Scopes": "agent:read,agent:write",
        "X-KB-AAL-Level": "invalid_number",
    }
    call_res = await mcp_client.post(
        "/mcp/agent",
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        headers=call_headers,
    )
    assert call_res.status_code == 200

    # 5. Delete session
    del_res = await mcp_client.request(
        "DELETE",
        "/mcp/agent",
        headers={"mcp-session-id": sid},
    )
    assert del_res.status_code == 204

    # Delete non-existent session
    del_nf = await mcp_client.request(
        "DELETE",
        "/mcp/agent",
        headers={"mcp-session-id": "missing_sid"},
    )
    assert del_nf.status_code == 404

    # Delete without header
    del_no_header = await mcp_client.request("DELETE", "/mcp/agent")
    assert del_no_header.status_code == 404


@pytest.mark.asyncio
async def test_protocol_schema_validation_special_branches() -> None:
    """Verify state and custom_fields hints, nullable types, and pattern checks."""
    registry = ToolRegistry(Surface.AGENT)
    handler = McpProtocolHandler(Surface.AGENT, registry, InMemorySessionStore(), McpSettings())

    spec_update = ToolSpec(
        name="update_ticket",
        description="Update ticket.",
        input_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "additionalProperties": False,
        },
        surface=Surface.AGENT,
        handler=lambda _args: {},
    )

    # 1. state hint in update_ticket
    with pytest.raises(KbMcpError) as exc_st:
        handler._validate_tool_arguments_schema(spec_update, {"state": "Todo"})
    assert exc_st.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_st.value.hint == "use transition_ticket"

    # 2. custom_fields hint in update_ticket
    with pytest.raises(KbMcpError) as exc_cf:
        handler._validate_tool_arguments_schema(spec_update, {"custom_fields": {}})
    assert exc_cf.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_cf.value.hint == "custom fields arrive in Phase 5"

    # 3. Nullable type
    spec_nullable = ToolSpec(
        name="test_tool",
        description="Test.",
        input_schema={"type": "object", "properties": {"val": {"type": ["string", "null"]}}},
        surface=Surface.AGENT,
        handler=lambda _args: {},
    )
    handler._validate_tool_arguments_schema(spec_nullable, {"val": None})

    # 4. Enum non-string
    spec_enum = ToolSpec(
        name="test_enum",
        description="Test.",
        input_schema={"type": "object", "properties": {"choice": {"enum": [10, 20]}}},
        surface=Surface.AGENT,
        handler=lambda _args: {},
    )
    with pytest.raises(KbMcpError) as exc_enum:
        handler._validate_tool_arguments_schema(spec_enum, {"choice": 99})
    assert exc_enum.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_protocol_initialize_and_admin_scope_branches() -> None:
    """Verify initialize request parsing, Bearer extraction, and admin write enforcement."""
    from starlette.requests import Request

    registry = ToolRegistry(Surface.ADMIN)
    admin_tool = ToolSpec(
        name="manage_something",
        description="Admin tool",
        input_schema={"type": "object", "properties": {"action": {"type": "string"}}},
        surface=Surface.ADMIN,
        handler=lambda _args: "done",
    )
    registry.register(admin_tool)
    handler = McpProtocolHandler(Surface.ADMIN, registry, InMemorySessionStore(), McpSettings())

    # 1. _handle_initialize with request=None
    res_none = await handler._handle_initialize(1, request=None)
    assert res_none.status_code == 200

    # 2. _handle_initialize with Bearer header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/admin",
        "headers": [(b"authorization", b"Bearer test_bearer_token")],
    }
    req_bearer = Request(scope)
    res_bearer = await handler._handle_initialize(2, request=req_bearer)
    assert res_bearer.status_code == 200

    # 3. Notification dispatch (req_id is None)
    res_notif = await handler._dispatch_method("any_method", None, {})
    assert res_notif.status_code == 204

    # 4. Admin write scope check failure
    res_admin = await handler._dispatch_method(
        "tools/call",
        3,
        {"name": "manage_something", "arguments": {"action": "create_item"}},
        caller_scopes=frozenset({"admin:read"}),
    )
    assert res_admin.status_code == 200
    assert "admin:write" in str(res_admin.body)

    # 5. Admin destructive scope check failure (caller has admin:write only)
    res_destr = await handler._dispatch_method(
        "tools/call",
        4,
        {"name": "manage_something", "arguments": {"action": "delete_item"}},
        caller_scopes=frozenset({"admin:write"}),
    )
    assert res_destr.status_code == 200
    assert "admin:destructive" in str(res_destr.body)

    # 6. Admin write allowed
    res_allowed = await handler._dispatch_method(
        "tools/call",
        5,
        {"name": "manage_something", "arguments": {"action": "create_item"}},
        caller_scopes=frozenset({"admin:write"}),
    )
    assert res_allowed.status_code == 200
    assert "done" in str(res_allowed.body)

    # 7. Connection scope error on initialize
    scope_bad = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/admin",
        "headers": [(b"x-project-key", b"invalid space key")],
    }
    req_bad = Request(scope_bad)
    res_bad = await handler._handle_initialize(6, request=req_bad)
    assert res_bad.status_code == 400

    # 8. x-kb-aal-level header with auth_context
    from dataclasses import replace

    from mcp.auth import McpAuthContext

    scope_auth = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/admin",
        "headers": [
            (b"x-kb-aal-level", b"1"),
            (b"mcp-session-id", b"sess_dummy"),
        ],
    }
    req_auth = Request(scope_auth)
    req_auth.state.mcp_auth = McpAuthContext(
        token="tok",
        token_sha256=b"hash",
        surface=Surface.ADMIN,
        scopes=frozenset({"admin:read"}),
        aal_level=2,
    )
    session = handler.session_store.create_session(Surface.ADMIN)
    req_auth.headers._list = [
        (b"x-kb-aal-level", b"1"),
        (b"mcp-session-id", session.session_id.encode()),
    ]
    await handler._process_valid_payload({"jsonrpc": "2.0", "id": 7, "method": "ping"}, req_auth)

    # 9. Ephemeral introspect branches
    docs_registry = ToolRegistry(Surface.DOCS)
    docs_registry.register(ToolSpec("search", "Search tool", {}, Surface.DOCS, lambda _args: {}))
    mock_client = MagicMock()
    mock_client.request = AsyncMock(side_effect=RuntimeError("internal err"))
    handler_eph = McpProtocolHandler(
        Surface.DOCS,
        docs_registry,
        InMemorySessionStore(),
        McpSettings(),
        internal_client=mock_client,
    )
    eph_auth = McpAuthContext(
        token="tok",
        token_sha256=b"h",
        surface=Surface.DOCS,
        scopes=frozenset(),
        aal_level=2,
        token_kind="ephemeral",
        allowed_tools=frozenset({"search"}),
    )
    res_eph_err = await handler_eph._dispatch_method(
        "tools/call", 8, {"name": "search", "arguments": {}}, auth_context=eph_auth
    )
    assert "UPSTREAM_UNAVAILABLE" in str(res_eph_err.body)

    mock_client.request = AsyncMock(
        return_value={"active": False, "reason": "EPHEMERAL_TOOL_FORBIDDEN"}
    )
    res_eph_forb = await handler_eph._dispatch_method(
        "tools/call", 9, {"name": "search", "arguments": {}}, auth_context=eph_auth
    )
    assert "EPHEMERAL_TOOL_FORBIDDEN" in str(res_eph_forb.body)

    mock_client.request = AsyncMock(
        return_value={"active": False, "reason": "TOKEN_EXPIRED_OR_REVOKED"}
    )
    res_eph_exp = await handler_eph._dispatch_method(
        "tools/call", 10, {"name": "search", "arguments": {}}, auth_context=eph_auth
    )
    assert "TOKEN_EXPIRED_OR_REVOKED" in str(res_eph_exp.body)

    mock_client.request = AsyncMock(return_value={"active": False, "reason": "OTHER"})
    res_eph_oth = await handler_eph._dispatch_method(
        "tools/call", 11, {"name": "search", "arguments": {}}, auth_context=eph_auth
    )
    assert "UNAUTHENTICATED" in str(res_eph_oth.body)

    eph_read_doc = replace(eph_auth, allowed_tools=frozenset({"read_doc"}))
    mock_client.request = AsyncMock(return_value={"active": True})
    await handler_eph._dispatch_method(
        "tools/call", 12, {"name": "search", "arguments": {}}, auth_context=eph_read_doc
    )
    eph_other = replace(eph_auth, allowed_tools=frozenset({"other"}))
    await handler_eph._dispatch_method(
        "tools/call", 13, {"name": "search", "arguments": {}}, auth_context=eph_other
    )


@pytest.mark.asyncio
async def test_case_13_protocol_coverage_exhaustion() -> None:
    """Exhaustively cover remaining protocol formatting, validation, and error branches."""
    from starlette.requests import Request

    from mcp.auth import McpAuthContext
    from mcp.scoping import ConnectionScope, ScopeMode

    # 1. _format_flag_val and _matches_schema_type branches
    assert _format_flag_val(True) == "true"
    assert _format_flag_val(False) == "false"
    assert _format_flag_val(42) == "42"
    assert _format_flag_val(3.14) == "3.14"
    assert _format_flag_val([1, "x"]) == "'[1, \"x\"]'"
    assert _format_flag_val({"key": "val"}) == '\'{"key": "val"}\''
    dummy_obj = object()
    assert _format_flag_val(dummy_obj) == f'"{dummy_obj}"'

    assert _matches_schema_type(10, "integer") is True
    assert _matches_schema_type(True, "integer") is False
    assert _matches_schema_type(True, "boolean") is True
    assert _matches_schema_type("str", "boolean") is False
    assert _matches_schema_type({"a": 1}, "object") is True
    assert _matches_schema_type([1], "object") is False
    assert _matches_schema_type("foo", "unsupported_type") is True

    # 2. Session token & scope fingerprint mismatch
    registry = ToolRegistry(Surface.AGENT)
    registry.register(
        ToolSpec(
            "ping", "Ping tool", {"type": "object"}, Surface.AGENT, lambda _args: {"pong": True}
        )
    )
    registry.register(
        ToolSpec(
            "read_ticket",
            "Read ticket",
            {"type": "object"},
            Surface.AGENT,
            lambda _args: {"ticket": "1"},
        )
    )
    store = InMemorySessionStore()
    handler = McpProtocolHandler(Surface.AGENT, registry, store, McpSettings())

    session = store.create_session(
        Surface.AGENT,
        token_sha256=b"token_a",
        scope_fingerprint=b"scope_a",
    )

    # Request with mismatched token
    req_scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/agent",
        "headers": [
            (b"mcp-session-id", session.session_id.encode()),
            (b"x-kb-subject-token", b"Bearer different_token"),
        ],
    }
    req_token_mismatch = Request(req_scope)
    req_token_mismatch.state.mcp_token_sha256 = b"token_b"
    req_token_mismatch.state.connection_scope = ConnectionScope(
        mode=ScopeMode.WORKSPACE, workspace_slug="ws"
    )
    res_mismatch = await handler._process_valid_payload(
        {"jsonrpc": "2.0", "id": 1, "method": "ping"}, req_token_mismatch
    )
    assert res_mismatch.status_code == 404
    assert b"Session bound to different token" in res_mismatch.body

    # Request with matching token but mismatched scope fingerprint
    req_scope_mismatch = Request(req_scope)
    req_scope_mismatch.state.mcp_token_sha256 = b"token_a"
    req_scope_mismatch.state.connection_scope = ConnectionScope(
        mode=ScopeMode.WORKSPACE, workspace_slug="other_ws"
    )
    res_scope_mismatch = await handler._process_valid_payload(
        {"jsonrpc": "2.0", "id": 2, "method": "ping"}, req_scope_mismatch
    )
    assert res_scope_mismatch.status_code == 404
    assert b"Session bound to different scope" in res_scope_mismatch.body

    # 3. _handle_tools_list with ephemeral tokens and allowed/disabled tools
    eph_auth = McpAuthContext(
        token="tok",
        token_sha256=b"h",
        surface=Surface.AGENT,
        scopes=frozenset(),
        aal_level=2,
        token_kind="ephemeral",
        allowed_tools=frozenset({"read_ticket"}),
    )
    res_tools_eph = handler._handle_tools_list(1, auth_context=eph_auth)
    assert res_tools_eph.status_code == 200

    disabled_auth = McpAuthContext(
        token="tok",
        token_sha256=b"h",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        aal_level=2,
        allowed_tools=frozenset({"ping"}),
        disabled_tools=frozenset({"ping"}),
    )
    res_tools_dis = handler._handle_tools_list(2, auth_context=disabled_auth)
    assert res_tools_dis.status_code == 200
    tools_dis = json.loads(bytes(res_tools_dis.body).decode())["result"]["tools"]
    assert len(tools_dis) == 0

    # 4. _handle_tool_call with disabled_tools & allowed_tools narrowing
    res_dis_call = await handler._dispatch_method(
        "tools/call", 3, {"name": "ping", "arguments": {}}, auth_context=disabled_auth
    )
    assert res_dis_call.status_code == 200
    assert "disabled for this API key" in bytes(res_dis_call.body).decode()

    narrowed_auth = McpAuthContext(
        token="tok",
        token_sha256=b"h",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        aal_level=2,
        allowed_tools=frozenset({"other_tool"}),
    )
    res_narrow_call = await handler._dispatch_method(
        "tools/call", 4, {"name": "ping", "arguments": {}}, auth_context=narrowed_auth
    )
    assert res_narrow_call.status_code == 200
    assert "not in allowed_tools" in bytes(res_narrow_call.body).decode()

    # 5. Ephemeral budget exceeded branch
    mock_client = MagicMock()
    mock_client.request = AsyncMock(
        return_value={
            "active": False,
            "reason": "EPHEMERAL_CALL_BUDGET_EXCEEDED",
            "calls_used": 25,
            "max_calls": 25,
        }
    )
    handler_budget = McpProtocolHandler(
        Surface.AGENT,
        registry,
        store,
        McpSettings(),
        internal_client=mock_client,
    )
    res_budget = await handler_budget._dispatch_method(
        "tools/call", 5, {"name": "read_ticket", "arguments": {}}, auth_context=eph_auth
    )
    assert res_budget.status_code == 200
    assert "EPHEMERAL_CALL_BUDGET_EXCEEDED" in bytes(res_budget.body).decode()

    # 6. Caller lacks required scopes branch
    reg_scoped = ToolRegistry(Surface.AGENT)
    reg_scoped.register(
        ToolSpec(
            "create_ticket", "Create ticket", {"type": "object"}, Surface.AGENT, lambda _args: {}
        )
    )
    handler_scoped = McpProtocolHandler(Surface.AGENT, reg_scoped, store, McpSettings())
    res_no_scope = await handler_scoped._dispatch_method(
        "tools/call",
        6,
        {"name": "create_ticket", "arguments": {}},
        caller_scopes=frozenset({"agent:read"}),
    )
    assert res_no_scope.status_code == 200
    assert "Caller lacks required scope(s)" in bytes(res_no_scope.body).decode()

    # 7. _handle_jit_help project argument
    mock_help_client = MagicMock()
    mock_help_client.request = AsyncMock(return_value={"options": []})
    handler_help = McpProtocolHandler(
        Surface.AGENT,
        reg_scoped,
        store,
        McpSettings(),
        internal_client=mock_help_client,
    )
    res_help = await handler_help._handle_jit_help(7, "create_ticket", {"project": "KAN"})
    assert res_help.status_code == 200
    assert "create_ticket" in bytes(res_help.body).decode()

    # 8. Schema validation branches: unknown parameter, missing required, type mismatch, pattern
    spec_schema = ToolSpec(
        "sample",
        "Sample tool",
        {
            "type": "object",
            "required": ["mandatory"],
            "properties": {
                "mandatory": {"type": "string"},
                "summary": {"type": "string"},
                "int_val": {"type": "integer"},
                "bool_val": {"type": "boolean"},
                "arr_val": {"type": "array"},
                "obj_val": {"type": "object"},
                "nullable_str": {"type": ["string", "null"]},
                "etag": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "bad_prop": "not_a_dict",  # non-dict prop_schema (line 1268)
            },
            "additionalProperties": False,
        },
        Surface.AGENT,
        lambda _args: {},
    )
    # Unknown parameter without close match
    with pytest.raises(KbMcpError) as exc_unknown:
        handler._validate_tool_arguments_schema(
            spec_schema, {"completely_unknown_xyz": 1, "mandatory": "ok"}
        )
    assert exc_unknown.value.code == McpErrorCode.VALIDATION_FAILED
    assert "Unknown parameter 'completely_unknown_xyz'" in exc_unknown.value.message

    # Unknown parameter with close match (did_you_mean)
    with pytest.raises(KbMcpError) as exc_typo:
        handler._validate_tool_arguments_schema(spec_schema, {"sumary": "typo", "mandatory": "ok"})
    assert exc_typo.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_typo.value.fix_hint is not None
    assert "Did you mean 'summary'?" in exc_typo.value.fix_hint

    # Missing required parameter
    with pytest.raises(KbMcpError) as exc_missing:
        handler._validate_tool_arguments_schema(spec_schema, {"summary": "no mandatory"})
    assert exc_missing.value.code == McpErrorCode.VALIDATION_FAILED
    assert "Missing required parameter 'mandatory'" in exc_missing.value.message

    # Type mismatch branches (integer, boolean, array, object)
    with pytest.raises(KbMcpError) as exc_type_int:
        handler._validate_tool_arguments_schema(
            spec_schema, {"mandatory": "ok", "int_val": "not_int"}
        )
    assert exc_type_int.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_type_bool:
        handler._validate_tool_arguments_schema(
            spec_schema, {"mandatory": "ok", "bool_val": "not_bool"}
        )
    assert exc_type_bool.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_type_arr:
        handler._validate_tool_arguments_schema(
            spec_schema, {"mandatory": "ok", "arr_val": "not_arr"}
        )
    assert exc_type_arr.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_type_obj:
        handler._validate_tool_arguments_schema(
            spec_schema, {"mandatory": "ok", "obj_val": "not_obj"}
        )
    assert exc_type_obj.value.code == McpErrorCode.VALIDATION_FAILED

    # Pattern mismatch branch
    with pytest.raises(KbMcpError) as exc_pat:
        handler._validate_tool_arguments_schema(
            spec_schema, {"mandatory": "ok", "etag": "short_not_64"}
        )
    assert exc_pat.value.code == McpErrorCode.VALIDATION_FAILED
    assert exc_pat.value.fix_hint is not None
    assert "64-character SHA-256 hex ETag" in exc_pat.value.fix_hint

    # Nullable property with None and bad_prop non-dict
    handler._validate_tool_arguments_schema(
        spec_schema, {"mandatory": "ok", "nullable_str": None, "bad_prop": 123}
    )

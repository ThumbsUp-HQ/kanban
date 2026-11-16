# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/agent tool: search_tickets (KB-P4-04)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from mcp.errors import KbMcpError, McpErrorCode
from mcp.surfaces.agent.search_tickets import _validate_search_arguments, search_tickets

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


async def _call_search_tickets(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke search_tickets via JSON-RPC 2.0 tools/call."""
    active_session_id = session_id
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/agent",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-agent", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_tickets",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data["result"])


@pytest.mark.asyncio
async def test_case_1_positive_search_tickets(agent_test_env: AgentTestEnv) -> None:
    """Case 1: search_tickets returns fixture-expected keys in rank order at summary LOD."""
    env = agent_test_env

    # 1. Initialize MCP session
    init_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            },
        },
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers["mcp-session-id"]

    # 2. Call search_tickets with filters
    res = await _call_search_tickets(
        env,
        {
            "query": "OIDC",
            "project": "KAN",
            "states": ["In Progress"],
            "assignees": ["me"],
            "lod": "summary",
        },
        subject_token=env.token_adam,
        session_id=session_id,
    )
    assert res["isError"] is False
    content_text = res["content"][0]["text"]
    parsed = yaml.safe_load(content_text)

    assert parsed["mode"] == "lexical"
    assert parsed["total"] == 1
    assert len(parsed["items"]) == 1
    item = parsed["items"][0]
    assert item["key"] == "KAN-142"
    assert item["summary"] == "Harden Multi-Card OIDC & LDAPS Auth Studio"
    assert item["state"] == "In Progress"
    assert item["priority"] == "urgent"
    assert item["assignees"] == ["@adam"]
    # summary LOD must NOT contain description_markdown
    assert "description_markdown" not in item


@pytest.mark.asyncio
async def test_case_2_rls_security_search_tickets(agent_test_env: AgentTestEnv) -> None:
    """Case 2: RLS security: search_tickets excludes restricted SEC issues."""
    env = agent_test_env

    # Search for 'secret' under Adam (who has NO access to SEC)
    res_adam = await _call_search_tickets(
        env,
        {"query": "secret"},
        subject_token=env.token_adam,
    )
    assert res_adam["isError"] is False
    parsed_adam = yaml.safe_load(res_adam["content"][0]["text"])
    assert parsed_adam["total"] == 0
    assert len(parsed_adam.get("items", [])) == 0

    # Search under Admin (who HAS access to SEC) -> should find SEC-1
    res_admin = await _call_search_tickets(
        env,
        {"query": "secret"},
        subject_token=env.token_admin,
    )
    assert res_admin["isError"] is False
    parsed_admin = yaml.safe_load(res_admin["content"][0]["text"])
    assert parsed_admin["total"] == 1
    assert parsed_admin["items"][0]["key"] == "SEC-1"

    # Agent key whose principal has no AgentGrant on KAN sees total: 0
    res_no_grant = await _call_search_tickets(
        env,
        {"query": "OIDC", "project": "KAN"},
        subject_token=env.token_no_grant,
    )
    assert res_no_grant["isError"] is False
    parsed_no_grant = yaml.safe_load(res_no_grant["content"][0]["text"])
    assert parsed_no_grant["total"] == 0
    assert len(parsed_no_grant.get("items", [])) == 0


@pytest.mark.asyncio
async def test_case_3_boundary_validation_and_pagination(agent_test_env: AgentTestEnv) -> None:
    """Case 3: Boundary validation and cursor pagination over 30 items."""
    env = agent_test_env

    # 1. limit=51 -> VALIDATION_FAILED
    res_lim51 = await _call_search_tickets(env, {"limit": 51})
    assert res_lim51["isError"] is True
    err1 = yaml.safe_load(res_lim51["content"][0]["text"])
    assert err1["error"]["code"] == "VALIDATION_FAILED"
    assert "limit must be an integer between 1 and 50" in err1["error"]["message"]

    # 2. query of 501 chars -> VALIDATION_FAILED
    res_long_q = await _call_search_tickets(env, {"query": "a" * 501})
    assert res_long_q["isError"] is True
    err2 = yaml.safe_load(res_long_q["content"][0]["text"])
    assert err2["error"]["code"] == "VALIDATION_FAILED"

    # 3. unknown key foo -> VALIDATION_FAILED
    res_unknown = await _call_search_tickets(env, {"foo": "bar"})
    assert res_unknown["isError"] is True
    err3 = yaml.safe_load(res_unknown["content"][0]["text"])
    assert err3["error"]["code"] == "VALIDATION_FAILED"
    assert "Unknown parameter 'foo'" in err3["error"]["message"]

    # 4. limit=50 with 30 matches returns 30 and NO next_cursor
    res_lim50 = await _call_search_tickets(
        env,
        {"limit": 50},
        subject_token=env.token_adam,
    )
    assert res_lim50["isError"] is False
    parsed_50 = yaml.safe_load(res_lim50["content"][0]["text"])
    assert parsed_50["total"] == 30
    assert len(parsed_50["items"]) == 30
    assert "next_cursor" not in parsed_50

    # 5. Cursor pagination over 30 items at limit=20 returns 20 then 10
    res_p1 = await _call_search_tickets(
        env,
        {"limit": 20},
        subject_token=env.token_adam,
    )
    assert res_p1["isError"] is False
    parsed_p1 = yaml.safe_load(res_p1["content"][0]["text"])
    assert len(parsed_p1["items"]) == 20
    assert "next_cursor" in parsed_p1
    cursor1 = parsed_p1["next_cursor"]
    assert cursor1

    res_p2 = await _call_search_tickets(
        env,
        {"limit": 20, "cursor": cursor1},
        subject_token=env.token_adam,
    )
    assert res_p2["isError"] is False
    parsed_p2 = yaml.safe_load(res_p2["content"][0]["text"])
    assert len(parsed_p2["items"]) == 10
    assert "next_cursor" not in parsed_p2


@pytest.mark.asyncio
async def test_case_4_lod_hybrid_mode_and_gate_status(agent_test_env: AgentTestEnv) -> None:
    """Case 4: LOD verification, mode='hybrid', and gate_status filtering."""
    env = agent_test_env

    # 1. summary output contains no description_markdown
    res_sum = await _call_search_tickets(
        env,
        {"query": "OIDC", "lod": "summary"},
        subject_token=env.token_adam,
    )
    parsed_sum = yaml.safe_load(res_sum["content"][0]["text"])
    for it in parsed_sum["items"]:
        assert "description_markdown" not in it

    # 2. standard LOD contains description_markdown
    res_std = await _call_search_tickets(
        env,
        {"query": "OIDC", "lod": "standard"},
        subject_token=env.token_adam,
    )
    parsed_std = yaml.safe_load(res_std["content"][0]["text"])
    assert len(parsed_std["items"]) == 2
    kan_142_item = next(it for it in parsed_std["items"] if it["key"] == "KAN-142")
    assert "description_markdown" in kan_142_item
    assert "# OIDC Architecture" in kan_142_item["description_markdown"]

    # 3. mode="hybrid" returns mode: lexical
    res_hyb = await _call_search_tickets(
        env,
        {"query": "OIDC", "mode": "hybrid"},
        subject_token=env.token_adam,
    )
    parsed_hyb = yaml.safe_load(res_hyb["content"][0]["text"])
    assert parsed_hyb["mode"] == "lexical"

    # 4. gate_status="pending" returns only issues with non-null pending_transition_exec_id
    res_gate = await _call_search_tickets(
        env,
        {"gate_status": "pending"},
        subject_token=env.token_adam,
    )
    parsed_gate = yaml.safe_load(res_gate["content"][0]["text"])
    assert parsed_gate["total"] == 1
    assert len(parsed_gate["items"]) == 1
    assert parsed_gate["items"][0]["key"] == "KAN-3"

    # 5. gate_status="approved" or "rejected" returns empty with note
    res_approved = await _call_search_tickets(
        env,
        {"gate_status": "approved"},
        subject_token=env.token_adam,
    )
    parsed_app = yaml.safe_load(res_approved["content"][0]["text"])
    assert parsed_app["total"] == 0
    assert parsed_app.get("items", []) == []
    assert parsed_app["note"] == "gate history available in Phase 5"


@pytest.mark.asyncio
async def test_search_tickets_additional_validations() -> None:
    """Verify detailed validation paths in search_tickets."""
    # Context None
    with pytest.raises(KbMcpError) as exc_ctx:
        await search_tickets({"query": "test"})
    assert exc_ctx.value.code == McpErrorCode.INTERNAL

    # Non-string query
    with pytest.raises(KbMcpError) as exc_q:
        _validate_search_arguments({"query": 123})
    assert exc_q.value.code == McpErrorCode.VALIDATION_FAILED

    # Non-string cursor
    with pytest.raises(KbMcpError) as exc_cur:
        _validate_search_arguments({"cursor": 123})
    assert exc_cur.value.code == McpErrorCode.VALIDATION_FAILED

    # Overly long cursor
    with pytest.raises(KbMcpError) as exc_long_cur:
        _validate_search_arguments({"cursor": "c" * 201})
    assert exc_long_cur.value.code == McpErrorCode.VALIDATION_FAILED

    # Invalid lod (full is rejected for search_tickets)
    with pytest.raises(KbMcpError) as exc_lod:
        _validate_search_arguments({"lod": "full"})
    assert exc_lod.value.code == McpErrorCode.VALIDATION_FAILED

    # Invalid mode
    with pytest.raises(KbMcpError) as exc_mode:
        _validate_search_arguments({"mode": "semantic"})
    assert exc_mode.value.code == McpErrorCode.VALIDATION_FAILED

    # Invalid gate_status
    with pytest.raises(KbMcpError) as exc_gate:
        _validate_search_arguments({"gate_status": "other"})
    assert exc_gate.value.code == McpErrorCode.VALIDATION_FAILED

    # Non-list states
    with pytest.raises(KbMcpError) as exc_states_list:
        _validate_search_arguments({"states": "Todo"})
    assert exc_states_list.value.code == McpErrorCode.VALIDATION_FAILED

    # Too many items in array
    with pytest.raises(KbMcpError) as exc_too_many:
        _validate_search_arguments({"states": [f"s{i}" for i in range(21)]})
    assert exc_too_many.value.code == McpErrorCode.VALIDATION_FAILED

    # Non-string item in array
    with pytest.raises(KbMcpError) as exc_non_str_item:
        _validate_search_arguments({"states": [123]})
    assert exc_non_str_item.value.code == McpErrorCode.VALIDATION_FAILED

    # Non-bool blocked
    with pytest.raises(KbMcpError) as exc_blocked:
        _validate_search_arguments({"blocked": "yes"})
    assert exc_blocked.value.code == McpErrorCode.VALIDATION_FAILED

    # Bool limit
    with pytest.raises(KbMcpError) as exc_bool_lim:
        _validate_search_arguments({"limit": True})
    assert exc_bool_lim.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_tools_list_agent_surface(agent_test_env: AgentTestEnv) -> None:
    """Verify tools/list on /mcp/agent returns exactly search_tickets and read_ticket."""
    env = agent_test_env
    init_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-agent", "version": "1.0"},
            },
        },
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers["mcp-session-id"]

    list_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        headers={"mcp-session-id": session_id},
    )
    assert list_resp.status_code == 200
    res_data = list_resp.json()
    assert res_data["jsonrpc"] == "2.0"
    tool_names = [t["name"] for t in res_data["result"]["tools"]]
    assert tool_names == [
        "search_tickets",
        "read_ticket",
        "create_ticket",
        "update_ticket",
        "begin_work",
        "transition_ticket",
        "complete_work",
        "add_comment",
        "link_objects",
    ]

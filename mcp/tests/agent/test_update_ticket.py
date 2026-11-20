# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLC0415, S106, ANN401
"""Feature unit tests for /mcp/agent tool: update_ticket (KB-P4-05)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
import yaml

from mcp.app import create_mcp_app
from mcp.auth import SCOPE_REQUIREMENTS, McpAuthMiddleware
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface
from mcp.settings import McpSettings
from mcp.surfaces.agent.update_ticket import update_ticket

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


async def _call_update_ticket(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke update_ticket via JSON-RPC 2.0 tools/call."""
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
            "name": "update_ticket",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data["result"])


async def _call_read_ticket(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
) -> dict[str, Any]:
    """Read ticket and obtain etag/details."""
    headers: dict[str, str] = {}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token
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
        headers=headers,
    )
    sid = init_resp.headers["mcp-session-id"]
    headers["mcp-session-id"] = sid

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "read_ticket",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    res = resp.json()["result"]
    assert res["isError"] is False
    return cast("dict[str, Any]", yaml.safe_load(res["content"][0]["text"]))


@pytest.mark.asyncio
async def test_case_1_positive_append(agent_test_env: AgentTestEnv) -> None:
    r"""Case 1: Positive append adds text after \n\n and returns a new etag."""
    env = agent_test_env

    # 1. Read existing ticket KAN-142 to obtain current ETag and description
    ticket_before = await _call_read_ticket(
        env,
        {"identifier": "KAN-142", "lod": "full"},
        subject_token=env.token_adam,
    )
    old_etag = ticket_before["etag"]
    old_desc = ticket_before["description_markdown"]

    append_text = "Appended security hardening specification notes."

    # 2. Update ticket in append mode
    update_res = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "description_markdown": append_text,
            "description_mode": "append",
            "if_match": old_etag,
        },
        subject_token=env.token_adam,
    )
    assert update_res["isError"] is False
    parsed_update = yaml.safe_load(update_res["content"][0]["text"])

    assert parsed_update["key"] == "KAN-142"
    assert "description_markdown" in parsed_update["changed"]
    new_etag = parsed_update["etag"]
    assert new_etag != old_etag
    assert len(new_etag) == 64

    # 3. Verify description in DB via read_ticket
    ticket_after = await _call_read_ticket(
        env,
        {"identifier": "KAN-142", "lod": "full"},
        subject_token=env.token_adam,
    )
    expected_desc = f"{old_desc}\n\n{append_text}"
    assert ticket_after["description_markdown"] == expected_desc
    assert ticket_after["etag"] == new_etag


@pytest.mark.asyncio
async def test_case_2_concurrency_stale_etag(agent_test_env: AgentTestEnv) -> None:
    """Case 2: Stale if_match after human edit -> CONFLICT_ETAG and description unchanged."""
    env = agent_test_env

    # 1. Read ticket KAN-150 to get initial etag
    t_init = await _call_read_ticket(
        env,
        {"identifier": "KAN-150", "lod": "full"},
        subject_token=env.token_adam,
    )
    stale_etag = t_init["etag"]
    original_desc = t_init["description_markdown"]

    # 2. Simulate human edit: update description directly via API
    interim_update = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-150",
            "description_markdown": "Human editor updated this description.",
            "description_mode": "replace",
            "if_match": stale_etag,
        },
        subject_token=env.token_adam,
    )
    assert interim_update["isError"] is False
    fresh_etag = yaml.safe_load(interim_update["content"][0]["text"])["etag"]
    assert fresh_etag != stale_etag

    # 3. Attempt update with stale_etag
    conflict_res = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-150",
            "description_markdown": "Conflicting background update.",
            "description_mode": "append",
            "if_match": stale_etag,
        },
        subject_token=env.token_adam,
    )
    assert conflict_res["isError"] is True
    err_parsed = yaml.safe_load(conflict_res["content"][0]["text"])
    assert err_parsed["error"]["code"] == "CONFLICT_ETAG"
    assert fresh_etag in str(err_parsed["error"]["hint"])

    # 4. Verify description remains as human edited, not overwritten
    t_final = await _call_read_ticket(
        env,
        {"identifier": "KAN-150", "lod": "full"},
        subject_token=env.token_adam,
    )
    assert t_final["description_markdown"] == "Human editor updated this description."
    assert t_final["description_markdown"] != original_desc


@pytest.mark.asyncio
async def test_case_3_boundary_validations(agent_test_env: AgentTestEnv) -> None:
    """Case 3: State changes, custom fields, date order, and byte limits rejected."""
    env = agent_test_env

    # 1. State changes rejected with hint: use transition_ticket
    res_state = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "state": "Done"},
        subject_token=env.token_adam,
    )
    assert res_state["isError"] is True
    err_state = yaml.safe_load(res_state["content"][0]["text"])
    assert err_state["error"]["code"] == "VALIDATION_FAILED"
    assert "use transition_ticket" in str(err_state["error"]["hint"])

    # 2. Custom fields rejected with hint: custom fields arrive in Phase 5
    res_cf = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "custom_fields": {"environment": "staging"}},
        subject_token=env.token_adam,
    )
    assert res_cf["isError"] is True
    err_cf = yaml.safe_load(res_cf["content"][0]["text"])
    assert err_cf["error"]["code"] == "VALIDATION_FAILED"
    assert "custom fields arrive in Phase 5" in str(err_cf["error"]["hint"])

    # 3. Missing if_match when description_markdown is present
    res_missing_etag = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "description_markdown": "No etag provided."},
        subject_token=env.token_adam,
    )
    assert res_missing_etag["isError"] is True
    err_no_etag = yaml.safe_load(res_missing_etag["content"][0]["text"])
    assert err_no_etag["error"]["code"] == "VALIDATION_FAILED"
    assert "provide 64-character SHA-256 hex ETag" in str(err_no_etag["error"]["hint"])

    # 4. due_date < start_date rejected
    res_dates = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "start_date": "2026-11-20",
            "due_date": "2026-11-10",
        },
        subject_token=env.token_adam,
    )
    assert res_dates["isError"] is True
    err_dates = yaml.safe_load(res_dates["content"][0]["text"])
    assert err_dates["error"]["code"] == "VALIDATION_FAILED"
    assert "due_date cannot be earlier than start_date" in err_dates["error"]["message"]

    # 5. Description appending that would reach > 1,048,576 bytes
    from sqlalchemy import text

    big_desc = "x" * 1048500
    await env.seed_session.execute(
        text("UPDATE issues SET description_markdown = :d WHERE id = :id"),
        {"d": big_desc, "id": env.issue_142_id},
    )
    await env.seed_session.commit()
    t_large = await _call_read_ticket(
        env, {"identifier": "KAN-142", "lod": "full"}, subject_token=env.token_adam
    )
    large_etag = t_large["etag"]

    res_oversize = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "description_markdown": "y" * 100,
            "description_mode": "append",
            "if_match": large_etag,
        },
        subject_token=env.token_adam,
    )
    assert res_oversize["isError"] is True
    err_oversize = yaml.safe_load(res_oversize["content"][0]["text"])
    assert err_oversize["error"]["code"] == "VALIDATION_FAILED"
    assert "exceeds maximum of 1048576 bytes" in err_oversize["error"]["message"]

    # 6. Summary > 500 characters
    res_summary = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "summary": "s" * 501},
        subject_token=env.token_adam,
    )
    assert res_summary["isError"] is True
    err_sum = yaml.safe_load(res_summary["content"][0]["text"])
    assert err_sum["error"]["code"] == "VALIDATION_FAILED"
    assert "exceeds maximum of 500" in err_sum["error"]["message"]


@pytest.mark.asyncio
async def test_case_4_assignees_add_and_remove(agent_test_env: AgentTestEnv) -> None:
    """Case 4: Add free-text and handle assignees, then remove them cleanly."""
    env = agent_test_env

    # 1. Add free-text assignee
    res_add = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "assignees_add": ["Vendor QA", "@adam"],
        },
        subject_token=env.token_adam,
    )
    assert res_add["isError"] is False
    parsed_add = yaml.safe_load(res_add["content"][0]["text"])
    assert "assignees" in parsed_add["changed"]
    assignees_list = parsed_add["assignees"]
    assert any("Vendor QA" in str(a) for a in assignees_list)

    # 2. Remove free-text assignee
    res_rem = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "assignees_remove": ["Vendor QA"],
        },
        subject_token=env.token_adam,
    )
    assert res_rem["isError"] is False
    parsed_rem = yaml.safe_load(res_rem["content"][0]["text"])
    assert "assignees" in parsed_rem["changed"]
    assignees_after = parsed_rem["assignees"]
    assert not any("Vendor QA" in str(a) for a in assignees_after)


@pytest.mark.asyncio
async def test_case_5_update_ticket_help(agent_test_env: AgentTestEnv) -> None:
    """Case 5: update_ticket(identifier='help') returns JIT progressive disclosure help."""
    env = agent_test_env

    res_help = await _call_update_ticket(env, {"identifier": "help"})
    assert res_help["isError"] is False
    parsed_help = yaml.safe_load(res_help["content"][0]["text"])
    assert parsed_help["tool"] == "update_ticket"
    assert "params" in parsed_help
    assert "identifier" in parsed_help["params"]
    assert "description_mode" in parsed_help["params"]


@pytest.mark.asyncio
async def test_case_6_scope_insufficient() -> None:
    """Case 6: Caller with agent:read only fails with INSUFFICIENT_SCOPE."""
    assert SCOPE_REQUIREMENTS["update_ticket"] == frozenset({"agent:write"})

    token_read = "kb_agt_" + "r" * 43

    async def _mock_introspect(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "token_type": "Bearer",
                "scope": "agent:read",
                "sub": "00000000-0000-0000-0000-000000000001",
                "exp": 9999999999,
                "surface": "agent",
            },
        )

    mock_transport = httpx.MockTransport(_mock_introspect)
    auth_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mock_kanban_client = KanbanApiClient(auth_settings, transport=mock_transport)
    scoped_mcp_app = create_mcp_app(auth_settings)
    mw = McpAuthMiddleware(
        scoped_mcp_app,
        surface=Surface.AGENT,
        internal_client=mock_kanban_client,
        settings=auth_settings,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mw), base_url="http://test"
    ) as auth_client:
        init_r = await auth_client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token_read}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-read", "version": "1.0"},
                },
            },
        )
        assert init_r.status_code == 200
        sid = init_r.headers["mcp-session-id"]

        call_r = await auth_client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token_read}",
                "Mcp-Session-Id": sid,
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "update_ticket",
                    "arguments": {"identifier": "KAN-142", "summary": "Read Only Agent Update"},
                },
            },
        )
        assert call_r.status_code == 200
        call_json = call_r.json()
        assert call_json["result"]["isError"] is True
        err_scope = yaml.safe_load(call_json["result"]["content"][0]["text"])
        assert err_scope["error"]["code"] == "INSUFFICIENT_SCOPE"


@pytest.mark.asyncio
async def test_update_ticket_context_none() -> None:
    """Direct update_ticket invocation without MCP context raises INTERNAL."""
    with pytest.raises(KbMcpError) as exc_info:
        await update_ticket({"identifier": "KAN-142"})
    assert exc_info.value.code == McpErrorCode.INTERNAL


def test_update_ticket_formatting_helpers() -> None:
    """Test formatting and extraction helpers in update_ticket."""
    from mcp.surfaces.agent.update_ticket import (
        _extract_principal_name,
        _format_assignees,
    )

    # 1. _extract_principal_name
    assert _extract_principal_name({"handle": "bob"}) == "@bob"
    assert _extract_principal_name({"handle": "@alice"}) == "@alice"
    assert _extract_principal_name({"display_name": "Bob Smith"}) == "@bobsmith"
    u_id = "00000000-0000-0000-0000-000000000001"
    assert _extract_principal_name({"id": u_id}) == u_id
    assert _extract_principal_name({}) is None

    # 2. _format_assignees
    raw = [
        "Plain String",
        {"kind": "free_text", "free_text": "Vendor QA"},
        {"kind": "principal", "principal": {"handle": "lead"}},
        {"kind": "principal", "principal": {"display_name": "Carol Danvers"}},
        {"handle": "direct_handle"},
    ]
    res = _format_assignees(raw)
    assert res == ["Plain String", "Vendor QA", "@lead", "@caroldanvers", "@direct_handle"]


@pytest.mark.asyncio
async def test_update_ticket_validation_errors(agent_test_env: AgentTestEnv) -> None:
    """Test input parameter validation branches in update_ticket."""
    env = agent_test_env

    # 1. Unknown parameter
    res1 = await _call_update_ticket(
        env, {"identifier": "KAN-142", "invalid_param": 123}, subject_token=env.token_adam
    )
    assert res1["isError"] is True
    assert "Unknown parameter" in res1["content"][0]["text"]

    # 2. Empty identifier
    res2 = await _call_update_ticket(env, {"identifier": "  "}, subject_token=env.token_adam)
    assert res2["isError"] is True
    assert "identifier must be a non-empty string" in res2["content"][0]["text"]

    # 3. Invalid if_match pattern
    res3 = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "description_markdown": "notes", "if_match": "short-sha"},
        subject_token=env.token_adam,
    )
    assert res3["isError"] is True
    parsed_err3 = yaml.safe_load(res3["content"][0]["text"])
    assert parsed_err3["error"]["code"] == "VALIDATION_FAILED"
    assert "provide 64-character SHA-256 hex ETag" in parsed_err3["error"]["hint"]

    # 4. Invalid description_mode
    valid_sha = "0" * 64
    res4 = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "description_markdown": "notes",
            "description_mode": "upsert",
            "if_match": valid_sha,
        },
        subject_token=env.token_adam,
    )
    assert res4["isError"] is True
    assert "description_mode must be 'append' or 'replace'" in res4["content"][0]["text"]

    # 5. Empty summary
    res5 = await _call_update_ticket(
        env, {"identifier": "KAN-142", "summary": "   "}, subject_token=env.token_adam
    )
    assert res5["isError"] is True
    assert "summary must be a non-empty string" in res5["content"][0]["text"]

    # 6. Ticket not found
    res6 = await _call_update_ticket(
        env, {"identifier": "NONEXISTENT-999"}, subject_token=env.token_adam
    )
    assert res6["isError"] is True
    parsed_err6 = yaml.safe_load(res6["content"][0]["text"])
    assert parsed_err6["error"]["code"] == "NOT_FOUND"

    # 7. Update priority, cycle, parent, modules, labels
    res7 = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "priority": "high",
            "cycle": None,
            "parent": None,
            "modules_add": [],
            "modules_remove": [],
            "labels_add": [],
            "labels_remove": [],
        },
        subject_token=env.token_adam,
    )
    assert res7["isError"] is False
    parsed7 = yaml.safe_load(res7["content"][0]["text"])
    assert "priority" in parsed7["changed"]


@pytest.mark.asyncio
async def test_update_ticket_assignees_and_summary_length(agent_test_env: AgentTestEnv) -> None:
    """Test assignees add/remove, summary length limit, replace mode, and direct non-dict handling."""
    from unittest.mock import AsyncMock, MagicMock

    from mcp.context import McpRequestContext, reset_current_mcp_context, set_current_mcp_context
    from mcp.errors import KbMcpError, McpErrorCode
    from mcp.registry import Surface
    from mcp.surfaces.agent.update_ticket import update_ticket

    env = agent_test_env

    # 1. Summary length > 500
    res_len = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "summary": "x" * 501},
        subject_token=env.token_adam,
    )
    assert res_len["isError"] is True
    parsed_len = yaml.safe_load(res_len["content"][0]["text"])
    assert parsed_len["error"]["code"] == "VALIDATION_FAILED"
    assert "exceeds maximum of 500" in parsed_len["error"]["message"]

    # 2. Summary valid update
    res_sum = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "summary": "Valid Updated Summary"},
        subject_token=env.token_adam,
    )
    assert res_sum["isError"] is False
    parsed_sum = yaml.safe_load(res_sum["content"][0]["text"])
    assert "summary" in parsed_sum["changed"]

    # 3. Remove @adam first so we can test adding a principal handle
    res_rem_adam = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "assignees_remove": ["@adam"]},
        subject_token=env.token_adam,
    )
    assert res_rem_adam["isError"] is False

    # 4. Add assignees: @adam (principal handle) and free text "Vendor Beta"
    res_add = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "assignees_add": ["@adam", "Vendor Beta"]},
        subject_token=env.token_adam,
    )
    assert res_add["isError"] is False
    parsed_add = yaml.safe_load(res_add["content"][0]["text"])
    assert "assignees" in parsed_add["changed"]
    assert "@adam" in parsed_add["assignees"]
    assert "Vendor Beta" in parsed_add["assignees"]

    # 5. Add same assignees again (already assigned branch)
    res_readd = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "assignees_add": ["@adam", "Vendor Beta"]},
        subject_token=env.token_adam,
    )
    assert res_readd["isError"] is False

    # 6. Remove assignees
    res_rem = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "assignees_remove": ["@adam", "Vendor Beta"]},
        subject_token=env.token_adam,
    )
    assert res_rem["isError"] is False
    parsed_rem = yaml.safe_load(res_rem["content"][0]["text"])
    assert "assignees" in parsed_rem["changed"]

    # 6. Description mode = 'replace'
    ticket_curr = await _call_read_ticket(
        env,
        {"identifier": "KAN-142", "lod": "full"},
        subject_token=env.token_adam,
    )
    res_rep = await _call_update_ticket(
        env,
        {
            "identifier": "KAN-142",
            "description_markdown": "Completely replaced description text.",
            "description_mode": "replace",
            "if_match": ticket_curr["etag"],
        },
        subject_token=env.token_adam,
    )
    assert res_rep["isError"] is False
    parsed_rep = yaml.safe_load(res_rep["content"][0]["text"])
    assert "description_markdown" in parsed_rep["changed"]

    # 7. Test assignee without leading @ (resolves via /api/v1/resolve or free text)
    res_no_at = await _call_update_ticket(
        env,
        {"identifier": "KAN-142", "assignees_add": ["Vendor Gamma"]},
        subject_token=env.token_adam,
    )
    assert res_no_at["isError"] is False

    # 8. Direct update_ticket non-dict ticket check
    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value="not-a-dict")
    ctx = McpRequestContext(
        surface=Surface.AGENT, client=mock_client, subject_token="token", session_id="session"
    )

    token = set_current_mcp_context(ctx)
    try:
        with pytest.raises(KbMcpError) as exc:
            await update_ticket({"identifier": "KAN-142"})
        assert exc.value.code == McpErrorCode.NOT_FOUND
    finally:
        reset_current_mcp_context(token)


@pytest.mark.asyncio
async def test_update_ticket_modules_labels_unit_branches() -> None:
    """Test modules and labels add/remove, format assignees, and parent patch branches."""
    from unittest.mock import AsyncMock, MagicMock

    from mcp.context import McpRequestContext, reset_current_mcp_context, set_current_mcp_context
    from mcp.registry import Surface
    from mcp.surfaces.agent.update_ticket import _format_assignees, update_ticket

    # 1. _format_assignees branches
    raw_mixed = [
        "raw_string",
        {"kind": "free_text", "free_text": "Vendor QA"},
        {"kind": "principal", "principal": {"handle": "alice"}},
        {"kind": "principal", "principal": {"display_name": "Bob Smith"}},
        {"kind": "principal", "principal": {"id": "uuid-here"}},
        {"kind": "principal", "principal": {}},
        {"kind": "unknown"},
        12345,
    ]
    res_formatted = _format_assignees(raw_mixed)
    assert "raw_string" in res_formatted
    assert "Vendor QA" in res_formatted
    assert "@alice" in res_formatted
    assert "@bobsmith" in res_formatted
    assert "uuid-here" in res_formatted

    # 2. update_ticket with modules_add/remove, labels_add/remove, parent
    mock_client = MagicMock()
    curr_issue = {
        "key": "KAN-1",
        "description_markdown": "desc",
        "description_sha256": "0" * 64,
        "module_ids": ["mod-1"],
        "labels": [{"id": "lbl-1"}],
        "assignees": [],
    }

    async def _mock_request(method: str, path: str, **kwargs: Any) -> Any:
        if method == "GET" and path == "/api/v1/issues/KAN-1":
            return curr_issue
        if method == "PATCH" and path == "/api/v1/issues/KAN-1":
            body = kwargs.get("json_data", {})
            return {**curr_issue, **body}
        return {}

    mock_client.request = AsyncMock(side_effect=_mock_request)
    ctx = McpRequestContext(
        surface=Surface.AGENT, client=mock_client, subject_token="tok", session_id="sid"
    )

    token = set_current_mcp_context(ctx)
    try:
        res = await update_ticket(
            {
                "identifier": "KAN-1",
                "modules_add": ["mod-2"],
                "modules_remove": ["mod-1"],
                "labels_add": ["lbl-2"],
                "labels_remove": ["lbl-1"],
                "parent": "KAN-99",
            }
        )
        assert "modules" in res["changed"]
        assert "labels" in res["changed"]
        assert "parent" in res["changed"]
    finally:
        reset_current_mcp_context(token)


@pytest.mark.asyncio
async def test_update_ticket_comprehensive_branch_coverage() -> None:  # noqa: C901, PLR0915
    """Target all uncovered branches in update_ticket.py to exceed 95% coverage."""
    from unittest.mock import AsyncMock, MagicMock

    from mcp.context import McpRequestContext, reset_current_mcp_context, set_current_mcp_context
    from mcp.registry import Surface
    from mcp.surfaces.agent.update_ticket import update_ticket

    mock_client = MagicMock()
    ctx = McpRequestContext(
        surface=Surface.AGENT, client=mock_client, subject_token="tok", session_id="sid"
    )
    token = set_current_mcp_context(ctx)

    try:
        # 1. identifier == "help"
        mock_client.request = AsyncMock(return_value={"key": "KAN"})
        res_help = await update_ticket({"identifier": "help"})
        assert "update_ticket" in res_help.get("tool", "")

        # 2. forbidden properties: custom_fields and state
        with pytest.raises(KbMcpError) as exc_cf:
            await update_ticket({"identifier": "KAN-1", "custom_fields": {}})
        assert exc_cf.value.code == McpErrorCode.VALIDATION_FAILED

        with pytest.raises(KbMcpError) as exc_st:
            await update_ticket({"identifier": "KAN-1", "state": "done"})
        assert exc_st.value.code == McpErrorCode.VALIDATION_FAILED

        # 3. unknown parameter
        with pytest.raises(KbMcpError) as exc_unk:
            await update_ticket({"identifier": "KAN-1", "bogus_param": True})
        assert exc_unk.value.code == McpErrorCode.VALIDATION_FAILED

        # 4. invalid description_mode
        curr_issue = {
            "key": "KAN-1",
            "description_markdown": "old text",
            "description_sha256": "a" * 64,
            "assignees": [
                {"kind": "free_text", "free_text": "Vendor QA", "id": "ft-1"},
                {
                    "kind": "principal",
                    "id": "p-1",
                    "principal": {
                        "handle": "@alice",
                        "display_name": "Alice Wonderland",
                        "id": "u-alice",
                    },
                },
            ],
            "module_ids": ["m-1"],
            "labels": [{"id": "l-1"}],
        }

        async def _mock_req(method: str, path: str, **kwargs: Any) -> Any:
            if method == "GET" and path == "/api/v1/issues/KAN-1":
                return curr_issue
            if method == "GET" and path == "/api/v1/resolve":
                params = kwargs.get("params", {})
                if params.get("ref") == "carol":
                    return {"id": "u-carol"}
                raise KbMcpError(McpErrorCode.NOT_FOUND, "User not found")
            if method == "PATCH" and path == "/api/v1/issues/KAN-1":
                return {**curr_issue, **kwargs.get("json_data", {})}
            if method == "POST" and "/assignees" in path:
                return {"status": "ok"}
            if method == "DELETE" and "/assignees/" in path:
                return {"status": "ok"}
            return {}

        mock_client.request = AsyncMock(side_effect=_mock_req)

        with pytest.raises(KbMcpError) as exc_mode:
            await update_ticket(
                {
                    "identifier": "KAN-1",
                    "description_markdown": "new text",
                    "if_match": "a" * 64,
                    "description_mode": "unsupported_mode",
                }
            )
        assert exc_mode.value.code == McpErrorCode.VALIDATION_FAILED

        # 5. ETag conflict handling (lines 357-382)
        async def _mock_req_conflict(method: str, path: str, **_kwargs: Any) -> Any:
            if method == "GET" and path == "/api/v1/issues/KAN-1":
                return {"key": "KAN-1", "description_sha256": "c" * 64}
            if method == "PATCH" and path == "/api/v1/issues/KAN-1":
                raise KbMcpError(McpErrorCode.CONFLICT_ETAG, "conflict")
            return curr_issue

        mock_client.request = AsyncMock(side_effect=_mock_req_conflict)
        with pytest.raises(KbMcpError) as exc_conflict:
            await update_ticket(
                {
                    "identifier": "KAN-1",
                    "description_markdown": "new text",
                    "if_match": "b" * 64,
                    "description_mode": "replace",
                }
            )
        assert exc_conflict.value.code == McpErrorCode.CONFLICT_ETAG
        assert exc_conflict.value.hint is not None and "c" * 64 in exc_conflict.value.hint

        # 6. Assignees add & remove complex paths (lines 388-489)
        mock_client.request = AsyncMock(side_effect=_mock_req)
        res_assign = await update_ticket(
            {
                "identifier": "KAN-1",
                "assignees_add": [
                    "",
                    "Vendor QA",
                    "alice",
                    "@bob",
                    "carol",
                    "external-contractor",
                ],
                "assignees_remove": [
                    "Vendor QA",
                    "Alice Wonderland",
                    "u-alice",
                    "ft-1",
                    "unknown-person",
                ],
            }
        )
        assert "assignees" in res_assign["changed"]

        # 7. Modules and labels no-op branches (lines 302-334)
        res_noop = await update_ticket(
            {
                "identifier": "KAN-1",
                "modules_add": ["m-1"],
                "modules_remove": ["non-existent"],
                "labels_add": ["l-1"],
                "labels_remove": ["non-existent"],
            }
        )
        assert "modules" not in res_noop["changed"]
        assert "labels" not in res_noop["changed"]

        # 8. Non-dict assignees in issue, non-list modules/labels, resolve returns dict without id
        curr_issue_dirty = {
            "key": "KAN-1",
            "assignees": [
                "not-a-dict",
                {"kind": "principal", "id": "p-2", "principal": "not-a-dict-principal"},
            ],
            "module_ids": ["m-1"],
            "labels": [{"id": "l-1"}],
        }

        async def _mock_req_dirty(method: str, path: str, **_kwargs: Any) -> Any:
            if method == "GET" and path == "/api/v1/issues/KAN-1":
                return curr_issue_dirty
            if method == "GET" and path == "/api/v1/resolve":
                return {"status": "resolved_without_id"}
            if method == "POST" and "/assignees" in path:
                return {"status": "ok"}
            if method == "DELETE" and "/assignees/" in path:
                return {"status": "ok"}
            return {}

        mock_client.request = AsyncMock(side_effect=_mock_req_dirty)
        res_dirty = await update_ticket(
            {
                "identifier": "KAN-1",
                "assignees_add": ["resolve-no-id"],
                "assignees_remove": ["some-user"],
                "modules_add": "not-a-list",
                "modules_remove": "not-a-list",
                "labels_add": "not-a-list",
                "labels_remove": "not-a-list",
            }
        )
        assert "assignees" in res_dirty["changed"]

    finally:
        reset_current_mcp_context(token)

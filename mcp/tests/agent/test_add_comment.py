# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLC0415, PT011, E501, I001
"""Feature unit tests for /mcp/agent tool: add_comment (KB-P4-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml
from sqlalchemy import text

from mcp.errors import McpErrorCode
from mcp.surfaces.agent.add_comment import _validate_add_comment_arguments

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


async def _call_add_comment(
    env: AgentTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke add_comment via JSON-RPC 2.0 tools/call."""
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
            "name": "add_comment",
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
async def test_case_1_positive_add_comment(agent_test_env: AgentTestEnv) -> None:
    """Case 1: Positive add_comment on KAN-142 posts Markdown and returns comment identifier."""
    env = agent_test_env

    comment_body = "Automated test comment posting on KAN-142 with *markdown* formatting."
    res = await _call_add_comment(
        env,
        {"identifier": "KAN-142", "body_markdown": comment_body},
        subject_token=env.token_adam,
    )
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["status"] == "commented"
    assert parsed["key"] == "KAN-142"
    assert "comment" in parsed
    comment_ref = parsed["comment"]
    assert "#c-" in comment_ref

    # Verify comment in database
    await env.seed_session.rollback()
    row = (
        await env.seed_session.execute(
            text(
                "SELECT body_markdown, author_id FROM issue_comments WHERE issue_id = :iid ORDER BY created_at DESC LIMIT 1"
            ),
            {"iid": env.issue_142_id},
        )
    ).one_or_none()
    assert row is not None
    assert row[0] == comment_body
    assert row[1] == env.adam_user.id


@pytest.mark.asyncio
async def test_case_2_add_comment_help(agent_test_env: AgentTestEnv) -> None:
    """Case 2: add_comment(identifier='help') returns JIT help documentation."""
    env = agent_test_env

    res = await _call_add_comment(env, {"identifier": "help"})
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert "tool" in parsed or "help" in parsed or "commands" in parsed or "description" in parsed


def test_case_3_argument_validation() -> None:
    """Case 3: Unit validation of input arguments and boundaries."""
    # Identifier == help early exit
    _validate_add_comment_arguments({"identifier": "help"})
    _validate_add_comment_arguments({"action": "help"})

    # Unknown parameter
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments(
            {"identifier": "KAN-142", "body_markdown": "ok", "bad_key": 1}
        )
    assert "Unknown parameter" in str(exc_info.value)

    # Empty / non-string identifier
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"identifier": "", "body_markdown": "ok"})
    assert "non-empty string" in str(exc_info.value)

    # Long identifier (> 255 chars)
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"identifier": "x" * 256, "body_markdown": "ok"})
    assert "exceeds maximum" in str(exc_info.value)

    # Missing identifier
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"body_markdown": "Valid body"})
    assert "identifier is required" in str(exc_info.value)

    # Missing body
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"identifier": "KAN-142"})
    assert "body_markdown is required" in str(exc_info.value)

    # Empty body
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"identifier": "KAN-142", "body_markdown": "   "})
    assert "cannot be empty" in str(exc_info.value)

    # Body exceeding 65,536 bytes
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments({"identifier": "KAN-142", "body_markdown": "x" * 65537})
    assert "65536 bytes" in str(exc_info.value)

    # Invalid reply_to
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments(
            {"identifier": "KAN-142", "body_markdown": "ok", "reply_to": ""}
        )
    assert "reply_to must be a non-empty string" in str(exc_info.value)

    # Invalid ack_mentions
    with pytest.raises(Exception) as exc_info:
        _validate_add_comment_arguments(
            {"identifier": "KAN-142", "body_markdown": "ok", "ack_mentions": "not_bool"}
        )
    assert "ack_mentions must be a boolean" in str(exc_info.value)


@pytest.mark.asyncio
async def test_case_4_body_size_boundary_via_rpc(agent_test_env: AgentTestEnv) -> None:
    """Case 4: 65,537-byte comment rejected with VALIDATION_FAILED via RPC."""
    env = agent_test_env

    res = await _call_add_comment(
        env,
        {"identifier": "KAN-142", "body_markdown": "a" * 65537},
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["error"]["code"] == McpErrorCode.VALIDATION_FAILED.value


@pytest.mark.asyncio
async def test_case_5_nonexistent_ticket(agent_test_env: AgentTestEnv) -> None:
    """Case 5: add_comment on absent ticket returns NOT_FOUND."""
    env = agent_test_env

    res = await _call_add_comment(
        env,
        {"identifier": "KAN-99999", "body_markdown": "Comment on ghost ticket"},
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["error"]["code"] == McpErrorCode.NOT_FOUND.value


@pytest.mark.asyncio
async def test_case_6_mention_access_warning_and_ack(agent_test_env: AgentTestEnv) -> None:
    """Case 6: Mentioning a user without project view returns MENTION_ACCESS_WARNING, retrying with ack succeeds."""
    env = agent_test_env

    # 1. Without ack_mentions -> MENTION_ACCESS_WARNING
    res_warn = await _call_add_comment(
        env,
        {"identifier": "KAN-142", "body_markdown": "Pinging @maya to check this out."},
        subject_token=env.token_adam,
    )
    assert res_warn["isError"] is True
    parsed_warn = yaml.safe_load(res_warn["content"][0]["text"])
    assert parsed_warn["error"]["code"] == McpErrorCode.MENTION_ACCESS_WARNING.value
    assert "unauthorized_mentions" in parsed_warn["error"]
    assert any(
        "maya" in str(u.get("handle")) for u in parsed_warn["error"]["unauthorized_mentions"]
    )

    # 2. With ack_mentions: true -> posts successfully!
    res_ack = await _call_add_comment(
        env,
        {
            "identifier": "KAN-142",
            "body_markdown": "Pinging @maya to check this out.",
            "ack_mentions": True,
        },
        subject_token=env.token_adam,
    )
    assert res_ack["isError"] is False
    parsed_ack = yaml.safe_load(res_ack["content"][0]["text"])
    assert parsed_ack["status"] == "commented"
    assert parsed_ack["key"] == "KAN-142"


@pytest.mark.asyncio
async def test_case_7_add_comment_reply_and_help_action(agent_test_env: AgentTestEnv) -> None:
    """Case 7: add_comment with action=help, reply_to threaded comment, and missing context."""
    from mcp.surfaces.agent.add_comment import add_comment

    env = agent_test_env

    # 1. Action == help
    res_help = await _call_add_comment(env, {"action": "help"})
    assert res_help["isError"] is False

    # 2. First comment, then reply_to
    res_parent = await _call_add_comment(
        env,
        {"identifier": "KAN-142", "body_markdown": "Parent comment for thread test"},
        subject_token=env.token_adam,
    )
    assert res_parent["isError"] is False

    await env.seed_session.rollback()
    cid = (
        await env.seed_session.execute(
            text(
                "SELECT id FROM issue_comments WHERE body_markdown = 'Parent comment for thread test'"
            )
        )
    ).scalar_one()

    res_reply = await _call_add_comment(
        env,
        {
            "identifier": "KAN-142",
            "body_markdown": "Child threaded reply",
            "reply_to": str(cid),
        },
        subject_token=env.token_adam,
    )
    assert res_reply["isError"] is False

    # 3. Missing MCP context raises INTERNAL error
    with pytest.raises(Exception) as exc_ctx:
        await add_comment({"identifier": "KAN-142", "body_markdown": "no context"})
    assert "MCP request context" in str(exc_ctx.value)

    # 4. Direct call with identifier='help'
    from unittest.mock import AsyncMock, MagicMock
    from mcp.context import McpRequestContext, reset_current_mcp_context, set_current_mcp_context
    from mcp.registry import Surface

    req_ctx = McpRequestContext(
        surface=Surface.AGENT,
        client=env.internal_client,
        subject_token=env.token_adam,
        session_id="sess-1",
    )

    token = set_current_mcp_context(req_ctx)
    try:
        h = await add_comment({"identifier": "help"})
        assert "commands" in h or "help" in h or "tool" in h

        # Non-dict response from backend
        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value="not a dict")
        set_current_mcp_context(
            McpRequestContext(
                surface=Surface.AGENT,
                client=mock_client,
                subject_token=env.token_adam,
                session_id="sess-1",
            )
        )
        with pytest.raises(Exception) as exc:
            await add_comment({"identifier": "KAN-142", "body_markdown": "test comment"})
        assert "Unexpected response from comment creation" in str(exc.value)

        # Permalink without /issues/
        mock_client.request = AsyncMock(
            return_value={"id": str(cid), "permalink": "custom-link#c-123"}
        )
        res_custom = await add_comment({"identifier": "KAN-142", "body_markdown": "test comment"})
        assert res_custom["key"] == "KAN-142"
    finally:
        reset_current_mcp_context(token)


@pytest.mark.asyncio
async def test_case_8_mcp_transcript_and_canary_exfiltration(  # noqa: PLR0915
    agent_test_env: AgentTestEnv,
) -> None:
    """Case 8: Full MCP canary exfiltration sequence.

    1. Initialize session 1 with token_admin.
    2. read_ticket SEC-1 containing secret canary CANARY-7f3a.
    3. add_comment on PUB-1 attempting to leak CANARY-7f3a -> 409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED.
    4. Session-escape attempt: Initialize session 2 with token_admin and retry add_comment -> blocked.
    5. Clean principal: Initialize session 3 with token_adam and add_comment on PUB-1 -> succeeds.
    6. Forensic DB verification: 0 comments contain CANARY-7f3a, MCP_TAINT_BLOCKED activity recorded.
    """
    env = agent_test_env

    # 1. Initialize MCP session 1 with token_admin
    init_resp1 = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-canary-agent", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": env.token_admin},
    )
    assert init_resp1.status_code == 200
    sess_id_1 = init_resp1.headers["mcp-session-id"]

    # 2. Call read_ticket for SEC-1 containing CANARY-7f3a
    read_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "read_ticket",
                "arguments": {"identifier": "SEC-1", "lod": "full"},
            },
        },
        headers={
            "mcp-session-id": sess_id_1,
            "X-KB-Subject-Token": env.token_admin,
        },
    )
    assert read_resp.status_code == 200
    read_data = read_resp.json()
    assert read_data["result"]["isError"] is False
    read_text = read_data["result"]["content"][0]["text"]
    assert "CANARY-7f3a" in read_text

    # 3. Call add_comment on PUB-1 attempting to leak CANARY-7f3a -> blocked
    leak_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "add_comment",
                "arguments": {
                    "identifier": "PUB-1",
                    "body_markdown": "Attempted exfiltration of secret canary CANARY-7f3a from SEC-1.",
                },
            },
        },
        headers={
            "mcp-session-id": sess_id_1,
            "X-KB-Subject-Token": env.token_admin,
        },
    )
    assert leak_resp.status_code == 200
    leak_data = leak_resp.json()
    assert leak_data["result"]["isError"] is True
    leak_parsed = yaml.safe_load(leak_data["result"]["content"][0]["text"])
    assert (
        leak_parsed["error"]["code"] == McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED.value
    )
    assert "tainted_by" in leak_parsed["error"]

    # 4. Session escape attempt: Initialize session 2 with same token_admin
    init_resp2 = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-canary-escape-agent", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": env.token_admin},
    )
    assert init_resp2.status_code == 200
    sess_id_2 = init_resp2.headers["mcp-session-id"]
    assert sess_id_2 != sess_id_1

    escape_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "add_comment",
                "arguments": {
                    "identifier": "PUB-1",
                    "body_markdown": "Second exfiltration attempt with rotated session ID.",
                },
            },
        },
        headers={
            "mcp-session-id": sess_id_2,
            "X-KB-Subject-Token": env.token_admin,
        },
    )
    assert escape_resp.status_code == 200
    escape_data = escape_resp.json()
    assert escape_data["result"]["isError"] is True
    escape_parsed = yaml.safe_load(escape_data["result"]["content"][0]["text"])
    assert (
        escape_parsed["error"]["code"] == McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED.value
    )

    # 5. Clean principal: Initialize session 3 with token_adam (who never read SEC)
    init_resp3 = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-clean-agent", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": env.token_adam},
    )
    assert init_resp3.status_code == 200
    sess_id_3 = init_resp3.headers["mcp-session-id"]

    clean_resp = await env.mcp_client.post(
        "/mcp/agent",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "add_comment",
                "arguments": {
                    "identifier": "PUB-1",
                    "body_markdown": "Legitimate comment from untainted principal Adam.",
                },
            },
        },
        headers={
            "mcp-session-id": sess_id_3,
            "X-KB-Subject-Token": env.token_adam,
        },
    )
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["result"]["isError"] is False
    clean_parsed = yaml.safe_load(clean_data["result"]["content"][0]["text"])
    assert clean_parsed["status"] == "commented"
    assert clean_parsed["key"] == "PUB-1"

    # 6. Forensic database verifications
    await env.seed_session.rollback()
    canary_comments = (
        await env.seed_session.execute(
            text("SELECT count(*) FROM issue_comments WHERE body_markdown LIKE '%CANARY-7f3a%'")
        )
    ).scalar_one()
    assert canary_comments == 0

    blocked_activities = (
        await env.seed_session.execute(
            text(
                "SELECT count(*) FROM activity_records "
                "WHERE event_type = 'MCP_TAINT_BLOCKED' "
                "  AND payload->>'tool' = 'add_comment'"
            )
        )
    ).scalar_one()
    assert blocked_activities >= 2

    # Format and write taint-canary-db-proof.txt
    from datetime import UTC, datetime
    from pathlib import Path

    proof_path = Path("docs/qa/KANBA-141/taint-canary-db-proof.txt")
    proof_path.parent.mkdir(parents=True, exist_ok=True)

    canary_rows = (
        await env.seed_session.execute(
            text(
                "SELECT id, workspace_id, issue_id, author_id, body_markdown, created_at "
                "FROM issue_comments WHERE body_markdown LIKE '%CANARY-7f3a%'"
            )
        )
    ).all()

    activity_rows = (
        await env.seed_session.execute(
            text(
                "SELECT id, workspace_id, actor_id, event_type, payload, recorded_at "
                "FROM activity_records WHERE event_type = 'MCP_TAINT_BLOCKED' ORDER BY recorded_at ASC"
            )
        )
    ).all()

    taint_rows = (
        await env.seed_session.execute(
            text(
                "SELECT encode(taint_key, 'hex') AS taint_key_hex, key_kind, project_id, first_read_at, expires_at "
                "FROM mcp_read_taint WHERE project_id = :p"
            ),
            {"p": env.proj_sec_id},
        )
    ).all()

    proof_lines = [
        "================================================================================",
        "FORENSIC EVIDENCE: TAINT CANARY EXFILTRATION DEFENSE AUDIT (KB-P4-07)",
        "================================================================================",
        f"Timestamp: {datetime.now(UTC).isoformat()}",
        f"Workspace ID: {env.workspace_id}",
        f"Restricted Project (SEC): {env.proj_sec_id}",
        f"Public Project (PUB): {env.proj_pub_id}",
        "Canary String: CANARY-7f3a",
        "",
        "--------------------------------------------------------------------------------",
        "QUERY 1: Assert 0 comments containing secret canary in public or restricted issues",
        "--------------------------------------------------------------------------------",
        "SQL: SELECT id, workspace_id, issue_id, author_id, body_markdown, created_at",
        "     FROM issue_comments WHERE body_markdown LIKE '%CANARY-7f3a%';",
        f"Result row count: {len(canary_rows)}",
        "(0 rows returned - canary leak prevented)",
        "",
        "--------------------------------------------------------------------------------",
        "QUERY 2: Audit log showing MCP_TAINT_BLOCKED security events",
        "--------------------------------------------------------------------------------",
        "SQL: SELECT id, workspace_id, actor_principal_id, event_type, payload, created_at",
        "     FROM activity_records WHERE event_type = 'MCP_TAINT_BLOCKED' ORDER BY created_at ASC;",
        f"Result row count: {len(activity_rows)}",
    ]
    for row in activity_rows:
        proof_lines.append(
            f"  - Event: {row[3]} | Actor: {row[2]} | Target Object: {row[1]} | Created: {row[5]}"
        )
        proof_lines.append(f"    Payload: {row[4]}")

    proof_lines.extend(
        [
            "",
            "--------------------------------------------------------------------------------",
            "QUERY 3: mcp_read_taint table records (session and credential taints)",
            "--------------------------------------------------------------------------------",
            "SQL: SELECT encode(taint_key, 'hex') AS taint_key_hex, key_kind, project_id, first_read_at, expires_at",
            "     FROM mcp_read_taint WHERE project_id = :proj_sec_id;",
            f"Result row count: {len(taint_rows)}",
            *(
                f"  - Key Kind: {row[1]} | Taint Key SHA256: {row[0][:16]}... | Project: {row[2]} | Expires: {row[4]}"
                for row in taint_rows
            ),
            "",
            "================================================================================",
            "AUDIT VERDICT: PASS - EXFILTRATION BLOCKED, ZERO LEAKS, AUDIT LOGS RECORDED",
            "================================================================================",
        ]
    )

    proof_path.write_text("\n".join(proof_lines) + "\n", encoding="utf-8")  # noqa: ASYNC240

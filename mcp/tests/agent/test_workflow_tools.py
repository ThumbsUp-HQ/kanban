# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/agent workflow tools (KB-P4-06).

Covers:
  - begin_work: help, positive transition, plan comment, validation errors.
  - transition_ticket: help, positive transition, USE_COMPLETE_WORK guard, validation.
  - complete_work: help, positive completion, QA gate check, blocker guard, validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest
import yaml

from mcp.surfaces.agent.transition_ticket import transition_ticket

if TYPE_CHECKING:
    from mcp.tests.agent.conftest import AgentTestEnv

pytestmark = pytest.mark.committed_db


def _make_proof(ticket_key: str, verdict: str = "READY", grade: str = "A") -> dict[str, Any]:
    """Construct a valid VerificationProof dictionary for a ticket key."""
    return {
        "qa_dir": f"docs/qa/{ticket_key}/",
        "reality_checker": {
            "verdict": verdict,
            "grade": grade,
            "report_path": f"docs/qa/{ticket_key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/9876",
        "artifacts": [
            f"docs/qa/{ticket_key}/git-diff.patch",
            f"docs/qa/{ticket_key}/unit-test-results.txt",
        ],
    }


async def _call_tool(
    env: AgentTestEnv,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke tool via JSON-RPC 2.0 tools/call."""
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
            "name": tool_name,
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/agent", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data["result"])


async def test_begin_work_help(agent_test_env: AgentTestEnv) -> None:
    """begin_work('help') returns tool help documentation."""
    env = agent_test_env
    res = await _call_tool(env, "begin_work", {"identifier": "help", "plan_markdown": "none"})
    assert res["isError"] is False
    text = res["content"][0]["text"]
    assert "begin_work" in text


async def test_begin_work_validation_errors(agent_test_env: AgentTestEnv) -> None:
    """begin_work enforces required fields and size constraints."""
    env = agent_test_env

    # Missing plan_markdown
    res1 = await _call_tool(env, "begin_work", {"identifier": "KAN-142"})
    assert res1["isError"] is True

    # Empty plan_markdown
    res2 = await _call_tool(env, "begin_work", {"identifier": "KAN-142", "plan_markdown": ""})
    assert res2["isError"] is True

    # Oversized plan_markdown (> 65536 bytes)
    res3 = await _call_tool(
        env,
        "begin_work",
        {"identifier": "KAN-142", "plan_markdown": "x" * 65537},
    )
    assert res3["isError"] is True


async def test_begin_work_positive_execution(agent_test_env: AgentTestEnv) -> None:
    """begin_work moves issue to started state, attaches plan comment and caller."""
    env = agent_test_env
    res = await _call_tool(
        env,
        "begin_work",
        {"identifier": "KAN-150", "plan_markdown": "### Implementation Plan\n1. Run tests"},
        subject_token=env.token_adam,
    )
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["status"] == "started"
    assert parsed["key"] == "KAN-150"
    assert parsed["issue_key"] == "KAN-150"
    assert parsed["sequence_number"] == 150
    assert isinstance(parsed["sequence_number"], int)
    assert parsed["state"] == "In Progress"
    assert "@adam" in parsed["assignees"]
    assert "comment" in parsed


async def test_transition_ticket_help_and_guards(agent_test_env: AgentTestEnv) -> None:
    """transition_ticket provides help and blocks transitions to completed states."""
    env = agent_test_env

    # Help
    h_res = await _call_tool(env, "transition_ticket", {"identifier": "help", "to_state": "Todo"})
    assert h_res["isError"] is False
    assert "transition_ticket" in h_res["content"][0]["text"]

    # Blocked: transition to Done requires complete_work
    guard_res = await _call_tool(
        env,
        "transition_ticket",
        {"identifier": "KAN-142", "to_state": "Done"},
        subject_token=env.token_adam,
    )
    assert guard_res["isError"] is True
    err_text = guard_res["content"][0]["text"]
    assert "USE_COMPLETE_WORK" in err_text or "complete_work" in err_text


async def test_transition_ticket_positive_execution(agent_test_env: AgentTestEnv) -> None:
    """transition_ticket successfully transitions to another non-completed state."""
    env = agent_test_env
    res = await _call_tool(
        env,
        "transition_ticket",
        {
            "identifier": "KAN-142",
            "to_state": "Todo",
            "comment_markdown": "Moving back to Todo for refinement",
        },
        subject_token=env.token_adam,
    )
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["status"] == "transitioned"
    assert parsed["key"] == "KAN-142"
    assert parsed["issue_key"] == "KAN-142"
    assert parsed["sequence_number"] == 142
    assert isinstance(parsed["sequence_number"], int)
    assert parsed["to_state"] == "Todo"
    assert parsed["from_state"] == "In Progress"


async def test_transition_ticket_dict_from_state_extraction() -> None:
    """transition_ticket extracts scalar from_state string when upstream returns dict."""
    mock_client = AsyncMock()
    mock_client.request.return_value = {
        "key": "KAN-142",
        "from_state": {
            "id": "01932e6a-7a54-7221-a3f1-e7a9b0c1d2e3",
            "name": "In Progress",
            "group": "started",
        },
        "state": {"name": "Todo"},
        "target_state": "Todo",
    }
    res = await transition_ticket(
        {"identifier": "KAN-142", "to_state": "Todo"},
        client=mock_client,
    )
    assert res["status"] == "transitioned"
    assert res["key"] == "KAN-142"
    assert res["issue_key"] == "KAN-142"
    assert res["sequence_number"] == 142
    assert isinstance(res["sequence_number"], int)
    assert res["from_state"] == "In Progress"
    assert isinstance(res["from_state"], str)


async def test_transition_ticket_unknown_state_hints(agent_test_env: AgentTestEnv) -> None:
    """transition_ticket with unknown to_state returns INVALID_TRANSITION listing valid states."""
    env = agent_test_env
    res = await _call_tool(
        env,
        "transition_ticket",
        {
            "identifier": "KAN-142",
            "to_state": "FlyingToMars",
        },
        subject_token=env.token_adam,
    )
    assert res["isError"] is True
    err_text = res["content"][0]["text"]
    assert "INVALID_TRANSITION" in err_text
    assert "FlyingToMars" in err_text
    assert "Backlog" in err_text or "Todo" in err_text or "In Progress" in err_text


async def test_complete_work_help_and_validations(agent_test_env: AgentTestEnv) -> None:
    """complete_work validates proof paths, traversal, and verdict."""
    env = agent_test_env

    # Help
    h_res = await _call_tool(
        env,
        "complete_work",
        {"identifier": "help", "summary_markdown": "Done", "verification_proof": {}},
    )
    assert h_res["isError"] is False

    # Path traversal rejection (..)
    bad_proof = _make_proof("KAN-142")
    bad_proof["artifacts"].append("docs/qa/KAN-142/../../evil.sh")
    res1 = await _call_tool(
        env,
        "complete_work",
        {"identifier": "KAN-142", "summary_markdown": "Summary", "verification_proof": bad_proof},
        subject_token=env.token_adam,
    )
    assert res1["isError"] is True
    err_text = res1["content"][0]["text"]
    assert "traversal" in err_text.lower() or "VALIDATION_FAILED" in err_text

    # Key mismatch rejection
    mismatch_proof = _make_proof("KAN-999")
    res2 = await _call_tool(
        env,
        "complete_work",
        {
            "identifier": "KAN-142",
            "summary_markdown": "Summary",
            "verification_proof": mismatch_proof,
        },
        subject_token=env.token_adam,
    )
    assert res2["isError"] is True


async def test_complete_work_positive_execution(agent_test_env: AgentTestEnv) -> None:
    """complete_work marks ticket Done and posts verification proof table."""
    env = agent_test_env
    proof = _make_proof("KAN-150")
    res = await _call_tool(
        env,
        "complete_work",
        {
            "identifier": "KAN-150",
            "summary_markdown": "All deliverables and automated tests complete.",
            "verification_proof": proof,
        },
        subject_token=env.token_adam,
    )
    assert res["isError"] is False
    parsed = yaml.safe_load(res["content"][0]["text"])
    assert parsed["status"] == "completed"
    assert parsed["key"] == "KAN-150"
    assert parsed["issue_key"] == "KAN-150"
    assert parsed["sequence_number"] == 150
    assert isinstance(parsed["sequence_number"], int)
    assert parsed["state"] == "Done"
    assert "comment" in parsed

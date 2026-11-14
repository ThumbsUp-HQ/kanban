# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for argument validation and client error handling in MCP workflow tools (KB-P4-06)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.surfaces.agent.begin_work import (
    _validate_begin_work_arguments,
    begin_work,
)
from mcp.surfaces.agent.complete_work import (
    _validate_complete_work_arguments,
    complete_work,
)
from mcp.surfaces.agent.transition_ticket import (
    _validate_transition_arguments,
    transition_ticket,
)


def _valid_proof(key: str = "KAN-142") -> dict[str, Any]:
    return {
        "qa_dir": f"docs/qa/{key}/",
        "artifacts": [f"docs/qa/{key}/git-diff.patch"],
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": f"docs/qa/{key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/1234",
    }


def test_begin_work_argument_validation() -> None:
    """Validate begin_work arguments against schema rules and type boundaries."""
    # Missing identifier
    with pytest.raises(KbMcpError) as exc:
        _validate_begin_work_arguments({})
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # Non-string identifier
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": 123})

    # Empty identifier
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "   "})

    # Identifier too long (> 200)
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "a" * 201, "plan_markdown": "plan"})

    # Identifier == "help" -> early exit
    _validate_begin_work_arguments({"identifier": "help"})

    # Missing plan_markdown
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "KAN-142"})

    # Non-string plan_markdown
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "KAN-142", "plan_markdown": 123})

    # Empty plan_markdown
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "KAN-142", "plan_markdown": ""})

    # Oversized plan_markdown
    with pytest.raises(KbMcpError):
        _validate_begin_work_arguments({"identifier": "KAN-142", "plan_markdown": "x" * 65537})

    # Valid
    _validate_begin_work_arguments({"identifier": "KAN-142", "plan_markdown": "Valid plan"})


def test_transition_ticket_argument_validation() -> None:
    """Validate transition_ticket arguments against schema rules and type boundaries."""
    # Missing identifier
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({})

    # Non-string identifier
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": 123})

    # Empty identifier
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "  "})

    # Identifier too long
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "a" * 201, "to_state": "Todo"})

    # Identifier == "help" -> early exit
    _validate_transition_arguments({"identifier": "help"})

    # Missing to_state
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "KAN-142"})

    # Non-string to_state
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "KAN-142", "to_state": 123})

    # Empty to_state
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "KAN-142", "to_state": "   "})

    # to_state too long (> 100)
    with pytest.raises(KbMcpError):
        _validate_transition_arguments({"identifier": "KAN-142", "to_state": "a" * 101})

    # Non-string comment_markdown
    with pytest.raises(KbMcpError):
        _validate_transition_arguments(
            {
                "identifier": "KAN-142",
                "to_state": "Todo",
                "comment_markdown": 123,
            }
        )

    # Oversized comment_markdown
    with pytest.raises(KbMcpError):
        _validate_transition_arguments(
            {
                "identifier": "KAN-142",
                "to_state": "Todo",
                "comment_markdown": "x" * 65537,
            }
        )

    # Non-dict verification_proof
    with pytest.raises(KbMcpError):
        _validate_transition_arguments(
            {
                "identifier": "KAN-142",
                "to_state": "Todo",
                "verification_proof": "not a dict",
            }
        )

    # Valid with proof
    proof = _valid_proof("KAN-142")
    _validate_transition_arguments(
        {
            "identifier": "KAN-142",
            "to_state": "Todo",
            "comment_markdown": "Comment",
            "verification_proof": proof,
        }
    )


def test_complete_work_argument_validation() -> None:
    """Validate complete_work arguments against schema rules and type boundaries."""
    # Missing identifier
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({})

    # Non-string identifier
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": 123})

    # Empty identifier
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": ""})

    # Identifier too long
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": "a" * 201})

    # Identifier == "help" -> returns None
    assert _validate_complete_work_arguments({"identifier": "help"}) is None

    # Missing summary_markdown
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": "KAN-142"})

    # Non-string summary_markdown
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": "KAN-142", "summary_markdown": 123})

    # Empty summary_markdown
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments({"identifier": "KAN-142", "summary_markdown": ""})

    # Oversized summary_markdown
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "x" * 65537,
            }
        )

    # Missing verification_proof
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "Summary",
            }
        )

    # Non-dict verification_proof
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "Summary",
                "verification_proof": "invalid",
            }
        )

    # Invalid to_state type / empty / too long
    proof = _valid_proof("KAN-142")
    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "Summary",
                "verification_proof": proof,
                "to_state": 123,
            }
        )

    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "Summary",
                "verification_proof": proof,
                "to_state": "   ",
            }
        )

    with pytest.raises(KbMcpError):
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-142",
                "summary_markdown": "Summary",
                "verification_proof": proof,
                "to_state": "x" * 101,
            }
        )

    # Valid
    p = _validate_complete_work_arguments(
        {
            "identifier": "KAN-142",
            "summary_markdown": "Summary",
            "verification_proof": proof,
            "to_state": "Done",
        }
    )
    assert p is not None


async def test_tool_invocations_without_client() -> None:
    """Invoking tools outside MCP request context and without client raises INTERNAL."""
    with pytest.raises(KbMcpError) as exc1:
        await begin_work({"identifier": "KAN-142", "plan_markdown": "plan"}, client=None)
    assert exc1.value.code == McpErrorCode.INTERNAL

    with pytest.raises(KbMcpError) as exc2:
        await transition_ticket({"identifier": "KAN-142", "to_state": "Todo"}, client=None)
    assert exc2.value.code == McpErrorCode.INTERNAL

    proof = _valid_proof("KAN-142")
    with pytest.raises(KbMcpError) as exc3:
        await complete_work(
            {"identifier": "KAN-142", "summary_markdown": "done", "verification_proof": proof},
            client=None,
        )
    assert exc3.value.code == McpErrorCode.INTERNAL


async def test_mocked_upstream_responses() -> None:
    """Test upstream error, pending_agent_gate, cycle handling, and comment handling."""
    mock_client = AsyncMock()

    # Upstream non-dict response
    mock_client.request.return_value = "not a dict"
    with pytest.raises(KbMcpError) as exc:
        await begin_work(
            {"identifier": "KAN-142", "plan_markdown": "plan"},
            client=mock_client,
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc_tr:
        await transition_ticket(
            {"identifier": "KAN-142", "to_state": "Todo"},
            client=mock_client,
        )
    assert exc_tr.value.code == McpErrorCode.UPSTREAM_ERROR

    proof = _valid_proof("KAN-142")
    with pytest.raises(KbMcpError) as exc_cw:
        await complete_work(
            {"identifier": "KAN-142", "summary_markdown": "done", "verification_proof": proof},
            client=mock_client,
        )
    assert exc_cw.value.code == McpErrorCode.UPSTREAM_ERROR

    # pending_agent_gate response in begin_work
    mock_client.request.return_value = {
        "execution_id": "01932e6a-7a54-7221-a3f1-e7a9b0c1d2e3",
        "active_agent": "reality-checker",
        "from_state": "Backlog",
        "to_state": "In Progress",
    }
    gate_res = await begin_work(
        {"identifier": "KAN-142", "plan_markdown": "plan"},
        client=mock_client,
    )
    assert gate_res["status"] == "pending_agent_gate"
    assert gate_res["active_agent"] == "reality-checker"

    # Comment in complete_work
    mock_client.request.return_value = {
        "key": "KAN-142",
        "state": {"name": "Done"},
        "comment_ref": "KAN-142#c-123",
    }
    cw_res = await complete_work(
        {"identifier": "KAN-142", "summary_markdown": "done", "verification_proof": proof},
        client=mock_client,
    )
    assert cw_res["status"] == "completed"
    assert cw_res["comment"] == "KAN-142#c-123"
    assert cw_res["proof"]["verdict"] == "READY"

    # Cycle as string in begin_work
    mock_client.request.return_value = {
        "key": "KAN-142",
        "state": "In Progress",
        "cycle": "Sprint 99",
        "assignees": [],
    }
    bw_res = await begin_work(
        {"identifier": "KAN-142", "plan_markdown": "plan"},
        client=mock_client,
    )
    assert bw_res["cycle"] == "Sprint 99"

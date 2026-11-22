# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for agent MCP tool lease and fencing parameters (KAN-69).

Covers:
  - begin_work: ttl_seconds, fencing_token, lease_action validation and return fields.
  - update_ticket: fencing_token, lease_action validation and upstream dispatch.
  - transition_ticket: fencing_token, lease_action validation and upstream dispatch.
  - complete_work: fencing_token, lease_action validation and upstream dispatch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from mcp.context import McpRequestContext, set_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
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
from mcp.surfaces.agent.update_ticket import update_ticket


def _make_valid_proof(key: str) -> dict[str, Any]:
    return {
        "qa_dir": f"docs/qa/{key}/",
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": f"docs/qa/{key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/12345",
        "artifacts": [
            f"docs/qa/{key}/git-diff.patch",
            f"docs/qa/{key}/unit-test-results.txt",
        ],
    }


def _make_valid_report() -> str:
    return """# Integration Agent Reality-Based Report

## Reality Check Validation
- Complete audit of all source files and assets.

## Complete System Evidence
- System running smoothly with zero errors.

## Integration Testing Results
- All unit and integration test suites executed cleanly.

## Comprehensive Issue Assessment
- Root cause identified and systematically resolved.

## Realistic Quality Certification
- Verdict: READY
- Grade: A

## Deployment Readiness Assessment
- Ready for immediate production deployment.
"""


def test_begin_work_lease_argument_validation() -> None:
    """Validate begin_work arguments for ttl_seconds, fencing_token, and lease_action."""
    # Valid arguments
    _validate_begin_work_arguments(
        {
            "identifier": "KAN-69",
            "plan_markdown": "Test plan",
            "ttl_seconds": 600,
            "fencing_token": 1,
            "lease_action": "acquire",
        }
    )
    _validate_begin_work_arguments(
        {
            "identifier": "KAN-69",
            "plan_markdown": "Test plan",
            "lease_action": "renew",
        }
    )

    # Invalid ttl_seconds boundaries
    with pytest.raises(KbMcpError) as exc_low:
        _validate_begin_work_arguments(
            {
                "identifier": "KAN-69",
                "plan_markdown": "Plan",
                "ttl_seconds": 30,
            }
        )
    assert exc_low.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_high:
        _validate_begin_work_arguments(
            {
                "identifier": "KAN-69",
                "plan_markdown": "Plan",
                "ttl_seconds": 8000,
            }
        )
    assert exc_high.value.code == McpErrorCode.VALIDATION_FAILED

    # Invalid lease_action
    with pytest.raises(KbMcpError) as exc_act:
        _validate_begin_work_arguments(
            {
                "identifier": "KAN-69",
                "plan_markdown": "Plan",
                "lease_action": "invalid_action",
            }
        )
    assert exc_act.value.code == McpErrorCode.VALIDATION_FAILED


def test_transition_ticket_lease_argument_validation() -> None:
    """Validate transition_ticket arguments for fencing_token and lease_action."""
    _validate_transition_arguments(
        {
            "identifier": "KAN-69",
            "to_state": "In Progress",
            "fencing_token": 2,
            "lease_action": "renew",
        }
    )

    with pytest.raises(KbMcpError) as exc_token:
        _validate_transition_arguments(
            {
                "identifier": "KAN-69",
                "to_state": "In Progress",
                "fencing_token": "not_an_int",
            }
        )
    assert exc_token.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_act:
        _validate_transition_arguments(
            {
                "identifier": "KAN-69",
                "to_state": "In Progress",
                "lease_action": "invalid_action",
            }
        )
    assert exc_act.value.code == McpErrorCode.VALIDATION_FAILED


def test_complete_work_lease_argument_validation() -> None:
    """Validate complete_work arguments for fencing_token and lease_action."""
    proof = _make_valid_proof("KAN-69")
    report = _make_valid_report()

    _validate_complete_work_arguments(
        {
            "identifier": "KAN-69",
            "summary_markdown": report,
            "verification_proof": proof,
            "fencing_token": 3,
            "lease_action": "release",
        }
    )

    with pytest.raises(KbMcpError) as exc_act:
        _validate_complete_work_arguments(
            {
                "identifier": "KAN-69",
                "summary_markdown": report,
                "verification_proof": proof,
                "lease_action": "invalid_action",
            }
        )
    assert exc_act.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_begin_work_tool_lease_unpacking() -> None:
    """Test begin_work tool formats and returns lease attributes from upstream response."""
    mock_client = AsyncMock()
    mock_client.request.return_value = {
        "key": "KAN-69",
        "sequence_id": 69,
        "state": {"name": "In Progress"},
        "assignees": [],
        "comment_ref": "KAN-69#c-12345678",
        "lease_id": "01935678-0000-7000-8000-000000000001",
        "fencing_token": 1,
        "lease_expires_at": "2026-11-22T20:00:00Z",
    }

    result = await begin_work(
        {
            "identifier": "KAN-69",
            "plan_markdown": "Test plan",
            "ttl_seconds": 600,
            "fencing_token": 0,
            "lease_action": "acquire",
        },
        client=mock_client,
    )

    assert result["status"] == "started"
    assert result["key"] == "KAN-69"
    assert result["lease_id"] == "01935678-0000-7000-8000-000000000001"
    assert result["fencing_token"] == 1
    assert result["lease_expires_at"] == "2026-11-22T20:00:00Z"

    # Verify upstream payload
    mock_client.request.assert_called_once()
    _, kwargs = mock_client.request.call_args
    assert kwargs["json_data"]["ttl_seconds"] == 600
    assert kwargs["json_data"]["fencing_token"] == 0
    assert kwargs["json_data"]["lease_action"] == "acquire"


@pytest.mark.asyncio
async def test_transition_ticket_tool_lease_dispatch() -> None:
    """Test transition_ticket passes fencing_token and lease_action upstream."""
    mock_client = AsyncMock()
    mock_client.request.return_value = {
        "key": "KAN-69",
        "sequence_id": 69,
        "target_state": "In Progress",
    }

    result = await transition_ticket(
        {
            "identifier": "KAN-69",
            "to_state": "In Progress",
            "fencing_token": 2,
            "lease_action": "renew",
        },
        client=mock_client,
    )

    assert result["status"] == "transitioned"
    assert result["key"] == "KAN-69"

    mock_client.request.assert_called_once()
    _, kwargs = mock_client.request.call_args
    assert kwargs["json_data"]["fencing_token"] == 2
    assert kwargs["json_data"]["lease_action"] == "renew"


@pytest.mark.asyncio
async def test_complete_work_tool_lease_dispatch() -> None:
    """Test complete_work passes fencing_token and lease_action upstream."""
    mock_client = AsyncMock()
    mock_client.request.return_value = {
        "key": "KAN-69",
        "sequence_id": 69,
        "target_state": "Done",
        "comment_ref": "KAN-69#c-abcdef12",
    }

    proof = _make_valid_proof("KAN-69")
    report = _make_valid_report()

    result = await complete_work(
        {
            "identifier": "KAN-69",
            "summary_markdown": report,
            "verification_proof": proof,
            "fencing_token": 3,
            "lease_action": "release",
        },
        client=mock_client,
    )

    assert result["status"] == "completed"
    assert result["key"] == "KAN-69"

    mock_client.request.assert_called_once()
    _, kwargs = mock_client.request.call_args
    assert kwargs["json_data"]["fencing_token"] == 3
    assert kwargs["json_data"]["lease_action"] == "release"


@pytest.mark.asyncio
async def test_update_ticket_tool_lease_and_fencing() -> None:
    """Test update_ticket sends X-Fencing-Token and executes heartbeat on renew."""
    mock_client = AsyncMock()
    mock_client.request.side_effect = [
        # GET /api/v1/issues/KAN-69
        {
            "id": "01935678-0000-7000-8000-000000000001",
            "key": "KAN-69",
            "sequence_id": 69,
            "summary": "Existing Summary",
            "priority": {"slug": "high"},
            "state": {"name": "In Progress"},
            "assignees": [],
            "etag": "etag123",
        },
        # PATCH /api/v1/issues/KAN-69
        {
            "id": "01935678-0000-7000-8000-000000000001",
            "key": "KAN-69",
            "sequence_id": 69,
            "summary": "Updated Summary",
            "priority": {"slug": "high"},
            "state": {"name": "In Progress"},
            "assignees": [],
            "etag": "etag456",
        },
        # POST /api/v1/issues/KAN-69/lease/heartbeat
        {
            "lease_id": "01935678-0000-7000-8000-000000000002",
            "fencing_token": 5,
        },
    ]

    ctx = McpRequestContext(
        surface=Surface.AGENT,
        client=mock_client,
        subject_token="tok",  # noqa: S106
        session_id="sess",
    )
    set_current_mcp_context(ctx)

    res = await update_ticket(
        {
            "identifier": "KAN-69",
            "summary": "Updated Summary",
            "fencing_token": 5,
            "lease_action": "renew",
        }
    )

    assert res["summary"] == "Updated Summary"
    assert mock_client.request.call_count == 3

    # Check PATCH headers
    patch_call = mock_client.request.call_args_list[1]
    assert patch_call[0][0] == "PATCH"
    assert patch_call[1]["headers"]["X-Fencing-Token"] == "5"

    # Check heartbeat call
    hb_call = mock_client.request.call_args_list[2]
    assert hb_call[0][0] == "POST"
    assert "/lease/heartbeat" in hb_call[0][1]
    assert hb_call[1]["json_data"]["fencing_token"] == 5

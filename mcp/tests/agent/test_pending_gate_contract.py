# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for pending_agent_gate contract and mock transport verification (KB-P4-06).

Covers:
  - 202 Accepted response translation to status: pending_agent_gate.
  - Exact YAML keys: status, key, from_state, to_state, execution_id, active_agent, hint.
  - TRANSITION_HELD error handling on non-null pending_transition_exec_id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import yaml

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.agent.complete_work import complete_work
from mcp.surfaces.agent.transition_ticket import transition_ticket
from mcp.yaml_out import dump_yaml

if TYPE_CHECKING:
    from collections.abc import Callable


def _create_mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> KanbanApiClient:
    """Instantiate a KanbanApiClient backed by an httpx.MockTransport."""

    def wrapped_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/session" and request.method == "GET":
            return httpx.Response(status_code=200, json={"csrf_token": "dummy_csrf_token"})
        return handler(request)

    transport = httpx.MockTransport(wrapped_handler)
    settings = McpSettings()
    return KanbanApiClient(settings=settings, transport=transport)


async def test_transition_ticket_pending_agent_gate_contract() -> None:
    """202 Accepted from kanban-api formats exact pending_agent_gate YAML structure."""
    execution_id = "0196ed40-7b2a-7000-8000-112233445566"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/transition" in request.url.path
        return httpx.Response(
            status_code=202,
            json={
                "status": "pending_agent_gate",
                "execution_id": execution_id,
                "active_agent": "code-reviewer",
                "from_state": "In Review",
                "to_state": "Done",
            },
        )

    client = _create_mock_client(handler)

    res = await transition_ticket(
        {
            "identifier": "KAN-142",
            "to_state": "Done",
            "comment_markdown": "Ready for review",
        },
        client=client,
    )

    assert res["status"] == "pending_agent_gate"
    assert res["key"] == "KAN-142"
    assert res["issue_key"] == "KAN-142"
    assert res["sequence_number"] == 142
    assert isinstance(res["sequence_number"], int)
    assert res["from_state"] == "In Review"
    assert res["to_state"] == "Done"
    assert res["execution_id"] == execution_id
    assert res["active_agent"] == "code-reviewer"
    assert res["hint"] == "transition is held; poll read_ticket for the gate verdict"

    # Verify YAML serialization produces exact required keys
    yaml_text = dump_yaml(res)
    parsed = yaml.safe_load(yaml_text)
    assert parsed["status"] == "pending_agent_gate"
    assert parsed["key"] == "KAN-142"
    assert parsed["issue_key"] == "KAN-142"
    assert parsed["sequence_number"] == 142
    assert isinstance(parsed["sequence_number"], int)
    assert parsed["from_state"] == "In Review"
    assert parsed["to_state"] == "Done"
    assert parsed["execution_id"] == execution_id
    assert parsed["active_agent"] == "code-reviewer"
    assert parsed["hint"] == "transition is held; poll read_ticket for the gate verdict"


async def test_complete_work_pending_agent_gate_contract() -> None:
    """complete_work returns pending_agent_gate structure on 202 Accepted."""
    execution_id = "0196ed40-7b2a-7000-8000-223344556677"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/complete-work" in request.url.path
        return httpx.Response(
            status_code=202,
            json={
                "status": "pending_agent_gate",
                "execution_id": execution_id,
                "active_agent": "reality-checker",
                "from_state": "In Progress",
                "to_state": "Done",
            },
        )

    client = _create_mock_client(handler)

    proof = {
        "qa_dir": "docs/qa/KAN-142/",
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": "docs/qa/KAN-142/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/4444",
        "artifacts": ["docs/qa/KAN-142/unit-test-results.txt"],
    }

    res = await complete_work(
        {
            "identifier": "KAN-142",
            "summary_markdown": "Completing work",
            "verification_proof": proof,
        },
        client=client,
    )

    assert res["status"] == "pending_agent_gate"
    assert res["key"] == "KAN-142"
    assert res["issue_key"] == "KAN-142"
    assert res["sequence_number"] == 142
    assert isinstance(res["sequence_number"], int)
    assert res["from_state"] == "In Progress"
    assert res["to_state"] == "Done"
    assert res["execution_id"] == execution_id
    assert res["active_agent"] == "reality-checker"
    assert res["hint"] == "transition is held; poll read_ticket for the gate verdict"


async def test_transition_held_error_mapping() -> None:
    """Issue with existing active gate hold yields TRANSITION_HELD error."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=409,
            json={
                "code": "TRANSITION_HELD",
                "title": "Transition Held",
                "detail": "Issue transition is currently held by an active gate hook",
            },
        )

    client = _create_mock_client(handler)

    with pytest.raises(KbMcpError) as exc_info:
        await transition_ticket(
            {
                "identifier": "KAN-142",
                "to_state": "In Review",
            },
            client=client,
        )

    assert exc_info.value.code == McpErrorCode.TRANSITION_HELD
    assert "currently held" in str(exc_info.value)

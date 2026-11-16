# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for transition_ticket and gate state machine responses over MCP (KB-P5-18).

Covers:
  - 202 Accepted mapping to pending_agent_gate response envelope.
  - 409 Conflict with TRANSITION_PENDING mapping to McpErrorCode.TRANSITION_PENDING.
  - 409 Conflict with TRANSITION_HELD mapping to McpErrorCode.TRANSITION_HELD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.agent.transition_ticket import transition_ticket

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


@pytest.mark.asyncio
async def test_transition_ticket_pending_agent_gate_202() -> None:
    """202 Accepted returns pending_agent_gate payload with active_agent and hint."""
    execution_id = "0196ed40-7b2a-7000-8000-112233445566"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            status_code=202,
            json={
                "status": "pending_agent_gate",
                "execution_id": execution_id,
                "active_agent": "reality-checker",
                "hook_name": "pre-done-gate",
                "harness_kind": "in_app_sdk",
                "from_state": "In Progress",
                "to_state": "Done",
            },
        )

    client = _create_mock_client(handler)

    res = await transition_ticket(
        {
            "identifier": "KAN-142",
            "to_state": "Done",
        },
        client=client,
    )

    assert res["status"] == "pending_agent_gate"
    assert res["key"] == "KAN-142"
    assert res["execution_id"] == execution_id
    assert res["active_agent"] == "reality-checker"
    assert res["hint"] == "transition is held; poll read_ticket for the gate verdict"


@pytest.mark.asyncio
async def test_transition_ticket_409_transition_pending() -> None:
    """409 Conflict with TRANSITION_PENDING maps to McpErrorCode.TRANSITION_PENDING."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=409,
            json={
                "code": "TRANSITION_PENDING",
                "title": "Transition Already Pending",
                "detail": "A transition execution is already in progress for this issue",
            },
        )

    client = _create_mock_client(handler)

    with pytest.raises(KbMcpError) as exc_info:
        await transition_ticket(
            {
                "identifier": "KAN-142",
                "to_state": "Done",
            },
            client=client,
        )

    assert exc_info.value.code == McpErrorCode.TRANSITION_PENDING
    assert "already in progress" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_transition_ticket_409_transition_held() -> None:
    """409 Conflict with TRANSITION_HELD maps to McpErrorCode.TRANSITION_HELD."""

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
                "to_state": "Done",
            },
            client=client,
        )

    assert exc_info.value.code == McpErrorCode.TRANSITION_HELD
    assert "currently held" in str(exc_info.value).lower()

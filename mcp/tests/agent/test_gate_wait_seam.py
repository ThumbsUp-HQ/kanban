# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Seam tests: MCP surfaces the synchronous gate verdict returned by the API (KAN-537/538)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.agent.complete_work import complete_work
from mcp.surfaces.agent.transition_ticket import transition_ticket

if TYPE_CHECKING:
    from collections.abc import Callable


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> KanbanApiClient:
    def wrapped(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/session" and request.method == "GET":
            return httpx.Response(status_code=200, json={"csrf_token": "t"})
        return handler(request)

    return KanbanApiClient(settings=McpSettings(), transport=httpx.MockTransport(wrapped))


def _hold(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": "KAN-1",
        "status": "pending_agent_gate",
        "execution_id": "e1",
        "active_agent": "a",
        "from_state": "In Review",
        "to_state": "Done",
        "gate": gate,
    }


async def test_complete_work_returns_sync_verdict_and_requests_wait() -> None:
    """Wait=true is requested and the approved verdict is surfaced synchronously."""
    gate = {
        "passed": True,
        "status": "approved",
        "verdict": "approve",
        "comment": "ok",
        "findings": ["a.py"],
        "execution_id": "e1",
    }
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.query.decode())
        return httpx.Response(200, json=_hold(gate))

    out = await complete_work({"identifier": "KAN-1"}, client=_client(handler))
    assert out["passed"] is True
    assert out["status"] == "approved"
    assert out["findings"] == ["a.py"]
    assert seen == ["wait=true"]


async def test_transition_sync_verdict_and_timeout_stays_pending() -> None:
    """Rejected verdict surfaces; a gate timeout remains pending_agent_gate."""
    gate = {
        "passed": False,
        "status": "rejected",
        "verdict": "reject",
        "comment": "no",
        "findings": [],
        "execution_id": "e1",
    }
    out = await transition_ticket(
        {"identifier": "KAN-1", "to_state": "Done"},
        client=_client(lambda _r: httpx.Response(200, json=_hold(gate))),
    )
    assert out["passed"] is False
    assert out["status"] == "rejected"

    timeout = {
        "passed": False,
        "status": "timeout",
        "error_code": "GATE_TIMEOUT",
        "execution_id": "e1",
    }
    body = {**_hold(timeout), "from_state": "In Review"}
    pend = await transition_ticket(
        {"identifier": "KAN-1", "to_state": "Done"},
        client=_client(lambda _r: httpx.Response(202, json=body)),
    )
    assert pend["status"] == "pending_agent_gate"

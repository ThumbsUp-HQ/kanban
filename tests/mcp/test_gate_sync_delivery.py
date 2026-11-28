"""Grade round-trip and synchronous gate delivery tests (KAN-544)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from kanban.workflows.async_gate import (
    _gate_result_from_row,
    format_approve_comment,
    format_veto_comment,
)
from kanban.workflows.gate_types import GateDecision
from mcp.internal_client import KanbanApiClient
from mcp.surfaces.agent.complete_work import complete_work
from mcp.surfaces.agent.transition_ticket import transition_ticket


class FakeClient:
    """Records request kwargs and returns a canned gate payload."""

    def __init__(self, gate: dict[str, Any]) -> None:
        self.gate = gate
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "path": path, **kwargs})
        return {"gate": self.gate, "sequence_number": 1}


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_row_surfaces_grade(status: str) -> None:
    row = _gate_result_from_row(uuid.uuid4(), status, {"decision": "x", "grade": "B+"})
    assert row["grade"] == "B+"
    assert row["passed"] is (status == "approved")


def test_row_grade_absent_is_none_and_failed_has_grade() -> None:
    assert _gate_result_from_row(uuid.uuid4(), "approved", None)["grade"] is None
    assert _gate_result_from_row(uuid.uuid4(), "error", {"grade": "F"})["grade"] == "F"


def test_comments_include_grade() -> None:
    assert "Grade: A" in format_approve_comment("h", "l", "a", "b", "good", grade="A")
    assert "Grade: F" in format_veto_comment("h", "l", "a", "b", "bad", grade="F")
    assert "Grade:" not in format_approve_comment("h", "l", "a", "b", "good")
    assert "Grade:" not in format_veto_comment("h", "l", "a", "b", "bad")


def test_gate_decision_grade_default() -> None:
    assert GateDecision(decision="approve", reason_markdown="r").grade is None
    assert GateDecision(decision="reject", reason_markdown="r", grade="C").grade == "C"


def _gate(passed: bool, grade: str | None) -> dict[str, Any]:
    return {
        "passed": passed,
        "status": "approved" if passed else "rejected",
        "verdict": "approve" if passed else "reject",
        "comment": "c",
        "findings": ["f.py"],
        "execution_id": "e1",
        "grade": grade,
    }


@pytest.mark.parametrize(("passed", "grade"), [(True, "A"), (False, "F")])
async def test_transition_ticket_returns_grade(passed: bool, grade: str) -> None:
    client = FakeClient(_gate(passed, grade))
    res = await transition_ticket(
        {"identifier": "KAN-1", "to_state": "In Review"},
        client=client,  # type: ignore[arg-type]
    )
    assert res["grade"] == grade
    assert res["passed"] is passed
    call = client.calls[0]
    assert call["timeout_s"] == 130.0
    assert call["params"] == {"wait": "true", "wait_timeout_ms": 120000}


async def test_transition_ticket_omits_grade_when_absent() -> None:
    client = FakeClient(_gate(True, None))
    res = await transition_ticket(
        {"identifier": "KAN-1", "to_state": "In Review"},
        client=client,  # type: ignore[arg-type]
    )
    assert "grade" not in res


@pytest.mark.parametrize(("passed", "grade"), [(True, "A-"), (False, "C")])
async def test_complete_work_returns_grade(passed: bool, grade: str) -> None:
    client = FakeClient(_gate(passed, grade))
    res = await complete_work(
        {"identifier": "KAN-1", "summary": "done work"},
        client=client,  # type: ignore[arg-type]
    )
    assert res["grade"] == grade
    call = client.calls[0]
    assert call["timeout_s"] == 130.0
    assert call["params"] == {"wait": "true", "wait_timeout_ms": 120000}


async def test_api_client_timeout_propagates() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = KanbanApiClient.__new__(KanbanApiClient)
    client.__dict__.update(mode="cli_remote", api_token="t", response_body_limit_bytes=1_000_000)
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )

    async def _noop(*_a: object, **_k: object) -> None:
        return None

    client._ensure_csrf_token = _noop  # type: ignore[method-assign]
    await client.request("GET", "/x", timeout_s=130.0)
    await client.request("GET", "/y")
    assert seen[0].extensions["timeout"]["read"] == 130.0
    assert seen[1].extensions["timeout"]["read"] != 130.0
    await client._client.aclose()

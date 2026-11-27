# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Offline tests for KAN-537: batch complete_work, Done routing, started-state pick."""

# ruff: noqa: ANN401, FBT001, FBT002, FBT003, D103

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from kanban.issues.proof import RealityCheckerProof
from kanban.issues.workflow_service import _pick_started_state, render_proof_table
from mcp.errors import KbMcpError, McpErrorCode
from mcp.surfaces.agent.complete_work import complete_work
from mcp.surfaces.agent.transition_ticket import transition_ticket


class _Client:
    def __init__(self, behaviors: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.behaviors = behaviors or {}

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        self.calls.append((method, path, kw.get("json_data") or {}))
        for frag, beh in self.behaviors.items():
            if frag in path:
                if isinstance(beh, Exception):
                    raise beh
                return beh
        return {"key": path.split("/")[4], "target_state": "Done"}


def _st(name: str, default: bool = False) -> Any:
    return SimpleNamespace(name=name, is_default=default)


def test_pick_started_state() -> None:
    assert _pick_started_state([]) is None
    a, b, c = _st("Crazy_Ideas"), _st("In Progress"), _st("Review", True)
    assert _pick_started_state([a, b, c]) is c
    assert _pick_started_state([a, _st(" in progress ")]) is not a
    d = _st("Review")
    assert _pick_started_state([a, d]) is d
    e = _st("Ideas")
    assert _pick_started_state([a, e]) is a


def test_grade_plus_minus_and_render() -> None:
    for g in ("A", "A-", "A+"):
        RealityCheckerProof(
            verdict="READY", grade=g, report_path="docs/qa/KAN-1/reality-checker-report.md"
        )
    with pytest.raises(ValueError, match="grade"):
        RealityCheckerProof(
            verdict="READY", grade="A++", report_path="docs/qa/KAN-1/reality-checker-report.md"
        )
    assert render_proof_table(" hi ", None) == "hi"


async def test_single_without_summary_or_proof() -> None:
    c = _Client()
    res = await complete_work({"identifier": "KAN-1"}, client=cast("Any", c))
    assert res["status"] == "completed"
    assert "proof" not in res
    assert c.calls[0][2] == {"summary_markdown": "Completed via MCP"}
    await complete_work({"identifier": "KAN-1", "summary": "ok"}, client=cast("Any", c))
    assert c.calls[1][2]["summary_markdown"] == "ok"


async def test_batch_isolated_failures() -> None:
    c = _Client(
        {
            "KAN-2": KbMcpError(McpErrorCode.VALIDATION_FAILED, "bad", fix_hint="fix"),
            "KAN-3": RuntimeError("boom"),
        }
    )
    res = await complete_work(
        {"identifiers": ["KAN-1", "KAN-2", "KAN-1", "KAN-3"]}, client=cast("Any", c)
    )
    assert res["status"] == "batch"
    assert (res["completed"], res["failed"]) == (1, 2)
    assert res["results"][1]["error"]["fix_hint"] == "fix"
    assert res["results"][2]["error"]["code"] == "INTERNAL"
    assert res["results"][0]["state"] == "Done"


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"identifier": "KAN-1", "identifiers": ["KAN-2"]},
        {"identifiers": []},
        {"identifiers": [1]},
        {"identifiers": ["x" * 201]},
        {"identifiers": [f"K-{i}" for i in range(26)]},
    ],
)
async def test_batch_arg_errors(args: dict[str, Any]) -> None:
    with pytest.raises(KbMcpError):
        await complete_work(args, client=cast("Any", _Client()))


async def test_transition_done_routes_to_complete_work() -> None:
    err = KbMcpError(McpErrorCode.USE_COMPLETE_WORK, "use cw")
    c = _Client({"/transition": err})
    res = await transition_ticket(
        {"identifier": "KAN-5", "to_state": "Done", "comment_markdown": "fin"},
        client=cast("Any", c),
    )
    assert res["status"] == "transitioned"
    assert c.calls[-1][1].endswith("/complete-work")
    assert c.calls[-1][2]["summary_markdown"] == "fin"
    other = _Client({"/transition": KbMcpError(McpErrorCode.NOT_FOUND, "nf")})
    with pytest.raises(KbMcpError):
        await transition_ticket(
            {"identifier": "KAN-5", "to_state": "Done"}, client=cast("Any", other)
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"summary": 5},
        {"summary": ""},
        {"verification_proof": "x"},
        {"to_state": ""},
        {"to_state": 3},
        {"to_state": "x" * 101},
        {"fencing_token": "1"},
        {"fencing_token": True},
        {"lease_action": "bogus"},
    ],
)
async def test_single_arg_validation(extra: dict[str, Any]) -> None:
    with pytest.raises(KbMcpError):
        await complete_work({"identifier": "KAN-1", **extra}, client=cast("Any", _Client()))


async def test_single_optional_passthrough() -> None:
    c = _Client({"/complete-work": {"key": "KAN-1", "execution_id": "e", "active_agent": "a"}})
    res = await complete_work(
        {"identifier": "KAN-1", "to_state": "Done", "fencing_token": 3, "lease_action": "keep"},
        client=cast("Any", c),
    )
    assert res["status"] == "pending_agent_gate"
    assert c.calls[0][2]["fencing_token"] == 3


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"identifier": 5, "to_state": "x"},
        {"identifier": "", "to_state": "x"},
        {"identifier": "K-1"},
        {"identifier": "K-1", "to_state": ""},
        {"identifier": "K-1", "to_state": "x" * 101},
        {"identifier": "K-1", "to_state": "x", "comment_markdown": 1},
        {"identifier": "K-1", "to_state": "x", "comment_markdown": "a" * 70000},
        {"identifier": "K-1", "to_state": "x", "verification_proof": "p"},
        {"identifier": "K-1", "to_state": "x", "verification_proof": {"bad": 1}},
        {"identifier": "K-1", "to_state": "x", "fencing_token": "1"},
        {"identifier": "K-1", "to_state": "x", "lease_action": "no"},
    ],
)
async def test_transition_arg_validation(args: dict[str, Any]) -> None:
    with pytest.raises(KbMcpError):
        await transition_ticket(args, client=cast("Any", _Client()))


async def test_transition_plain_and_gate_hold() -> None:
    c = _Client({"/transition": {"key": "K-1", "state": {"name": "Review"}, "from_state": "Todo"}})
    res = await transition_ticket(
        {
            "identifier": "K-1",
            "to_state": "Review",
            "comment_markdown": "c",
            "fencing_token": 1,
            "lease_action": "keep",
        },
        client=cast("Any", c),
    )
    assert res["status"] == "transitioned"
    assert res["from_state"] == "Todo"
    assert c.calls[0][2]["fencing_token"] == 1
    held = _Client({"/transition": {"key": "K-1", "execution_id": "e", "active_agent": "a"}})
    res = await transition_ticket({"identifier": "K-1", "to_state": "R"}, client=cast("Any", held))
    assert res["status"] == "pending_agent_gate"
    bad = _Client({"/transition": ["x"]})
    with pytest.raises(KbMcpError):
        await transition_ticket({"identifier": "K-1", "to_state": "R"}, client=cast("Any", bad))


async def test_transition_invalid_options_and_route_extras() -> None:
    inv = KbMcpError(McpErrorCode.INVALID_TRANSITION, "no", valid_options=["A", "B"])
    with pytest.raises(KbMcpError) as ei:
        await transition_ticket(
            {"identifier": "K-1", "to_state": "Z"},
            client=cast("Any", _Client({"/transition": inv})),
        )
    assert "A, B" in (ei.value.fix_hint or "")
    c = _Client({"/transition": KbMcpError(McpErrorCode.USE_COMPLETE_WORK, "u")})
    await transition_ticket(
        {"identifier": "K-1", "to_state": "Done", "fencing_token": 2, "lease_action": "release"},
        client=cast("Any", c),
    )
    assert c.calls[-1][2]["fencing_token"] == 2


async def test_single_summary_secret_and_bad_report() -> None:
    cl = cast("Any", _Client())
    with pytest.raises(KbMcpError):
        await complete_work(
            {"identifier": "K-1", "summary": "NEEDS_WORK", "verification_proof": {}}, client=cl
        )
    with pytest.raises(KbMcpError):
        await complete_work(
            {
                "identifier": "K-1",
                "summary": "AKIAIOSFODNN7EXAMPLE secret_key=AKIAIOSFODNN7EXAMPLE",
            },
            client=cl,
        )

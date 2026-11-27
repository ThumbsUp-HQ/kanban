# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for the synchronous gate-wait bridge in the workflow API (KAN-537/538 seam)."""

# ruff: noqa: SLF001, TC002

from __future__ import annotations

import json
from typing import Any

import pytest

from kanban.api.v1 import issue_workflow as iw

HOLD = {"status": "pending_agent_gate", "execution_id": "e1", "active_agent": "a"}


class _Sess:
    """Minimal session double tracking commits so no txn stays open across waits."""

    def __init__(self) -> None:
        self.open = True
        self.commits = 0

    def in_transaction(self) -> bool:
        return self.open

    async def commit(self) -> None:
        self.commits += 1
        self.open = False


async def test_no_wait_returns_202_hold() -> None:
    """Without wait the hold is returned immediately."""
    resp = await iw._gate_hold_response(_Sess(), dict(HOLD), wait=False, wait_timeout_ms=1)  # type: ignore[arg-type]
    assert resp.status_code == 202
    assert json.loads(bytes(resp.body)) == HOLD


async def test_wait_returns_verdict_and_ends_txn(monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal verdict yields 200 with merged fields; the poll txn is ended."""
    sess = _Sess()
    seen: dict[str, Any] = {}

    async def fake_wait(factory: Any, exec_id: str, *, timeout_ms: int) -> dict[str, Any]:  # noqa: ANN401
        async with factory() as s:
            seen["same"] = s is sess
        seen["timeout"] = timeout_ms
        return {"passed": True, "status": "approved", "execution_id": exec_id}

    monkeypatch.setattr(iw, "wait_for_gate_execution", fake_wait)
    resp = await iw._gate_hold_response(sess, dict(HOLD), wait=True, wait_timeout_ms=10**9)  # type: ignore[arg-type]
    body = json.loads(bytes(resp.body))
    assert resp.status_code == 200
    assert body["passed"] is True
    assert body["gate"]["status"] == "approved"
    assert seen == {"same": True, "timeout": iw._MAX_GATE_WAIT_MS}
    assert sess.commits == 1


async def test_wait_timeout_stays_202(monkeypatch: pytest.MonkeyPatch) -> None:
    """GATE_TIMEOUT keeps the 202 hold with the timeout attached."""

    async def fake_wait(*_a: Any, **_k: Any) -> dict[str, Any]:  # noqa: ANN401
        return {"passed": False, "status": "timeout", "error_code": "GATE_TIMEOUT"}

    monkeypatch.setattr(iw, "wait_for_gate_execution", fake_wait)
    resp = await iw._gate_hold_response(_Sess(), dict(HOLD), wait=True, wait_timeout_ms=5)  # type: ignore[arg-type]
    assert resp.status_code == 202
    assert json.loads(bytes(resp.body))["gate"]["error_code"] == "GATE_TIMEOUT"


def test_gate_wait_dependency() -> None:
    """The query dependency maps to the GateWait dataclass."""
    assert iw._gate_wait(True, 7) == iw.GateWait(wait=True, timeout_ms=7)  # noqa: FBT003

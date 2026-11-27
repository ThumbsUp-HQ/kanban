# Copyright 2026 Kanban Platform Contributors
"""KAN-538: wait_for_gate_execution unit tests (fake sessions, no DB)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

from kanban.workflows.async_gate import wait_for_gate_execution

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _Res:
    def __init__(self, row: Any) -> None:  # noqa: ANN401
        self._row = row

    def first(self) -> Any:  # noqa: ANN401
        return self._row


class _Sess:
    def __init__(self, rows: list[Any], opened: list[int]) -> None:
        self._rows = rows
        self._opened = opened

    async def execute(self, _stmt: object) -> _Res:
        return _Res(self._rows.pop(0) if len(self._rows) > 1 else self._rows[0])


def _factory(rows: list[Any]) -> Any:  # noqa: ANN401
    opened: list[int] = []

    @asynccontextmanager
    async def f() -> AsyncIterator[_Sess]:
        opened.append(1)
        yield _Sess(rows, opened)

    f.opened = opened  # type: ignore[attr-defined]
    return f


@pytest.mark.asyncio
async def test_approved_after_poll() -> None:
    """test_approved_after_poll."""
    f = _factory(
        [
            ("pending_async", None),
            ("approved", {"decision": "approve", "reason": "ok", "cited_files": ["a"]}),
        ]
    )
    r = await wait_for_gate_execution(f, uuid.uuid4(), timeout_ms=2000, poll_interval_s=0.01)
    assert r["passed"] is True
    assert r["status"] == "approved"
    assert r["comment"] == "ok"
    assert r["findings"] == ["a"]
    assert len(f.opened) == 2


@pytest.mark.asyncio
async def test_rejected() -> None:
    """test_rejected."""
    f = _factory([("rejected", {"decision": "reject", "reason": "bad"})])
    r = await wait_for_gate_execution(f, uuid.uuid4(), timeout_ms=100)
    assert r["passed"] is False
    assert r["status"] == "rejected"
    assert r["comment"] == "bad"


@pytest.mark.asyncio
async def test_failed_status() -> None:
    """test_failed_status."""
    f = _factory([("timed_out", {"decision": "timed_out", "code": "GATE_TIMEOUT"})])
    r = await wait_for_gate_execution(f, uuid.uuid4(), timeout_ms=100)
    assert r["status"] == "failed"
    assert r["error_code"] == "GATE_TIMEOUT"
    f2 = _factory([("error", None)])
    r2 = await wait_for_gate_execution(f2, uuid.uuid4(), timeout_ms=100)
    assert r2["error_code"] == "GATE_FAILED"


@pytest.mark.asyncio
async def test_deadline_timeout() -> None:
    """test_deadline_timeout."""
    f = _factory([("pending_async", None)])
    r = await wait_for_gate_execution(f, uuid.uuid4(), timeout_ms=30, poll_interval_s=0.01)
    assert r == {
        "passed": False,
        "status": "timeout",
        "error_code": "GATE_TIMEOUT",
        "execution_id": r["execution_id"],
    }


@pytest.mark.asyncio
async def test_not_found() -> None:
    """test_not_found."""
    f = _factory([None])
    r = await wait_for_gate_execution(f, uuid.uuid4(), timeout_ms=100)
    assert r["error_code"] == "EXECUTION_NOT_FOUND"

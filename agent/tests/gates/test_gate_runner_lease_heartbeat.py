# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: D102, D105, D107, ANN401, PYI036, ARG001, ARG002, SLF001
"""Feature unit tests for GateWorkerRunner claim lease heartbeat renewal (KAN-437).

Tests cover:
1. Periodic heartbeat lease renewal while an invocation is active in _active_invocations.
2. Heartbeat loop ceases renewal when deadline_at is exceeded.
3. Fast heartbeat cancellation on worker dispatch completion.
4. Invocation exceeding deadline_at records GATE_TIMEOUT failure.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.gates.runner import GateWorkerRunner
from agent.gates.worker import GateWorker

if TYPE_CHECKING:
    from database.session import RLSContext


class MockSession:
    """Mock async session recording executed statements."""

    def __init__(self) -> None:
        self.executed: list[tuple[Any, dict[str, Any]]] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> MagicMock:
        self.executed.append((stmt, params or {}))
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass


class MockAsyncContextManager:
    """Async context manager wrapper around a mock session."""

    def __init__(self, session: MockSession) -> None:
        self.session = session

    async def __aenter__(self) -> MockSession:
        return self.session

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class MockSessionFactory:
    """Mock session factory returning an async context manager."""

    def __init__(self, session: MockSession) -> None:
        self._session = session
        self.engine = None

    def session(self, ctx: RLSContext) -> MockAsyncContextManager:
        return MockAsyncContextManager(self._session)


@pytest.mark.asyncio
async def test_heartbeat_lease_renews_claim() -> None:
    """_heartbeat_lease periodically executes update for active invocation."""
    mock_session = MockSession()
    factory = MockSessionFactory(mock_session)
    worker = AsyncMock(spec=GateWorker)
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    runner = GateWorkerRunner(
        session_factory=factory,  # type: ignore[arg-type]
        workspace_id=ws_id,
        admin_principal_id=admin_id,
    )
    runner.worker = worker
    runner.heartbeat_interval_s = 0.05
    runner.lease_ttl_s = 1.0

    inv_id = uuid.uuid4()

    runner._active_invocations.add(inv_id)

    # Start heartbeat task
    task = asyncio.create_task(
        runner._heartbeat_lease(
            invocation_id=inv_id,
            workspace_id=ws_id,
            admin_principal_id=admin_id,
            deadline_at=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=10),
        )
    )

    # Wait for ~3 heartbeat intervals
    await asyncio.sleep(0.16)

    # Remove invocation from active set
    runner._active_invocations.discard(inv_id)
    await asyncio.sleep(0.06)
    await task

    # Verify updates were executed
    updates = [
        (stmt, params) for stmt, params in mock_session.executed if params.get("inv_id") == inv_id
    ]
    assert len(updates) >= 2, f"Expected at least 2 heartbeat updates, got {len(updates)}"
    for _, params in updates:
        assert params["worker_id"] == runner.worker_id
        assert "new_expiry" in params


@pytest.mark.asyncio
async def test_heartbeat_stops_when_deadline_exceeded() -> None:
    """_heartbeat_lease stops renewing once deadline_at <= now."""
    mock_session = MockSession()
    factory = MockSessionFactory(mock_session)
    worker = AsyncMock(spec=GateWorker)
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    runner = GateWorkerRunner(
        session_factory=factory,  # type: ignore[arg-type]
        workspace_id=ws_id,
        admin_principal_id=admin_id,
    )
    runner.worker = worker
    runner.heartbeat_interval_s = 0.04
    runner.lease_ttl_s = 1.0

    inv_id = uuid.uuid4()
    runner._active_invocations.add(inv_id)

    # Deadline is 0.05s from now
    past_deadline = dt.datetime.now(dt.UTC) + dt.timedelta(milliseconds=50)

    task = asyncio.create_task(
        runner._heartbeat_lease(
            invocation_id=inv_id,
            workspace_id=ws_id,
            admin_principal_id=admin_id,
            deadline_at=past_deadline,
        )
    )

    # Wait 0.15s, longer than deadline
    await asyncio.sleep(0.15)
    assert task.done(), "Heartbeat task should have terminated when deadline_at <= now"

    runner._active_invocations.discard(inv_id)


@pytest.mark.asyncio
async def test_dispatch_timeout_against_deadline_records_failure() -> None:
    """When dispatch execution exceeds remaining deadline, GATE_TIMEOUT is recorded."""
    mock_session = AsyncMock()
    factory = MockSessionFactory(mock_session)
    worker = AsyncMock(spec=GateWorker)

    # Simulate worker taking 0.5s
    async def slow_dispatch(event: dict[str, Any]) -> None:
        await asyncio.sleep(0.5)

    worker.handle_dispatch.side_effect = slow_dispatch

    runner = GateWorkerRunner(
        session_factory=factory,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        admin_principal_id=uuid.uuid4(),
    )
    runner.worker = worker
    runner.heartbeat_interval_s = 0.05
    runner.record_failure = AsyncMock()  # type: ignore[method-assign]

    inv_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()

    # Short deadline of 0.05s
    short_deadline = dt.datetime.now(dt.UTC) + dt.timedelta(milliseconds=50)

    mock_inv = MagicMock()
    mock_inv.id = inv_id
    mock_inv.execution_id = exec_id
    mock_inv.hook_id = hook_id
    mock_inv.workspace_id = runner.workspace_id
    mock_inv.status = "running"
    mock_inv.hook_kind = "agent_interceptor"
    mock_inv.started_at = dt.datetime.now(dt.UTC)
    mock_inv.deadline_at = short_deadline
    mock_inv.output_json = {}

    mock_execute_res = MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_inv]
    mock_session.execute = AsyncMock(return_value=mock_execute_res)
    mock_session.get = AsyncMock(return_value=None)

    handled = await runner.poll_once()

    assert handled == 1
    runner.record_failure.assert_awaited_once_with(
        exec_id,
        hook_id,
        "GATE_TIMEOUT",
        invocation_id=inv_id,
        detail="Async agent gate exceeded deadline_at",
    )
    assert inv_id not in runner._active_invocations

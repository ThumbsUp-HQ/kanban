# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for GateWorkerRunner and background gate execution (KAN-45).

Covers:
  - GateWorkerRunner initialization and configuration.
  - Outbox event polling and dispatch.
  - Background task start and cancellation lifecycle.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.gates.runner import GateWorkerRunner, start_gate_worker

if TYPE_CHECKING:
    import types


class MockSessionFactory:
    """Mock session factory for GateWorkerRunner."""

    def __init__(self, session: object) -> None:
        """Initialize mock session factory with session object."""
        self._session = session

    class SessionContext:
        """Async context manager wrapper around mock session."""

        def __init__(self, session: object) -> None:
            """Initialize context manager with mock session."""
            self._session = session

        async def __aenter__(self) -> object:
            """Enter async context returning session."""
            return self._session

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: types.TracebackType | None,
        ) -> None:
            """Exit async context."""
            del exc_type, exc_val, exc_tb

    def session(self, ctx: object = None) -> SessionContext:
        """Create a session context."""
        del ctx
        return self.SessionContext(self._session)


@pytest.mark.asyncio
async def test_gate_worker_runner_init_and_properties() -> None:
    """Runner initializes with poll interval and default harness registry."""
    runner = GateWorkerRunner(
        session_factory=None,
        poll_interval_s=0.25,
    )
    assert runner.poll_interval_s == 0.25
    assert runner.registry is not None
    assert runner.worker is not None


@pytest.mark.asyncio
async def test_gate_worker_runner_poll_once_empty() -> None:
    """Runner handles empty event queue gracefully."""
    mock_session = AsyncMock()
    # Return empty list of invocations
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    processed = await runner.poll_once()
    assert processed == 0


@pytest.mark.asyncio
async def test_start_gate_worker_lifecycle() -> None:
    """start_gate_worker launches a task that cancels cleanly on stop_event."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    session_factory = MockSessionFactory(mock_session)

    class DummyApp:
        class State:
            session_factory = None

        state = State()

    task, stop_event = await start_gate_worker(
        DummyApp(),
        session_target=session_factory,  # type: ignore[arg-type]
    )

    # Let worker run one cycle
    await asyncio.sleep(0.05)
    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()

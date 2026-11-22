# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for GateWorkerRunner FOR UPDATE SKIP LOCKED distributed claiming (KAN-69)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.gates.runner import GateWorkerRunner
from database.models.workflow import WorkflowHookInvocation

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
async def test_gate_runner_skip_locked_claiming() -> None:
    """Verify that GateWorkerRunner poll claims invocations with worker_id and TTL."""
    inv_id1 = uuid.uuid4()
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    mock_inv1 = MagicMock(spec=WorkflowHookInvocation)
    mock_inv1.id = inv_id1
    mock_inv1.execution_id = exec_id
    mock_inv1.hook_id = hook_id
    mock_inv1.status = "running"
    mock_inv1.hook_kind = "agent_interceptor"
    mock_inv1.started_at = dt.datetime.now(dt.UTC)
    mock_inv1.deadline_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=60)
    mock_inv1.claimed_by_worker = None
    mock_inv1.claim_expires_at = None

    mock_session = AsyncMock()
    captured_statements: list[object] = []

    def mock_execute(stmt: object) -> MagicMock:
        captured_statements.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_inv1]
        return result

    mock_session.execute = AsyncMock(side_effect=mock_execute)
    session_factory = MockSessionFactory(mock_session)

    runner = GateWorkerRunner(
        session_factory=session_factory,  # type: ignore[arg-type]
        workspace_id=ws_id,
        admin_principal_id=admin_id,
        worker_id="runner-worker-1",
    )
    runner.worker.handle_dispatch = AsyncMock()  # type: ignore[method-assign]

    processed = await runner.poll_once()
    assert processed == 1

    # Verify claim was stamped on inv1
    assert mock_inv1.claimed_by_worker == "runner-worker-1"
    assert mock_inv1.claim_expires_at is not None
    assert mock_inv1.claim_expires_at > dt.datetime.now(dt.UTC)

    # Verify session flush was called to persist claims immediately
    mock_session.flush.assert_called()

    # Verify the SQL statement included FOR UPDATE SKIP LOCKED
    assert len(captured_statements) >= 1
    stmt = captured_statements[0]
    for_update = getattr(stmt, "_for_update_arg", None)
    assert for_update is not None
    assert getattr(for_update, "skip_locked", None) is True

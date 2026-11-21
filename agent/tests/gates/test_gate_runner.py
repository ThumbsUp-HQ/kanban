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
import datetime as dt
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.gates.runner import GateWorkerRunner, start_gate_worker
from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue
from database.models.projects import Project, WorkflowState
from database.models.workflow import WorkflowTransitionExecution, WorkflowTransitionHook

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


@pytest.mark.asyncio
async def test_gate_worker_runner_dispatch_and_prevent_double_dispatch() -> None:
    """Runner dispatches pending running invocation once and guards against double-dispatch."""
    inv_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()

    mock_inv = MagicMock()
    mock_inv.id = inv_id
    mock_inv.execution_id = exec_id
    mock_inv.hook_id = hook_id
    mock_inv.status = "running"
    mock_inv.hook_kind = "agent_interceptor"
    mock_inv.started_at = dt.datetime.now(dt.UTC)
    mock_inv.deadline_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=60)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_inv]
    mock_session.execute.return_value = mock_result

    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    # Track dispatches on worker
    dispatches: list[dict[str, str]] = []

    async def fake_handle_dispatch(event: dict[str, str]) -> None:
        dispatches.append(event)
        # Verify active guard is active during dispatch execution
        assert inv_id in runner.active_invocations

    runner.worker.handle_dispatch = AsyncMock(side_effect=fake_handle_dispatch)  # type: ignore[method-assign]

    processed = await runner.poll_once()
    assert processed == 1
    assert len(dispatches) == 1
    assert dispatches[0]["execution_id"] == str(exec_id)
    assert dispatches[0]["hook_id"] == str(hook_id)

    # In-memory claim active: guard prevents double dispatch
    runner._active_invocations.add(inv_id)  # noqa: SLF001
    processed_2 = await runner.poll_once()
    assert processed_2 == 0
    assert len(dispatches) == 1  # Still 1, NOT double dispatched!


@pytest.mark.asyncio
async def test_gate_worker_runner_timeout_sweep() -> None:
    """Runner sweeps expired invocations and calls record_failure with GATE_TIMEOUT."""
    inv_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()

    mock_inv = MagicMock()
    mock_inv.id = inv_id
    mock_inv.execution_id = exec_id
    mock_inv.hook_id = hook_id
    mock_inv.status = "running"
    mock_inv.hook_kind = "agent_interceptor"
    mock_inv.started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=120)
    mock_inv.deadline_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_inv]
    mock_session.execute.return_value = mock_result

    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    with patch("agent.gates.runner.GateCoordinator") as mock_coord_cls:
        mock_coord_instance = AsyncMock()
        mock_coord_cls.return_value = mock_coord_instance

        processed = await runner.poll_once()
        assert processed == 1

        mock_coord_instance.record_failure.assert_awaited_once_with(
            invocation_id=inv_id,
            error_code="GATE_TIMEOUT",
            detail="Async agent gate exceeded deadline_at",
        )


@pytest.mark.asyncio
async def test_gate_worker_runner_record_decision_and_failure() -> None:
    """record_decision and record_failure invoke GateCoordinator within admin session."""
    # 1. Without session factory: no-op
    runner_no_sf = GateWorkerRunner(session_factory=None)
    await runner_no_sf.record_decision(uuid.uuid4(), uuid.uuid4(), "approve")
    await runner_no_sf.record_failure(uuid.uuid4(), uuid.uuid4(), "TIMEOUT")

    # 2. With session factory
    mock_session = AsyncMock()
    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()

    with patch("agent.gates.runner.GateCoordinator") as mock_coord_cls:
        mock_coord_cls.record_decision = AsyncMock()
        mock_coord_cls.record_failure = AsyncMock()

        await runner.record_decision(exec_id, hook_id, "approve")
        mock_coord_cls.record_decision.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

        mock_session.commit.reset_mock()
        await runner.record_failure(exec_id, hook_id, "ERROR_CODE")
        mock_coord_cls.record_failure.assert_awaited_once()
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_gate_worker_runner_load_entities_no_session_factory() -> None:
    """_load_entities returns event payload when session_factory is None."""
    runner_no_sf = GateWorkerRunner(session_factory=None)
    res_no_sf = await runner_no_sf._load_entities(  # noqa: SLF001
        {"execution": "ex", "issue": "iss", "agent_def": "ag"}
    )
    assert res_no_sf[0] == "ex"
    assert res_no_sf[1] == "iss"


@pytest.mark.asyncio
async def test_gate_worker_runner_load_entities() -> None:
    """_load_entities loads entities from DB when session_factory is present."""
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    agent_def_id = uuid.uuid4()
    issue_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    mock_session = AsyncMock()

    mock_exec = MagicMock()
    mock_exec.id = exec_id
    mock_exec.issue_id = issue_id
    mock_exec.project_id = proj_id
    mock_exec.from_state_id = uuid.uuid4()
    mock_exec.to_state_id = uuid.uuid4()
    mock_exec.invoking_principal_id = uuid.uuid4()

    mock_hook = MagicMock()
    mock_hook.agent_definition_id = agent_def_id
    mock_hook.allowed_mutable_fields = ("labels", "priority")

    mock_agent = MagicMock()
    mock_agent.slug = "test-agent"
    mock_agent.harness_kind = "in_app_sdk"
    mock_agent.timeout_ms = 30000
    mock_agent.repo_access_mode = "read-only"
    mock_agent.cli_binary_allowlist_id = None
    mock_agent.model_id = "test-model"

    mock_issue = MagicMock()
    mock_issue.id = issue_id
    mock_issue.sequence_id = 42
    mock_issue.summary = "Test issue"
    mock_issue.description_markdown = "Test desc"

    mock_proj = MagicMock()
    mock_proj.identifier = "TEST"

    mock_from = MagicMock()
    mock_from.name = "In Progress"

    mock_to = MagicMock()
    mock_to.name = "Done"

    entity_map: dict[object, object] = {
        WorkflowTransitionExecution: mock_exec,
        WorkflowTransitionHook: mock_hook,
        AgentDefinition: mock_agent,
        Issue: mock_issue,
        Project: mock_proj,
        WorkflowState: mock_to,
    }

    async def fake_get(model_cls: type, _key: uuid.UUID) -> object:
        return entity_map.get(model_cls)

    mock_session.get.side_effect = fake_get
    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    event = {
        "execution_id": str(exec_id),
        "hook_id": str(hook_id),
        "agent_definition_id": str(agent_def_id),
    }
    exec_dict, issue_dict, agent_dict, repo_ctx, _mcp_urls = await runner._load_entities(event)  # noqa: SLF001

    assert isinstance(exec_dict, dict)
    assert isinstance(issue_dict, dict)
    assert isinstance(agent_dict, dict)
    assert exec_dict["id"] == str(exec_id)
    assert issue_dict["key"] == "TEST-42"
    assert agent_dict["slug"] == "test-agent"
    assert repo_ctx is None


@pytest.mark.asyncio
async def test_gate_worker_runner_poll_once_inferred_deadline_and_exceptions() -> None:
    """poll_once infers deadline when None and handles dispatch/timeout exceptions gracefully."""
    inv_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()

    mock_inv = MagicMock()
    mock_inv.id = inv_id
    mock_inv.execution_id = exec_id
    mock_inv.hook_id = hook_id
    mock_inv.status = "running"
    mock_inv.hook_kind = "agent_interceptor"
    mock_inv.started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=120)
    mock_inv.deadline_at = None  # Inferred from hook / agent_def

    mock_hook = MagicMock()
    mock_hook.agent_definition_id = uuid.uuid4()

    mock_agent = MagicMock()
    mock_agent.timeout_ms = 30000

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_inv]
    mock_session.execute.return_value = mock_result

    hook_map: dict[object, object] = {
        WorkflowTransitionHook: mock_hook,
        AgentDefinition: mock_agent,
    }

    async def fake_get(model_cls: type, _key: uuid.UUID) -> object:
        return hook_map.get(model_cls)

    mock_session.get.side_effect = fake_get
    session_factory = MockSessionFactory(mock_session)
    runner = GateWorkerRunner(session_factory=session_factory)  # type: ignore[arg-type]

    # Test failure record exception branch
    with patch("agent.gates.runner.GateCoordinator") as mock_coord_cls:
        mock_coord_instance = AsyncMock()
        mock_coord_instance.record_failure.side_effect = RuntimeError("DB write error")
        mock_coord_cls.return_value = mock_coord_instance

        processed = await runner.poll_once()
        assert processed == 0  # Exception caught and logged

    # Test dispatch exception branch
    mock_inv.deadline_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=60)
    mock_inv.started_at = dt.datetime.now(dt.UTC)  # Not expired
    runner.worker.handle_dispatch = AsyncMock(side_effect=RuntimeError("Dispatch error"))  # type: ignore[method-assign]
    processed_dispatch_err = await runner.poll_once()
    assert processed_dispatch_err == 0


@pytest.mark.asyncio
async def test_gate_worker_runner_run_exception_and_start_worker_app_state() -> None:
    """Run handles exceptions in loop and start_gate_worker falls back.

    Verifies fallback to app.state.session_factory.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    session_factory = MockSessionFactory(mock_session)

    runner = GateWorkerRunner(session_factory=session_factory, poll_interval_s=0.01)  # type: ignore[arg-type]
    runner.poll_once = AsyncMock(side_effect=[RuntimeError("Loop error"), 0])  # type: ignore[method-assign]

    stop_event = asyncio.Event()
    task = asyncio.create_task(runner.run(stop_event))
    await asyncio.sleep(0.03)
    stop_event.set()
    await task
    assert task.done()

    # start_gate_worker with app.state.session_factory fallback
    app_obj = MagicMock()
    app_obj.state.session_factory = session_factory

    t2, s2 = await start_gate_worker(app_obj)
    s2.set()
    await t2
    assert t2.done()

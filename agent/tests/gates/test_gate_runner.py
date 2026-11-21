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
from agent.gates.worker import GateWorker, HarnessRegistry
from agent.providers.errors import ProviderTimeout
from agent.providers.gemini import GeminiProvider
from agent.providers.ollama import OllamaProvider
from agent.providers.openai_provider import OpenAIProvider
from database.models.agent_definition import AgentDefinition
from database.models.ai import AIProviderConfig
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


@pytest.mark.asyncio
async def test_gate_worker_runner_load_entities_wires_live_provider_and_timeout() -> None:  # noqa: PLR0915
    """_load_entities queries AIProviderConfig, unwraps key, and sets effective cutoff."""
    exec_id = uuid.uuid4()
    hook_id = uuid.uuid4()
    agent_def_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    mock_agent = MagicMock()
    mock_agent.slug = "live-gemini-agent"
    mock_agent.harness_kind = "in_app_sdk"
    mock_agent.provider_kind = "gemini"
    mock_agent.model_id = "gemini-2.5-flash-lite"
    mock_agent.timeout_ms = 45000
    mock_agent.repo_access_mode = "none"
    mock_agent.cli_binary_allowlist_id = None
    mock_agent.system_instructions_md = "Evaluate carefully"
    mock_agent.mcp_allowed_tools = ["read_ticket"]

    mock_exec = MagicMock()
    mock_exec.id = exec_id
    mock_exec.issue_id = uuid.uuid4()
    mock_exec.project_id = uuid.uuid4()
    mock_exec.from_state_id = uuid.uuid4()
    mock_exec.to_state_id = uuid.uuid4()
    mock_exec.invoking_principal_id = uuid.uuid4()

    mock_hook = MagicMock()
    mock_hook.agent_definition_id = agent_def_id
    mock_hook.allowed_mutable_fields = ("labels",)

    mock_cfg = MagicMock(spec=AIProviderConfig)
    mock_cfg.id = uuid.uuid4()
    mock_cfg.workspace_id = ws_id
    mock_cfg.provider_kind = "gemini"
    mock_cfg.display_name = "Gemini Express"
    mock_cfg.base_url = None
    mock_cfg.model_allowlist = ["gemini-2.5-flash-lite"]
    mock_cfg.settings_json = {"timeout_ms": 20000}
    mock_cfg.wrapped_api_key = b"encrypted"
    mock_cfg.residency_tier = "gemini-vertex:us-central1"

    mock_session = AsyncMock()

    async def fake_get(model_cls: type, _key: uuid.UUID) -> object:
        if model_cls == AgentDefinition:
            return mock_agent
        if model_cls == WorkflowTransitionExecution:
            return mock_exec
        if model_cls == WorkflowTransitionHook:
            return mock_hook
        return None

    mock_session.get.side_effect = fake_get

    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_exec_result

    with patch(
        "kanban.ai_config.service.AIProviderConfigService.unwrap_api_key",
        new_callable=AsyncMock,
    ) as mock_unwrap:
        mock_unwrap.return_value = bytearray(b"AQ.mockkey12345678901234567890")

        session_factory = MockSessionFactory(mock_session)
        runner = GateWorkerRunner(session_factory=session_factory, workspace_id=ws_id)  # type: ignore[arg-type]

        event = {
            "execution_id": str(exec_id),
            "hook_id": str(hook_id),
            "agent_definition_id": str(agent_def_id),
            "workspace_id": str(ws_id),
        }

        _ex, _iss, agent_dict, _rc, _mcp = await runner._load_entities(event)  # noqa: SLF001

        assert agent_dict["model"] == "gemini-2.5-flash-lite"
        assert agent_dict["model_identifier"] == "gemini-2.5-flash-lite"
        assert agent_dict["provider_kind"] == "gemini"
        assert agent_dict["system_instructions_md"] == "Evaluate carefully"
        assert agent_dict["mcp_allowed_tools"] == ["read_ticket"]
        assert agent_dict["timeout_ms"] == 20000  # min(20000, 45000)
        assert isinstance(agent_dict["provider"], GeminiProvider)
        assert runner.registry.get("in_app_sdk") is not None


@pytest.mark.asyncio
async def test_gate_worker_runner_load_entities_wires_ollama_and_openai_providers() -> None:  # noqa: PLR0915
    """_load_entities correctly builds Ollama and OpenAI providers and handles unwrap failures."""
    exec_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    mock_exec = MagicMock()
    mock_exec.id = exec_id
    mock_exec.issue_id = uuid.uuid4()
    mock_exec.project_id = uuid.uuid4()
    mock_exec.from_state_id = uuid.uuid4()
    mock_exec.to_state_id = uuid.uuid4()
    mock_exec.invoking_principal_id = uuid.uuid4()

    # 1. Ollama provider
    mock_agent_ollama = MagicMock()
    mock_agent_ollama.slug = "ollama-agent"
    mock_agent_ollama.harness_kind = "in_app_sdk"
    mock_agent_ollama.provider_kind = "ollama"
    mock_agent_ollama.model_id = "gemma3:4b"
    mock_agent_ollama.timeout_ms = 35000
    mock_agent_ollama.repo_access_mode = "none"
    mock_agent_ollama.cli_binary_allowlist_id = None
    mock_agent_ollama.system_instructions_md = ""
    mock_agent_ollama.mcp_allowed_tools = []

    mock_cfg_ollama = MagicMock(spec=AIProviderConfig)
    mock_cfg_ollama.id = uuid.uuid4()
    mock_cfg_ollama.workspace_id = ws_id
    mock_cfg_ollama.provider_kind = "ollama"
    mock_cfg_ollama.base_url = "http://127.0.0.1:11434"
    mock_cfg_ollama.model_allowlist = ["gemma3:4b"]
    mock_cfg_ollama.settings_json = {"timeout_ms": 30000}
    mock_cfg_ollama.wrapped_api_key = None

    mock_session_ollama = AsyncMock()
    mock_session_ollama.get.return_value = mock_agent_ollama
    mock_result_ollama = MagicMock()
    mock_result_ollama.scalar_one_or_none.return_value = mock_cfg_ollama
    mock_session_ollama.execute.return_value = mock_result_ollama

    runner_ollama = GateWorkerRunner(
        session_factory=MockSessionFactory(mock_session_ollama), workspace_id=ws_id  # type: ignore[arg-type]
    )
    event_ollama = {
        "execution_id": str(exec_id),
        "hook_id": str(uuid.uuid4()),
        "agent_definition_id": str(uuid.uuid4()),
    }
    _ex, _iss, agent_dict_ollama, _rc, _mcp = await runner_ollama._load_entities(event_ollama)  # noqa: SLF001
    assert isinstance(agent_dict_ollama["provider"], OllamaProvider)
    assert agent_dict_ollama["timeout_ms"] == 30000

    # 2. OpenAI provider with unwrapped key
    mock_agent_openai = MagicMock()
    mock_agent_openai.slug = "openai-agent"
    mock_agent_openai.harness_kind = "in_app_sdk"
    mock_agent_openai.provider_kind = "openai"
    mock_agent_openai.model_id = "gpt-4o-mini"
    mock_agent_openai.timeout_ms = 50000
    mock_agent_openai.repo_access_mode = "none"
    mock_agent_openai.cli_binary_allowlist_id = None
    mock_agent_openai.system_instructions_md = ""
    mock_agent_openai.mcp_allowed_tools = []

    mock_cfg_openai = MagicMock(spec=AIProviderConfig)
    mock_cfg_openai.id = uuid.uuid4()
    mock_cfg_openai.workspace_id = ws_id
    mock_cfg_openai.provider_kind = "openai"
    mock_cfg_openai.base_url = "https://api.openai.com/v1"
    mock_cfg_openai.model_allowlist = ["gpt-4o-mini"]
    mock_cfg_openai.settings_json = {"timeout_ms": 40000}
    mock_cfg_openai.wrapped_api_key = b"wrapped_secret_bytes"
    mock_cfg_openai.residency_tier = "openai-zdr-us"

    mock_session_openai = AsyncMock()
    mock_session_openai.get.return_value = mock_agent_openai
    mock_result_openai = MagicMock()
    mock_result_openai.scalar_one_or_none.return_value = mock_cfg_openai
    mock_session_openai.execute.return_value = mock_result_openai

    with patch(
        "kanban.ai_config.service.AIProviderConfigService.unwrap_api_key",
        return_value=b"sk-test-openai-key-valid-12345",
    ):
        runner_openai = GateWorkerRunner(
            session_factory=MockSessionFactory(mock_session_openai), workspace_id=ws_id  # type: ignore[arg-type]
        )
        event_openai = {
            "execution_id": str(exec_id),
            "hook_id": str(uuid.uuid4()),
            "agent_definition_id": str(uuid.uuid4()),
        }
        _ex, _iss, agent_dict_openai, _rc, _mcp = await runner_openai._load_entities(event_openai)  # noqa: SLF001
        assert isinstance(agent_dict_openai["provider"], OpenAIProvider)
        assert agent_dict_openai["timeout_ms"] == 40000

    # 3. OpenAI provider with corrupted key unwrap failure handled gracefully
    with patch(
        "kanban.ai_config.service.AIProviderConfigService.unwrap_api_key",
        side_effect=ValueError("Corrupted key envelope"),
    ):
        runner_openai_fail = GateWorkerRunner(
            session_factory=MockSessionFactory(mock_session_openai), workspace_id=ws_id  # type: ignore[arg-type]
        )
        event_openai_fail = {
            "execution_id": str(exec_id),
            "hook_id": str(uuid.uuid4()),
            "agent_definition_id": str(uuid.uuid4()),
        }
        _ex, _iss, agent_dict_openai_fail, _rc, _mcp = await runner_openai_fail._load_entities(  # noqa: SLF001
            event_openai_fail
        )
        assert agent_dict_openai_fail.get("provider") is None
        assert agent_dict_openai_fail["timeout_ms"] == 40000



@pytest.mark.asyncio
async def test_gate_worker_fail_closed_on_provider_timeout() -> None:
    """GateWorker fails closed with GATE_TIMEOUT when provider raises ProviderTimeout."""
    mock_coordinator = AsyncMock()
    registry = HarnessRegistry()

    class TimingOutHarness:
        async def run(self, _ctx: object, _agent_def: object) -> bytes:
            msg = "Upstream request timed out: deadline breached"
            raise ProviderTimeout(msg, code="TIMEOUT")

    registry.register("in_app_sdk", TimingOutHarness())  # type: ignore[arg-type]

    worker = GateWorker(registry=registry, coordinator=mock_coordinator)

    event = {
        "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
        "hook_id": "0196ed40-7b2a-7000-8000-223344556677",
        "harness_kind": "in_app_sdk",
        "timeout_ms": 5000,
        "to_state": "Done",
    }

    await worker.handle_dispatch(event)

    mock_coordinator.record_failure.assert_called_once_with(
        "0196ed40-7b2a-7000-8000-112233445566",
        "0196ed40-7b2a-7000-8000-223344556677",
        "GATE_TIMEOUT",
    )


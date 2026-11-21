# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for GateWorker and harness execution (KB-P5-19a)."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest import mock

from agent.gates.worker import (
    GateWorker,
    HarnessRegistry,
)

if TYPE_CHECKING:
    from agent.context.transition_context import RenderedContext


class MockCoordinator:
    """Mock GateCoordinator tracking recorded decisions and failures."""

    def __init__(self) -> None:
        """Initialize mock coordinator."""
        self.decisions: list[tuple[object, object, object]] = []
        self.failures: list[tuple[object, object, str]] = []

    async def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> None:
        """Record decision in internal tracking list."""
        self.decisions.append((execution_id, hook_id, decision))

    async def record_failure(self, execution_id: object, hook_id: object, code: str) -> None:
        """Record failure code in internal tracking list."""
        self.failures.append((execution_id, hook_id, code))


class MockSuccessHarness:
    """Harness returning a valid verdict with the context's nonce."""

    def __init__(self, decision: str = "approve") -> None:
        """Initialize with desired decision."""
        self.decision = decision
        self.last_ctx: RenderedContext | None = None

    async def run(self, ctx: RenderedContext, _agent_def: object) -> bytes:
        """Return valid verdict payload matching ctx nonce."""
        self.last_ctx = ctx
        payload = {
            "schema": "kb-transition-verdict/v1",
            "nonce": ctx.verdict_nonce,
            "decision": self.decision,
            "reason_markdown": "Gate criteria satisfied.",
            "field_updates": {},
            "add_labels": ["security-gate-passed"],
            "add_links": [],
        }
        return json.dumps(payload).encode()


class MockTimeoutHarness:
    """Harness that sleeps longer than deadline."""

    async def run(self, _ctx: RenderedContext, _agent_def: object) -> bytes:
        """Sleep to trigger timeout."""
        await asyncio.sleep(1.0)
        return b""


class MockFailingHarness:
    """Harness that raises an execution error."""

    async def run(self, _ctx: RenderedContext, _agent_def: object) -> bytes:
        """Raise runtime error simulating failure."""
        msg = "Process failed with status 137"
        raise RuntimeError(msg)


def _make_event(
    harness_kind: str = "cli_pipe",
    timeout_ms: int = 50,
) -> dict[str, object]:
    return {
        "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
        "hook_id": "0196ed40-7b2a-7000-8000-998877665544",
        "project_key": "KAN",
        "agent_def": {
            "slug": "sec-gate",
            "harness_kind": harness_kind,
            "timeout_ms": timeout_ms,
        },
        "issue": {
            "key": "KAN-142",
            "summary": "Sample Issue",
            "description_markdown": "Test description",
        },
    }


async def test_worker_success_records_decision_and_destroys_token() -> None:
    """Test Case 6: Registered harness succeeds, decision recorded, token destroyed."""
    registry = HarnessRegistry()
    harness = MockSuccessHarness()
    registry.register("cli_pipe", harness)

    coordinator = MockCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = _make_event("cli_pipe", timeout_ms=500)
    await worker.handle_dispatch(event)

    assert len(coordinator.decisions) == 1
    execution_id, hook_id, decision = coordinator.decisions[0]
    assert execution_id == "0196ed40-7b2a-7000-8000-112233445566"
    assert hook_id == "0196ed40-7b2a-7000-8000-998877665544"
    assert getattr(decision, "decision", "") == "approve"
    assert getattr(decision, "add_labels", ()) == ("security-gate-passed",)

    # Verify token zeroization in finally block
    assert harness.last_ctx is not None
    assert len(harness.last_ctx.ephemeral_token) == 0


async def test_worker_unregistered_harness_records_unavailable() -> None:
    """Test Case 6: Unregistered harness records HARNESS_UNAVAILABLE."""
    registry = HarnessRegistry()
    coordinator = MockCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = _make_event("unknown_harness")
    await worker.handle_dispatch(event)

    assert len(coordinator.failures) == 1
    execution_id, _hook_id, code = coordinator.failures[0]
    assert execution_id == "0196ed40-7b2a-7000-8000-112233445566"
    assert code == "HARNESS_UNAVAILABLE"


async def test_worker_timeout_records_gate_timeout() -> None:
    """Test Case 6: Harness exceeding timeout_ms records GATE_TIMEOUT."""
    registry = HarnessRegistry()
    registry.register("cli_pipe", MockTimeoutHarness())

    coordinator = MockCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = _make_event("cli_pipe", timeout_ms=20)
    await worker.handle_dispatch(event)

    assert len(coordinator.failures) == 1
    _exec_id, _hook_id, code = coordinator.failures[0]
    assert code == "GATE_TIMEOUT"


async def test_worker_parse_error_records_failure_code() -> None:
    """Test Case 6: Harness producing malformed output records parse failure code."""
    registry = HarnessRegistry()

    class MalformedHarness:
        async def run(self, _ctx: RenderedContext, _agent_def: object) -> bytes:
            return b"plain prose without json"

    registry.register("cli_pipe", MalformedHarness())

    coordinator = MockCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = _make_event("cli_pipe", timeout_ms=500)
    await worker.handle_dispatch(event)

    assert len(coordinator.failures) == 1
    _exec_id, _hook_id, code = coordinator.failures[0]
    assert code == "VERDICT_MALFORMED"


async def test_worker_harness_exception_records_gate_execution_error() -> None:
    """Test Case 6: Harness exception records GATE_EXECUTION_ERROR."""
    registry = HarnessRegistry()
    registry.register("cli_pipe", MockFailingHarness())

    coordinator = MockCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = _make_event("cli_pipe", timeout_ms=500)
    await worker.handle_dispatch(event)

    assert len(coordinator.failures) == 1
    _exec_id, _hook_id, code = coordinator.failures[0]
    assert code.startswith("HARNESS_ERROR")


async def test_worker_custom_entity_loader_and_sync_coordinator() -> None:
    """Worker handles custom entity loader and synchronous coordinator methods."""
    registry = HarnessRegistry()
    registry.register("cli_pipe", MockSuccessHarness())
    assert "cli_pipe" in registry
    assert "missing" not in registry

    class SyncCoordinator:
        def __init__(self) -> None:
            self.decisions: list[object] = []

        def record_decision(self, execution_id: object, hook_id: object, decision: object) -> None:
            self.decisions.append((execution_id, hook_id, decision))

    async def custom_loader(_event: object) -> tuple[object, object, object, object, object]:
        execution = {
            "id": "custom-exec-id",
            "project_key": "KAN",
            "from_state": "In Review",
            "to_state": "Done",
            "actor": "@bot",
        }
        issue = {"key": "KAN-200", "summary": "Custom issue"}
        agent_def = {"slug": "custom-agent", "harness_kind": "cli_pipe", "timeout_ms": 1000}
        return execution, issue, agent_def, None, None

    sync_coord = SyncCoordinator()
    worker = GateWorker(
        registry=registry,
        coordinator=sync_coord,
        entity_loader=custom_loader,
    )

    await worker.handle_dispatch({"any": "event"})
    assert len(sync_coord.decisions) == 1
    first_dec = sync_coord.decisions[0]
    assert isinstance(first_dec, tuple)
    assert first_dec[0] == "custom-exec-id"


async def test_worker_none_coordinator_safe() -> None:
    """Worker safely runs without raising when coordinator is None."""
    registry = HarnessRegistry()
    registry.register("cli_pipe", MockSuccessHarness())
    worker = GateWorker(registry=registry, coordinator=None)
    event = _make_event("cli_pipe")
    await worker.handle_dispatch(event)


async def test_worker_entity_load_failure() -> None:
    """Worker records failure when entity loading raises an exception."""
    registry = HarnessRegistry()
    coordinator = MockCoordinator()

    async def bad_loader(_event: object) -> tuple[object, object, object, object, object]:
        msg = "Database connection lost"
        raise RuntimeError(msg)

    worker = GateWorker(
        registry=registry,
        coordinator=coordinator,
        entity_loader=bad_loader,
    )
    await worker.handle_dispatch({"execution_id": "exec-bad"})
    assert len(coordinator.failures) == 1
    assert coordinator.failures[0][0] == "exec-bad"
    assert "ENTITY_LOAD_FAILED" in coordinator.failures[0][2]


async def test_worker_register_defaults_import_error() -> None:
    """_register_defaults catches and ignores ImportError."""
    with mock.patch.dict("sys.modules", {"agent.harnesses.in_app_sdk": None}):
        reg = HarnessRegistry(register_defaults=True)
        assert reg.get("in_app_sdk") is None


async def test_worker_invoke_coordinator_none() -> None:
    """_invoke_coordinator returns None if coordinator is None."""
    worker = GateWorker(registry=HarnessRegistry(), coordinator=None)
    await worker._invoke_coordinator("record_decision", "ex", "hk", {})  # noqa: SLF001


async def test_worker_handle_dispatch_unexpected_exception() -> None:
    """Worker records VERDICT_MALFORMED when verdict parsing raises unexpected exception."""
    coordinator = MockCoordinator()
    registry = HarnessRegistry()

    class CorruptHarness:
        async def run(self, _ctx: object, _agent_def: object) -> bytes:
            return b"some-output"

    registry.register("in_app_sdk", CorruptHarness())
    worker = GateWorker(registry=registry, coordinator=coordinator)
    event = _make_event("in_app_sdk")

    with mock.patch("agent.gates.worker.parse_verdict_output", side_effect=ValueError("Corrupt")):
        await worker.handle_dispatch(event)

    assert len(coordinator.failures) == 1
    assert "VERDICT_MALFORMED: Corrupt" in coordinator.failures[0][2]

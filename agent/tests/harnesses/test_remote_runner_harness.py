# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for RemoteRunnerHarness and GateWorker integration (KB-P5-22a, S14.2)."""

from __future__ import annotations

import base64
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from agent.context.transition_context import RepoContext
from agent.gates.worker import GateWorker, HarnessRegistry
from agent.harnesses.remote_runner import (
    RemoteRunnerHarness,
    register_remote_runner_harness,
)
from kanban.runners.hub import (
    RemoteRunnerDisconnectedError,
    RemoteRunnerRevokedError,
    RemoteRunnerUnavailableError,
    RunnerWssHub,
    get_global_hub,
)

if TYPE_CHECKING:
    from agent.context.transition_context import RenderedContext


@dataclass
class DummyContext:
    """Mock RenderedContext matching agent.context.transition_context.RenderedContext."""

    yaml_bytes: bytes = b"issue:\n  key: KAN-100\n"
    ephemeral_token: bytes | str | None = b"kb_agt_eph_test_token"
    workspace_id: uuid.UUID = field(default_factory=lambda: uuid.UUID(int=1))
    execution_id: str = "exec-test-123"
    repo_context: RepoContext | None = None


class RecordingCoordinator:
    """Mock GateCoordinator recording decisions and failures."""

    def __init__(self) -> None:
        """Initialize empty records."""
        self.decisions: list[tuple[object, object, object]] = []
        self.failures: list[tuple[object, object, str]] = []

    async def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> None:
        """Record transition decision."""
        self.decisions.append((execution_id, hook_id, decision))

    async def record_failure(self, execution_id: object, hook_id: object, code: str) -> None:
        """Record transition failure."""
        self.failures.append((execution_id, hook_id, code))


class FakeDispatchHub:
    """In-memory mock hub recording dispatch calls and returning preset responses."""

    def __init__(self) -> None:
        """Initialize records and errors."""
        self.dispatches: list[dict[str, Any]] = []
        self.raise_exc: Exception | None = None

    async def dispatch_job(
        self,
        workspace_id: uuid.UUID,
        pool_slug: str,
        job_spec: dict[str, Any],
        timeout_s: float | None = None,
    ) -> bytes:
        """Record dispatch call and return mock payload or raise error."""
        self.dispatches.append(
            {
                "workspace_id": workspace_id,
                "pool_slug": pool_slug,
                "job_spec": job_spec,
                "timeout_s": timeout_s,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc

        nonce = "test-nonce-12345678"
        raw_b64 = job_spec.get("context_yaml_b64")
        if raw_b64:
            with contextlib.suppress(Exception):
                parsed = yaml.safe_load(base64.b64decode(raw_b64))
                if isinstance(parsed, dict) and "verdict_nonce" in parsed:
                    nonce = parsed["verdict_nonce"]

        return json.dumps(
            {
                "schema": "kb-transition-verdict/v1",
                "nonce": nonce,
                "decision": "approve",
                "reason_markdown": "Remote audit passed flawlessly.",
            }
        ).encode("utf-8")


def test_harness_registration_and_hub_property() -> None:
    """Verify register_remote_runner_harness registers under kind 'remote_runner'."""
    registry = HarnessRegistry()
    fake_hub = RunnerWssHub()

    harness = register_remote_runner_harness(registry, hub=fake_hub)
    assert "remote_runner" in registry
    assert registry.get("remote_runner") is harness
    assert harness.hub is fake_hub

    # Default hub fallback
    default_harness = RemoteRunnerHarness()
    assert default_harness.hub is get_global_hub()


@pytest.mark.asyncio
async def test_harness_run_validates_pool_slug() -> None:
    """Verify run raises ValueError when agent_def has no remote_runner_pool_slug."""
    harness = RemoteRunnerHarness()
    ctx = DummyContext()

    # Empty agent def
    with pytest.raises(ValueError, match="must specify remote_runner_pool_slug"):
        await harness.run(cast("RenderedContext", ctx), {})

    # Agent def with None slug
    with pytest.raises(ValueError, match="must specify remote_runner_pool_slug"):
        await harness.run(cast("RenderedContext", ctx), {"remote_runner_pool_slug": ""})


@pytest.mark.asyncio
async def test_harness_run_dispatches_with_mapped_spec() -> None:
    """Verify context and agent_def fields are correctly mapped into JobDispatchFrame spec."""
    fake_hub = FakeDispatchHub()
    harness = RemoteRunnerHarness(hub=fake_hub)  # type: ignore[arg-type]

    ws_id = uuid.uuid4()
    repo_ctx = RepoContext(
        head_commit="abcdef0123456789",
    )
    ctx = DummyContext(
        yaml_bytes=b"issue_summary: Hello",
        ephemeral_token=b"kb_agt_eph_xyz",
        workspace_id=ws_id,
        execution_id="exec-456",
        repo_context=repo_ctx,
    )

    agent_def = {
        "remote_runner_pool_slug": "gpu-fast",
        "provider_kind": "custom",
        "model_id": "model-v1",
        "cli_binary_allowlist_id": "cli-1",
        "cli_args_json": ["--verbose"],
        "repo_access_mode": "read-only",
        "mcp_allowed_tools": ["search", "fetch"],
        "system_instructions_md": "Check thoroughly",
        "timeout_ms": 30_000,
    }

    result = await harness.run(cast("RenderedContext", ctx), agent_def)
    assert b"kb-transition-verdict/v1" in result

    assert len(fake_hub.dispatches) == 1
    dispatch = fake_hub.dispatches[0]
    assert dispatch["workspace_id"] == ws_id
    assert dispatch["pool_slug"] == "gpu-fast"
    assert dispatch["timeout_s"] == 30.0

    job_spec = dispatch["job_spec"]
    assert job_spec["execution_id"] == "exec-456"
    assert job_spec["ephemeral_mcp_token"] == "kb_agt_eph_xyz"
    assert job_spec["head_commit"] == "abcdef0123456789"
    assert job_spec["context_yaml_b64"] == base64.b64encode(b"issue_summary: Hello").decode("ascii")

    spec = job_spec["agent_spec"]
    assert spec["harness_mode"] == "remote_runner"
    assert spec["provider_kind"] == "custom"
    assert spec["cli_args"] == ["--verbose"]
    assert spec["mcp_allowed_tools"] == ["search", "fetch"]


@pytest.mark.asyncio
async def test_gate_worker_positive_verdict_integration() -> None:
    """Verify GateWorker receives stdout from RemoteRunnerHarness and records decision."""
    fake_hub = FakeDispatchHub()
    registry = HarnessRegistry()
    register_remote_runner_harness(registry, hub=fake_hub)  # type: ignore[arg-type]

    coordinator = RecordingCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = {
        "execution_id": "exec-gate-1",
        "hook_id": "hook-sec-1",
        "agent_def": {
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "audit-pool",
        },
        "execution": {
            "id": "exec-gate-1",
            "workspace_id": str(uuid.uuid4()),
        },
    }

    await worker.handle_dispatch(event)

    assert len(coordinator.decisions) == 1
    exec_id, hook_id, decision = coordinator.decisions[0]
    assert exec_id == "exec-gate-1"
    assert hook_id == "hook-sec-1"
    assert getattr(decision, "decision", None) == "approve"
    assert len(coordinator.failures) == 0


@pytest.mark.asyncio
async def test_gate_worker_revoked_runner_records_failure() -> None:
    """Verify GateWorker records REMOTE_RUNNER_REVOKED when runner is revoked during job."""
    fake_hub = FakeDispatchHub()
    fake_hub.raise_exc = RemoteRunnerRevokedError("REMOTE_RUNNER_REVOKED")

    registry = HarnessRegistry()
    register_remote_runner_harness(registry, hub=fake_hub)  # type: ignore[arg-type]

    coordinator = RecordingCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    event = {
        "execution_id": "exec-revoked-1",
        "hook_id": "hook-sec-2",
        "agent_def": {
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "audit-pool",
        },
    }

    await worker.handle_dispatch(event)

    assert len(coordinator.decisions) == 0
    assert len(coordinator.failures) == 1
    exec_id, hook_id, code = coordinator.failures[0]
    assert exec_id == "exec-revoked-1"
    assert hook_id == "hook-sec-2"
    assert "REMOTE_RUNNER_REVOKED" in code


@pytest.mark.asyncio
async def test_gate_worker_disconnected_and_pool_offline_records_failure() -> None:
    """Verify GateWorker records failure on disconnect or pool offline."""
    fake_hub = FakeDispatchHub()
    registry = HarnessRegistry()
    register_remote_runner_harness(registry, hub=fake_hub)  # type: ignore[arg-type]

    coordinator = RecordingCoordinator()
    worker = GateWorker(registry=registry, coordinator=coordinator)

    # 1. Disconnected
    fake_hub.raise_exc = RemoteRunnerDisconnectedError("REMOTE_RUNNER_DISCONNECTED")
    event1 = {
        "execution_id": "exec-disc-1",
        "hook_id": "hook-1",
        "agent_def": {
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "pool-disc",
        },
    }
    await worker.handle_dispatch(event1)
    assert len(coordinator.failures) == 1
    assert "REMOTE_RUNNER_DISCONNECTED" in coordinator.failures[0][2]

    # 2. Pool offline
    fake_hub.raise_exc = RemoteRunnerUnavailableError("REMOTE_RUNNER_POOL_OFFLINE")
    event2 = {
        "execution_id": "exec-offline-1",
        "hook_id": "hook-2",
        "agent_def": {
            "harness_kind": "remote_runner",
            "remote_runner_pool_slug": "empty-pool",
        },
    }
    await worker.handle_dispatch(event2)
    assert len(coordinator.failures) == 2
    assert "REMOTE_RUNNER_POOL_OFFLINE" in coordinator.failures[1][2]


@pytest.mark.asyncio
async def test_remote_runner_harness_variations_and_branches() -> None:
    """Verify object agent_def, token formats, default timeouts, and missing pool validation."""
    fake_hub = FakeDispatchHub()
    harness = RemoteRunnerHarness(hub=fake_hub)  # type: ignore[arg-type]

    # 1. Missing pool slug -> ValueError
    bad_def = SimpleNamespace(remote_runner_pool_slug=None)
    with pytest.raises(ValueError, match="remote_runner_pool_slug"):
        await harness.run(cast("RenderedContext", DummyContext()), bad_def)

    # 2. Object agent_def + string token + default timeout
    obj_def = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        remote_runner_pool_slug="object-pool",
        timeout_ms=None,
        cli_args=["--obj-arg"],
        mcp_allowed_tools=["read_ticket"],
        repo_access_mode="ro_vfs_mount",
        system_instructions_md="Follow all invariants.",
        provider_kind=None,
        model_id=None,
        cli_binary_allowlist_id=None,
    )
    ctx_str = DummyContext(
        ephemeral_token="kb_agt_eph_plaintext_string",  # noqa: S106
    )
    res = await harness.run(cast("RenderedContext", ctx_str), obj_def)
    assert b"Remote audit passed" in res
    assert fake_hub.dispatches[-1]["timeout_s"] == 60.0
    assert (
        fake_hub.dispatches[-1]["job_spec"]["ephemeral_mcp_token"] == "kb_agt_eph_plaintext_string"
    )

    # 3. None token + int token + None workspace in context
    ctx_none = DummyContext(
        ephemeral_token=None,
        workspace_id=None,  # type: ignore[arg-type]
    )
    obj_no_ws = SimpleNamespace(
        remote_runner_pool_slug="no-ws-pool",
        timeout_ms=15000,
    )
    await harness.run(cast("RenderedContext", ctx_none), obj_no_ws)
    assert fake_hub.dispatches[-1]["workspace_id"] == uuid.UUID(int=0)
    assert fake_hub.dispatches[-1]["job_spec"]["ephemeral_mcp_token"] == ""

    # 4. Int token branch
    ctx_int = DummyContext(
        ephemeral_token=99999,  # type: ignore[arg-type]
    )
    await harness.run(cast("RenderedContext", ctx_int), obj_no_ws)
    assert fake_hub.dispatches[-1]["job_spec"]["ephemeral_mcp_token"] == "99999"

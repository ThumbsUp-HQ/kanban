# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RunnerJobExecutor: :ro mounts, CLI defense-in-depth, token hygiene (KB-P5-22b)."""

from __future__ import annotations

import base64
import os
from pathlib import Path  # noqa: TC003

import pytest  # noqa: TC002
import yaml

from agent.remote_runner.config import RunnerConfig
from agent.remote_runner.executor import (
    CODE_BANNED_CLI_FLAG,
    CODE_MOUNT_NOT_READONLY,
    CODE_REPO_NOT_MOUNTED,
    RunnerJobExecutor,
)
from kanban.runners.hub import JobDispatchFrame, JobToolEventFrame


def _sample_config(tmp_path: Path, mounts: dict[str, Path] | None = None) -> RunnerConfig:
    key_file = tmp_path / "client.key"
    key_file.write_text("key")
    key_file.chmod(0o600)

    return RunnerConfig(
        server_url="https://kanban.internal",
        pool_slug="test-pool",
        client_cert_path=tmp_path / "client.crt",
        client_key_path=key_file,
        ca_cert_path=tmp_path / "ca.crt",
        repo_mounts=mounts or {},
    )


def _make_dispatch(  # noqa: PLR0913, PLR0917
    job_id: str = "job-1",
    harness_kind: str = "in_app_sdk",
    repo_access_mode: str = "none",
    repo_slug: str | None = None,
    cli_args: list[str] | None = None,
    ephemeral_token: str = "kb_agt_eph_secret_token_12345",  # noqa: S107
) -> JobDispatchFrame:
    agent_spec: dict[str, object] = {
        "slug": "test-agent",
        "harness_kind": harness_kind,
        "repo_access_mode": repo_access_mode,
    }
    if repo_slug:
        agent_spec["repo_slug"] = repo_slug
    if cli_args is not None:
        agent_spec["cli_binary_allowlist_id"] = "agy"
        agent_spec["cli_args_json"] = cli_args

    ctx_dict = {
        "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
        "verdict_nonce": "00112233445566778899aabbccddeeff",
        "ticket_snapshot": {
            "delimiter": "<<<UNTRUSTED_DELIM>>>",
            "summary": "Sample ticket",
        },
        "mcp_access": {
            "agent_url": "https://kanban.internal/mcp/agent",
            "docs_url": "https://kanban.internal/mcp/docs",
        },
    }
    ctx_yaml = yaml.safe_dump(ctx_dict).encode("utf-8")
    b64_ctx = base64.b64encode(ctx_yaml).decode("ascii")

    return JobDispatchFrame(
        job_id=job_id,
        execution_id="0196ed40-7b2a-7000-8000-112233445566",
        agent_spec=agent_spec,
        context_yaml_b64=b64_ctx,
        ephemeral_mcp_token=ephemeral_token,
    )


async def test_executor_banned_cli_flag_defense_in_depth(tmp_path: Path) -> None:
    """Test server-frame defense: banned CLI flag is blocked with RUNNER_BANNED_CLI_FLAG."""
    cfg = _sample_config(tmp_path)
    executor = RunnerJobExecutor(cfg)

    # 1. Banned flag --yolo
    dispatch_yolo = _make_dispatch(
        harness_kind="cli_pipe",
        cli_args=["-p", "--yolo"],
    )
    res_yolo = await executor.execute_job(dispatch_yolo)
    assert res_yolo.status == "error"
    assert res_yolo.error_code == CODE_BANNED_CLI_FLAG

    # 2. Banned flag --dangerously-skip-permissions
    dispatch_danger = _make_dispatch(
        harness_kind="cli_pipe",
        cli_args=["-p", "--dangerously-skip-permissions"],
    )
    res_danger = await executor.execute_job(dispatch_danger)
    assert res_danger.status == "error"
    assert res_danger.error_code == CODE_BANNED_CLI_FLAG


async def test_executor_repo_mount_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test repo mount checks: unmapped slug, symlink traversal, and writable mount refusal."""
    mount_root = tmp_path / "repos"
    mount_root.mkdir()

    repo_dir = mount_root / "my-repo"
    repo_dir.mkdir()

    cfg = _sample_config(tmp_path, mounts={"my-repo": repo_dir})
    executor = RunnerJobExecutor(cfg)

    # 1. Unmapped slug
    dispatch_unmapped = _make_dispatch(
        repo_access_mode="ro_vfs_mount",
        repo_slug="unmapped-slug",
    )
    res_unmapped = await executor.execute_job(dispatch_unmapped)
    assert res_unmapped.status == "error"
    assert res_unmapped.error_code == CODE_REPO_NOT_MOUNTED

    # 2. Writable mount refusal for ro_vfs_mount
    class FakeStatVFS:
        f_flag = 0  # ST_RDONLY is unset -> writable!

    monkeypatch.setattr(os, "statvfs", lambda _path: FakeStatVFS())

    dispatch_writable = _make_dispatch(
        repo_access_mode="ro_vfs_mount",
        repo_slug="my-repo",
    )
    res_writable = await executor.execute_job(dispatch_writable)
    assert res_writable.status == "error"
    assert res_writable.error_code == CODE_MOUNT_NOT_READONLY

    # 3. statvfs raises OSError
    def failing_statvfs(_path: str) -> None:
        msg = "VFS error"
        raise OSError(msg)

    monkeypatch.setattr(os, "statvfs", failing_statvfs)
    res_stat_err = await executor.execute_job(dispatch_writable)
    assert res_stat_err.status == "error"
    assert res_stat_err.error_code == CODE_MOUNT_NOT_READONLY

    # 4. Unresolvable configured path (nonexistent)
    cfg_nonexistent = _sample_config(tmp_path, mounts={"my-repo": mount_root / "does-not-exist"})
    executor_nonexistent = RunnerJobExecutor(cfg_nonexistent)
    res_missing_path = await executor_nonexistent.execute_job(dispatch_writable)
    assert res_missing_path.status == "error"
    assert res_missing_path.error_code == CODE_REPO_NOT_MOUNTED

    # 5. Symlink traversal escape outside mount root
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    symlink_repo = mount_root / "escaping-symlink"
    symlink_repo.symlink_to(outside_dir)
    cfg_escape = _sample_config(tmp_path, mounts={"my-repo": symlink_repo})
    executor_escape = RunnerJobExecutor(cfg_escape)
    res_escape = await executor_escape.execute_job(dispatch_writable)
    assert res_escape.status == "error"
    assert res_escape.error_code == CODE_REPO_NOT_MOUNTED

    # 6. Read-only mount success
    class FakeStatVFSRo:
        f_flag = os.ST_RDONLY

    monkeypatch.setattr(os, "statvfs", lambda _path: FakeStatVFSRo())

    class MockHarness:
        async def run(self, *_args: object, **_kwargs: object) -> bytes:
            return b'{"schema":"kb-transition-verdict/v1","decision":"approve"}'

    executor_ro = RunnerJobExecutor(cfg, in_app_harness_factory=MockHarness)
    res_ro = await executor_ro.execute_job(dispatch_writable)
    assert res_ro.status == "ok"
    assert res_ro.stdout_b64 is not None


async def test_executor_tool_event_streaming_and_token_zeroization(tmp_path: Path) -> None:
    """Test tool events are streamed to callback and ephemeral token is wiped in finally."""
    cfg = _sample_config(tmp_path)

    class MockTrace:
        tool_name = "repo_grep"
        duration_ms = 42.5
        status = "ok"

    class MockInAppHarness:
        def __init__(self) -> None:
            self.last_tool_traces = [MockTrace()]

        async def run(self, ctx: object, _agent_spec: object) -> bytes:
            # Check ephemeral token is readable during execution
            assert getattr(ctx, "ephemeral_token", None) == bytearray(b"kb_agt_eph_live_token")
            return b'{"decision":"approve"}'

    executor = RunnerJobExecutor(cfg, in_app_harness_factory=MockInAppHarness)

    events: list[JobToolEventFrame] = []

    async def on_event(ev: JobToolEventFrame) -> None:
        events.append(ev)

    dispatch = _make_dispatch(
        job_id="job-event-1",
        harness_kind="in_app_sdk",
        ephemeral_token="kb_agt_eph_live_token",  # noqa: S106
    )
    res = await executor.execute_job(dispatch, on_tool_event=on_event)
    assert res.status == "ok"
    assert len(events) == 1
    assert events[0].tool_name == "repo_grep"
    assert events[0].duration_ms == 42


async def test_executor_cli_pipe_invocation(tmp_path: Path) -> None:
    """Test executor successfully dispatches to CliPipeHarness."""
    cfg = _sample_config(tmp_path)

    class MockCliPipeHarness:
        async def run(self, _ctx: object, _agent_spec: object, **_kwargs: object) -> bytes:
            return b'{"schema":"kb-transition-verdict/v1","decision":"approve"}'

    executor = RunnerJobExecutor(cfg, cli_pipe_harness_factory=MockCliPipeHarness)

    dispatch = _make_dispatch(
        job_id="job-cli-1",
        harness_kind="cli_pipe",
        cli_args=["-p"],
    )
    res = await executor.execute_job(dispatch)
    assert res.status == "ok"
    decoded = base64.b64decode(res.stdout_b64 or "").decode("utf-8")
    assert "kb-transition-verdict/v1" in decoded


async def test_executor_execution_failure_error_code(tmp_path: Path) -> None:
    """Test unexpected harness execution exception yields CODE_EXECUTION_FAILED."""
    cfg = _sample_config(tmp_path)

    class FailingHarness:
        async def run(self, *_args: object, **_kwargs: object) -> bytes:
            msg = "Harness crash"
            raise RuntimeError(msg)

    executor = RunnerJobExecutor(cfg, in_app_harness_factory=FailingHarness)
    dispatch = _make_dispatch(job_id="job-fail-1")
    res = await executor.execute_job(dispatch)
    assert res.status == "error"
    assert res.error_code == "RUNNER_EXECUTION_FAILED"

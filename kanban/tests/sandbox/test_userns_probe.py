# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: TC002, TC003, ANN401, D102, D107, ARG001, TRY003, EM101
"""Tests for startup CLONE_NEWUSER probe and standalone status reporting (KB-P5-14)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from deploy.standalone.storage_probe import StandaloneStatus, probe_storage
from kanban.sandbox.probe import (
    SandboxProbeResult,
    get_cached_sandbox_probe,
    probe_nsjail_userns,
    reset_cached_sandbox_probe,
    set_cached_sandbox_probe,
)


class FakeSubprocessLauncher:
    """Configurable subprocess launcher for probing nsjail."""

    def __init__(self, exit_code: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.recorded_cmds: list[list[str]] = []

    def run_sync(
        self,
        argv: list[str],
        *,
        timeout_seconds: float = 1.0,
    ) -> tuple[int, bytes, bytes]:
        del timeout_seconds
        self.recorded_cmds.append(argv)
        return self.exit_code, self.stdout, self.stderr


def test_probe_missing_nsjail_binary(tmp_path: Path) -> None:
    """Missing nsjail binary returns available=False with SANDBOX_UNAVAILABLE_IN_STANDALONE."""
    ghost_bin = tmp_path / "ghost_nsjail"
    result = probe_nsjail_userns(nsjail_bin=ghost_bin)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "not found" in (result.message or "")


def test_probe_invalid_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Binary not owned by UID 0 returns available=False fail-closed."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o755)

    # Mock os.stat returning st_uid = 1000
    real_stat = Path.stat

    def fake_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        orig = real_stat(path_obj, *args, **kwargs)
        mock_res = MagicMock(spec=orig)
        mock_res.st_uid = 1000
        mock_res.st_mode = 0o100755
        return mock_res

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = probe_nsjail_userns(nsjail_bin=fake_bin)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "UID 0" in (result.message or "")


def test_probe_world_writable_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Binary with group or world writable permissions returns available=False fail-closed."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o777)

    real_stat = Path.stat

    def fake_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        orig = real_stat(path_obj, *args, **kwargs)
        mock_res = MagicMock(spec=orig)
        mock_res.st_uid = 0
        mock_res.st_mode = 0o100777  # writable by group and other
        return mock_res

    monkeypatch.setattr(Path, "stat", fake_stat)

    result = probe_nsjail_userns(nsjail_bin=fake_bin)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "writable" in (result.message or "")


def test_probe_self_test_failure_eperm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unprivileged kernel blocking CLONE_NEWUSER (EPERM / exit 1) fails closed."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o755)

    real_stat = Path.stat

    def fake_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        orig = real_stat(path_obj, *args, **kwargs)
        mock_res = MagicMock(spec=orig)
        mock_res.st_uid = 0
        mock_res.st_mode = 0o100755
        return mock_res

    monkeypatch.setattr(Path, "stat", fake_stat)

    failing_launcher = FakeSubprocessLauncher(
        exit_code=1, stderr=b"clone(CLONE_NEWUSER): Operation not permitted"
    )
    result = probe_nsjail_userns(nsjail_bin=fake_bin, runner=failing_launcher)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "non-zero exit code 1" in (result.message or "")
    assert len(failing_launcher.recorded_cmds) == 1
    cmd = failing_launcher.recorded_cmds[0]
    assert cmd[0] == str(fake_bin)
    assert "--mode" in cmd
    assert "/bin/true" in cmd


def test_probe_self_test_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Functional nsjail returns available=True."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o755)

    real_stat = Path.stat

    def fake_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        orig = real_stat(path_obj, *args, **kwargs)
        mock_res = MagicMock(spec=orig)
        mock_res.st_uid = 0
        mock_res.st_mode = 0o100755
        return mock_res

    monkeypatch.setattr(Path, "stat", fake_stat)

    success_launcher = FakeSubprocessLauncher(exit_code=0)
    result = probe_nsjail_userns(nsjail_bin=fake_bin, runner=success_launcher)
    assert result.available
    assert result.error_code is None


def test_cached_probe_state() -> None:
    """Test get_cached_sandbox_probe and set/reset operations."""
    reset_cached_sandbox_probe()
    assert get_cached_sandbox_probe() is None

    res = SandboxProbeResult(available=False, error_code="TEST_CODE", message="Test detail")
    set_cached_sandbox_probe(res)
    assert get_cached_sandbox_probe() == res

    reset_cached_sandbox_probe()
    assert get_cached_sandbox_probe() is None


def test_standalone_status_serialization_with_tier_b() -> None:
    """Test StandaloneStatus correctly serializes tier_b_sandbox_available fields."""
    status = StandaloneStatus(
        mode="standalone_embedded_pg",
        persistent_volume=True,
        data_mount_point="/var/lib/kanban/data",
        data_mount_fstype="ext4",
        generated_at="2026-11-14T00:00:00Z",
        tier_b_sandbox_available=False,
        tier_b_unavailable_reason="SANDBOX_UNAVAILABLE_IN_STANDALONE",
    )
    raw_dict = json.loads(json.dumps(status.__dict__))
    assert raw_dict["tier_b_sandbox_available"] is False
    assert raw_dict["tier_b_unavailable_reason"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

    # probe_storage test
    data_dir = Path("/var/lib/kanban/data")
    mock_mounts = "/dev/sda1 /var/lib/kanban/data ext4 rw,relatime 0 0\n"
    res_status = probe_storage(
        data_dir=data_dir,
        mounts_text=mock_mounts,
        tier_b_sandbox_available=True,
        tier_b_unavailable_reason=None,
    )
    assert res_status.tier_b_sandbox_available is True
    assert res_status.tier_b_unavailable_reason is None


def test_probe_stat_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError during stat returns available=False fail-closed."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o755)

    def failing_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        del path_obj, args, kwargs
        raise OSError("I/O error reading inode")

    monkeypatch.setattr(Path, "stat", failing_stat)
    result = probe_nsjail_userns(nsjail_bin=fake_bin)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "Cannot stat" in (result.message or "")


def test_probe_runner_varieties(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe handles runner with .run() returning tuple or int, and runner=None."""
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch(mode=0o755)

    real_stat = Path.stat

    def fake_stat(path_obj: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        orig = real_stat(fake_bin)
        mock_res = MagicMock(spec=orig)
        mock_res.st_uid = 0
        mock_res.st_mode = 0o100755
        return mock_res

    monkeypatch.setattr(Path, "stat", fake_stat)

    # 1. runner with .run returning tuple (0, b"", b"")
    class TupleRunner:
        def run(self, *args: object, **kwargs: object) -> tuple[int, bytes, bytes]:
            del args, kwargs
            return 0, b"", b""

    res1 = probe_nsjail_userns(nsjail_bin=fake_bin, runner=TupleRunner())
    assert res1.available is True

    # 2. runner with .run returning int 0
    class IntRunner:
        def run(self, *args: object, **kwargs: object) -> int:
            del args, kwargs
            return 0

    res2 = probe_nsjail_userns(nsjail_bin=fake_bin, runner=IntRunner())
    assert res2.available is True

    # 3. runner without run or run_sync
    res3 = probe_nsjail_userns(nsjail_bin=fake_bin, runner=object())
    assert res3.available is False

    # 4. runner=None with subprocess.run raising TimeoutExpired
    def fake_subp_run(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        raise subprocess.TimeoutExpired(cmd="nsjail", timeout=0.5)

    monkeypatch.setattr(subprocess, "run", fake_subp_run)
    res4 = probe_nsjail_userns(nsjail_bin=fake_bin, runner=None)
    assert res4.available is False
    assert "self-test failed" in (res4.message or "")

    # 5. runner=None with subprocess.run succeeding
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: mock_proc)
    res5 = probe_nsjail_userns(nsjail_bin=fake_bin, runner=None)
    assert res5.available is True

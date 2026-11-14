"""Behavior tests for scripts/ci/run_and_log.sh (KB-P0-06 / KANBA-28)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "run_and_log.sh"


def _run(tmp_path: Path, *args: str, job: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", "CI_LOG_DIR": str(tmp_path / "logs")}
    if job is not None:
        env.pop("CI_LOG_DIR")
        env["CI_JOB_NAME"] = job
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
    )


def test_success_writes_log_and_zero_exit(tmp_path: Path) -> None:
    """Positive: a passing command exits 0 and records exit code 0."""
    result = _run(tmp_path, "ok", "--", "true")
    assert result.returncode == 0
    assert (tmp_path / "logs" / "ok.exit").read_text() == "0\n"
    assert (tmp_path / "logs" / "ok.log").exists()


def test_failure_propagates_exit_code(tmp_path: Path) -> None:
    """Positive: a failing command exits 1 and records exit code 1."""
    result = _run(tmp_path, "bad", "--", "false")
    assert result.returncode == 1
    assert (tmp_path / "logs" / "bad.exit").read_text() == "1\n"


def test_output_is_teed_to_stdout_and_log(tmp_path: Path) -> None:
    """Positive: combined stdout and stderr are captured and still echoed."""
    result = _run(tmp_path, "tee-check", "--", "bash", "-c", "echo out; echo err >&2; exit 3")
    assert result.returncode == 3
    log = (tmp_path / "logs" / "tee-check.log").read_text()
    assert "out" in log
    assert "err" in log
    assert "out" in result.stdout
    assert (tmp_path / "logs" / "tee-check.exit").read_text() == "3\n"


def test_path_traversal_log_name_rejected(tmp_path: Path) -> None:
    """Security: '../x' exits 64 and writes nothing outside the log dir."""
    result = _run(tmp_path, "../x", "--", "true")
    assert result.returncode == 64
    assert not (tmp_path / "x.log").exists()
    assert not (tmp_path / "x.exit").exists()
    assert not (tmp_path / "logs").exists()


def test_uppercase_and_slash_names_rejected(tmp_path: Path) -> None:
    """Boundary: only ^[a-z0-9-]+$ is accepted."""
    for bad in ("Bad", "a/b", "a b", "a_b", ""):
        assert _run(tmp_path, bad, "--", "true").returncode == 64


def test_missing_separator_is_usage_error(tmp_path: Path) -> None:
    """Negative: omitting '--' is a usage error (64)."""
    assert _run(tmp_path, "ok", "true", "x").returncode == 64
    assert _run(tmp_path, "ok").returncode == 64


def test_arguments_are_not_shell_expanded(tmp_path: Path) -> None:
    """Security: arguments are passed as an argv vector, never eval'd."""
    result = _run(tmp_path, "argv", "--", "printf", "%s", "$(touch pwned); `id`")
    assert result.returncode == 0
    assert not (tmp_path / "pwned").exists()
    assert "$(touch pwned)" in (tmp_path / "logs" / "argv.log").read_text()


def test_default_dir_uses_job_name(tmp_path: Path) -> None:
    """Positive: without CI_LOG_DIR logs land in ci-logs/<CI_JOB_NAME>/."""
    result = _run(tmp_path, "ok", "--", "true", job="my-job")
    assert result.returncode == 0
    assert (tmp_path / "ci-logs" / "my-job" / "ok.exit").read_text() == "0\n"

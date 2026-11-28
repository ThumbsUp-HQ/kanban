# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""KAN-545: mirror sync, ref validation, redirect hardening, and runner purity tests."""
# ruff: noqa: ANN401, INP001, TC003, D103, SLF001, PT011, B017, ARG002, PLC0415

from __future__ import annotations

import asyncio
import inspect
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agent.context.repo_context import RepoContextResolutionError, resolve_repo_context
from agent.gates import runner as runner_mod
from database.models.repo_binding import ProjectRepoBinding
from kanban.repos.mirror import (
    FakeGitCommandRunner,
    MirrorManager,
    MirrorPolicy,
    resolve_mirror_base_dir,
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "PATH": "/usr/bin:/bin",
    "HOME": "/tmp",
}


def _binding(url: str = "file:///nonexistent") -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        remote_url=url,
        default_ref="main",
        access_mode="bare_git_tools",
        credential_ciphertext=None,
        credential_dek_kid=None,
        last_fetch_error=None,
        last_fetched_commit=None,
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_mirror_path_unified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", str(tmp_path / "m"))
    b = ProjectRepoBinding(id=uuid.uuid4(), workspace_id=uuid.uuid4())
    assert b.mirror_path == MirrorManager().mirror_path(b)
    assert b.mirror_path.is_relative_to(resolve_mirror_base_dir())


def test_mirror_path_unified_when_default_unwritable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KANBAN_REPO_MIRROR_DIR", raising=False)
    monkeypatch.delenv("KANBAN_GIT_MIRRORS_DIR", raising=False)
    monkeypatch.delenv("KB_DATA_DIR", raising=False)
    b = ProjectRepoBinding(id=uuid.uuid4(), workspace_id=uuid.uuid4())
    assert b.mirror_path == MirrorManager().mirror_path(b)


def test_base_argv_disables_redirects() -> None:
    argv = MirrorManager()._build_base_argv()
    assert "http.followRedirects=false" in argv


async def test_ssrf_url_rejected_without_spawning_git(tmp_path: Path) -> None:
    fake = FakeGitCommandRunner()
    mgr = MirrorManager(base_dir=tmp_path, runner=fake)
    with pytest.raises(Exception):
        await mgr.clone_or_fetch(_binding("https://127.0.0.1/x.git"))
    with pytest.raises(Exception):
        await mgr.clone_or_fetch(_binding("ext::sh -c id"))
    assert fake.calls == []


@pytest.mark.parametrize("ref", ["../foo", "-flag", "main@{0}", "a b", "a\x00b", "a\nb"])
async def test_invalid_target_ref_rejected_before_git(ref: str) -> None:
    fake = FakeGitCommandRunner()
    b = _binding()
    with pytest.raises(RepoContextResolutionError):
        await resolve_repo_context(b, ref, runner=fake)
    assert fake.calls == []


async def test_rev_parse_hardened_argv(tmp_path: Path) -> None:
    fake = FakeGitCommandRunner()
    await resolve_repo_context(_binding(), "main", runner=fake, mirror_path_override=tmp_path)
    argv, env = fake.calls[0]
    assert "protocol.allow=never" in argv
    assert env["GIT_ALLOW_PROTOCOL"] == ""
    assert f"--git-dir={tmp_path}" in argv


async def test_per_mirror_lock_serializes(tmp_path: Path) -> None:
    active = 0
    peak = 0

    class SlowRunner:
        async def run(self, argv: Any, env: Any, timeout_seconds: float = 0.0) -> Any:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return FakeGitCommandRunner().default_response

    mgr = MirrorManager(
        base_dir=tmp_path, runner=SlowRunner(), policy=MirrorPolicy(allow_file_protocol=True)
    )
    b = _binding()
    await asyncio.gather(*(mgr.clone_or_fetch(b) for _ in range(4)))
    assert peak == 1


async def test_fetch_error_is_scrubbed(tmp_path: Path) -> None:
    from kanban.repos.mirror import GitExecutionError, GitResult

    secret = "ghp_" + "A" * 36
    fake = FakeGitCommandRunner([GitResult(128, "", f"fatal: token {secret} denied")])
    mgr = MirrorManager(
        base_dir=tmp_path, runner=fake, policy=MirrorPolicy(allow_file_protocol=True)
    )
    b = _binding()
    with pytest.raises(GitExecutionError):
        await mgr.clone_or_fetch(b)
    assert secret not in (b.last_fetch_error or "")


async def test_sync_fetches_new_commit(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(work, "init", "-b", "main")
    (work / "f").write_text("1")
    _git(work, "add", "f")
    _git(work, "commit", "-m", "one")
    _git(work, "push", str(origin), "main")
    b = _binding(f"file://{origin}")
    mgr = MirrorManager(
        base_dir=tmp_path / "mirrors", policy=MirrorPolicy(allow_file_protocol=True)
    )
    pol = MirrorPolicy(allow_file_protocol=True)
    first = await resolve_repo_context(b, sync=True, mirror_manager=mgr, policy=pol)
    (work / "f").write_text("2")
    _git(work, "commit", "-am", "two")
    _git(work, "push", str(origin), "main")
    second = await resolve_repo_context(b, sync=True, mirror_manager=mgr, policy=pol)
    assert second.head_commit == _git(work, "rev-parse", "HEAD")
    assert second.head_commit != first.head_commit
    assert second.mirror_path == str(mgr.mirror_path(b))


def test_runner_does_not_mutate_registry_and_gates_repo_access() -> None:
    src = inspect.getsource(runner_mod.GateWorkerRunner._load_entities)
    assert "registry.register" not in src
    assert 'repo_access_mode != "none"' in src
    for key in ("budget_enforcer", "provider_config_id", "workspace_id", "project_id"):
        assert f'agent_dict["{key}"]' in src

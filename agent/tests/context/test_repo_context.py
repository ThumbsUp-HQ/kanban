# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for repository context resolution for agent transition runners (KB-P5-19b, S14.3)."""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent.context.repo_context import (
    InvalidCommitHashError,
    RepoContext,
    RepoContextResolutionError,
    resolve_repo_context,
)
from database.models.repo_binding import ProjectRepoBinding
from kanban.repos.mirror import (
    ExecGitCommandRunner,
    FakeGitCommandRunner,
    GitResult,
    MirrorManager,
    MirrorPolicy,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_binding(
    workspace_id: uuid.UUID | None = None,
    binding_id: uuid.UUID | None = None,
    default_ref: str = "main",
    access_mode: str = "ro",
) -> ProjectRepoBinding:
    ws_id = workspace_id or uuid.uuid4()
    b_id = binding_id or uuid.uuid4()
    return ProjectRepoBinding(
        id=b_id,
        workspace_id=ws_id,
        project_id=uuid.uuid4(),
        remote_url="https://github.com/example/repo.git",
        default_ref=default_ref,
        access_mode=access_mode,
    )


@pytest.mark.asyncio
async def test_resolve_repo_context_success() -> None:
    """Successful rev-parse constructs read-only RepoContext with 40-hex commit hash."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\n", ""),
        ]
    )
    binding = _make_binding(default_ref="release-1.0", access_mode="ro")

    context = await resolve_repo_context(binding, runner=fake_runner)

    assert isinstance(context, RepoContext)
    assert context.mount_path == "/workspace/repo"
    assert context.access == "read-only"
    assert context.head_commit == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert context.access_mode == "ro"
    assert str(MirrorManager().mirror_path(binding)) == context.mirror_path

    argv, env = fake_runner.calls[0]
    assert "rev-parse" in argv
    assert "--verify" in argv
    assert "--end-of-options" in argv
    assert "release-1.0^{commit}" in argv
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"


@pytest.mark.asyncio
async def test_resolve_repo_context_explicit_ref() -> None:
    """Explicit ref overrides default_ref on binding."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    binding = _make_binding(default_ref="main")

    context = await resolve_repo_context(binding, ref="refs/tags/v1.2.3", runner=fake_runner)
    assert context.head_commit == "0123456789abcdef0123456789abcdef01234567"

    argv, _ = fake_runner.calls[0]
    assert "refs/tags/v1.2.3^{commit}" in argv


@pytest.mark.asyncio
async def test_resolve_repo_context_git_failure_raises() -> None:
    """Non-zero git rev-parse status raises RepoContextResolutionError."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(128, "", "fatal: Needed a single revision\n"),
        ]
    )
    binding = _make_binding(default_ref="nonexistent")

    with pytest.raises(RepoContextResolutionError) as exc_info:
        await resolve_repo_context(binding, runner=fake_runner)

    assert "Failed to resolve ref" in str(exc_info.value)
    assert "nonexistent" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_repo_context_invalid_commit_format_raises() -> None:
    """Rev-parse returning invalid hash raises InvalidCommitHashError."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "not-a-valid-40-hex-commit\n", ""),
        ]
    )
    binding = _make_binding(default_ref="main")

    with pytest.raises(InvalidCommitHashError) as exc_info:
        await resolve_repo_context(binding, runner=fake_runner)

    assert "Invalid commit hash received" in str(exc_info.value)


def test_resolve_repo_context_real_git(tmp_path: Path) -> None:
    """Real git execution against a local bare mirror resolves the exact head commit."""
    # Create git repo and commit
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Agent"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "agent@test.local"],
        check=True,
    )
    (repo_dir / "file.txt").write_text("content\n")
    subprocess.run(["git", "-C", str(repo_dir), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Initial"], check=True)

    expected_sha = subprocess.check_output(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True
    ).strip()

    # Mock mirror_path property on binding
    class MockBinding:
        default_ref = "main"
        access_mode = "ro"

    policy = MirrorPolicy(allow_file_protocol=True)
    runner = ExecGitCommandRunner()

    context = asyncio.run(
        resolve_repo_context(
            MockBinding(),  # type: ignore[arg-type]
            mirror_path_override=repo_dir / ".git",
            policy=policy,
            runner=runner,
        )
    )

    assert context.head_commit == expected_sha
    assert context.access == "read-only"
    assert context.mount_path == "/workspace/repo"

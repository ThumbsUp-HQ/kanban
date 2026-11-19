# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for bare git mirror root resolution and writable fallback (KB-P3-AUDIT-04)."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from database.models.repo_binding import ProjectRepoBinding
from kanban.repos.mirror import (
    FakeGitCommandRunner,
    GitResult,
    MirrorManager,
    MirrorPolicy,
    is_dir_writable,
    resolve_mirror_base_dir,
)


def test_is_dir_writable_success(tmp_path: Path) -> None:
    """Verifies writable directory returns True."""
    target = tmp_path / "writable_sub"
    assert is_dir_writable(target) is True


def test_is_dir_writable_failure() -> None:
    """Verifies unwritable path returns False cleanly."""
    unwritable = Path("/proc/kanban_unwritable_probe_dir")
    assert is_dir_writable(unwritable) is False


def test_resolve_mirror_base_dir_override(tmp_path: Path) -> None:
    """Explicit override parameter is honored immediately."""
    override = tmp_path / "custom-mirrors"
    assert resolve_mirror_base_dir(override) == override


def test_resolve_mirror_base_dir_kanban_repo_mirror_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variable KANBAN_REPO_MIRROR_DIR takes priority."""
    custom_dir = tmp_path / "custom_repo_mirror"
    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", str(custom_dir))
    assert resolve_mirror_base_dir() == custom_dir


def test_resolve_mirror_base_dir_kb_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment variable KB_DATA_DIR derives git-mirrors directory."""
    data_root = tmp_path / "kb_data_root"
    monkeypatch.delenv("KANBAN_REPO_MIRROR_DIR", raising=False)
    monkeypatch.delenv("KANBAN_GIT_MIRRORS_DIR", raising=False)
    monkeypatch.setenv("KB_DATA_DIR", str(data_root))
    resolved = resolve_mirror_base_dir()
    assert resolved == data_root / "git-mirrors"


def test_resolve_mirror_base_dir_unwritable_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When standard paths are unwritable, falls back to tempdir."""
    monkeypatch.delenv("KANBAN_REPO_MIRROR_DIR", raising=False)
    monkeypatch.delenv("KANBAN_GIT_MIRRORS_DIR", raising=False)
    monkeypatch.delenv("KB_DATA_DIR", raising=False)

    def mock_is_writable(path: Path) -> bool:
        return "kanban-git-mirrors" in str(path) and "tmp" in str(path)

    with patch("kanban.repos.mirror.is_dir_writable", side_effect=mock_is_writable):
        resolved = resolve_mirror_base_dir()
        assert "kanban-git-mirrors" in str(resolved)
        expected_tmp = Path(tempfile.gettempdir())
        assert expected_tmp in resolved.parents or resolved == expected_tmp / "kanban-git-mirrors"


def test_mirror_manager_default_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MirrorManager defaults to resolve_mirror_base_dir when unspecified."""
    mirror_dir = tmp_path / "manager_mirrors"
    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", str(mirror_dir))
    mgr = MirrorManager()
    assert mgr.base_dir == mirror_dir


def test_project_repo_binding_mirror_path_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProjectRepoBinding.mirror_path reflects KANBAN_REPO_MIRROR_DIR and KB_DATA_DIR."""
    ws_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    binding = ProjectRepoBinding(
        id=binding_id,
        workspace_id=ws_id,
        project_id=uuid.uuid4(),
        remote_url="https://github.com/example/repo.git",
        default_ref="main",
        access_mode="ro",
    )

    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", "/mnt/custom-git")
    assert binding.mirror_path == Path(f"/mnt/custom-git/{ws_id}/{binding_id}.git")

    monkeypatch.delenv("KANBAN_REPO_MIRROR_DIR")
    monkeypatch.setenv("KB_DATA_DIR", "/var/lib/custom-kb")
    assert binding.mirror_path == Path(f"/var/lib/custom-kb/git-mirrors/{ws_id}/{binding_id}.git")

    monkeypatch.delenv("KB_DATA_DIR")
    assert binding.mirror_path == Path(f"/var/lib/kanban/git-mirrors/{ws_id}/{binding_id}.git")


@pytest.mark.asyncio
async def test_clone_or_fetch_permission_fallback() -> None:
    """clone_or_fetch recovers cleanly when initial target_path directory is unwritable."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned\n", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    unwritable_base = Path("/proc/unwritable_mirrors")
    manager = MirrorManager(
        base_dir=unwritable_base,
        runner=fake_runner,
        policy=MirrorPolicy(allow_file_protocol=False),
    )

    binding = ProjectRepoBinding(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        remote_url="https://github.com/example/repo.git",
        default_ref="main",
        access_mode="ro",
    )

    await manager.clone_or_fetch(binding, pinned_ip="140.82.121.3")
    assert manager.base_dir != unwritable_base
    assert "kanban-git-mirrors" in str(manager.base_dir)

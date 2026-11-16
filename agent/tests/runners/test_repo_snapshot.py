# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RoRepoSnapshotManager and discover_whiteout_targets (KB-P5-21, S14.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.runners.repo_snapshot import (
    RepoSnapshotError,
    RepoWhiteoutLimitExceededError,
    RoRepoSnapshotManager,
    discover_whiteout_targets,
)


async def test_case_4_ro_repo_snapshot_and_whiteouts(
    bare_git_fixture: tuple[Path, str], tmp_path: Path
) -> None:
    """Test Case 4: 4-layer :ro mount + whiteouts and escaping symlink rejection."""
    mirror_path, head_commit = bare_git_fixture
    staging_base = tmp_path / "staging_base"
    staging_base.mkdir()

    repo_context = {
        "mount_path": "/workspace/repo",
        "access": "read-only",
        "head_commit": head_commit,
        "mirror_path": str(mirror_path),
    }

    manager = RoRepoSnapshotManager(
        execution_id="exec-test-case-4",
        repo_context=repo_context,
        base_dir=staging_base,
    )

    async with manager:
        assert manager.staging_dir is not None
        assert manager.staging_dir.exists()

        # Permissions check: snapshot root 0555
        st_mode = manager.staging_dir.stat().st_mode & 0o777
        assert st_mode == 0o555

        # Verify symlink was stripped/rejected by tarfile data filter
        assert not (manager.staging_dir / "escape").exists()

        # Verify regular files extracted
        assert (manager.staging_dir / "src" / "app.py").exists()
        assert (manager.staging_dir / ".env").exists()
        assert (manager.staging_dir / "config" / ".env.local").exists()
        assert (manager.staging_dir / "tls" / "private.key").exists()
        assert (manager.staging_dir / "certs" / "ca.pem").exists()

        # Verify stub .git metadata
        git_dir = manager.staging_dir / ".git"
        assert git_dir.exists()
        assert (git_dir / "HEAD").read_text(encoding="utf-8") == f"{head_commit}\n"
        assert (git_dir / "config").exists()
        assert (git_dir / "hooks").is_dir()

        # Verify whiteout targets
        targets = manager.discover_whiteout_targets()
        expected = [
            ".env",
            ".git/config",
            ".git/hooks",
            "certs/ca.pem",
            "config/.env.local",
            "tls/private.key",
        ]
        for exp in expected:
            assert exp in targets

        # Verify generated nsjail config
        config_text = manager.generate_nsjail_config()
        assert 'dst: "/workspace/repo"' in config_text
        assert "MS_RDONLY" in config_text
        assert "MS_NOEXEC" in config_text
        assert "MS_NOSUID" in config_text
        assert "MS_NODEV" in config_text

        # Verify 0000 whiteout entries for discovered secrets
        assert 'dst: "/workspace/repo/.env"' in config_text
        assert 'dst: "/workspace/repo/config/.env.local"' in config_text
        assert 'dst: "/workspace/repo/tls/private.key"' in config_text
        assert 'dst: "/workspace/repo/certs/ca.pem"' in config_text
        assert 'dst: "/workspace/repo/.git/config"' in config_text
        assert 'dst: "/workspace/repo/.git/hooks"' in config_text
        assert "mode=0000" in config_text

    # After context exit, staging directory is deleted
    assert not (staging_base / "exec-test-case-4").exists()


def test_discover_whiteout_targets_boundary_limit_exceeded(tmp_path: Path) -> None:
    """Test Case 6: Repo with > 256 secret files raises REPO_WHITEOUT_LIMIT_EXCEEDED."""
    repo_dir = tmp_path / "oversize_secrets"
    repo_dir.mkdir()

    # Create 257 .env.* files
    for i in range(257):
        (repo_dir / f".env.{i:03d}").write_text("SECRET=1\n")

    with pytest.raises(RepoWhiteoutLimitExceededError) as exc_info:
        discover_whiteout_targets(repo_dir)

    assert exc_info.value.code == "REPO_WHITEOUT_LIMIT_EXCEEDED"
    assert exc_info.value.count == 257


def test_discover_whiteout_targets_empty_or_nonexistent(tmp_path: Path) -> None:
    """Test discover_whiteout_targets handles empty and nonexistent paths."""
    assert discover_whiteout_targets(tmp_path / "nonexistent") == []
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert discover_whiteout_targets(empty_dir) == []


async def test_repo_snapshot_manager_missing_context(tmp_path: Path) -> None:
    """Test RoRepoSnapshotManager returns None when context or commits are absent."""
    mgr1 = RoRepoSnapshotManager(execution_id="e1", repo_context=None, base_dir=tmp_path)
    assert await mgr1.materialize() is None

    mgr2 = RoRepoSnapshotManager(
        execution_id="e2", repo_context={"head_commit": "abc"}, base_dir=tmp_path
    )
    assert await mgr2.materialize() is None

    mgr3 = RoRepoSnapshotManager(
        execution_id="e3", repo_context={"mirror_path": "x"}, base_dir=tmp_path
    )
    assert await mgr3.materialize() is None


async def test_repo_snapshot_manager_git_archive_failure(tmp_path: Path) -> None:
    """Test RoRepoSnapshotManager raises RepoSnapshotError when git archive fails."""
    bogus_repo = tmp_path / "bogus.git"
    bogus_repo.mkdir()

    repo_context = {
        "head_commit": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "mirror_path": str(bogus_repo),
    }

    mgr = RoRepoSnapshotManager(execution_id="e-fail", repo_context=repo_context, base_dir=tmp_path)
    with pytest.raises(RepoSnapshotError) as exc_info:
        await mgr.materialize()

    assert exc_info.value.code == "GIT_ARCHIVE_FAILED"
    mgr.cleanup()


def test_discover_whiteout_targets_dirs_and_git_variations(tmp_path: Path) -> None:
    """Test discovering .env directories and missing git subcomponents."""
    repo = tmp_path / "mixed_repo"
    repo.mkdir()
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    # Only config exists, no hooks
    (git_dir / "config").write_text("[core]\n")

    # .env directory
    env_dir = repo / ".env.local.d"
    env_dir.mkdir()
    (env_dir / "item").write_text("a=1\n")

    targets = discover_whiteout_targets(repo)
    assert ".git/config" in targets
    assert ".git/hooks" not in targets
    assert ".env.local.d" in targets or ".env.local.d/item" in targets


def test_repo_snapshot_manager_default_dir_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test RoRepoSnapshotManager falls back to /tmp/kanban/repo-snapshots on OSError."""
    orig_mkdir = Path.mkdir

    def mock_mkdir(
        self: Path, mode: int = 0o777, *, parents: bool = False, exist_ok: bool = False
    ) -> None:
        if str(self) == "/run/kanban/repo-snapshots":
            msg = "EACCES"
            raise PermissionError(msg)
        orig_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    mgr = RoRepoSnapshotManager(execution_id="e-fallback")
    assert mgr.base_dir == Path("/tmp/kanban/repo-snapshots")


async def test_repo_snapshot_manager_existing_staging_and_cleanup_error(
    bare_git_fixture: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test RoRepoSnapshotManager cleans existing staging dir and handles cleanup OSError."""
    mirror_path, head_commit = bare_git_fixture
    staging_base = tmp_path / "staging_existing"
    staging_base.mkdir()

    # Pre-create staging dir with dummy file
    pre_dir = staging_base / "exec-pre"
    pre_dir.mkdir()
    (pre_dir / "dummy.txt").write_text("old")

    repo_context = {
        "mount_path": "/workspace/repo",
        "access": "read-only",
        "head_commit": head_commit,
        "mirror_path": str(mirror_path),
    }

    mgr = RoRepoSnapshotManager(
        execution_id="exec-pre", repo_context=repo_context, base_dir=staging_base
    )
    await mgr.materialize()
    assert mgr.staging_dir is not None
    assert (mgr.staging_dir / "src" / "app.py").exists()
    assert not (mgr.staging_dir / "dummy.txt").exists()

    # Test discover_whiteout_targets when staging_dir is None
    cached_targets = mgr.discover_whiteout_targets()
    assert len(cached_targets) > 0

    # Test generate_nsjail_config with custom staging path and custom targets
    custom_cfg = mgr.generate_nsjail_config(
        staging_path=Path("/custom/repo"),
        whiteout_targets=[".env", ".git/hooks"],
    )
    assert 'src: "/custom/repo"' in custom_cfg
    assert 'dst: "/workspace/repo/.env"' in custom_cfg

    # Test cleanup handling OSError
    def mock_rmtree(*_args: object, **_kwargs: object) -> None:
        msg = "Failed to remove"
        raise OSError(msg)

    monkeypatch.setattr("shutil.rmtree", mock_rmtree)
    # Should not raise
    mgr.cleanup()

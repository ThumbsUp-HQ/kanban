# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Read-only repository snapshot manager and secret whiteout discovery (S14.3, KB-P5-21)."""

from __future__ import annotations

import asyncio
import fnmatch
import io
import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Self

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "MAX_WHITEOUT_MOUNTS",
    "RepoSnapshotError",
    "RepoWhiteoutLimitExceededError",
    "RoRepoSnapshotManager",
    "discover_whiteout_targets",
]

MAX_WHITEOUT_MOUNTS: Final[int] = 256


class RepoSnapshotError(Exception):
    """Base error raised for repository snapshot materialization failures."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize RepoSnapshotError with code and explanatory detail."""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class RepoWhiteoutLimitExceededError(RepoSnapshotError):
    """Raised when discovered secret files exceed the safe 256 whiteout limit."""

    def __init__(self, count: int, max_limit: int = MAX_WHITEOUT_MOUNTS) -> None:
        """Initialize RepoWhiteoutLimitExceededError with target count and limit."""
        super().__init__(
            code="REPO_WHITEOUT_LIMIT_EXCEEDED",
            detail=(
                f"Discovered secret file count ({count}) exceeds maximum whiteout mount "
                f"limit of {max_limit}. Failing closed to prevent unmasked secret exposure."
            ),
        )
        self.count = count
        self.max_limit = max_limit


def discover_whiteout_targets(snapshot_root: Path) -> list[str]:  # noqa: C901
    """Scan repository snapshot and discover all secret files and sensitive Git paths.

    Discovers:
    - `.git/config` and `.git/hooks`
    - Any path matching `.env*` anywhere in the tree
    - Any path matching `*.pem` anywhere in the tree
    - Any path matching `*.key` anywhere in the tree

    Fails closed with RepoWhiteoutLimitExceededError if discovered targets exceed 256.
    """
    if not snapshot_root.exists() or not snapshot_root.is_dir():
        return []

    discovered: set[str] = set()

    # Always mask .git/config and .git/hooks if .git directory exists
    git_dir = snapshot_root / ".git"
    if git_dir.exists():
        if (git_dir / "config").exists():
            discovered.add(".git/config")
        if (git_dir / "hooks").exists():
            discovered.add(".git/hooks")

    for root, dirs, files in os.walk(snapshot_root):
        rel_root = Path(root).relative_to(snapshot_root).as_posix()
        for filename in files:
            rel_file = filename if rel_root == "." else f"{rel_root}/{filename}"
            if rel_file.startswith(".git/") and (
                rel_file == ".git/config" or rel_file.startswith(".git/hooks")
            ):
                continue
            if (
                filename.startswith(".env")
                or fnmatch.fnmatch(filename, "*.pem")
                or fnmatch.fnmatch(filename, "*.key")
            ):
                discovered.add(rel_file)

        for dirname in dirs:
            rel_dir = dirname if rel_root == "." else f"{rel_root}/{dirname}"
            if dirname.startswith(".env") and not rel_dir.startswith(".git/"):
                discovered.add(rel_dir)

    # Sort deterministically
    sorted_targets = sorted(discovered)

    if len(sorted_targets) > MAX_WHITEOUT_MOUNTS:
        raise RepoWhiteoutLimitExceededError(len(sorted_targets), MAX_WHITEOUT_MOUNTS)

    return sorted_targets


@dataclass
class RoRepoSnapshotManager:
    """Manages detached, read-only repository snapshots with whiteout discovery."""

    execution_id: str
    repo_context: Any = None
    base_dir: Path | None = None

    def __post_init__(self) -> None:
        """Initialize default snapshot directories and whiteout target tracking."""
        if self.base_dir is None:
            default_dir = Path("/run/kanban/repo-snapshots")
            try:
                default_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.base_dir = default_dir
            except OSError:
                self.base_dir = Path("/tmp/kanban/repo-snapshots")  # noqa: S108
        self.staging_dir: Path | None = None
        self.whiteout_targets: list[str] = []

    async def materialize(self) -> Path | None:
        """Extract a clean detached snapshot of repo_context.head_commit into host staging dir."""
        if self.repo_context is None:
            return None

        if isinstance(self.repo_context, dict):
            mirror_path = self.repo_context.get("mirror_path")
            head_commit = self.repo_context.get("head_commit")
        else:
            mirror_path = getattr(self.repo_context, "mirror_path", None)
            head_commit = getattr(self.repo_context, "head_commit", None)

        if not mirror_path or not head_commit:
            return None

        if self.base_dir is not None:
            self.base_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            staging_dir = self.base_dir / self.execution_id
        else:
            staging_dir = Path(f"/tmp/kanban/repo-snapshots/{self.execution_id}")  # noqa: S108
        if staging_dir.exists():
            self.staging_dir = staging_dir
            self.cleanup()

        self.staging_dir = staging_dir
        self.staging_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Run git archive
        cmd = [
            "git",
            f"--git-dir={mirror_path}",
            "archive",
            "--format=tar",
            str(head_commit),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RepoSnapshotError(
                code="GIT_ARCHIVE_FAILED",
                detail=f"git archive failed with exit code {proc.returncode}: {err_msg}",
            )

        # Extract archive safely using Python tarfile with data_filter
        with tarfile.open(fileobj=io.BytesIO(stdout), mode="r") as tf:
            safe_members = []
            for member in tf.getmembers():
                try:
                    filtered = tarfile.data_filter(member, str(self.staging_dir))
                    if filtered is not None:
                        safe_members.append(filtered)
                except tarfile.FilterError:
                    # Strip/reject symlinks escaping destination or device/FIFO/setuid members
                    continue
            tf.extractall(path=self.staging_dir, members=safe_members, filter="data")

        # Create stub .git/HEAD, .git/config, and .git/hooks directory
        git_dir = self.staging_dir / ".git"
        git_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        (git_dir / "HEAD").write_text(f"{head_commit}\n", encoding="utf-8")
        (git_dir / "config").write_text("", encoding="utf-8")
        (git_dir / "hooks").mkdir(parents=True, exist_ok=True, mode=0o755)

        # Discover whiteout targets
        self.whiteout_targets = discover_whiteout_targets(self.staging_dir)

        # Apply snapshot root 0555 read-only permissions
        self.staging_dir.chmod(0o555)
        return self.staging_dir

    def discover_whiteout_targets(self) -> list[str]:
        """Return discovered whiteout targets for current snapshot."""
        if self.staging_dir is not None and self.staging_dir.exists():
            return discover_whiteout_targets(self.staging_dir)
        return list(self.whiteout_targets)

    def generate_nsjail_config(
        self,
        staging_path: Path | None = None,
        whiteout_targets: Sequence[str] | None = None,
    ) -> str:
        """Generate nsjail protobuf configuration with 4-layer :ro mounts and 0000 whiteouts."""
        snapshot_path = staging_path or self.staging_dir or Path("/tmp/placeholder-repo")  # noqa: S108
        targets = (
            whiteout_targets
            if whiteout_targets is not None
            else (self.whiteout_targets or self.discover_whiteout_targets())
        )

        lines: list[str] = [
            "# nsjail configuration for /workspace/repo snapshot",
            'name: "kanban-cli-pipe-repo"',
            "mode: ONCE",
            'cwd: "/workspace/repo"',
            "",
            "# Primary repository mount: MS_RDONLY | MS_NOEXEC | MS_NOSUID | MS_NODEV",
            "mount {",
            f'    src: "{snapshot_path.as_posix()}"',
            '    dst: "/workspace/repo"',
            "    is_bind: true",
            "    rw: false",
            '    options: "MS_BIND,MS_REC,MS_RDONLY,MS_NODEV,MS_NOSUID,MS_NOEXEC"',
            "    nodev: true",
            "    nosuid: true",
            "    noexec: true",
            "    mandatory: true",
            "}",
            "",
            "# 0000 secret and hook whiteout tmpfs overlays",
        ]

        for target in targets:
            clean_target = target.lstrip("/")
            dst_path = f"/workspace/repo/{clean_target}"
            lines.extend(
                [
                    "mount {",
                    f'    dst: "{dst_path}"',
                    '    fstype: "tmpfs"',
                    "    rw: false",
                    '    options: "size=0,mode=0000,MS_RDONLY,MS_NODEV,MS_NOSUID,MS_NOEXEC"',
                    "    nodev: true",
                    "    nosuid: true",
                    "    noexec: true",
                    "    mandatory: false",
                    "}",
                ]
            )

        return "\n".join(lines) + "\n"

    def cleanup(self) -> None:
        """Unconditionally clean up the host staging directory."""
        if self.staging_dir is not None and self.staging_dir.exists():
            try:
                self.staging_dir.chmod(0o700)
                shutil.rmtree(self.staging_dir, ignore_errors=True)
            except OSError:
                pass
            self.staging_dir = None

    async def __aenter__(self) -> Self:
        """Enter snapshot context and materialize detached read-only snapshot."""
        await self.materialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit snapshot context and clean up staging directory."""
        self.cleanup()

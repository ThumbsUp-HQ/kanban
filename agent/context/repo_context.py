# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Repository context resolution for agent transition execution (KB-P5-19b, S14.3)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from kanban.repos.mirror import (
    ExecGitCommandRunner,
    GitCommandRunner,
    MirrorManager,
    MirrorPolicy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from database.models.repo_binding import ProjectRepoBinding

__all__ = [
    "InvalidCommitHashError",
    "RepoContext",
    "RepoContextResolutionError",
    "resolve_repo_context",
]

_COMMIT_HEX_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


_BAD_REF_RE = re.compile(r"[\x00-\x20\x7f]")


def _validate_target_ref(ref: str) -> None:
    """Reject hostile refs before any git process is spawned."""
    if not ref or _BAD_REF_RE.search(ref) or ".." in ref or ref.startswith("-") or "@{" in ref:
        msg = "Invalid target ref"
        raise RepoContextResolutionError(msg)


class RepoContextResolutionError(ValueError):
    """Raised when git rev-parse fails to resolve the requested ref."""


class InvalidCommitHashError(ValueError):
    """Raised when git rev-parse outputs an invalid commit hash format."""


class RepoContext(BaseModel):
    """Read-only repository mount configuration and commit metadata for agent runners."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mount_path: str = "/workspace/repo"
    access: Literal["read-only"] = "read-only"
    head_commit: str
    mirror_path: str
    access_mode: str


async def resolve_repo_context(  # noqa: PLR0913
    binding: ProjectRepoBinding,
    ref: str | None = None,
    *,
    runner: GitCommandRunner | None = None,
    policy: MirrorPolicy | None = None,
    sync: bool = False,
    mirror_manager: MirrorManager | None = None,
    mirror_path_override: Path | str | None = None,
    allowed_git_cidrs: Sequence[str] | None = None,
    air_gap_mode: bool = False,
    kek_provider: Any = None,  # noqa: ANN401
) -> RepoContext:
    """Resolve repository head commit and build read-only RepoContext for agent execution."""
    target_ref = ref if ref and ref.strip() else binding.default_ref
    git_runner = runner or ExecGitCommandRunner()
    git_policy = policy or MirrorPolicy(allow_file_protocol=False)

    _validate_target_ref(target_ref)

    active_mgr = mirror_manager
    if sync:
        if active_mgr is None:
            active_mgr = MirrorManager(
                policy=git_policy, runner=git_runner, kek_provider=kek_provider
            )
        await active_mgr.clone_or_fetch(
            binding, allowed_git_cidrs=allowed_git_cidrs, air_gap_mode=air_gap_mode
        )

    if mirror_path_override is not None:
        mirror_path = Path(mirror_path_override)
    elif active_mgr is not None:
        mirror_path = active_mgr.mirror_path(binding)
    else:
        mirror_path = binding.mirror_path
    allow_file = git_policy.allow_file_protocol

    argv = [
        "git",
        "-c",
        "protocol.allow=never",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        f"protocol.file.allow={'always' if allow_file else 'never'}",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "submodule.recurse=false",
        "-c",
        "transfer.fsckObjects=true",
        f"--git-dir={mirror_path}",
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{target_ref}^{{commit}}",
    ]

    env = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "",
        "HOME": tempfile.gettempdir(),
        "PATH": "/usr/bin:/bin",
    }

    res = await git_runner.run(argv, env, timeout_seconds=120.0)
    if res.returncode != 0:
        err_msg = res.stderr.strip()
        msg = f"Failed to resolve ref '{target_ref}' in mirror {mirror_path}: {err_msg}"
        raise RepoContextResolutionError(msg)

    commit = res.stdout.strip()
    if not _COMMIT_HEX_RE.match(commit):
        msg = f"Invalid commit hash received for ref '{target_ref}': {commit}"
        raise InvalidCommitHashError(msg)

    return RepoContext(
        mount_path="/workspace/repo",
        access="read-only",
        head_commit=commit,
        mirror_path=str(mirror_path),
        access_mode=binding.access_mode,
    )

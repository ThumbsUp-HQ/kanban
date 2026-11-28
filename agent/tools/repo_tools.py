# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Read-only bare Git repository toolkit for SDK transition helpers (S14.2)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Final

from agent.tools.repo_path_guard import (
    CODE_REPO_BINARY_FILE_UNSUPPORTED,
    CODE_REPO_EXEC_FAILED,
    CODE_REPO_FILE_NOT_FOUND,
    CODE_REPO_GREP_PATTERN_INVALID,
    CODE_REPO_PATH_INVALID,
    CODE_REPO_SECRET_PATH_DENIED,
    CODE_REPO_TIMEOUT,
    RepoToolPolicyError,
    is_secret_repo_path,
    normalize_repo_relpath,
)
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from agent.context.transition_context import RepoContext

__all__ = [
    "DEFAULT_GIT_TIMEOUT_S",
    "MAX_BLOB_READ_BYTES",
    "MAX_DIFF_BASE_REF_LEN",
    "MAX_FILE_READ_LINES_SPAN",
    "MAX_GREP_PATTERN_LEN",
    "MAX_LOG_COMMITS",
    "MAX_OUTPUT_BYTES",
    "MAX_TREE_DEPTH",
    "MAX_TREE_ENTRIES",
    "BareGitRepoToolkit",
]

MAX_OUTPUT_BYTES: Final[int] = 65_536  # 64 KiB
DEFAULT_GIT_TIMEOUT_S: Final[float] = 5.0
MAX_TREE_DEPTH: Final[int] = 6
MAX_TREE_ENTRIES: Final[int] = 500
MAX_FILE_READ_LINES_SPAN: Final[int] = 400
MAX_GREP_PATTERN_LEN: Final[int] = 200
MAX_LOG_COMMITS: Final[int] = 50
MAX_DIFF_BASE_REF_LEN: Final[int] = 120
MAX_BLOB_READ_BYTES: Final[int] = 1_048_576  # 1 MiB

_RE_SHA: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{40,64}$")
_RE_BASE_REF: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._/~^-]{1,120}$")

_SECRET_PATH_EXCLUDES: Final[tuple[str, ...]] = (
    ":(exclude).env*",
    ":(exclude)*.env",
    ":(exclude)*.pem",
    ":(exclude)*.key",
    ":(exclude)*.p12",
    ":(exclude)*.pfx",
    ":(exclude)*.jks",
    ":(exclude)*id_rsa*",
    ":(exclude)*id_ed25519*",
    ":(exclude)*id_ecdsa*",
    ":(exclude).git",
    ":(exclude).git/*",
    ":(exclude).netrc",
    ":(exclude).npmrc",
    ":(exclude).pypirc",
    ":(exclude).ssh/*",
    ":(exclude)*/.ssh/*",
    ":(exclude).aws/*",
    ":(exclude)*/.aws/*",
    ":(exclude).kube/*",
    ":(exclude)*/.kube/*",
    ":(exclude)*.tfvars",
    ":(exclude)*.tfstate*",
    ":(exclude)*credentials*",
    ":(exclude)*.keystore",
    ":(exclude)secrets.*",
)

_CLEAN_GIT_ENV: Final[dict[str, str]] = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "PATH": "/usr/bin:/bin",
}


def _cap_and_scrub(output_bytes: bytes, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Cap byte length, decode UTF-8 safely, and scrub sensitive secrets."""
    is_truncated = len(output_bytes) > max_bytes
    sliced = output_bytes[:max_bytes]
    text = sliced.decode("utf-8", errors="replace")
    if is_truncated:
        text += "\n[TRUNCATED]"
    return scrub_text(text)


def _require_regular_blob(ls_tree_entry: str, norm_path: str) -> None:
    """Reject trees, git symlinks (120000), and submodules (160000)."""
    meta = ls_tree_entry.split("\t", 1)[0].split()
    mode, kind = [*meta, "", ""][:2]
    if mode not in {"100644", "100755"} or kind != "blob":
        msg = f"Path is not a regular file blob (symlink, submodule, or tree): {norm_path}"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)


def _filter_tree_lines(stdout: bytes, norm_path: str, depth: int) -> list[str]:
    """Filter raw git ls-tree lines by secret paths and maximum depth."""
    filtered_entries: list[str] = []
    path_prefix = f"{norm_path}/" if norm_path else ""

    for line in stdout.splitlines():
        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str or "\t" not in line_str:
            continue

        metadata, file_path = line_str.split("\t", 1)
        file_path = file_path.strip()

        if is_secret_repo_path(file_path):
            continue

        if path_prefix:
            if not file_path.startswith(path_prefix) and file_path != norm_path:
                continue
            rel = file_path[len(path_prefix) :]
        else:
            rel = file_path

        if rel.count("/") + 1 > depth:
            continue

        filtered_entries.append(f"{metadata}\t{file_path}")
        if len(filtered_entries) >= MAX_TREE_ENTRIES:
            break

    return filtered_entries


class BareGitRepoToolkit:
    """Read-only bare Git repository toolkit executing against a pinned commit."""

    def __init__(
        self,
        mirror_path: Path | str,
        head_commit: str,
        *,
        timeout_s: float = DEFAULT_GIT_TIMEOUT_S,
    ) -> None:
        """Initialize bare Git repo toolkit with mirror path and head commit.

        Args:
            mirror_path: Path to bare git repository mirror.
            head_commit: Pinned 40 or 64-hex commit hash.
            timeout_s: Per-command timeout in seconds.

        """
        self.mirror_path = Path(mirror_path).resolve()
        if not self.mirror_path.exists():
            msg = f"Bare repository mirror path does not exist: {self.mirror_path}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        cleaned_head = head_commit.strip()
        if not _RE_SHA.match(cleaned_head):
            msg = f"Invalid head_commit hash format (expected 40/64 hex): {head_commit!r}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
        self.head_commit = cleaned_head
        self.timeout_s = timeout_s

    @classmethod
    def from_repo_context(
        cls,
        repo_ctx: RepoContext,
        *,
        timeout_s: float = DEFAULT_GIT_TIMEOUT_S,
    ) -> BareGitRepoToolkit:
        """Construct toolkit from a validated RepoContext."""
        mirror = repo_ctx.mirror_path or repo_ctx.mount_path
        return cls(mirror_path=mirror, head_commit=repo_ctx.head_commit, timeout_s=timeout_s)

    async def _exec_git(self, *args: str) -> tuple[int, bytes, bytes]:
        """Execute a git subcommand inside the bare repository with strict hardening."""
        cmd = [
            "git",
            f"--git-dir={self.mirror_path}",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.allow=never",
            *args,
        ]

        proc: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout_s):
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_CLEAN_GIT_ENV,
                    start_new_session=True,
                )
                stdout, stderr = await proc.communicate()
                return proc.returncode if proc.returncode is not None else -1, stdout, stderr
        except (TimeoutError, asyncio.CancelledError) as exc:
            if proc is not None:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(proc.pid, signal.SIGKILL)
                with contextlib.suppress(Exception):
                    await asyncio.shield(proc.wait())
            if isinstance(exc, asyncio.CancelledError):
                raise
            msg = f"Git subprocess execution timed out after {self.timeout_s}s: {' '.join(cmd[:6])}"
            raise RepoToolPolicyError(CODE_REPO_TIMEOUT, msg) from exc
        except OSError as exc:
            msg = f"Failed to spawn git subprocess: {exc}"
            raise RepoToolPolicyError(CODE_REPO_EXEC_FAILED, msg) from exc

    async def repo_tree(self, path: str = "", max_depth: int = 3) -> str:
        """List repository files up to max_depth, filtering secret paths."""
        norm_path = normalize_repo_relpath(path) if path else ""
        if norm_path and is_secret_repo_path(norm_path):
            msg = f"Access to secret path denied: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_SECRET_PATH_DENIED, msg)

        depth = max(1, min(MAX_TREE_DEPTH, int(max_depth)))

        cmd_args = ["ls-tree", "-r", "--full-tree", "--end-of-options", self.head_commit]
        cmd_args.extend(["--", norm_path] if norm_path else [])

        rc, stdout, stderr = await self._exec_git(*cmd_args)
        if rc != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return scrub_text(f"repo_tree error (exit {rc}): {err_msg}")

        filtered_entries = _filter_tree_lines(stdout, norm_path, depth)
        joined = "\n".join(filtered_entries)
        return _cap_and_scrub(joined.encode("utf-8"))

    async def repo_read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> str:
        """Read a slice of lines from a commit-pinned file in the repository."""
        norm_path = normalize_repo_relpath(path)
        if not norm_path:
            msg = "File path cannot be empty"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        if is_secret_repo_path(norm_path):
            msg = f"Access to secret path denied: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_SECRET_PATH_DENIED, msg)

        start = int(start_line)
        end = int(end_line)
        if start < 1 or end < start or (end - start) >= MAX_FILE_READ_LINES_SPAN:
            msg = (
                f"Invalid line range (start={start}, end={end}): "
                f"must satisfy 1 <= start <= end and end - start < {MAX_FILE_READ_LINES_SPAN}"
            )
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        rc_ls, out_ls, _err_ls = await self._exec_git(
            "ls-tree", "--end-of-options", self.head_commit, "--", norm_path
        )
        entry = out_ls.decode("utf-8", errors="replace").strip()
        if rc_ls != 0 or not entry:
            msg = f"File '{norm_path}' not found at {self.head_commit}"
            raise RepoToolPolicyError(CODE_REPO_FILE_NOT_FOUND, msg)
        _require_regular_blob(entry, norm_path)

        blob_ref = f"{self.head_commit}:{norm_path}"
        rc_sz, out_sz, _err_sz = await self._exec_git(
            "cat-file", "-s", "--end-of-options", blob_ref
        )
        try:
            blob_size = int(out_sz.decode("ascii", errors="replace").strip())
        except ValueError:
            blob_size = -1
        if rc_sz != 0 or blob_size < 0:
            msg = f"File '{norm_path}' not found at {self.head_commit}"
            raise RepoToolPolicyError(CODE_REPO_FILE_NOT_FOUND, msg)
        if blob_size > MAX_BLOB_READ_BYTES:
            msg = f"File too large ({blob_size} bytes > {MAX_BLOB_READ_BYTES}): {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        rc, stdout, stderr = await self._exec_git("cat-file", "-p", "--end-of-options", blob_ref)
        if rc != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            msg = f"File '{norm_path}' not found at {self.head_commit}: {err_msg}"
            raise RepoToolPolicyError(CODE_REPO_FILE_NOT_FOUND, msg)

        stdout = stdout[:MAX_BLOB_READ_BYTES]
        if b"\0" in stdout:
            msg = f"Binary file unsupported: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_BINARY_FILE_UNSUPPORTED, msg)

        text = stdout.decode("utf-8", errors="replace")
        lines = text.splitlines()

        # Slice 1-indexed line range
        selected_lines = lines[start - 1 : end]
        formatted = "\n".join(
            f"{start + idx:4d} | {line_content}" for idx, line_content in enumerate(selected_lines)
        )
        return _cap_and_scrub(formatted.encode("utf-8"))

    async def repo_grep(self, pattern: str, path: str = "") -> str:
        """Search commit-pinned files for literal string pattern."""
        if not (1 <= len(pattern) <= MAX_GREP_PATTERN_LEN):
            msg = f"Pattern length must be between 1 and {MAX_GREP_PATTERN_LEN} characters"
            raise RepoToolPolicyError(CODE_REPO_GREP_PATTERN_INVALID, msg)

        norm_path = normalize_repo_relpath(path) if path else ""
        if norm_path and is_secret_repo_path(norm_path):
            msg = f"Access to secret path denied: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_SECRET_PATH_DENIED, msg)

        cmd_args = [
            "grep",
            "-I",
            "-n",
            "--fixed-strings",
            "--max-count=50",
            "-e",
            pattern,
            "--end-of-options",
            self.head_commit,
            "--",
        ]
        cmd_args.append(norm_path or ".")
        cmd_args.extend(_SECRET_PATH_EXCLUDES)

        rc, stdout, _stderr = await self._exec_git(*cmd_args)
        if rc == 1:
            # Exit code 1 means pattern not found (clean)
            return ""
        if rc != 0:
            # Other errors
            return ""

        prefix_to_strip = f"{self.head_commit}:"
        filtered_lines: list[str] = []

        for line in stdout.splitlines():
            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            line_str = line_str.removeprefix(prefix_to_strip)

            # Split path:line_num:match
            parts = line_str.split(":", 2)
            if parts:
                rel_file = parts[0]
                if is_secret_repo_path(rel_file):
                    continue

            filtered_lines.append(line_str)

        joined = "\n".join(filtered_lines)
        return _cap_and_scrub(joined.encode("utf-8"))

    async def repo_git_log(self, path: str = "", max_commits: int = 20) -> str:
        """Retrieve commit log history leading up to head_commit."""
        norm_path = normalize_repo_relpath(path) if path else ""
        if norm_path and is_secret_repo_path(norm_path):
            msg = f"Access to secret path denied: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_SECRET_PATH_DENIED, msg)

        commits_limit = max(1, min(MAX_LOG_COMMITS, int(max_commits)))

        cmd_args = [
            "log",
            f"-n{commits_limit}",
            "--format=%H%x09%ad%x09%an%x09%s%x09%G?%x09%GS%x09%GK",
            "--date=iso-strict",
            "--end-of-options",
            self.head_commit,
        ]
        cmd_args.append("--")
        cmd_args.append(norm_path or ".")
        cmd_args.extend(_SECRET_PATH_EXCLUDES)

        rc, stdout, stderr = await self._exec_git(*cmd_args)
        if rc != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return scrub_text(f"repo_git_log error (exit {rc}): {err_msg}")

        return _cap_and_scrub(stdout)

    async def repo_git_diff(self, base_ref: str, path: str = "") -> str:
        """Generate unified diff between base_ref and head_commit excluding secret files."""
        if not (1 <= len(base_ref) <= MAX_DIFF_BASE_REF_LEN):
            msg = f"base_ref length must be between 1 and {MAX_DIFF_BASE_REF_LEN}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        if not _RE_BASE_REF.match(base_ref) or ".." in base_ref or base_ref.startswith("-"):
            msg = f"Invalid base_ref syntax: {base_ref}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        # Resolve base_ref to 40/64 hex sha
        rc_rev, stdout_rev, stderr_rev = await self._exec_git(
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        )
        if rc_rev != 0:
            err_msg = stderr_rev.decode("utf-8", errors="replace").strip()
            msg = f"Base ref '{base_ref}' cannot be resolved to a commit: {err_msg}"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

        base_sha = stdout_rev.decode("utf-8", errors="replace").strip()

        norm_path = normalize_repo_relpath(path) if path else ""
        if norm_path and is_secret_repo_path(norm_path):
            msg = f"Access to secret path denied: {norm_path}"
            raise RepoToolPolicyError(CODE_REPO_SECRET_PATH_DENIED, msg)

        cmd_args = [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--unified=3",
            "--end-of-options",
            base_sha,
            self.head_commit,
        ]
        if norm_path:
            cmd_args.extend(["--", norm_path])
        else:
            cmd_args.append("--")

        cmd_args.extend(_SECRET_PATH_EXCLUDES)

        rc, stdout, stderr = await self._exec_git(*cmd_args)
        if rc != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return scrub_text(f"repo_git_diff error (exit {rc}): {err_msg}")

        return _cap_and_scrub(stdout)

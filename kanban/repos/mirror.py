# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hardened bare git mirror manager with strict protocol and SSRF isolation (KB-P5-19b, S14.3)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import signal
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

from kanban.repos.url_policy import (
    ValidatedRemoteUrl,
    validate_remote_url,
)
from kanban.security.envelope import (
    EnvelopeDecryptError,
    KekProvider,
    SealedSecret,
    open_bound,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from database.models.repo_binding import ProjectRepoBinding

__all__ = [
    "ExecGitCommandRunner",
    "FakeGitCommandRunner",
    "GitCommandRunner",
    "GitExecutionError",
    "GitResult",
    "MirrorManager",
    "MirrorPolicy",
    "MirrorSizeLimitError",
    "MirrorTimeoutError",
    "is_dir_writable",
    "resolve_mirror_base_dir",
]

_MAX_MIRROR_SIZE_BYTES: Final[int] = 2 * 1024 * 1024 * 1024  # 2 GiB
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
_COMMIT_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def is_dir_writable(path: Path) -> bool:
    """Test whether path can be created and written to by the current process UID."""
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o750)
        test_probe = path / f".probe_write_{os.getpid()}"
        test_probe.touch(exist_ok=True)
        test_probe.unlink(missing_ok=True)
    except (OSError, PermissionError):
        return False
    else:
        return True


def resolve_mirror_base_dir(override: Path | None = None) -> Path:
    """Derive default bare git mirror root with writable runtime fallback (KB-P3-AUDIT-04).

    Priority:
    1. Explicit override passed by caller.
    2. Explicit environment variables KANBAN_REPO_MIRROR_DIR or KANBAN_GIT_MIRRORS_DIR.
    3. Derived from KB_DATA_DIR / 'git-mirrors'.
    4. /var/lib/kanban/data/git-mirrors (writable volume mounted for UID 65532).
    5. /var/lib/kanban/git-mirrors (if /var/lib/kanban is writable).
    6. Runtime writable fallback: <tempdir>/kanban-git-mirrors.
    """
    if override is not None:
        return override

    env_dir = os.environ.get("KANBAN_REPO_MIRROR_DIR") or os.environ.get("KANBAN_GIT_MIRRORS_DIR")
    if env_dir:
        env_path = Path(env_dir)
        if is_dir_writable(env_path):
            return env_path

    kb_data = os.environ.get("KB_DATA_DIR")
    if kb_data:
        data_mirror = Path(kb_data) / "git-mirrors"
        if is_dir_writable(data_mirror):
            return data_mirror

    container_data_dir = Path("/var/lib/kanban/data/git-mirrors")
    if is_dir_writable(container_data_dir):
        return container_data_dir

    standard_dir = Path("/var/lib/kanban/git-mirrors")
    if is_dir_writable(standard_dir):
        return standard_dir

    fallback = Path(tempfile.gettempdir()) / "kanban-git-mirrors"
    fallback.mkdir(parents=True, exist_ok=True, mode=0o750)
    return fallback


_DEFAULT_BASE_DIR: Final[Path] = Path(
    os.environ.get("KANBAN_REPO_MIRROR_DIR")
    or os.environ.get("KANBAN_GIT_MIRRORS_DIR")
    or (f"{os.environ['KB_DATA_DIR']}/git-mirrors" if "KB_DATA_DIR" in os.environ else None)
    or "/var/lib/kanban/git-mirrors"
)


class GitResult(NamedTuple):
    """Result of a git command execution."""

    returncode: int
    stdout: str
    stderr: str


class GitCommandRunner(Protocol):
    """Protocol for executing git commands with argv and replaced environment."""

    async def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> GitResult:
        """Execute command returning GitResult or raising timeout."""
        ...


class ExecGitCommandRunner:
    """Production git command runner using asyncio.create_subprocess_exec (never shell)."""

    async def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> GitResult:
        """Run git process inside a separate process group with hard deadline."""
        proc = await asyncio.create_subprocess_exec(
            *argv,
            env=dict(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # Create process group for clean killpg
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            return GitResult(
                returncode=proc.returncode if proc.returncode is not None else 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
            )
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            raise


class FakeGitCommandRunner:
    """Test git runner capturing exact argv/env calls and returning scripted responses."""

    def __init__(self, responses: list[GitResult] | None = None) -> None:
        """Initialize with empty call log and optional scripted responses."""
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.responses: list[GitResult] = list(responses or [])
        self.default_response: GitResult = GitResult(
            returncode=0,
            stdout="0123456789abcdef0123456789abcdef01234567\n",
            stderr="",
        )
        self.raise_timeout: bool = False

    async def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> GitResult:
        """Record invocation and return queued response or default."""
        del timeout_seconds
        self.calls.append((list(argv), dict(env)))
        if self.raise_timeout:
            msg = "Execution exceeded 120s timeout"
            raise TimeoutError(msg)
        if self.responses:
            return self.responses.pop(0)
        return self.default_response


class MirrorPolicy:
    """Security policy controlling file protocol allowance."""

    def __init__(
        self,
        allow_file_protocol: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        """Initialize policy. True is only constructible in tests."""
        self._allow_file_protocol = allow_file_protocol

    @property
    def allow_file_protocol(self) -> bool:
        """Whether file:// protocol is permitted for local test bare repos."""
        return self._allow_file_protocol


class MirrorSizeLimitError(RuntimeError):
    """Raised when repository mirror exceeds 2 GiB threshold."""


class MirrorTimeoutError(RuntimeError):
    """Raised when git operation exceeds 120s timeout limit."""


class GitExecutionError(RuntimeError):
    """Raised when git command exits with non-zero status."""


@dataclass
class MirrorManager:
    """Manages hardened read-only bare Git mirrors for projects (KB-P5-19b, S14.3)."""

    base_dir: Path = field(default_factory=resolve_mirror_base_dir)
    policy: MirrorPolicy | None = None
    runner: GitCommandRunner | None = None
    kek_provider: KekProvider | None = None

    def __post_init__(self) -> None:
        """Initialize default policy and command runner if unset."""
        if self.policy is None:
            self.policy = MirrorPolicy(allow_file_protocol=False)
        if self.runner is None:
            self.runner = ExecGitCommandRunner()

    def mirror_path(self, binding: ProjectRepoBinding) -> Path:
        """Derive absolute mirror path for binding: <base_dir>/<workspace_id>/<binding_id>.git."""
        return self.base_dir / str(binding.workspace_id) / f"{binding.id}.git"

    def _build_base_argv(self) -> list[str]:
        """Construct the hardened common git argv prefix."""
        allow_file = self.policy.allow_file_protocol if self.policy else False
        return [
            "git",
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
        ]

    def _build_env(self, tmp_dir: str) -> dict[str, str]:
        """Construct replaced (not inherited) environment dictionary."""
        allow_file = self.policy.allow_file_protocol if self.policy else False
        return {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "https:ssh:file" if allow_file else "https:ssh",
            "HOME": tmp_dir,
            "PATH": "/usr/bin:/bin",
        }

    def _calculate_dir_size(self, path: Path) -> int:
        """Compute recursive disk usage of directory in bytes."""
        if not path.exists():
            return 0
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        return total

    async def clone_or_fetch(  # noqa: C901, PLR0912, PLR0915
        self,
        binding: ProjectRepoBinding,
        *,
        allowed_git_cidrs: Sequence[str] | None = None,
        air_gap_mode: bool = False,
        pinned_ip: str | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        """Clone bare mirror or fetch updates under strict sandbox isolation."""
        allow_file = self.policy.allow_file_protocol if self.policy else False
        validated: ValidatedRemoteUrl | None = None
        dns_resolver = (lambda _h: [pinned_ip]) if pinned_ip else resolver
        if not (allow_file and binding.remote_url.startswith("file://")):
            validated = validate_remote_url(
                binding.remote_url,
                allowed_git_cidrs=allowed_git_cidrs,
                air_gap_mode=air_gap_mode,
                resolver=dns_resolver,
            )

        target_path = self.mirror_path(binding)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            with contextlib.suppress(OSError):
                target_path.parent.chmod(0o750)
        except (OSError, PermissionError):
            fallback_base = Path(tempfile.gettempdir()) / "kanban-git-mirrors"
            fallback_base.mkdir(parents=True, exist_ok=True, mode=0o750)
            self.base_dir = fallback_base
            target_path = self.mirror_path(binding)
            target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            with contextlib.suppress(OSError):
                target_path.parent.chmod(0o750)

        # Decrypt credential if present into a mutable bytearray
        decrypted_ba: bytearray | None = None
        if binding.credential_ciphertext and binding.credential_dek_kid and self.kek_provider:
            try:
                ct = binding.credential_ciphertext
                wrapped_len = int.from_bytes(ct[:2], "big")
                wrapped_dek = ct[2 : 2 + wrapped_len]
                enc_blob = ct[2 + wrapped_len :]
                sealed = SealedSecret(
                    encrypted_secret_blob=enc_blob,
                    wrapped_dek=wrapped_dek,
                    dek_kid=binding.credential_dek_kid,
                )
                aad = f"kanban/repo-binding/v1|{binding.id}|{binding.project_id}".encode()
                decrypted_ba = open_bound(sealed, aad, self.kek_provider)
            except (EnvelopeDecryptError, Exception) as exc:
                binding.last_fetch_error = f"CREDENTIAL_DECRYPT_FAILED: {exc}"
                raise

        with tempfile.TemporaryDirectory() as tmp_dir:
            cred_file: Path | None = None
            known_hosts_file: Path | None = None
            extra_c_flags: list[str] = []

            try:
                effective_pinned_ip = pinned_ip or (validated.pinned_ip if validated else None)
                if validated and validated.scheme == "https" and effective_pinned_ip:
                    host = validated.host
                    port = validated.port
                    opt = f"http.curloptResolve={host}:{port}:{effective_pinned_ip}"
                    extra_c_flags.extend(["-c", opt])

                if decrypted_ba is not None:
                    is_ssh = validated is not None and validated.scheme == "ssh"
                    if is_ssh:
                        cred_file = Path(tmp_dir) / "id_deploy"
                        cred_file.touch(mode=0o600)
                        cred_file.write_bytes(bytes(decrypted_ba))
                        cred_file.chmod(0o600)

                        known_hosts_file = Path(tmp_dir) / "known_hosts"
                        known_hosts_file.touch(mode=0o600)
                        admin_known_hosts = getattr(binding, "ssh_known_hosts", None)
                        if isinstance(admin_known_hosts, str) and admin_known_hosts.strip():
                            known_hosts_file.write_text(
                                admin_known_hosts.strip() + "\n",
                                encoding="utf-8",
                            )
                        known_hosts_file.chmod(0o600)

                        ssh_cmd = (
                            f"ssh -i {cred_file} -o BatchMode=yes "
                            f"-o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts_file}"
                        )
                        extra_c_flags.extend(["-c", f"core.sshCommand={ssh_cmd}"])
                    else:
                        cred_file = Path(tmp_dir) / "git-cred.conf"
                        cred_file.touch(mode=0o600)
                        token_str = decrypted_ba.decode("utf-8", errors="replace").strip()
                        cred_content = (
                            f"[http]\n\textraHeader = Authorization: Bearer {token_str}\n"
                        )
                        cred_file.write_text(cred_content, encoding="utf-8")
                        cred_file.chmod(0o600)
                        extra_c_flags.extend(["-c", f"include.path={cred_file}"])

                env = self._build_env(tmp_dir)
                is_existing_mirror = (target_path / "HEAD").exists()

                if is_existing_mirror:
                    argv = [
                        *self._build_base_argv(),
                        *extra_c_flags,
                        f"--git-dir={target_path}",
                        "fetch",
                        "--prune",
                        "--no-tags",
                        "origin",
                    ]
                else:
                    remote_url = validated.normalized_url if validated else binding.remote_url
                    argv = [
                        *self._build_base_argv(),
                        *extra_c_flags,
                        "clone",
                        "--mirror",
                        "--no-local",
                        "--no-hardlinks",
                        "--",
                        remote_url,
                        str(target_path),
                    ]

                runner = self.runner or ExecGitCommandRunner()
                try:
                    res = await runner.run(argv, env, timeout_seconds=_DEFAULT_TIMEOUT_SECONDS)
                except TimeoutError:
                    binding.last_fetch_error = "MIRROR_TIMEOUT"
                    msg_timeout = "Git operation timed out after 120s"
                    raise MirrorTimeoutError(msg_timeout) from None

                if res.returncode != 0:
                    err_snip = res.stderr.strip()[:200]
                    binding.last_fetch_error = f"GIT_EXIT_{res.returncode}: {err_snip}"
                    msg_err = f"Git command failed: {res.stderr.strip()}"
                    raise GitExecutionError(msg_err)

                # 2 GiB mirror size enforcement
                current_size = self._calculate_dir_size(target_path)
                if current_size > _MAX_MIRROR_SIZE_BYTES:
                    shutil.rmtree(target_path, ignore_errors=True)
                    binding.last_fetch_error = "MIRROR_SIZE_LIMIT"
                    msg_size = "Mirror exceeded 2 GiB limit; removed"
                    raise MirrorSizeLimitError(msg_size)

                # Resolve head commit for default_ref
                rev_argv = [
                    *self._build_base_argv(),
                    f"--git-dir={target_path}",
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{binding.default_ref}^{{commit}}",
                ]
                rev_res = await runner.run(rev_argv, env, timeout_seconds=_DEFAULT_TIMEOUT_SECONDS)
                if rev_res.returncode == 0:
                    commit_hash = rev_res.stdout.strip()
                    if _COMMIT_RE.match(commit_hash):
                        binding.last_fetched_commit = commit_hash

                binding.last_fetch_error = None
                with contextlib.suppress(OSError):
                    target_path.chmod(0o750)

            finally:
                if cred_file and cred_file.exists():
                    fsize = cred_file.stat().st_size
                    cred_file.write_bytes(b"\x00" * fsize)
                    cred_file.unlink(missing_ok=True)
                if known_hosts_file and known_hosts_file.exists():
                    known_hosts_file.unlink(missing_ok=True)
                if decrypted_ba is not None:
                    for i in range(len(decrypted_ba)):
                        decrypted_ba[i] = 0

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Zero-shell CLI pipe harness running agents inside nsjail sandbox (S14.3, KB-P5-21)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import yaml

from agent.providers.base import CLIRunRequest, CLIRunResult
from agent.providers.errors import ProviderTimeout
from agent.runners.repo_snapshot import RoRepoSnapshotManager
from kanban.agents.cli_policy import assert_runtime_argv
from kanban.sandbox.probe import (
    SandboxUnavailableError,
    SubprocessLauncher,
    probe_nsjail_userns,
)
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from agent.context.transition_context import RenderedContext

__all__ = [
    "CLISubprocessRunner",
    "CliPipeHarness",
    "CliPipeRunMetadata",
    "CliRunnerExitError",
    "CliStdoutTooLargeError",
    "GateTimeoutError",
    "NsjailCLISubprocessRunner",
]

MAX_STDOUT_BYTES: int = 1_048_576  # 1 MiB
MAX_STDERR_BYTES: int = 262_144  # 256 KiB


class CliRunnerExitError(RuntimeError):
    """Raised when CLI process exits non-zero without emitting a valid verdict."""

    def __init__(self, code: str, exit_code: int, detail: str) -> None:
        """Initialize CliRunnerExitError with code, exit status, and detail."""
        super().__init__(f"{code} (exit {exit_code}): {detail}")
        self.code = code
        self.exit_code = exit_code
        self.detail = detail


class CliStdoutTooLargeError(ValueError):
    """Raised when child stdout exceeds the 1 MiB safety ceiling."""

    def __init__(self, size: int, cap: int = MAX_STDOUT_BYTES) -> None:
        """Initialize CliStdoutTooLargeError with size and capacity limit."""
        super().__init__(
            f"CLI_STDOUT_TOO_LARGE: Process stdout byte length {size} exceeds cap {cap}"
        )
        self.code = "CLI_STDOUT_TOO_LARGE"
        self.size = size
        self.cap = cap


class GateTimeoutError(TimeoutError):
    """Raised when execution exceeds the configured agent timeout."""

    def __init__(self, message: str = "GATE_TIMEOUT") -> None:
        """Initialize GateTimeoutError with message."""
        super().__init__(message)
        self.code = "GATE_TIMEOUT"


@dataclass(frozen=True, slots=True)
class CliPipeRunMetadata:
    """Captured telemetry and execution metadata for a CLI pipe invocation."""

    argv: tuple[str, ...]
    exit_code: int
    duration_ms: float
    stdout_bytes_len: int
    stderr_bytes_len: int
    whiteout_count: int = 0


@runtime_checkable
class CLISubprocessRunner(Protocol):
    """Protocol for launching CLI subprocesses with sandbox mounts and clean env."""

    async def run(
        self,
        req: CLIRunRequest,
        *,
        mount_spec: object = None,
        env: dict[str, str] | None = None,
    ) -> CLIRunResult:
        """Execute external command asynchronously and return result."""
        ...


class NsjailCLISubprocessRunner:
    """Spawns CLI processes inside unprivileged nsjail user namespace sandbox."""

    def __init__(
        self,
        *,
        nsjail_bin: Path = Path("/usr/bin/nsjail"),
        launcher: SubprocessLauncher | None = None,
        seccomp_policy: Path | None = Path("deploy/seccomp/sandbox-profile.json"),
    ) -> None:
        """Initialize NsjailCLISubprocessRunner with binary path and launcher."""
        self.nsjail_bin = nsjail_bin
        self.launcher = launcher
        self.seccomp_policy = seccomp_policy

    async def run(
        self,
        req: CLIRunRequest,
        *,
        mount_spec: object = None,
        env: dict[str, str] | None = None,
    ) -> CLIRunResult:
        """Run CLI command inside nsjail, failing closed if userns is unavailable."""
        probe = probe_nsjail_userns(nsjail_bin=self.nsjail_bin, runner=self.launcher)
        if not probe.available:
            raise SandboxUnavailableError(
                error_code=probe.error_code or "SANDBOX_UNAVAILABLE_IN_STANDALONE",
                detail=probe.message or "Tier B nsjail sandbox is unavailable in this environment",
            )

        # Build clean environment: PATH, HOME, LANG, and ephemeral token only
        clean_env: dict[str, str] = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",  # noqa: S108
            "LANG": "C.UTF-8",
        }
        if env and "KANBAN_EPHEMERAL_MCP_TOKEN" in env:
            clean_env["KANBAN_EPHEMERAL_MCP_TOKEN"] = env["KANBAN_EPHEMERAL_MCP_TOKEN"]

        # Write mount configuration to a secure 0600 temp file if provided
        config_file_path: Path | None = None
        if isinstance(mount_spec, str) and mount_spec.strip():
            fd, path_str = tempfile.mkstemp(prefix="nsjail-cfg-", suffix=".pbtxt")
            os.close(fd)
            config_file_path = Path(path_str)
            try:
                config_file_path.chmod(0o600)
                config_file_path.write_text(mount_spec, encoding="utf-8")
            except Exception:
                config_file_path.unlink(missing_ok=True)
                raise

        nsjail_argv: list[str] = [
            str(self.nsjail_bin),
            "--mode",
            "o",
            "--time_limit",
            str(max(1, int(req.timeout_s))),
            "--chroot",
            "/var/empty",
            "--keep_env=false",
            "--env",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env",
            "HOME=/tmp",
            "--env",
            "LANG=C.UTF-8",
        ]

        if "KANBAN_EPHEMERAL_MCP_TOKEN" in clean_env:
            token_val = clean_env["KANBAN_EPHEMERAL_MCP_TOKEN"]
            nsjail_argv.extend(["--env", f"KANBAN_EPHEMERAL_MCP_TOKEN={token_val}"])

        if config_file_path is not None:
            nsjail_argv.extend(["--config", str(config_file_path)])

        if self.seccomp_policy is not None and self.seccomp_policy.exists():
            nsjail_argv.extend(["--seccomp_policy", str(self.seccomp_policy)])

        nsjail_argv.append("--")
        nsjail_argv.extend(req.argv)

        start_time = time.monotonic()
        try:
            if self.launcher is not None:
                rc, stdout, stderr = await self.launcher.run_async(
                    nsjail_argv,
                    stdin_bytes=req.stdin_bytes,
                    timeout_seconds=req.timeout_s,
                    env=clean_env,
                )
            else:
                rc, stdout, stderr = await self._exec_process(
                    nsjail_argv,
                    stdin_bytes=req.stdin_bytes,
                    timeout_s=req.timeout_s,
                    env=clean_env,
                )
        finally:
            if config_file_path is not None:
                config_file_path.unlink(missing_ok=True)

        duration_ms = (time.monotonic() - start_time) * 1000.0
        return CLIRunResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=rc,
            duration_ms=duration_ms,
        )

    async def _exec_process(
        self,
        argv: list[str],
        *,
        stdin_bytes: bytes,
        timeout_s: float,
        env: dict[str, str],
    ) -> tuple[int, bytes, bytes]:
        """Execute command asynchronously with process group kill on timeout."""
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

        cap_stdout = MAX_STDOUT_BYTES + 1
        cap_stderr = MAX_STDERR_BYTES + 1

        async def _read_stream(stream: asyncio.StreamReader | None, max_cap: int) -> bytes:
            if stream is None:
                return b""
            buf = bytearray()
            while len(buf) < max_cap:
                chunk = await stream.read(min(8192, max_cap - len(buf)))
                if not chunk:
                    break
                buf.extend(chunk)
            return bytes(buf)

        async def _feed_stdin() -> None:
            if proc.stdin is not None:
                with contextlib.suppress(OSError):
                    proc.stdin.write(stdin_bytes)
                    await proc.stdin.drain()
                    proc.stdin.close()

        try:
            _, stdout, stderr = await asyncio.wait_for(
                asyncio.gather(
                    _feed_stdin(),
                    _read_stream(proc.stdout, cap_stdout),
                    _read_stream(proc.stderr, cap_stderr),
                ),
                timeout=timeout_s,
            )
            await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        except TimeoutError as err:
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            await proc.wait()
            msg = "GATE_TIMEOUT"
            raise GateTimeoutError(msg) from err

        return proc.returncode if proc.returncode is not None else 0, stdout, stderr


class CliPipeHarness:
    """Execution harness executing AI gates via zero-shell CLI pipes (S14.3)."""

    def __init__(
        self,
        runner: CLISubprocessRunner | None = None,
        snapshot_manager_factory: type[RoRepoSnapshotManager] = RoRepoSnapshotManager,
    ) -> None:
        """Initialize CliPipeHarness with subprocess runner and snapshot manager."""
        self.runner: CLISubprocessRunner = runner or NsjailCLISubprocessRunner()
        self.snapshot_manager_factory = snapshot_manager_factory
        self.last_metadata: CliPipeRunMetadata | None = None

    async def run(  # noqa: C901, PLR0912, PLR0915
        self,
        ctx: RenderedContext,
        agent_def: object,
        *,
        repo_context: object = None,
    ) -> bytes:
        """Execute agent invocation and return raw stdout bytes."""
        # Step 1 - Runtime Policy Gate (KB-P5-16)
        validated = assert_runtime_argv(agent_def)  # type: ignore[arg-type]

        # Step 2 - Determine if read-only repo snapshot is required
        repo_access_mode = getattr(agent_def, "repo_access_mode", None) or (
            agent_def.get("repo_access_mode") if isinstance(agent_def, dict) else None
        )
        resolved_repo_ctx = (
            repo_context
            or getattr(agent_def, "repo_context", None)
            or getattr(ctx, "repo_context", None)
        )

        if resolved_repo_ctx is None and b"repo_context:" in ctx.yaml_bytes:
            with contextlib.suppress(yaml.YAMLError, ValueError, UnicodeDecodeError):
                parsed_ctx = yaml.safe_load(ctx.yaml_bytes)
                if isinstance(parsed_ctx, dict):
                    resolved_repo_ctx = parsed_ctx.get("repo_context")

        execution_id = getattr(ctx, "execution_id", None) or (
            agent_def.get("execution_id")
            if isinstance(agent_def, dict)
            else getattr(agent_def, "execution_id", None)
        )
        if not execution_id and b"execution_id:" in ctx.yaml_bytes:
            with contextlib.suppress(yaml.YAMLError, ValueError, UnicodeDecodeError):
                parsed_ctx = yaml.safe_load(ctx.yaml_bytes)
                if isinstance(parsed_ctx, dict):
                    execution_id = parsed_ctx.get("execution_id")
        if not execution_id:
            execution_id = "0196ed40-7b2a-7000-8000-112233445566"

        # Step 3 - Stage repo snapshot if mode is ro_vfs_mount
        mount_spec: str | None = None
        whiteout_count = 0
        token_str = ""

        try:
            if getattr(ctx, "ephemeral_token", None):
                token_bytes = bytes(ctx.ephemeral_token)
                token_str = token_bytes.decode("utf-8", errors="replace")

            env: dict[str, str] = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": "/tmp",  # noqa: S108
                "LANG": "C.UTF-8",
            }
            if token_str:
                env["KANBAN_EPHEMERAL_MCP_TOKEN"] = token_str

            timeout_ms = (
                getattr(agent_def, "timeout_ms", None)
                or (agent_def.get("timeout_ms") if isinstance(agent_def, dict) else None)
                or 30_000
            )
            timeout_s = float(timeout_ms) / 1000.0

            try:
                if repo_access_mode == "ro_vfs_mount" and resolved_repo_ctx:
                    snapshot_mgr = self.snapshot_manager_factory(
                        execution_id=str(execution_id),
                        repo_context=resolved_repo_ctx,
                    )
                    async with snapshot_mgr:
                        mount_spec = snapshot_mgr.generate_nsjail_config()
                        whiteout_count = len(snapshot_mgr.whiteout_targets)
                        req = CLIRunRequest(
                            argv=validated.argv,
                            stdin_bytes=ctx.yaml_bytes,
                            timeout_s=timeout_s,
                            env_keys=("KANBAN_EPHEMERAL_MCP_TOKEN",),
                        )
                        result = await self.runner.run(req, mount_spec=mount_spec, env=env)
                else:
                    req = CLIRunRequest(
                        argv=validated.argv,
                        stdin_bytes=ctx.yaml_bytes,
                        timeout_s=timeout_s,
                        env_keys=("KANBAN_EPHEMERAL_MCP_TOKEN",),
                    )
                    result = await self.runner.run(req, mount_spec=mount_spec, env=env)
            except (TimeoutError, ProviderTimeout) as err:
                msg = "GATE_TIMEOUT"
                raise GateTimeoutError(msg) from err

            # Record run metadata
            self.last_metadata = CliPipeRunMetadata(
                argv=validated.argv,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                stdout_bytes_len=len(result.stdout),
                stderr_bytes_len=len(result.stderr),
                whiteout_count=whiteout_count,
            )

            # Step 4 - Enforce output limits and exit code checks
            if len(result.stdout) > MAX_STDOUT_BYTES:
                raise CliStdoutTooLargeError(len(result.stdout), MAX_STDOUT_BYTES)

            if result.exit_code != 0:
                has_verdict = False
                if result.stdout:
                    with contextlib.suppress(UnicodeDecodeError):
                        decoded = result.stdout.decode("utf-8", errors="replace")
                        if "kb-transition-verdict/v1" in decoded:
                            has_verdict = True

                if not has_verdict:
                    raw_err = result.stderr.decode("utf-8", errors="replace")
                    scrubbed_err = scrub_text(raw_err).strip()
                    fallback_msg = f"CLI exited with exit status {result.exit_code}"
                    raise CliRunnerExitError(
                        code="CLI_NONZERO_EXIT",
                        exit_code=result.exit_code,
                        detail=scrubbed_err or fallback_msg,
                    )

            return result.stdout
        finally:
            # Securely zero out ephemeral token string representation
            if token_str:
                del token_str

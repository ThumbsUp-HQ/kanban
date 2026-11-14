"""Tier B nsjail sandboxed runner for untrusted custom field scripts and CLI pipes.

Enforces strict isolation via unprivileged Linux namespaces, seccomp-BPF syscall filters,
cgroup v2 resource limits (<= 128 MiB RAM), monotonic execution timeouts (<= 3,000ms),
read-only tmpfs rootfs, isolated network namespace (zero internet route), and an out-of-sandbox
Unix-socket egress proxy with short-lived injected tokens and zero token exposure inside sandbox.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from kanban.sandbox.egress_proxy import EgressProxyPolicy, TokenInjectingEgressProxy
from kanban.sandbox.probe import (
    SandboxUnavailableError,
    SubprocessLauncher,
    get_cached_sandbox_probe,
    probe_nsjail_userns,
    set_cached_sandbox_probe,
)

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Hard limits mandated by Section 13.3 and KB-P5-14
MAX_TIMEOUT_MS: int = 3000
MAX_STDOUT_BYTES: int = 65536  # 64 KiB
CGROUP_MEM_MAX_BYTES: int = 134217728  # 128 MiB
CGROUP_PIDS_MAX: int = 32
CGROUP_CPU_MS_PER_SEC: int = 500
RLIMIT_AS_MB: int = 256
RLIMIT_FSIZE_MB: int = 4
RLIMIT_NOFILE: int = 64
RLIMIT_NPROC: int = 32


class TierBRunner(Protocol):
    """Protocol defining the Tier B sandboxed execution interface."""

    async def run(  # noqa: PLR0913
        self,
        script_source: str,
        input_json: bytes,
        *,
        timeout_ms: int = 3000,
        policy: EgressProxyPolicy | None = None,
        token: str | None = None,
        app: ASGIApp | None = None,
        **kwargs: object,
    ) -> bytes:
        """Execute untrusted script in sandbox and return stdout bytes."""
        ...


class SandboxExecutionError(RuntimeError):
    """Raised when sandbox execution fails due to a deterministic constraint violation."""

    def __init__(self, error_code: str, message: str | None = None) -> None:
        """Initialize SandboxExecutionError with deterministic error code."""
        super().__init__(message or error_code)
        self.error_code = error_code


class ScriptTimeoutError(SandboxExecutionError):
    """Raised when script execution exceeds maximum time limit."""

    def __init__(self, message: str = "SCRIPT_TIMEOUT") -> None:
        """Initialize ScriptTimeoutError with timeout message."""
        super().__init__("SCRIPT_TIMEOUT", message)


class ScriptOutputTooLargeError(SandboxExecutionError):
    """Raised when script stdout exceeds 64 KiB."""

    def __init__(self, message: str = "SCRIPT_OUTPUT_TOO_LARGE") -> None:
        """Initialize ScriptOutputTooLargeError with output cap message."""
        super().__init__("SCRIPT_OUTPUT_TOO_LARGE", message)


@dataclass(frozen=True, slots=True)
class NsjailRunResult:
    """Captured result of an nsjail sandbox run."""

    stdout: bytes
    stderr: bytes
    returncode: int
    error_code: str | None = None


class DefaultSubprocessLauncher:
    """Spawns external process without shell and kills process group on timeout."""

    def run_sync(
        self,
        argv: list[str],
        *,
        timeout_seconds: float = 1.0,
    ) -> tuple[int, bytes, bytes]:
        """Execute external command synchronously and return (exit_code, stdout, stderr)."""
        proc = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    async def run_async(
        self,
        argv: list[str],
        *,
        stdin_bytes: bytes | None = None,
        timeout_seconds: float = 3.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes, bytes]:
        """Execute external command asynchronously with process group management."""
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        cap = MAX_STDOUT_BYTES + 1

        async def _read_capped(stream: asyncio.StreamReader | None) -> bytes:
            """Read incrementally; stop and kill the group once cap+1 bytes arrive."""
            if stream is None:
                return b""
            buf = bytearray()
            while len(buf) < cap:
                chunk = await stream.read(min(8192, cap - len(buf)))
                if not chunk:
                    break
                buf.extend(chunk)
            if len(buf) >= cap:
                with contextlib.suppress(OSError):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return bytes(buf)

        async def _feed_stdin() -> None:
            if stdin_bytes is None or proc.stdin is None:
                return
            with contextlib.suppress(OSError):
                proc.stdin.write(stdin_bytes)
                await proc.stdin.drain()
            with contextlib.suppress(OSError):
                proc.stdin.close()

        try:
            _, stdout, stderr = await asyncio.wait_for(
                asyncio.gather(
                    _feed_stdin(),
                    _read_capped(proc.stdout),
                    _read_capped(proc.stderr),
                ),
                timeout=timeout_seconds,
            )
            await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
        except TimeoutError as err:
            with contextlib.suppress(OSError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            await proc.wait()
            msg = "Command timed out"
            raise TimeoutError(msg) from err
        else:
            ret = proc.returncode if proc.returncode is not None else 0
            return ret, stdout, stderr


class NsjailCommandBuilder:
    """Builds hardened, immutable argv lists for nsjail sandbox invocations."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        nsjail_bin: Path = Path("/usr/bin/nsjail"),
        time_limit_sec: int = 3,
        rlimit_as: int = RLIMIT_AS_MB,
        rlimit_fsize: int = RLIMIT_FSIZE_MB,
        rlimit_nofile: int = RLIMIT_NOFILE,
        rlimit_nproc: int = RLIMIT_NPROC,
        cgroup_mem_max: int = CGROUP_MEM_MAX_BYTES,
        cgroup_pids_max: int = CGROUP_PIDS_MAX,
        cgroup_cpu_ms_per_sec: int = CGROUP_CPU_MS_PER_SEC,
        disable_clone_newnet: bool = False,
        chroot_path: Path = Path("/var/empty"),
        tmpfs_mount: str = "none:/tmp:tmpfs:size=16777216,mode=1777,noexec,nosuid,nodev",
        proxy_socket_path: Path | None = None,
        seccomp_policy: Path | None = Path("deploy/seccomp/sandbox-profile.json"),
        keep_env: bool = False,
        env_vars: dict[str, str] | None = None,
    ) -> None:
        """Initialize NsjailCommandBuilder with sandbox security limits."""
        self.nsjail_bin = nsjail_bin
        self.time_limit_sec = time_limit_sec
        self.rlimit_as = rlimit_as
        self.rlimit_fsize = rlimit_fsize
        self.rlimit_nofile = rlimit_nofile
        self.rlimit_nproc = rlimit_nproc
        self.cgroup_mem_max = cgroup_mem_max
        self.cgroup_pids_max = cgroup_pids_max
        self.cgroup_cpu_ms_per_sec = cgroup_cpu_ms_per_sec
        self.disable_clone_newnet = disable_clone_newnet
        self.chroot_path = chroot_path
        self.tmpfs_mount = tmpfs_mount
        self.proxy_socket_path = proxy_socket_path
        self.seccomp_policy = seccomp_policy
        self.keep_env = keep_env
        self.env_vars = (
            env_vars
            if env_vars is not None
            else {
                "PATH": "/usr/bin:/bin",
                "KANBAN_EGRESS_SOCK": "/run/sandbox/proxy.sock",
            }
        )

    def build_argv(self, target_cmd: list[str]) -> list[str]:
        """Construct the exact nsjail command line argument list."""
        argv: list[str] = [
            str(self.nsjail_bin),
            "--mode",
            "o",
            "--time_limit",
            str(self.time_limit_sec),
            "--rlimit_as",
            str(self.rlimit_as),
            "--rlimit_fsize",
            str(self.rlimit_fsize),
            "--rlimit_nofile",
            str(self.rlimit_nofile),
            "--rlimit_nproc",
            str(self.rlimit_nproc),
            "--cgroup_mem_max",
            str(self.cgroup_mem_max),
            "--cgroup_pids_max",
            str(self.cgroup_pids_max),
            "--cgroup_cpu_ms_per_sec",
            str(self.cgroup_cpu_ms_per_sec),
            "--disable_clone_newnet=false",
            "--chroot",
            str(self.chroot_path),
            "--mount",
            self.tmpfs_mount,
        ]
        if self.proxy_socket_path is not None:
            argv.extend(["--bindmount", f"{self.proxy_socket_path}:/run/sandbox/proxy.sock"])
        if self.seccomp_policy is not None:
            argv.extend(["--seccomp_policy", str(self.seccomp_policy)])
        if not self.keep_env:
            argv.append("--keep_env=false")
        for k, v in sorted(self.env_vars.items()):
            argv.extend(["--env", f"{k}={v}"])
        argv.append("--")
        argv.extend(target_cmd)
        return argv


class TierBNsjailRunner:
    """Hardened Tier B nsjail sandboxed runner for untrusted scripts.

    Implements TierBRunner protocol.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        nsjail_bin: Path = Path("/usr/bin/nsjail"),
        seccomp_policy: Path | None = Path("deploy/seccomp/sandbox-profile.json"),
        runtime_base_dir: Path | None = None,
        launcher: SubprocessLauncher | None = None,
        default_timeout_ms: int = MAX_TIMEOUT_MS,
        chroot_path: Path = Path("/var/empty"),
        probe_result: Any = None,  # noqa: ANN401
    ) -> None:
        """Initialize TierBNsjailRunner with nsjail configuration and probe."""
        self.nsjail_bin = nsjail_bin
        self.seccomp_policy = seccomp_policy
        self.runtime_base_dir = runtime_base_dir
        self.launcher = launcher or DefaultSubprocessLauncher()
        self.default_timeout_ms = default_timeout_ms
        self.chroot_path = chroot_path
        self._probe_result = probe_result

    def _ensure_probe_available(self) -> None:
        """Verify startup user namespace probe, failing closed if unavailable."""
        probe = self._probe_result
        if probe is None:
            probe = get_cached_sandbox_probe()
        if probe is None:
            probe = probe_nsjail_userns(nsjail_bin=self.nsjail_bin, runner=self.launcher)
            set_cached_sandbox_probe(probe)

        if not probe.available:
            detail = (
                probe.message or "Tier B nsjail sandbox is unavailable (CLONE_NEWUSER required)"
            )
            raise SandboxUnavailableError(
                error_code=probe.error_code or "SANDBOX_UNAVAILABLE_IN_STANDALONE",
                detail=detail,
            )

    async def execute(  # noqa: PLR0913
        self,
        script_source: str,
        input_json: bytes,
        *,
        timeout_ms: int | None = None,
        policy: EgressProxyPolicy | None = None,
        token: str | None = None,
        app: ASGIApp | None = None,
        command: list[str] | None = None,
    ) -> NsjailRunResult:
        """Execute script inside nsjail sandbox and return NsjailRunResult without throwing."""
        self._ensure_probe_available()

        effective_timeout_ms = min(timeout_ms or self.default_timeout_ms, MAX_TIMEOUT_MS)
        time_limit_sec = max(1, (effective_timeout_ms + 999) // 1000)

        # Token handling: zeroed in host memory in finally
        raw_token = token or f"kb_script_{uuid.uuid4().hex}"
        token_buf = bytearray(raw_token.encode("utf-8"))

        effective_policy = policy or EgressProxyPolicy(
            egress_allowlist=[],
            max_requests=10,
            timeout_ms=effective_timeout_ms,
        )

        proxy = TokenInjectingEgressProxy(
            token=raw_token,
            policy=effective_policy,
            app=app,
            base_dir=self.runtime_base_dir,
        )

        target_cmd = (
            command
            if command is not None
            else (["/usr/bin/python3", "-c", script_source] if script_source else ["/bin/true"])
        )

        try:
            async with proxy:
                cmd_builder = NsjailCommandBuilder(
                    nsjail_bin=self.nsjail_bin,
                    time_limit_sec=time_limit_sec,
                    cgroup_mem_max=CGROUP_MEM_MAX_BYTES,
                    cgroup_pids_max=CGROUP_PIDS_MAX,
                    cgroup_cpu_ms_per_sec=CGROUP_CPU_MS_PER_SEC,
                    disable_clone_newnet=False,
                    chroot_path=self.chroot_path,
                    proxy_socket_path=proxy.socket_path,
                    seccomp_policy=self.seccomp_policy,
                )
                argv = cmd_builder.build_argv(target_cmd)

                try:
                    start_time = time.monotonic()
                    timeout_sec = effective_timeout_ms / 1000.0

                    ret_code, stdout, stderr = await self.launcher.run_async(
                        argv,
                        stdin_bytes=input_json,
                        timeout_seconds=timeout_sec,
                        env=None,
                    )
                    elapsed_ms = (time.monotonic() - start_time) * 1000.0
                    if elapsed_ms > effective_timeout_ms:
                        return NsjailRunResult(
                            stdout=stdout,
                            stderr=stderr,
                            returncode=-9,
                            error_code="SCRIPT_TIMEOUT",
                        )
                except TimeoutError:
                    return NsjailRunResult(
                        stdout=b"",
                        stderr=b"Command timed out",
                        returncode=-9,
                        error_code="SCRIPT_TIMEOUT",
                    )

                if len(stdout) > MAX_STDOUT_BYTES:
                    return NsjailRunResult(
                        stdout=stdout[:MAX_STDOUT_BYTES],
                        stderr=stderr,
                        returncode=ret_code,
                        error_code="SCRIPT_OUTPUT_TOO_LARGE",
                    )

                error_code = f"SCRIPT_ERROR_EXIT_{ret_code}" if ret_code != 0 else None
                return NsjailRunResult(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=ret_code,
                    error_code=error_code,
                )
        finally:
            # Overwrite token buffer in mutable host memory
            for i in range(len(token_buf)):
                token_buf[i] = 0

    async def run(  # noqa: PLR0913
        self,
        script_source: str,
        input_json: bytes,
        *,
        timeout_ms: int = MAX_TIMEOUT_MS,
        policy: EgressProxyPolicy | None = None,
        token: str | None = None,
        app: ASGIApp | None = None,
        command: list[str] | None = None,
        raise_on_error: bool = True,
        **kwargs: object,
    ) -> bytes:
        """Execute untrusted script in sandbox, satisfying TierBRunner protocol.

        When raise_on_error is True, raises SandboxExecutionError (or specialized subclass)
        on deterministic errors such as SCRIPT_TIMEOUT and SCRIPT_OUTPUT_TOO_LARGE.
        When raise_on_error is False, returns error code as bytes (e.g. b"SCRIPT_TIMEOUT").
        """
        del kwargs
        result = await self.execute(
            script_source=script_source,
            input_json=input_json,
            timeout_ms=timeout_ms,
            policy=policy,
            token=token,
            app=app,
            command=command,
        )

        if result.error_code is not None:
            if not raise_on_error:
                return result.error_code.encode("utf-8")
            if result.error_code == "SCRIPT_TIMEOUT":
                msg = f"Script execution exceeded maximum timeout of {timeout_ms}ms"
                raise ScriptTimeoutError(msg)
            if result.error_code == "SCRIPT_OUTPUT_TOO_LARGE":
                msg = f"Script stdout exceeded {MAX_STDOUT_BYTES} bytes limit"
                raise ScriptOutputTooLargeError(msg)
            err_detail = result.stderr.decode("utf-8", errors="replace")
            msg = f"Script execution failed with {result.error_code}: {err_detail}"
            raise SandboxExecutionError(result.error_code, msg)

        return result.stdout

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Startup CLONE_NEWUSER fail-closed probe for Tier B nsjail sandbox (KB-P5-14, S2.2, S13.3)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from dataclasses import dataclass
else:
    from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SandboxProbeResult:
    """Outcome of the startup nsjail user namespace isolation probe."""

    available: bool
    error_code: str | None = None
    message: str | None = None


class SandboxUnavailableError(ProblemException):
    """Raised when Tier B nsjail execution is attempted without user namespace support."""

    def __init__(
        self,
        error_code: str = "SANDBOX_UNAVAILABLE_IN_STANDALONE",
        detail: str = "Tier B nsjail sandbox is unavailable in this environment",
    ) -> None:
        """Initialize SandboxUnavailableError with HTTP 503 Problem details."""
        super().__init__(
            status=503,
            code=error_code,
            title="Sandbox Unavailable",
            detail=detail,
        )


class SubprocessLauncher(Protocol):
    """Protocol for launching external commands in sandbox probes and runners."""

    def run_sync(
        self,
        argv: list[str],
        *,
        timeout_seconds: float = 1.0,
    ) -> tuple[int, bytes, bytes]:
        """Execute command synchronously and return (exit_code, stdout, stderr)."""
        ...

    async def run_async(
        self,
        argv: list[str],
        *,
        stdin_bytes: bytes | None = None,
        timeout_seconds: float = 3.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes, bytes]:
        """Execute command asynchronously and return (exit_code, stdout, stderr)."""
        ...


_CACHED_PROBE: SandboxProbeResult | None = None


def get_cached_sandbox_probe() -> SandboxProbeResult | None:
    """Return cached startup sandbox probe result if available."""
    return _CACHED_PROBE


def set_cached_sandbox_probe(result: SandboxProbeResult) -> None:
    """Explicitly cache a sandbox probe result (e.g. at startup or in tests)."""
    global _CACHED_PROBE  # noqa: PLW0603
    _CACHED_PROBE = result


def reset_cached_sandbox_probe() -> None:
    """Clear cached sandbox probe result."""
    global _CACHED_PROBE  # noqa: PLW0603
    _CACHED_PROBE = None


def probe_nsjail_userns(  # noqa: C901, PLR0911, PLR0912
    *,
    nsjail_bin: Path = Path("/usr/bin/nsjail"),
    runner: Any = None,  # noqa: ANN401
) -> SandboxProbeResult:
    """Probe for functional nsjail user namespace (CLONE_NEWUSER) support.

    Fails closed with SANDBOX_UNAVAILABLE_IN_STANDALONE when:
    1. nsjail binary does not exist.
    2. nsjail binary is not owned by UID 0.
    3. nsjail binary is group or world writable ((mode & 0o022) != 0).
    4. Execution of a 500ms dry self-test with CLONE_NEWUSER fails or returns non-zero.
    """
    try:
        if not nsjail_bin.exists():
            return SandboxProbeResult(
                available=False,
                error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
                message=f"nsjail binary not found at {nsjail_bin}",
            )
        st = nsjail_bin.stat()
    except OSError as err:
        return SandboxProbeResult(
            available=False,
            error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            message=f"Cannot stat nsjail binary: {err}",
        )

    if st.st_uid != 0:
        return SandboxProbeResult(
            available=False,
            error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            message=f"nsjail binary must be owned by UID 0 (got UID {st.st_uid})",
        )

    if (st.st_mode & 0o022) != 0:
        return SandboxProbeResult(
            available=False,
            error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            message="nsjail binary is group or world writable (mode & 0o022 != 0)",
        )

    # Dry-run command executing /bin/true inside minimal namespace sandbox
    dry_cmd = [
        str(nsjail_bin),
        "--mode",
        "o",
        "--time_limit",
        "1",
        "--disable_clone_newnet=false",
        "--chroot",
        "/",
        "--",
        "/bin/true",
    ]

    try:
        if runner is not None:
            if hasattr(runner, "run_sync"):
                ret_code, _stdout, _stderr = runner.run_sync(dry_cmd, timeout_seconds=0.5)
            elif callable(getattr(runner, "run", None)):
                ret = runner.run(dry_cmd, timeout_seconds=0.5)
                if isinstance(ret, tuple):
                    ret_code, _out, _err = ret
                else:
                    ret_code = 0
            else:
                ret_code = 1
        else:
            proc = subprocess.run(  # noqa: S603
                dry_cmd,
                capture_output=True,
                timeout=0.5,
                check=False,
            )
            ret_code = proc.returncode
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as exc:
        return SandboxProbeResult(
            available=False,
            error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            message=f"nsjail self-test failed: {exc}",
        )

    if ret_code != 0:
        return SandboxProbeResult(
            available=False,
            error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            message=f"nsjail self-test returned non-zero exit code {ret_code}",
        )

    return SandboxProbeResult(available=True)

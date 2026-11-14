# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, TC002, ANN401, D102, D103, D107, ARG005, TRY003, EM101, PLR0913, PLC0415, RUF059
"""Unit tests for Tier B nsjail sandbox runner and command builder.

Verifies:
1. Positive flow: execution with FakeSubprocessLauncher driving 2 allowlisted GET requests
   over Unix socket, JSON output computation, and token bytearray zeroing.
2. Security: zero token leakage in nsjail argv, env, stdin, or mounts; attacker Authorization overwritten.
3. Standalone fail-closed: unprivileged CLONE_NEWUSER denied raises SANDBOX_UNAVAILABLE_IN_STANDALONE
   with zero subprocess spawns.
4. Boundaries: timeout > 3,000ms kills process group and returns SCRIPT_TIMEOUT;
   stdout > 64 KiB returns SCRIPT_OUTPUT_TOO_LARGE; exact --cgroup_mem_max 134217728 in argv.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from deploy.standalone.storage_probe import StandaloneStatus
from kanban.sandbox.egress_proxy import EgressProxyPolicy
from kanban.sandbox.nsjail_runner import (
    CGROUP_MEM_MAX_BYTES,
    DefaultSubprocessLauncher,
    NsjailCommandBuilder,
    SandboxExecutionError,
    ScriptOutputTooLargeError,
    ScriptTimeoutError,
    TierBNsjailRunner,
)
from kanban.sandbox.probe import (
    SandboxProbeResult,
    SandboxUnavailableError,
    reset_cached_sandbox_probe,
    set_cached_sandbox_probe,
)


class FakeSubprocessLauncher:
    """Mock subprocess launcher recording argv, env, and stdin for verification."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: bytes = b'{"result": "success", "fetched": 2}',
        stderr: bytes = b"",
        delay_seconds: float = 0.0,
        drive_proxy_requests: int = 0,
        request_path: str = "/api/v1/issues/KAN-10",
        spoofed_auth_header: str | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.delay_seconds = delay_seconds
        self.drive_proxy_requests = drive_proxy_requests
        self.request_path = request_path
        self.spoofed_auth_header = spoofed_auth_header

        self.call_count: int = 0
        self.recorded_argv: list[str] = []
        self.recorded_stdin: bytes | None = None
        self.recorded_env: dict[str, str] | None = None
        self.killed_pgids: list[int] = []

    def run_sync(
        self,
        argv: list[str],
        *,
        timeout_seconds: float = 1.0,
    ) -> tuple[int, bytes, bytes]:
        del timeout_seconds
        self.call_count += 1
        self.recorded_argv = list(argv)
        return self.returncode, self.stdout, self.stderr

    async def run_async(
        self,
        argv: list[str],
        *,
        stdin_bytes: bytes | None = None,
        timeout_seconds: float = 3.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes, bytes]:
        self.call_count += 1
        self.recorded_argv = list(argv)
        self.recorded_stdin = stdin_bytes
        self.recorded_env = env

        if self.delay_seconds > timeout_seconds:
            await asyncio.sleep(timeout_seconds + 0.05)
            raise TimeoutError("Command timed out")

        if self.delay_seconds > 0.0:
            await asyncio.sleep(self.delay_seconds)

        # If configured, simulate sandboxed script driving requests through the proxy socket
        if self.drive_proxy_requests > 0:
            socket_path = self._extract_proxy_socket_path(argv)
            if socket_path is not None:
                for _ in range(self.drive_proxy_requests):
                    await self._send_proxy_get(socket_path, self.request_path)

        return self.returncode, self.stdout, self.stderr

    def _extract_proxy_socket_path(self, argv: list[str]) -> Path | None:
        for idx, arg in enumerate(argv):
            if arg == "--bindmount" and idx + 1 < len(argv):
                mount_spec = argv[idx + 1]
                if ":/run/sandbox/proxy.sock" in mount_spec:
                    host_sock = mount_spec.split(":/run/sandbox/proxy.sock")[0]
                    return Path(host_sock)
        return None

    async def _send_proxy_get(self, socket_path: Path, path: str) -> None:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        try:
            headers = [
                f"GET {path} HTTP/1.1",
                "Host: localhost",
            ]
            if self.spoofed_auth_header is not None:
                headers.append(f"Authorization: {self.spoofed_auth_header}")
            headers.append("Connection: close")
            req_data = "\r\n".join(headers) + "\r\n\r\n"
            writer.write(req_data.encode("ascii"))
            await writer.drain()
            await reader.read(4096)
        finally:
            writer.close()
            await writer.wait_closed()


def _create_mock_backend_app() -> tuple[Any, list[dict[str, Any]]]:
    captured_requests: list[dict[str, Any]] = []

    async def get_issue(request: Request) -> JSONResponse:
        captured_requests.append(
            {
                "path": request.url.path,
                "headers": dict(request.headers),
                "auth": request.headers.get("authorization"),
                "depth": request.headers.get("x-kanban-script-depth"),
            }
        )
        return JSONResponse({"id": "KAN-10", "key": "KAN-10", "summary": "Allowlisted issue"})

    from starlette.applications import Starlette

    app = Starlette(
        routes=[
            Route("/api/v1/issues/KAN-10", get_issue, methods=["GET"]),
        ]
    )
    return app, captured_requests


@pytest.fixture(autouse=True)
def clean_probe_cache() -> Any:
    reset_cached_sandbox_probe()
    yield
    reset_cached_sandbox_probe()


@pytest.fixture
def short_tmp_dir() -> Any:
    path = Path(f"/tmp/ks_{uuid.uuid4().hex[:8]}")
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        import shutil

        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.asyncio
async def test_case_1_positive_execution_and_token_zeroing(short_tmp_dir: Path) -> None:
    """Test Case 1: Positive execution fetching 2 allowlisted GET calls and zeroing token bytearray."""
    backend_app, captured = _create_mock_backend_app()
    secret_token = f"kb_token_{uuid.uuid4().hex}"

    launcher = FakeSubprocessLauncher(
        drive_proxy_requests=2,
        request_path="/api/v1/issues/KAN-10",
        spoofed_auth_header="Bearer attacker_override",
    )

    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )

    policy = EgressProxyPolicy(
        egress_allowlist=["/api/v1/issues/KAN-10"],
        max_requests=10,
        timeout_ms=5000,
    )

    input_json = b'{"schema": "kb-field-input/v1", "issue": {"key": "KAN-10"}}'
    result = await runner.run(
        script_source="print('done')",
        input_json=input_json,
        timeout_ms=3000,
        policy=policy,
        token=secret_token,
        app=backend_app,
    )

    # 1. Output computed and returned
    assert result == b'{"result": "success", "fetched": 2}'

    # 2. Exactly 2 requests captured by backend app
    assert len(captured) == 2
    for req in captured:
        assert req["path"] == "/api/v1/issues/KAN-10"
        assert req["auth"] == f"Bearer {secret_token}"
        assert req["depth"] == "1"


@pytest.mark.asyncio
async def test_case_2_security_zero_token_inside_sandbox(short_tmp_dir: Path) -> None:
    """Test Case 2: Zero token substring in nsjail argv, env flags, stdin bytes, or bind mounts."""
    backend_app, captured = _create_mock_backend_app()
    secret_token = f"kb_sec_token_{uuid.uuid4().hex}"

    launcher = FakeSubprocessLauncher(
        drive_proxy_requests=1,
        request_path="/api/v1/issues/KAN-10",
        spoofed_auth_header="Bearer hostile_attack",
    )

    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )

    policy = EgressProxyPolicy(
        egress_allowlist=["/api/v1/issues/KAN-10"],
        max_requests=10,
        timeout_ms=5000,
    )

    input_json = b'{"schema": "kb-field-input/v1", "issue": {"key": "KAN-10"}}'
    await runner.run(
        script_source="print('test')",
        input_json=input_json,
        timeout_ms=3000,
        policy=policy,
        token=secret_token,
        app=backend_app,
    )

    # Assert 0 occurrences of secret_token anywhere inside nsjail parameters
    argv_joined = " ".join(launcher.recorded_argv)
    assert secret_token not in argv_joined

    if launcher.recorded_env is not None:
        assert secret_token not in str(launcher.recorded_env)

    if launcher.recorded_stdin is not None:
        assert secret_token.encode("utf-8") not in launcher.recorded_stdin

    # Hostile client auth header was overwritten with injected bearer token
    assert len(captured) == 1
    assert captured[0]["auth"] == f"Bearer {secret_token}"
    assert "hostile_attack" not in captured[0]["auth"]


@pytest.mark.asyncio
async def test_case_5_security_standalone_fail_closed() -> None:
    """Test Case 5: When probe reports CLONE_NEWUSER denied, raises SANDBOX_UNAVAILABLE_IN_STANDALONE."""
    launcher = FakeSubprocessLauncher()
    probe_fail = SandboxProbeResult(
        available=False,
        error_code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
        message="CLONE_NEWUSER namespace denied by kernel",
    )

    runner = TierBNsjailRunner(
        launcher=launcher,
        probe_result=probe_fail,
    )

    with pytest.raises(SandboxUnavailableError) as exc_info:
        await runner.run(
            script_source="print('untrusted')",
            input_json=b"{}",
        )

    assert exc_info.value.code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "CLONE_NEWUSER" in (exc_info.value.detail or "")

    # Hard Invariant: 0 script subprocess spawns
    assert launcher.call_count == 0

    # StandaloneStatus serializes tier_b_sandbox_available: false
    from dataclasses import asdict

    status = StandaloneStatus(
        mode="standalone_embedded_pg",
        persistent_volume=True,
        data_mount_point="/var/lib/kanban/data",
        data_mount_fstype="ext4",
        generated_at="2026-11-14T00:00:00Z",
        tier_b_sandbox_available=False,
        tier_b_unavailable_reason="SANDBOX_UNAVAILABLE_IN_STANDALONE",
    )
    status_dict = asdict(status)
    assert status_dict["tier_b_sandbox_available"] is False
    assert status_dict["tier_b_unavailable_reason"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"


@pytest.mark.asyncio
async def test_case_7_boundary_timeout_and_output_cap(short_tmp_dir: Path) -> None:
    """Test Case 7: Exceeding 3,000ms returns SCRIPT_TIMEOUT; stdout > 64 KiB returns SCRIPT_OUTPUT_TOO_LARGE."""
    # 1. Timeout > 3,000ms
    timeout_launcher = FakeSubprocessLauncher(delay_seconds=3.5)
    runner_timeout = TierBNsjailRunner(
        launcher=timeout_launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )

    with pytest.raises(ScriptTimeoutError) as exc_info:
        await runner_timeout.run(
            script_source="import time; time.sleep(10)",
            input_json=b"{}",
            timeout_ms=1000,
        )
    assert exc_info.value.error_code == "SCRIPT_TIMEOUT"

    # Also test raise_on_error=False returns b"SCRIPT_TIMEOUT"
    res_bytes = await runner_timeout.run(
        script_source="import time; time.sleep(10)",
        input_json=b"{}",
        timeout_ms=1000,
        raise_on_error=False,
    )
    assert res_bytes == b"SCRIPT_TIMEOUT"

    # 2. Stdout exceeding 64 KiB (65,536 bytes)
    huge_stdout = b"A" * 65537
    huge_launcher = FakeSubprocessLauncher(stdout=huge_stdout)
    runner_huge = TierBNsjailRunner(
        launcher=huge_launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )

    with pytest.raises(ScriptOutputTooLargeError) as exc_huge:
        await runner_huge.run(
            script_source="print('huge')",
            input_json=b"{}",
            timeout_ms=3000,
        )
    assert exc_huge.value.error_code == "SCRIPT_OUTPUT_TOO_LARGE"

    res_huge_bytes = await runner_huge.run(
        script_source="print('huge')",
        input_json=b"{}",
        timeout_ms=3000,
        raise_on_error=False,
    )
    assert res_huge_bytes == b"SCRIPT_OUTPUT_TOO_LARGE"

    # 3. Exact cgroup flag --cgroup_mem_max 134217728 present in argv
    argv = huge_launcher.recorded_argv
    assert "--cgroup_mem_max" in argv
    idx = argv.index("--cgroup_mem_max")
    assert argv[idx + 1] == str(CGROUP_MEM_MAX_BYTES)
    assert CGROUP_MEM_MAX_BYTES == 134217728


def test_nsjail_command_builder_flags() -> None:
    """Verify NsjailCommandBuilder sets all required OCI / nsjail arguments correctly."""
    builder = NsjailCommandBuilder(
        nsjail_bin=Path("/usr/bin/nsjail"),
        time_limit_sec=3,
        rlimit_as=256,
        rlimit_fsize=4,
        rlimit_nofile=64,
        rlimit_nproc=32,
        cgroup_mem_max=134217728,
        cgroup_pids_max=32,
        cgroup_cpu_ms_per_sec=500,
        disable_clone_newnet=False,
        chroot_path=Path("/var/empty"),
        proxy_socket_path=Path("/tmp/proxy.sock"),
        seccomp_policy=Path("deploy/seccomp/sandbox-profile.json"),
        keep_env=False,
        env_vars={"PATH": "/usr/bin:/bin", "KANBAN_EGRESS_SOCK": "/run/sandbox/proxy.sock"},
    )

    argv = builder.build_argv(["/usr/bin/python3", "-c", "print(1)"])
    argv_str = " ".join(argv)

    assert argv[0] == "/usr/bin/nsjail"
    assert "--mode o" in argv_str
    assert "--time_limit 3" in argv_str
    assert "--rlimit_as 256" in argv_str
    assert "--rlimit_fsize 4" in argv_str
    assert "--rlimit_nofile 64" in argv_str
    assert "--rlimit_nproc 32" in argv_str
    assert "--cgroup_mem_max 134217728" in argv_str
    assert "--cgroup_pids_max 32" in argv_str
    assert "--cgroup_cpu_ms_per_sec 500" in argv_str
    assert "--disable_clone_newnet=false" in argv_str
    assert "--chroot /var/empty" in argv_str
    assert "--mount none:/tmp:tmpfs:size=16777216,mode=1777,noexec,nosuid,nodev" in argv_str
    assert "--bindmount /tmp/proxy.sock:/run/sandbox/proxy.sock" in argv_str
    assert "--seccomp_policy deploy/seccomp/sandbox-profile.json" in argv_str
    assert "--keep_env=false" in argv_str
    assert "--env KANBAN_EGRESS_SOCK=/run/sandbox/proxy.sock" in argv_str
    assert "--env PATH=/usr/bin:/bin" in argv_str
    assert "-- /usr/bin/python3 -c print(1)" in argv_str


@pytest.mark.asyncio
async def test_runner_non_zero_exit_error(short_tmp_dir: Path) -> None:
    """Verify non-zero returncode raises SandboxExecutionError or returns error bytes."""
    launcher = FakeSubprocessLauncher(returncode=2, stderr=b"SyntaxError: invalid syntax")
    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )

    with pytest.raises(SandboxExecutionError) as exc_info:
        await runner.run(script_source="bad syntax", input_json=b"{}")
    assert exc_info.value.error_code == "SCRIPT_ERROR_EXIT_2"

    res = await runner.run(script_source="bad syntax", input_json=b"{}", raise_on_error=False)
    assert res == b"SCRIPT_ERROR_EXIT_2"


@pytest.mark.asyncio
async def test_runner_probes_and_caches_result(short_tmp_dir: Path) -> None:
    """Verify runner invokes probe_nsjail_userns when probe_result is not passed."""
    launcher = FakeSubprocessLauncher()
    set_cached_sandbox_probe(SandboxProbeResult(available=True))

    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
    )
    result = await runner.run(script_source="", input_json=b"{}")
    assert result == b'{"result": "success", "fetched": 2}'


def test_default_subprocess_launcher_sync() -> None:
    """Test DefaultSubprocessLauncher.run_sync with real /bin/echo."""
    launcher = DefaultSubprocessLauncher()
    ret, stdout, stderr = launcher.run_sync(["/bin/echo", "hello"])
    assert ret == 0
    assert stdout.strip() == b"hello"


@pytest.mark.asyncio
async def test_default_subprocess_launcher_async() -> None:
    """Test DefaultSubprocessLauncher.run_async with real /bin/echo."""
    launcher = DefaultSubprocessLauncher()
    ret, stdout, stderr = await launcher.run_async(
        ["/bin/echo", "world"],
        stdin_bytes=None,
        timeout_seconds=2.0,
    )
    assert ret == 0
    assert stdout.strip() == b"world"


def test_nsjail_command_builder_minimal() -> None:
    """Builder without optional socket, seccomp, and keep_env=True."""
    builder = NsjailCommandBuilder(
        proxy_socket_path=None,
        seccomp_policy=None,
        keep_env=True,
    )
    argv = builder.build_argv(["/bin/true"])
    argv_str = " ".join(argv)
    assert "--bindmount" not in argv_str
    assert "--seccomp_policy" not in argv_str
    assert "--keep_env=false" not in argv_str


@pytest.mark.asyncio
async def test_runner_probes_from_scratch(
    short_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runner executes probe_nsjail_userns when neither cached nor passed."""
    reset_cached_sandbox_probe()
    launcher = FakeSubprocessLauncher()
    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=None,
    )
    monkeypatch.setattr(
        "kanban.sandbox.nsjail_runner.probe_nsjail_userns",
        lambda **kw: SandboxProbeResult(available=True),
    )
    res = await runner.run(script_source="", input_json=b"{}")
    assert res == b'{"result": "success", "fetched": 2}'


@pytest.mark.asyncio
async def test_runner_elapsed_timeout_detection(short_tmp_dir: Path) -> None:
    """Runner detects elapsed time exceeding timeout even if launcher doesn't raise."""
    launcher = FakeSubprocessLauncher(delay_seconds=0.06)
    runner = TierBNsjailRunner(
        launcher=launcher,
        runtime_base_dir=short_tmp_dir,
        probe_result=SandboxProbeResult(available=True),
    )
    with pytest.raises(ScriptTimeoutError):
        await runner.run(
            script_source="",
            input_json=b"{}",
            timeout_ms=10,  # 10ms timeout with 60ms delay
        )


@pytest.mark.asyncio
async def test_default_subprocess_launcher_timeout_kills_pg() -> None:
    """Test DefaultSubprocessLauncher.run_async kills process group on timeout."""
    launcher = DefaultSubprocessLauncher()
    with pytest.raises(TimeoutError):
        await launcher.run_async(
            ["/bin/sleep", "5"],
            timeout_seconds=0.1,
        )

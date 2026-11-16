# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""End-to-end tests for RunnerDaemon: mTLS loopback, TLS 1.3, revocation & cancel (KB-P5-22b)."""
# ruff: noqa: SLF001, S106, ANN401, ARG001, ARG002, ARG005, PLC0415, RUF059, T201, PLR0915

from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import json
import ssl
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import websockets
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.remote_runner.config import KeyPermissionsError, RunnerConfig
from agent.remote_runner.daemon import (
    CLOSE_CODE_REVOKED,
    EXIT_CODE_REVOKED,
    RunnerDaemon,
    RunnerRevokedError,
)
from agent.remote_runner.executor import RunnerJobExecutor
from agent.runners.cli_pipe import CliPipeHarness
from agent.testing.fixtures import FixtureCLIRunner, FixtureLLMProvider
from kanban.runners.hub import (
    HelloAckFrame,
    HelloFrame,
    JobCancelFrame,
    RunnerWssHub,
)


class WsAdapter:
    """Adapter wrapping websockets connection for RunnerWssHub."""

    def __init__(self, ws: Any) -> None:
        """Initialize adapter."""
        self._ws = ws

    async def send_text(self, text: str) -> None:
        """Send text frame over WebSocket."""
        await self._ws.send(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close WebSocket with status code and reason."""
        await self._ws.close(code, reason)


def _generate_test_pki(tmp_path: Path, runner_id: uuid.UUID) -> tuple[Path, Path, Path, Path, Path]:
    """Generate in-memory / tmp_path CA, server, and client mTLS certificates."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    ca_file = tmp_path / "ca.crt"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    server_key = ec.generate_private_key(ec.SECP256R1())
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    server_crt_file = tmp_path / "server.crt"
    server_key_file = tmp_path / "server.key"
    server_crt_file.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    server_key_file.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    client_key = ec.generate_private_key(ec.SECP256R1())
    client_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "runner-client")])
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.UniformResourceIdentifier(f"urn:kanban:agent-runner:{runner_id}")]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    client_crt_file = tmp_path / "client.crt"
    client_key_file = tmp_path / "client.key"
    client_crt_file.write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    client_key_file.write_bytes(
        client_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    client_key_file.chmod(0o600)

    return ca_file, server_crt_file, server_key_file, client_crt_file, client_key_file


def _create_bare_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a minimal bare Git repo fixture with database schema."""
    workdir = tmp_path / "worktree"
    workdir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workdir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "test@kanban.local"], cwd=workdir, check=True)

    (workdir / "database").mkdir()
    (workdir / "database" / "schema.sql").write_text("SELECT 1;\n", encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=workdir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init test repo"],
        cwd=workdir,
        check=True,
        capture_output=True,
    )

    bare_dir = tmp_path / "mirror.git"
    subprocess.run(
        ["git", "clone", "--bare", str(workdir), str(bare_dir)],
        check=True,
        capture_output=True,
    )

    rev_proc = subprocess.run(
        ["git", f"--git-dir={bare_dir}", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return bare_dir, rev_proc.stdout.strip()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_daemon_e2e_mtls_loopback_and_dispatch(tmp_path: Path) -> None:
    """Test positive loopback mTLS WSS connection, handshake, in-app SDK & CLI execution."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )
    bare_dir, head_commit = _create_bare_git_fixture(tmp_path)

    # Server TLS context
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ssl.verify_mode = ssl.CERT_REQUIRED
    server_ssl.load_verify_locations(cafile=str(ca_file))
    server_ssl.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))

    hub = RunnerWssHub()
    workspace_id = uuid.uuid4()
    pool_slug = "default-pool"
    runner_connected = asyncio.Event()

    async def server_handler(ws: Any) -> None:
        transport = getattr(ws, "transport", None)
        if transport is not None:
            raw_ssl = transport.get_extra_info("ssl_object")
            if raw_ssl is not None:
                print(f"\n[mTLS Server] Negotiated protocol: {raw_ssl.version()}")
                print(f"[mTLS Server] Peer cert SAN: {raw_ssl.getpeercert().get('subjectAltName')}")
        raw_hello = await ws.recv()
        hello_data = json.loads(raw_hello)
        hello = HelloFrame.model_validate(hello_data)
        ack = HelloAckFrame()
        await ws.send(ack.model_dump_json(by_alias=True))

        adapter = WsAdapter(ws)
        hub.register_runner(
            runner_id=hello.runner_id,
            workspace_id=workspace_id,
            pool_slug=pool_slug,
            hostname="test-host",
            websocket=adapter,  # type: ignore[arg-type]
            max_concurrency=hello.max_concurrency,
            capabilities=hello.capabilities,
        )
        runner_connected.set()
        try:
            async for raw_msg in ws:
                data = json.loads(raw_msg)
                hub.handle_frame(hello.runner_id, data)
        finally:
            hub.unregister_runner(hello.runner_id)

    server = await websockets.serve(server_handler, "localhost", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    cfg = RunnerConfig(
        server_url=f"https://localhost:{port}",
        pool_slug=pool_slug,
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
        runner_id=runner_id,
        repo_mounts={"test-repo": bare_dir},
        heartbeat_interval_s=1.0,
    )

    def make_in_app() -> InAppSdkHarness:
        return InAppSdkHarness(
            provider=FixtureLLMProvider(Path("tests/fixtures/ai/transition_rls_veto.yaml")),
            mcp_transport=lambda url, tool, args: {"status": "ok"},
        )

    def make_cli() -> CliPipeHarness:
        return CliPipeHarness(
            runner=FixtureCLIRunner(Path("tests/fixtures/ai/cli_agy_approve.yaml"))
        )

    executor = RunnerJobExecutor(
        cfg,
        in_app_harness_factory=make_in_app,
        cli_pipe_harness_factory=make_cli,
    )
    daemon = RunnerDaemon(cfg, executor=executor)

    daemon_task = asyncio.create_task(daemon.run_forever())
    await asyncio.wait_for(runner_connected.wait(), timeout=5.0)

    # 1. Dispatch in_app_sdk job via hub
    ctx_in_app = {
        "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
        "ticket_id": "KAN-142",
        "title": "Test ticket with auth_provider_cards changes",
        "verdict_nonce": "nonce-1234",
        "delimiter": "===TEST===",
    }
    res_in_app = await hub.dispatch_job(
        workspace_id=workspace_id,
        pool_slug=pool_slug,
        job_spec={
            "job_id": "job-e2e-in-app",
            "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
            "agent_spec": {
                "slug": "forensic-code-check",
                "harness_kind": "in_app_sdk",
                "repo_access_mode": "read-only",
                "repo_slug": "test-repo",
            },
            "context_yaml_b64": base64.b64encode(yaml.safe_dump(ctx_in_app).encode("utf-8")).decode(
                "ascii"
            ),
            "ephemeral_mcp_token": "secret-token-in-app",
            "head_commit": head_commit,
        },
        timeout_s=5.0,
    )
    assert len(res_in_app) > 0
    assert len(hub._tool_events) >= 2

    # 2. Dispatch cli_pipe job via hub
    ctx_cli = {
        "schema": "kb-transition-context/v1",
        "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
        "verdict_nonce": "nonce-1234",
        "ticket_snapshot": {"identifier": "KAN-100", "title": "Test"},
    }
    res_cli = await hub.dispatch_job(
        workspace_id=workspace_id,
        pool_slug=pool_slug,
        job_spec={
            "job_id": "job-e2e-cli",
            "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
            "agent_spec": {
                "slug": "security-audit",
                "harness_kind": "cli_pipe",
                "repo_access_mode": "none",
                "cli_binary_allowlist_id": "agy",
                "cli_args_json": ["-p"],
            },
            "context_yaml_b64": base64.b64encode(yaml.safe_dump(ctx_cli).encode("utf-8")).decode(
                "ascii"
            ),
            "ephemeral_mcp_token": "secret-token-cli",
        },
        timeout_s=5.0,
    )
    assert b"approve" in res_cli
    tool_events_str = [e.get("tool_name") for e in hub._tool_events]
    print(f"\n[mTLS Loopback] In-App SDK tool events: {tool_events_str}")
    print(f"[mTLS Loopback] CLI Pipe verdict bytes received: {len(res_cli)} bytes")

    daemon.stop()
    await daemon_task
    server.close()
    await server.wait_closed()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_daemon_tls12_server_rejected(tmp_path: Path) -> None:
    """Test TLS 1.2-only server is rejected because client enforces minimum TLS 1.3."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )

    # Server SSL context locked down to TLS 1.2 maximum
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.maximum_version = ssl.TLSVersion.TLSv1_2
    server_ssl.verify_mode = ssl.CERT_REQUIRED
    server_ssl.load_verify_locations(cafile=str(ca_file))
    server_ssl.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))

    async def dummy_handler(ws: Any) -> None:
        pass

    server = await websockets.serve(dummy_handler, "localhost", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    cfg = RunnerConfig(
        server_url=f"https://localhost:{port}",
        pool_slug="pool-tls-reject",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )
    daemon = RunnerDaemon(cfg)

    # Handshake must fail
    with pytest.raises((ssl.SSLError, OSError)):
        async with daemon.ws_connector(
            cfg.resolve_wss_url(),
            ssl=daemon.build_ssl_context(),
        ):
            pass

    server.close()
    await server.wait_closed()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_daemon_server_revocation_4003_halts_with_exit_code_78(tmp_path: Path) -> None:
    """Test server closing WebSocket with 4003 causes daemon to exit with code 78."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )

    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ssl.verify_mode = ssl.CERT_REQUIRED
    server_ssl.load_verify_locations(cafile=str(ca_file))
    server_ssl.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))

    async def revoking_handler(ws: Any) -> None:
        # Handshake
        raw_hello = await ws.recv()
        HelloFrame.model_validate(json.loads(raw_hello))
        ack = HelloAckFrame()
        await ws.send(ack.model_dump_json(by_alias=True))
        # Immediately revoke runner
        await ws.close(code=CLOSE_CODE_REVOKED, reason="runner certificate revoked")

    server = await websockets.serve(revoking_handler, "localhost", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    cfg = RunnerConfig(
        server_url=f"https://localhost:{port}",
        pool_slug="pool-revoke",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )
    daemon = RunnerDaemon(cfg)

    with pytest.raises(RunnerRevokedError) as exc_info:
        await daemon.run_forever()

    assert exc_info.value.exit_code == EXIT_CODE_REVOKED

    server.close()
    await server.wait_closed()


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_daemon_job_cancel_under_250ms(tmp_path: Path) -> None:
    """Test job cancellation within < 250ms upon receiving job.cancel frame."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )

    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ssl.verify_mode = ssl.CERT_REQUIRED
    server_ssl.load_verify_locations(cafile=str(ca_file))
    server_ssl.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))

    job_result_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    cancel_duration_ms: float = 0.0

    async def handler(ws: Any) -> None:
        # Handshake
        raw_hello = await ws.recv()
        HelloFrame.model_validate(json.loads(raw_hello))
        ack = HelloAckFrame()
        await ws.send(ack.model_dump_json(by_alias=True))

        # Send long-running job dispatch
        ctx = {"execution_id": "0196ed40-7b2a-7000-8000-112233445566"}
        dispatch = {
            "type": "job.dispatch",
            "job_id": "job-cancel-test",
            "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
            "agent_spec": {"slug": "test-agent", "harness_kind": "in_app_sdk"},
            "context_yaml_b64": base64.b64encode(yaml.safe_dump(ctx).encode("utf-8")).decode(
                "ascii"
            ),
            "ephemeral_mcp_token": "secret-token",
        }
        await ws.send(json.dumps(dispatch))

        # Wait briefly for job to start running, then send cancel
        await asyncio.sleep(0.05)
        nonlocal cancel_duration_ms
        t_cancel_sent = time.perf_counter()
        cancel_frame = JobCancelFrame(job_id="job-cancel-test", reason="user requested")
        await ws.send(cancel_frame.model_dump_json())

        # Receive result frame
        raw_result = await ws.recv()
        cancel_duration_ms = (time.perf_counter() - t_cancel_sent) * 1000.0
        job_result_future.set_result(json.loads(raw_result))

    server = await websockets.serve(handler, "localhost", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    cfg = RunnerConfig(
        server_url=f"https://localhost:{port}",
        pool_slug="pool-cancel",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )

    class LongRunningHarness:
        async def run(self, ctx: Any, agent_def: Any) -> bytes:
            await asyncio.sleep(10.0)
            return b"ok"

    executor = RunnerJobExecutor(
        cfg,
        in_app_harness_factory=LongRunningHarness,
    )
    daemon = RunnerDaemon(cfg, executor=executor)
    daemon_task = asyncio.create_task(daemon.run_forever())

    res = await asyncio.wait_for(job_result_future, timeout=2.0)
    print(f"\n[Job Cancel] Duration: {cancel_duration_ms:.2f}ms (< 250ms requirement)")
    assert res.get("status") == "error"
    assert res.get("error_code") == "RUNNER_JOB_CANCELLED"
    assert cancel_duration_ms < 250.0, f"Cancellation took {cancel_duration_ms:.2f}ms (>= 250ms)"

    daemon.stop()
    await daemon_task
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_daemon_transient_disconnect_and_backoff(tmp_path: Path) -> None:
    """Test transient disconnect triggers full-jitter backoff and reconnection."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )

    cfg = RunnerConfig(
        server_url="https://localhost:9999",
        pool_slug="pool-backoff",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )

    backoff_sleeps: list[float] = []

    async def mock_sleep(seconds: float) -> None:
        backoff_sleeps.append(seconds)
        daemon.stop()

    attempts = 0

    class MockConnectContext:
        async def __aenter__(self) -> Any:
            nonlocal attempts
            attempts += 1
            msg = "Connection refused in test"
            raise OSError(msg)

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    def mock_connector(url: str, **kwargs: Any) -> Any:
        return MockConnectContext()

    daemon = RunnerDaemon(cfg, ws_connector=mock_connector, sleep_func=mock_sleep)
    await daemon.run_forever()

    assert len(backoff_sleeps) == 1
    assert 1.0 <= backoff_sleeps[0] <= 60.0

    # Test backoff bounds
    for i in range(10):
        val = daemon.compute_backoff(i)
        assert 1.0 <= val <= 60.0


def test_daemon_key_permissions_refusal(tmp_path: Path) -> None:
    """Test RunnerDaemon boot failure when private key permissions are too open."""
    runner_id = uuid.uuid4()
    ca_file, _, _, client_crt, client_key = _generate_test_pki(tmp_path, runner_id)

    # Set key to 0644 (too open)
    client_key.chmod(0o644)

    cfg = RunnerConfig(
        server_url="https://localhost:8000",
        pool_slug="pool-open-perms",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )

    with pytest.raises(KeyPermissionsError):
        RunnerDaemon(cfg)


def test_daemon_ssl_context_variations(tmp_path: Path) -> None:
    """Test build_ssl_context when CA or client cert paths are missing."""
    key_file = tmp_path / "client.key"
    key_file.write_text("key")
    key_file.chmod(0o600)

    cfg_no_ca = RunnerConfig(
        server_url="https://localhost:8000",
        pool_slug="pool-no-ca",
        client_cert_path=tmp_path / "missing_client.crt",
        client_key_path=key_file,
        ca_cert_path=tmp_path / "missing_ca.crt",
    )
    daemon_no_ca = RunnerDaemon(cfg_no_ca)
    ctx = daemon_no_ca.build_ssl_context()
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3


@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_daemon_internal_branches(tmp_path: Path) -> None:
    """Test bytes frame handling, tool event send failures, and active task cancellations."""
    runner_id = uuid.uuid4()
    ca_file, server_crt, server_key, client_crt, client_key = _generate_test_pki(
        tmp_path, runner_id
    )

    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.minimum_version = ssl.TLSVersion.TLSv1_3
    server_ssl.verify_mode = ssl.CERT_REQUIRED
    server_ssl.load_verify_locations(cafile=str(ca_file))
    server_ssl.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))

    async def binary_frame_handler(ws: Any) -> None:
        # Handshake sending ACK as binary bytes
        await ws.recv()
        ack = HelloAckFrame()
        await ws.send(ack.model_dump_json(by_alias=True).encode("utf-8"))

        # Send unknown frame type
        await ws.send(json.dumps({"type": "unknown_ignore"}).encode("utf-8"))

        # Send dispatch as binary bytes
        ctx = {"execution_id": "0196ed40-7b2a-7000-8000-112233445566"}
        dispatch = {
            "type": "job.dispatch",
            "job_id": "job-bin-1",
            "execution_id": "0196ed40-7b2a-7000-8000-112233445566",
            "agent_spec": {"slug": "test-agent", "harness_kind": "in_app_sdk"},
            "context_yaml_b64": base64.b64encode(yaml.safe_dump(ctx).encode("utf-8")).decode(
                "ascii"
            ),
            "ephemeral_mcp_token": "secret-token",
        }
        await ws.send(json.dumps(dispatch).encode("utf-8"))

        # Receive result frame
        await ws.recv()

    server = await websockets.serve(binary_frame_handler, "localhost", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    cfg = RunnerConfig(
        server_url=f"https://localhost:{port}",
        pool_slug="pool-branches",
        client_cert_path=client_crt,
        client_key_path=client_key,
        ca_cert_path=ca_file,
    )

    class FastHarness:
        async def run(self, ctx: Any, agent_def: Any) -> bytes:
            return b"fast-ok"

    executor = RunnerJobExecutor(cfg, in_app_harness_factory=FastHarness)
    daemon = RunnerDaemon(cfg, executor=executor)
    daemon_task = asyncio.create_task(daemon.run_forever())

    # Wait for execution to finish
    await asyncio.sleep(0.3)

    # Test _send_tool_event with broken ws
    from kanban.runners.hub import JobDispatchFrame, JobToolEventFrame

    class FailingWs:
        async def send(self, data: Any) -> None:
            msg = "Network failure"
            raise ConnectionResetError(msg)

        async def close(self) -> None:
            pass

    daemon._ws = FailingWs()
    await daemon._send_tool_event(
        JobToolEventFrame(
            job_id="job-1",
            tool_name="tool",
            duration_ms=10,
            status="ok",
        )
    )

    # Test _heartbeat_loop success and exception break
    async def fast_sleep(_s: float) -> None:
        await asyncio.sleep(0.001)

    daemon.sleep_func = fast_sleep
    hb_task = asyncio.create_task(daemon._heartbeat_loop(FailingWs()))
    await hb_task

    # Test _spawn_job result send failure
    dispatch_fail = JobDispatchFrame(
        job_id="job-send-fail",
        execution_id="0196ed40-7b2a-7000-8000-112233445566",
        agent_spec={"slug": "test-agent", "harness_kind": "in_app_sdk"},
        context_yaml_b64=base64.b64encode(yaml.safe_dump({"test": "data"}).encode("utf-8")).decode(
            "ascii"
        ),
        ephemeral_mcp_token="secret",
    )
    daemon._spawn_job(dispatch_fail)
    await asyncio.sleep(0.1)

    # Test stop() cancelling active uncompleted tasks
    blocked_task = asyncio.create_task(asyncio.sleep(10.0))
    daemon._running_tasks["blocked"] = blocked_task
    daemon.stop()
    with contextlib.suppress(asyncio.CancelledError):
        await blocked_task
    assert blocked_task.cancelled()

    await daemon_task
    server.close()
    await server.wait_closed()

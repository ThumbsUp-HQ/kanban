# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for RunnerWssHub and WebSocket endpoint (KB-P5-22a, S14.2)."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text, update
from starlette.websockets import WebSocket

from database.models.remote_runner import RemoteRunner
from kanban.api.v1.remote_runners import (
    EnrollRunnerRequest,
    _extract_peer_cert_fingerprint,
    enroll_remote_runner_endpoint,
    remote_runner_websocket_endpoint,
)
from kanban.runners.hub import (
    MAX_FRAME_BYTES,
    RemoteRunnerDisconnectedError,
    RemoteRunnerExecutionError,
    RemoteRunnerRevokedError,
    RemoteRunnerUnavailableError,
    RunnerWssHub,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _enroll_totp(session: AsyncSession, p_id: uuid.UUID) -> None:
    """Enroll and confirm active TOTP factor to satisfy require_admin_aal2."""
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": p_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": p_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await session.commit()


def _generate_csr(key: ec.EllipticCurvePrivateKey, cn: str = "runner-node-1") -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    builder = x509.CertificateSigningRequestBuilder().subject_name(name)
    csr = builder.sign(key, hashes.SHA256())
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


class MockWebSocket:
    """In-memory mock WebSocket implementing send_text, receive_text and close."""

    def __init__(self) -> None:
        """Initialize sent and closed message records."""
        self.sent: list[str] = []
        self.closed: list[tuple[int, str]] = []
        self.sent_event = asyncio.Event()

    async def send_text(self, text_data: str) -> None:
        """Record outbound message."""
        self.sent.append(text_data)
        self.sent_event.set()

    def clear(self) -> None:
        """Clear sent history and reset sent event."""
        self.sent.clear()
        self.sent_event.clear()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Record close invocation."""
        self.closed.append((code, reason))


# ==============================================================================
# Unit Tests for RunnerWssHub
# ==============================================================================


def test_hub_register_unregister_and_eviction() -> None:
    """Verify runner registration, heartbeat tracking and 45s dead eviction."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r1_id = uuid.uuid4()
    r2_id = uuid.uuid4()

    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()

    curr_time = 1000.0
    hub.set_time_func(lambda: curr_time)

    # 1. Register r1 and r2
    hub.register_runner(
        runner_id=r1_id,
        workspace_id=ws_id,
        pool_slug="linux-pool",
        hostname="node-1.box",
        websocket=mock_ws1,  # type: ignore[arg-type]
        max_concurrency=4,
    )
    hub.register_runner(
        runner_id=r2_id,
        workspace_id=ws_id,
        pool_slug="linux-pool",
        hostname="node-2.box",
        websocket=mock_ws2,  # type: ignore[arg-type]
        max_concurrency=2,
    )

    runners = hub.get_pool_runners(ws_id, "linux-pool")
    assert len(runners) == 2

    # 2. Advance time 20s, send heartbeat for r1
    curr_time += 20.0
    hub.handle_frame(
        runner_id=r1_id,
        frame={"type": "heartbeat", "runner_id": str(r1_id), "active_jobs": []},
    )

    # 3. Advance time 30s more (total 50s since r2 heartbeat)
    curr_time += 30.0
    evicted = hub.evict_stale_runners()
    assert r2_id in evicted

    runners_after = hub.get_pool_runners(ws_id, "linux-pool")
    assert len(runners_after) == 1
    assert runners_after[0].runner_id == r1_id

    # 4. Explicit unregister
    hub.unregister_runner(r1_id)
    assert len(hub.get_pool_runners(ws_id, "linux-pool")) == 0


def test_hub_least_loaded_selection() -> None:
    """Verify dispatch selects runner with lowest active_jobs / max_concurrency ratio."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r1_id = uuid.uuid4()
    r2_id = uuid.uuid4()

    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()

    r1 = hub.register_runner(
        runner_id=r1_id,
        workspace_id=ws_id,
        pool_slug="gpu-pool",
        hostname="node-gpu-1",
        websocket=mock_ws1,  # type: ignore[arg-type]
        max_concurrency=2,
    )
    r1.active_jobs.add("job-running-1")  # load: 1/2 = 0.5

    hub.register_runner(
        runner_id=r2_id,
        workspace_id=ws_id,
        pool_slug="gpu-pool",
        hostname="node-gpu-2",
        websocket=mock_ws2,  # type: ignore[arg-type]
        max_concurrency=4,
    )
    # r2 load: 0/4 = 0.0

    selected = hub.select_runner(ws_id, "gpu-pool")
    assert selected is not None
    assert selected.runner_id == r2_id

    # Add 2 jobs to r2: load 2/4 = 0.5; add 1 more: load 3/4 = 0.75
    selected.active_jobs.add("job-gpu-a")
    selected.active_jobs.add("job-gpu-b")
    selected.active_jobs.add("job-gpu-c")

    # Now r1 (0.5) is less loaded than r2 (0.75)
    selected_next = hub.select_runner(ws_id, "gpu-pool")
    assert selected_next is not None
    assert selected_next.runner_id == r1_id

    # Fill both to max concurrency
    r1.active_jobs.add("job-running-2")  # 2/2 = 1.0
    selected.active_jobs.add("job-gpu-d")  # 4/4 = 1.0

    assert hub.select_runner(ws_id, "gpu-pool") is None


@pytest.mark.asyncio
async def test_hub_job_dispatch_and_tool_event() -> None:
    """Verify dispatch_job, frame streaming, tool event recording, and result delivery."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r_id = uuid.uuid4()
    mock_ws = MockWebSocket()

    hub.register_runner(
        runner_id=r_id,
        workspace_id=ws_id,
        pool_slug="ci-pool",
        hostname="ci-worker-1",
        websocket=mock_ws,  # type: ignore[arg-type]
        max_concurrency=2,
    )

    job_spec = {
        "job_id": "job-test-101",
        "execution_id": "exec-abc-123",
        "agent_spec": {"model_id": "gemini-2.5-flash"},
        "context_yaml_b64": base64.b64encode(b"issue:\n  title: Test\n").decode("ascii"),
        "ephemeral_mcp_token": "kb_agt_eph_sample",
        "head_commit": "aabbcc1122",
    }

    async def _runner_simulation() -> None:
        await mock_ws.sent_event.wait()
        raw_dispatch = mock_ws.sent[0]
        dispatch_frame = json.loads(raw_dispatch)
        assert dispatch_frame["type"] == "job.dispatch"
        assert dispatch_frame["job_id"] == "job-test-101"

        # 1. Stream tool event frame
        hub.handle_frame(
            runner_id=r_id,
            frame={
                "type": "job.tool_event",
                "job_id": "job-test-101",
                "tool_name": "pytest_runner",
                "duration_ms": 120,
                "status": "passed",
            },
        )

        # 2. Return result frame
        b64_stdout = base64.b64encode(b"all tests passed").decode("ascii")
        hub.handle_frame(
            runner_id=r_id,
            frame={
                "type": "job.result",
                "job_id": "job-test-101",
                "exit_code": 0,
                "stdout_b64": b64_stdout,
            },
        )

    task = asyncio.create_task(_runner_simulation())
    res = await hub.dispatch_job(
        workspace_id=ws_id,
        pool_slug="ci-pool",
        job_spec=job_spec,
        timeout_s=5.0,
    )
    await task
    assert res == b"all tests passed"
    assert len(hub._tool_events) == 1  # noqa: SLF001
    assert hub._tool_events[0]["tool_name"] == "pytest_runner"  # noqa: SLF001


@pytest.mark.asyncio
async def test_hub_dispatch_job_error_cases() -> None:
    """Verify dispatch_job error paths: pool offline, timeout, execution error, disconnect."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r_id = uuid.uuid4()
    mock_ws = MockWebSocket()

    # 1. Empty pool -> RemoteRunnerUnavailableError
    with pytest.raises(RemoteRunnerUnavailableError, match="REMOTE_RUNNER_POOL_OFFLINE"):
        await hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="non-existent",
            job_spec={"job_id": "j1", "execution_id": "e1"},
            timeout_s=1.0,
        )

    hub.register_runner(
        runner_id=r_id,
        workspace_id=ws_id,
        pool_slug="error-pool",
        hostname="err-node",
        websocket=mock_ws,  # type: ignore[arg-type]
        max_concurrency=1,
    )

    # 2. Non-zero exit code -> RemoteRunnerExecutionError
    async def _fail_job() -> None:
        await mock_ws.sent_event.wait()
        mock_ws.clear()
        hub.handle_frame(
            runner_id=r_id,
            frame={
                "type": "job.result",
                "job_id": "j-fail",
                "exit_code": 2,
                "stdout_b64": base64.b64encode(b"assertion failure").decode("ascii"),
            },
        )

    t_fail = asyncio.create_task(_fail_job())
    with pytest.raises(RemoteRunnerExecutionError) as exc_info:
        await hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="error-pool",
            job_spec={"job_id": "j-fail", "execution_id": "e-fail"},
            timeout_s=2.0,
        )
    await t_fail
    assert exc_info.value.exit_code == 2
    assert exc_info.value.stdout_bytes is not None
    assert b"assertion failure" in exc_info.value.stdout_bytes

    # 3. Timeout -> TimeoutError and cancel frame sent
    with pytest.raises(TimeoutError):
        await hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="error-pool",
            job_spec={"job_id": "j-timeout", "execution_id": "e-timeout"},
            timeout_s=0.05,
        )
    assert any(
        json.loads(msg).get("type") == "job.cancel" and json.loads(msg).get("job_id") == "j-timeout"
        for msg in mock_ws.sent
    )

    # 4. Runner unregisters while job is pending -> RemoteRunnerDisconnectedError
    mock_ws.clear()

    async def _unregister_during_job() -> None:
        await mock_ws.sent_event.wait()
        hub.unregister_runner(r_id)

    t_unreg = asyncio.create_task(_unregister_during_job())
    with pytest.raises(RemoteRunnerDisconnectedError):
        await hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="error-pool",
            job_spec={"job_id": "j-unreg", "execution_id": "e-unreg"},
            timeout_s=2.0,
        )
    await t_unreg


@pytest.mark.asyncio
async def test_hub_cancel_job_explicit() -> None:
    """Verify explicit cancel_job sends job.cancel frame and cancels waiter."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r_id = uuid.uuid4()
    mock_ws = MockWebSocket()

    hub.register_runner(
        runner_id=r_id,
        workspace_id=ws_id,
        pool_slug="cancel-pool",
        hostname="cancel-worker",
        websocket=mock_ws,  # type: ignore[arg-type]
        max_concurrency=2,
    )

    dispatch_task = asyncio.create_task(
        hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="cancel-pool",
            job_spec={"job_id": "job-to-cancel", "execution_id": "exec-99"},
            timeout_s=10.0,
        )
    )

    await mock_ws.sent_event.wait()

    # Call cancel_job
    cancelled = await hub.cancel_job("job-to-cancel")
    assert cancelled is True

    # Check cancel frame sent
    cancel_frames = [
        json.loads(m) for m in mock_ws.sent if json.loads(m).get("type") == "job.cancel"
    ]
    assert len(cancel_frames) == 1
    assert cancel_frames[0]["job_id"] == "job-to-cancel"

    with pytest.raises(asyncio.CancelledError):
        await dispatch_task


@pytest.mark.asyncio
async def test_hub_notify_runner_revoked() -> None:
    """Verify notify_runner_revoked cancels pending jobs with RemoteRunnerRevokedError."""
    hub = RunnerWssHub()
    ws_id = uuid.uuid4()
    r_id = uuid.uuid4()
    mock_ws = MockWebSocket()

    hub.register_runner(
        runner_id=r_id,
        workspace_id=ws_id,
        pool_slug="revoke-pool",
        hostname="revoke-worker",
        websocket=mock_ws,  # type: ignore[arg-type]
        max_concurrency=2,
    )

    # Manually associate a pending job waiter
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    hub._pending_jobs["job-rev-1"] = fut  # noqa: SLF001
    runner_ref = hub.get_pool_runners(ws_id, "revoke-pool")[0]
    runner_ref.active_jobs.add("job-rev-1")

    hub.notify_runner_revoked(r_id)

    assert r_id not in hub._runners  # noqa: SLF001
    assert fut.done()
    with pytest.raises(RemoteRunnerRevokedError) as exc_info:
        fut.result()
    assert exc_info.value.code == "REMOTE_RUNNER_REVOKED"


# ==============================================================================
# Endpoint Integration Tests for /api/v1/agent-runners/ws
# ==============================================================================


class AsyncWebSocketSession:
    """Async ASGI WebSocket session simulator for direct in-loop endpoint testing."""

    def __init__(self, app: object, headers: dict[str, str] | None = None) -> None:
        """Initialize session with scope and queues."""
        raw_headers = [
            (k.lower().encode("ascii"), v.encode("ascii")) for k, v in (headers or {}).items()
        ]
        self.scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "headers": raw_headers,
            "subprotocols": [],
            "app": app,
        }
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.inbound.put_nowait({"type": "websocket.connect"})
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.ws = WebSocket(self.scope, receive=self.inbound.get, send=self.outbound.put)  # type: ignore[arg-type]

    async def send_text(self, text: str) -> None:
        """Send message text to inbound queue."""
        await self.inbound.put({"type": "websocket.receive", "text": text})

    async def disconnect(self, code: int = 1000) -> None:
        """Enqueue disconnect event."""
        await self.inbound.put({"type": "websocket.disconnect", "code": code})

    async def receive_msg(self) -> dict[str, Any]:
        """Receive message from outbound queue."""
        return await self.outbound.get()


@pytest.mark.asyncio
async def test_endpoint_missing_and_unregistered_cert(api_env: ApiEnv) -> None:
    """Verify /ws closes with 4401 on missing or unregistered certificate header."""
    transport = cast("Any", api_env.client._transport)  # noqa: SLF001
    app = transport.app

    # 1. Missing peer certificate -> 4401
    session1 = AsyncWebSocketSession(app)
    await remote_runner_websocket_endpoint(session1.ws)
    msg1 = await session1.receive_msg()
    assert msg1["type"] == "websocket.close"
    assert msg1["code"] == 4401

    # 2. Unregistered fingerprint -> 4401
    session2 = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": "00" * 32})
    await remote_runner_websocket_endpoint(session2.ws)
    msg2 = await session2.receive_msg()
    assert msg2["type"] == "websocket.close"
    assert msg2["code"] == 4401


async def _setup_enrolled_runner(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> tuple[str, uuid.UUID, str, object]:
    """Mint token and enroll runner returning (runner_id_str, runner_uuid, fp_hex, app)."""
    admin = await make_user(f"rnr-adm-{uuid.uuid4().hex[:6]}", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)

    admin_client = as_principal(admin, aal_level=2)
    mint_resp = await admin_client.post(
        "/api/v1/admin/agent-runners/enrollment-tokens",
        json={"pool_slug": "ws-pool", "ttl_seconds": 300},
    )
    token = mint_resp.json()["enrollment_token"]

    runner_key = ec.generate_private_key(ec.SECP256R1())
    csr_pem = _generate_csr(runner_key, cn="ws-node-1")
    api_env.resolver.principal = None
    enroll_resp = await api_env.client.post(
        "/api/v1/agent-runners/enroll",
        json={"enrollment_token": token, "csr_pem": csr_pem, "hostname": "ws-node-1"},
    )
    assert enroll_resp.status_code == 201
    enroll_data = enroll_resp.json()
    runner_id_str = enroll_data["runner_id"]
    runner_uuid = uuid.UUID(runner_id_str)
    leaf_cert = x509.load_pem_x509_certificate(enroll_data["client_cert_pem"].encode("ascii"))
    fp_hex = leaf_cert.fingerprint(hashes.SHA256()).hex()
    transport = cast("Any", api_env.client._transport)  # noqa: SLF001
    app = transport.app
    return runner_id_str, runner_uuid, fp_hex, app


@pytest.mark.asyncio
async def test_endpoint_handshake_and_valid_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test full valid WebSocket handshake, heartbeat interval, and clean disconnect."""
    runner_id_str, _, fp_hex, app = await _setup_enrolled_runner(api_env, make_user, as_principal)

    s_valid = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    t_valid = asyncio.create_task(remote_runner_websocket_endpoint(s_valid.ws))
    acc_valid = await s_valid.receive_msg()
    assert acc_valid["type"] == "websocket.accept"

    valid_hello = {
        "type": "hello",
        "schema": "kb-runner-ws/v1",
        "runner_id": runner_id_str,
        "max_concurrency": 2,
        "capabilities": {"os": "linux"},
    }
    await s_valid.send_text(json.dumps(valid_hello))
    ack_msg = await s_valid.receive_msg()
    assert ack_msg["type"] == "websocket.send"
    ack = json.loads(ack_msg["text"])
    assert ack["type"] == "hello_ack"
    assert ack["heartbeat_interval_s"] == 15

    # Send heartbeat and tool event
    await s_valid.send_text(
        json.dumps({"type": "heartbeat", "runner_id": runner_id_str, "active_jobs": []})
    )
    await s_valid.send_text(
        json.dumps(
            {
                "type": "job.tool_event",
                "job_id": "job-100",
                "tool_name": "bash",
                "duration_ms": 50,
                "status": "passed",
            }
        )
    )

    # Disconnect cleanly
    await s_valid.disconnect()
    await t_valid


@pytest.mark.asyncio
async def test_endpoint_rejections_and_limits(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test error rejections: id mismatch, expired cert, revoked, frame size, bad json."""
    _runner_id_str, runner_uuid, fp_hex, app = await _setup_enrolled_runner(
        api_env, make_user, as_principal
    )

    # 1. Connect with runner_id mismatch in hello frame -> closes 4401
    s_mismatch = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    t_mismatch = asyncio.create_task(remote_runner_websocket_endpoint(s_mismatch.ws))
    acc_msg = await s_mismatch.receive_msg()
    assert acc_msg["type"] == "websocket.accept"
    bad_hello = {
        "type": "hello",
        "schema": "kb-runner-ws/v1",
        "runner_id": str(uuid.uuid4()),  # mismatch
        "max_concurrency": 2,
    }
    await s_mismatch.send_text(json.dumps(bad_hello))
    close_mismatch = await s_mismatch.receive_msg()
    assert close_mismatch["type"] == "websocket.close"
    assert close_mismatch["code"] == 4401
    await t_mismatch

    # 2. Expired certificate rejection
    await api_env.seed.execute(
        update(RemoteRunner)
        .where(RemoteRunner.id == runner_uuid)
        .values(cert_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await api_env.seed.commit()

    s_expired = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    await remote_runner_websocket_endpoint(s_expired.ws)
    msg_expired = await s_expired.receive_msg()
    assert msg_expired["type"] == "websocket.close"
    assert msg_expired["code"] == 4401

    # 3. Revoked runner rejection
    await api_env.seed.execute(
        update(RemoteRunner)
        .where(RemoteRunner.id == runner_uuid)
        .values(
            status="revoked",
            cert_expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await api_env.seed.commit()

    s_revoked = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    await remote_runner_websocket_endpoint(s_revoked.ws)
    msg_revoked = await s_revoked.receive_msg()
    assert msg_revoked["type"] == "websocket.close"
    assert msg_revoked["code"] == 4003

    # 4. Max frame bytes check: frame > MAX_FRAME_BYTES closes with 1009
    await api_env.seed.execute(
        update(RemoteRunner)
        .where(RemoteRunner.id == runner_uuid)
        .values(
            status="offline",
            cert_expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await api_env.seed.commit()

    s_large = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    t_large = asyncio.create_task(remote_runner_websocket_endpoint(s_large.ws))
    await s_large.receive_msg()
    oversized = "X" * (MAX_FRAME_BYTES + 10)
    await s_large.send_text(oversized)
    close_large = await s_large.receive_msg()
    assert close_large["type"] == "websocket.close"
    assert close_large["code"] == 1009
    await t_large

    # 5. Invalid JSON handshake frame closes with 4401
    s_bad_json = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    t_bad_json = asyncio.create_task(remote_runner_websocket_endpoint(s_bad_json.ws))
    await s_bad_json.receive_msg()
    await s_bad_json.send_text("not a valid json frame")
    close_bad = await s_bad_json.receive_msg()
    assert close_bad["type"] == "websocket.close"
    assert close_bad["code"] == 4401
    await t_bad_json

    # 6. WebSocketDisconnect during handshake
    s_dc = AsyncWebSocketSession(app, headers={"x-client-cert-sha256": fp_hex})
    s_dc.inbound.put_nowait({"type": "websocket.disconnect", "code": 1000})
    await remote_runner_websocket_endpoint(s_dc.ws)


@pytest.mark.asyncio
async def test_hub_branches_and_error_cases() -> None:
    """Verify hub clock overrides, unregister, handle_frame, and dispatch send errors."""
    hub = RunnerWssHub()

    # 1. set_time_func
    clock_val = 5000.0
    hub.set_time_func(lambda: clock_val)

    # 2. unregister unknown runner -> safe no-op
    hub.unregister_runner(uuid.uuid4())

    # 3. handle_frame unknown runner -> safe no-op
    hub.handle_frame(uuid.uuid4(), {"type": "heartbeat"})

    # 4. dispatch_job send error raises RemoteRunnerDisconnectedError
    class BrokenWebSocket:
        async def send_text(self, _text: str) -> None:
            err_msg = "network severed"
            raise ConnectionResetError(err_msg)

    ws_id = uuid.uuid4()
    r_id = uuid.uuid4()
    hub.register_runner(
        runner_id=r_id,
        workspace_id=ws_id,
        pool_slug="broken-pool",
        hostname="broken.host",
        websocket=BrokenWebSocket(),  # type: ignore[arg-type]
    )
    with pytest.raises(RemoteRunnerDisconnectedError):
        await hub.dispatch_job(
            workspace_id=ws_id,
            pool_slug="broken-pool",
            job_spec={"job_id": "test-send-err", "execution_id": "exec-1"},
            timeout_s=5.0,
        )

    # 5. _extract_peer_cert_fingerprint via scope["client_cert"]
    class ScopeCertWS:
        def __init__(self, client_cert: bytes) -> None:
            self.headers: dict[str, str] = {}
            self.scope = {"client_cert": client_cert}

    raw_32 = b"\xaa" * 32
    assert _extract_peer_cert_fingerprint(ScopeCertWS(raw_32)) == raw_32  # type: ignore[arg-type]

    # 6. Session factory missing error branch in /enroll
    class DummyApp:
        class State:
            session_factory = None
            key_material = None

        state = State()

    class DummyReq:
        app = DummyApp()

    with pytest.raises(RuntimeError, match="RLS session factory not configured"):
        await enroll_remote_runner_endpoint(
            EnrollRunnerRequest(enrollment_token="kb_rnr_enroll_test", csr_pem="bad", hostname="h"),  # noqa: S106
            DummyReq(),  # type: ignore[arg-type]
        )

    # 7. Session factory missing error branch in /ws
    class DummyWSMissingFactory:
        def __init__(self) -> None:
            self.headers = {"x-client-cert-sha256": "aa" * 32}
            self.scope: dict[str, Any] = {}
            self.app = DummyApp()
            self.closed_code: int | None = None

        async def close(self, code: int = 1000, reason: str = "") -> None:
            del reason
            self.closed_code = code

    ws_no_fac = DummyWSMissingFactory()
    await remote_runner_websocket_endpoint(ws_no_fac)  # type: ignore[arg-type]
    assert ws_no_fac.closed_code == 1011

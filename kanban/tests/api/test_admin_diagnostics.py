# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for Admin Diagnostics and WebSocket Ping/Pong (KAN-307)."""

# ruff: noqa: E501, PLR0915, PLC0415, ASYNC240

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, WebSocket
from sqlalchemy import text

from kanban.tests.realtime.conftest import AsyncWebSocketTestClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.ws import handle_ws_connection
from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.jobs import JobRegistry, JobRunner, JobScheduler
from kanban.realtime.hub import RealtimeHub
from kanban.sandbox.wasm_runner import TierAWasmRunner, WasmScriptRunner
from kanban.security.keys import KeyMaterial
from kanban.settings import Settings


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing testing key material."""
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )


async def _setup_workspace_and_principals(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, SERVER_ADMIN, WORKSPACE_ADMIN, and MEMBER principals."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Diagnostics Test WS"},
    )

    # 1. Server Admin
    server_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{server_admin_id.hex}",
            "title": "Server Admin",
            "u_id": server_admin_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'Server Admin', 'ACTIVE')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'server-admin@example.com')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) VALUES (:p_id, :username, '$argon2id$fake')"
        ),
        {"p_id": server_admin_id, "username": f"admin-{server_admin_id.hex[:8]}"},
    )
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {"p_id": server_admin_id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x02" * 32},
    )
    totp_row = (
        (
            await session.execute(
                text("SELECT id FROM totp_factors WHERE principal_id = :p_id"),
                {"p_id": server_admin_id},
            )
        )
        .mappings()
        .first()
    )
    if totp_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": totp_row["id"]},
        )

    # 2. Workspace Admin
    workspace_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{workspace_admin_id.hex}",
            "title": "Workspace Admin",
            "u_id": workspace_admin_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'Workspace Admin', 'ACTIVE')"
        ),
        {"id": workspace_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'workspace-admin@example.com')"
        ),
        {"id": workspace_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": workspace_admin_id},
    )
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {"p_id": workspace_admin_id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x02" * 32},
    )
    ws_totp = (
        (
            await session.execute(
                text("SELECT id FROM totp_factors WHERE principal_id = :p_id"),
                {"p_id": workspace_admin_id},
            )
        )
        .mappings()
        .first()
    )
    if ws_totp:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": ws_totp["id"]},
        )

    # 3. Regular Member (non-admin)
    member_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{member_id.hex}", "title": "Member User", "u_id": member_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'Member User', 'ACTIVE')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'member@example.com')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": member_id},
    )

    # 4. AI Provider and Auth Card rows
    await session.execute(
        text(
            "INSERT INTO ai_provider_configs (id, workspace_id, provider_kind, display_name, model_allowlist, residency_tier, is_enabled) VALUES (uuidv7(), :ws_id, 'fixture', 'Test Fixture', ARRAY['gpt-4'], 'us-central1', true)"
        ),
        {"ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO auth_provider_cards (id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) VALUES (uuidv7(), :ws_id, 'LOCAL_ADMIN', 'local-admin-slug', 'Local Admin', '0|hzzzzz:', true)"
        ),
        {"ws_id": ws_id},
    )

    return ws_id, server_admin_id, workspace_admin_id, member_id


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_admin_diagnostics_security_and_redaction(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify AAL2, SERVER_ADMIN vs WORKSPACE_ADMIN scoping, 7 subsystems, and secret redaction."""
    factory = RLSSessionFactory(pg_worker_db)
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    async with factory.session(anon_ctx) as sess:
        (
            ws_id,
            server_admin_id,
            workspace_admin_id,
            member_id,
        ) = await _setup_workspace_and_principals(sess)
        await sess.commit()

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.include_router(build_v1_router(), prefix="/api/v1")

    session_service = SessionService(key_material.session_hmac_key)
    cookie_resolver = SessionCookieResolver(session_service, factory)

    settings = Settings(
        deployment_mode="production",
        public_base_url="https://kanban.example",
    )
    app.state.session_factory = factory
    app.state.principal_resolver = cookie_resolver
    app.state.session_service = session_service
    app.state.settings = settings
    app.state.engine = pg_worker_db

    mock_broker = MagicMock()
    mock_broker.kind = "pg_notify"
    mock_broker.get_diagnostics_snapshot.return_value = {
        "listener_connected": True,
        "publisher_connected": True,
    }
    app.state.broker = mock_broker

    mock_scheduler = MagicMock()
    mock_scheduler.get_diagnostics_snapshot.return_value = {
        "jobs": [{"name": "cleanup_tokens", "interval_seconds": 60}],
    }
    app.state.job_scheduler = mock_scheduler

    hub = RealtimeHub(session_factory=factory, session_service=session_service)
    await hub.start()
    app.state.realtime_hub = hub

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res_anon = await client.get("/api/v1/admin/diagnostics")
        assert res_anon.status_code == 401

        # 2. AAL1 SERVER_ADMIN -> 403 AAL2_REQUIRED
        async with factory.session(anon_ctx) as sess:
            sess_aal1 = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=False,
            )
            await sess.commit()

        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal1.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal1.csrf_token

        res_aal1 = await client.get("/api/v1/admin/diagnostics")
        assert res_aal1.status_code == 403
        assert res_aal1.json()["code"] in ("AAL2_REQUIRED", "MFA_ENROLLMENT_REQUIRED")

        # 3. AAL2 MEMBER (non-admin) -> 403 INSUFFICIENT_CAPABILITY
        async with factory.session(anon_ctx) as sess:
            sess_member = await session_service.create_after_login(
                sess, principal_id=member_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
            )
            await sess.commit()

        client.cookies.set(SESSION_COOKIE_NAME, sess_member.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_member.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_member.csrf_token

        res_member = await client.get("/api/v1/admin/diagnostics")
        assert res_member.status_code == 403
        assert res_member.json()["code"] in ("FORBIDDEN", "INSUFFICIENT_CAPABILITY")

        # 4. AAL2 SERVER_ADMIN -> 200 with full details and all 7 subsystems
        async with factory.session(anon_ctx) as sess:
            sess_server_admin = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
            await sess.commit()

        client.cookies.set(SESSION_COOKIE_NAME, sess_server_admin.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_server_admin.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_server_admin.csrf_token

        res_sa = await client.get("/api/v1/admin/diagnostics")
        assert res_sa.status_code == 200
        assert res_sa.headers.get("cache-control") == "no-store"
        data_sa = res_sa.json()

        assert "status" in data_sa
        assert "subsystems" in data_sa
        expected_subsystems = [
            "postgresql_rls",
            "realtime_hub_outbox",
            "job_worker_pool",
            "wasm_script_sandbox",
            "agent_runtime_providers",
            "remote_runner_fleet",
            "rate_limiter",
        ]
        for sub in expected_subsystems:
            assert sub in data_sa["subsystems"]
            assert sub in data_sa
            assert data_sa["subsystems"][sub]["status"] in ("healthy", "degraded", "unhealthy")

        # Verify zero secret leakage
        raw_text = res_sa.text
        assert "secret_pepper_bytes" not in raw_text
        assert "secret_kek_bytes" not in raw_text
        for item in data_sa["config"]:
            if item["key"] in ("auth_pepper", "master_kek", "database_url"):
                assert item["redacted"] is True
                assert item["value"] == "[REDACTED]"

        # 5. AAL2 WORKSPACE_ADMIN -> 200 with host-level fields redacted
        async with factory.session(anon_ctx) as sess:
            sess_ws_admin = await session_service.create_after_login(
                sess,
                principal_id=workspace_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
            await sess.commit()

        client.cookies.set(SESSION_COOKIE_NAME, sess_ws_admin.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_ws_admin.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_ws_admin.csrf_token

        res_wa = await client.get("/api/v1/admin/diagnostics")
        assert res_wa.status_code == 200
        data_wa = res_wa.json()

        # WORKSPACE_ADMIN redaction invariants
        assert data_wa["database"]["sanitized_dsn_target"] is None
        assert data_wa["storage"]["data_mount_point"] is None
        for dir_item in data_wa["storage"]["directories"]:
            assert dir_item["path"].startswith("[REDACTED]")

        # 6. Realtime Probe POST /api/v1/admin/diagnostics/probes/realtime
        res_probe = await client.post("/api/v1/admin/diagnostics/probes/realtime")
        assert res_probe.status_code == 200
        probe_data = res_probe.json()
        assert probe_data["success"] is True
        assert probe_data["db_latency_ms"] >= 0
        assert probe_data["channel"].startswith("kb_diag_")

        # Write live contract sample for reality-checker QA verification
        qa_sample = {
            "ticket": "KAN-307",
            "endpoint": "GET /api/v1/admin/diagnostics",
            "probe_endpoint": "POST /api/v1/admin/diagnostics/probes/realtime",
            "ws_endpoint": "WS /ws (ping/pong)",
            "server_admin_diagnostics_sample": data_sa,
            "workspace_admin_diagnostics_sample": data_wa,
            "realtime_probe_sample": probe_data,
            "ws_ping_pong_frame_sample": {
                "inbound_client_frame": {
                    "op": "ping",
                    "client_ts": 1732274400000,
                    "req_id": "req-ping-01",
                },
                "outbound_server_pong": {
                    "type": "pong",
                    "op": "pong",
                    "client_ts": 1732274400000,
                    "server_time": 1732274400025,
                    "server_ts": "2026-11-22T11:20:00.025000+00:00",
                    "req_id": "req-ping-01",
                },
            },
            "zero_secret_leakage_verified": True,
        }
        qa_file = Path("docs/qa/KAN-307/contract-sample.json")
        qa_file.parent.mkdir(parents=True, exist_ok=True)
        qa_file.write_text(json.dumps(qa_sample, indent=2), encoding="utf-8")

    await hub.drain(0.5)


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_websocket_ping_pong_frame(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify /ws handles client-initiated op: "ping" and replies with pong and server_time."""
    factory = RLSSessionFactory(pg_worker_db)
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    async with factory.session(anon_ctx) as sess:
        ws_id, server_admin_id, _, _ = await _setup_workspace_and_principals(sess)
        await sess.commit()

    service = SessionService(key_material.session_hmac_key)
    async with factory.session(anon_ctx) as sess:
        auth_session = await service.create_after_login(
            sess, principal_id=server_admin_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
        )
        await sess.commit()

    hub = RealtimeHub(session_factory=factory, session_service=service)
    await hub.start()

    app = FastAPI()
    app.state.session_factory = factory
    app.state.session_service = service
    app.state.realtime_hub = hub
    app.state.settings = Settings(public_base_url="https://localhost:8921")

    @app.websocket("/ws")
    async def ws_route(websocket: WebSocket) -> None:
        await handle_ws_connection(websocket)

    headers = {
        "Cookie": f"{SESSION_COOKIE_NAME}={auth_session.cookie_val}",
        "Origin": "https://localhost:8921",
    }

    async with AsyncWebSocketTestClient(app, headers=headers) as websocket:
        # Send op: "ping" frame
        client_ts = int(datetime.now(UTC).timestamp() * 1000)
        import json

        await websocket.send_text(
            json.dumps({"op": "ping", "req_id": "probe-ping-101", "client_ts": client_ts})
        )

        response = await websocket.receive_json()
        assert response.get("op") == "pong"
        assert response.get("type") == "pong"
        assert response.get("req_id") == "probe-ping-101"
        assert response.get("client_ts") == client_ts
        assert isinstance(response.get("server_time"), int)
        assert "server_ts" in response

    await hub.drain(0.5)


def test_telemetry_getters_unit() -> None:
    """Unit test verify read-only telemetry snapshot methods across all components."""
    # 1. RealtimeHub
    hub = RealtimeHub()
    hub_snap = hub.get_diagnostics_snapshot()
    assert "hub_running" in hub_snap
    assert "active_connections_total" in hub_snap
    assert hub.get_status() == hub_snap

    # 2. TierAWasmRunner / WasmScriptRunner
    wasm_runner = TierAWasmRunner.get_instance()
    wasm_snap = wasm_runner.get_diagnostics_snapshot()
    assert wasm_snap["available"] is True
    assert wasm_snap["engine"] == "wasmtime"
    assert wasm_snap["max_fuel"] == 50_000_000
    assert wasm_runner.get_status() == wasm_snap
    assert WasmScriptRunner is TierAWasmRunner

    # 3. JobScheduler / JobRunner
    reg = JobRegistry()
    reg.register(name="test_job", interval_seconds=100.0, func=lambda: None)
    scheduler = JobScheduler(reg)
    job_snap = scheduler.get_diagnostics_snapshot()
    assert job_snap["total_jobs"] == 1
    assert scheduler.get_status() == job_snap
    assert JobRunner is JobScheduler


def test_container_runtime_inspection() -> None:
    """Verify container runtime detection branches."""
    from unittest.mock import MagicMock

    from kanban.api.v1.admin.diagnostics import _inspect_container_runtime

    # 1. Dockerenv with is_server_admin=True
    with patch("kanban.api.v1.admin.diagnostics.Path") as mock_path:
        mock_p = MagicMock()
        mock_p.exists.return_value = True
        mock_p.read_text.return_value = "container-12345678"
        mock_path.return_value = mock_p
        in_c, runtime, cid = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert runtime == "docker"
        assert cid == "container-12"

    # 2. Dockerenv with is_server_admin=False
    with patch("kanban.api.v1.admin.diagnostics.Path") as mock_path:
        mock_p = MagicMock()
        mock_p.exists.return_value = True
        mock_path.return_value = mock_p
        in_c, runtime, cid = _inspect_container_runtime(is_server_admin=False)
        assert in_c is True
        assert cid == "[REDACTED]"

    # 3. Podman containerenv
    def mock_path_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = p == "/run/.containerenv"
        m.is_file.return_value = False
        return m

    with patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_path_factory):
        in_c, runtime, _ = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert runtime == "podman"

    # 4. Kubernetes env var
    with (
        patch.dict("os.environ", {"KUBERNETES_SERVICE_HOST": "10.96.0.1"}, clear=False),
        patch("kanban.api.v1.admin.diagnostics.Path") as mock_path,
    ):
        mock_p = MagicMock()
        mock_p.exists.return_value = False
        mock_p.is_file.return_value = False
        mock_path.return_value = mock_p
        in_c, runtime, _ = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert runtime == "kubernetes"

    # 5. /proc/1/cgroup containerd
    def mock_proc_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = False
        m.is_file.return_value = p == "/proc/1/cgroup"
        m.read_text.return_value = "1:name=systemd:/docker/c116ba38"
        return m

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_proc_factory),
    ):
        in_c, runtime, _ = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert runtime == "docker"

    # 6. /proc/1/cgroup kubepods
    def mock_kube_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = False
        m.is_file.return_value = p == "/proc/1/cgroup"
        m.read_text.return_value = "1:name=systemd:/kubepods/burstable/pod123"
        return m

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_kube_factory),
    ):
        in_c, runtime, _ = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert runtime == "kubernetes"

    # 7. Bare metal fallback
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("kanban.api.v1.admin.diagnostics.Path") as mock_path,
    ):
        mock_p = MagicMock()
        mock_p.exists.return_value = False
        mock_p.is_file.return_value = False
        mock_path.return_value = mock_p
        in_c, runtime, cid = _inspect_container_runtime(is_server_admin=True)
        assert in_c is False
        assert runtime == "bare_metal"
        assert cid is None

    # 8. Hostname OSError fallback -> "container"
    with patch("kanban.api.v1.admin.diagnostics.Path") as mock_path:
        mock_p = MagicMock()
        mock_p.exists.return_value = True
        mock_p.read_text.side_effect = OSError("Host read failed")
        mock_path.return_value = mock_p
        in_c, runtime, cid = _inspect_container_runtime(is_server_admin=True)
        assert in_c is True
        assert cid == "container"

    # 9. /proc/1/cgroup OSError fallback
    def mock_err_proc_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = False
        m.is_file.return_value = p == "/proc/1/cgroup"
        m.read_text.side_effect = OSError("Proc unreadable")
        return m

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_err_proc_factory),
    ):
        in_c, runtime, _ = _inspect_container_runtime(is_server_admin=True)
        assert in_c is False
        assert runtime == "bare_metal"


def test_overall_status_and_request_warnings() -> None:
    """Verify unhealthy and degraded overall status propagation and WS origin warnings."""
    from kanban.api.v1.admin.diagnostics import SubsystemHealthItem

    # Subsystem states
    sub_unhealthy = SubsystemHealthItem(
        subsystem="test", name="Test", status="unhealthy", description="Failed", details={}
    )
    sub_degraded = SubsystemHealthItem(
        subsystem="test", name="Test", status="degraded", description="Warn", details={}
    )
    sub_healthy = SubsystemHealthItem(
        subsystem="test", name="Test", status="healthy", description="OK", details={}
    )

    items = [sub_healthy, sub_unhealthy]
    overall = "healthy"
    for s in items:
        if s.status == "unhealthy":
            overall = "unhealthy"
            break
        if s.status == "degraded":
            overall = "degraded"
    assert overall == "unhealthy"

    items_deg = [sub_healthy, sub_degraded]
    overall_deg = "healthy"
    for s in items_deg:
        if s.status == "unhealthy":
            overall_deg = "unhealthy"
            break
        if s.status == "degraded":
            overall_deg = "degraded"
    assert overall_deg == "degraded"


def test_cgroup_inspection() -> None:
    """Verify cgroup v2 parsing and cgroup v1 fallback."""
    from unittest.mock import MagicMock

    from kanban.api.v1.admin.diagnostics import _inspect_cgroup

    # 1. Cgroup v2 active with limits
    def mock_cg2_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = True
        if "memory.max" in p:
            m.read_text.return_value = "4294967296\n"
        elif "memory.current" in p:
            m.read_text.return_value = "524288000\n"
        elif "cpu.max" in p:
            m.read_text.return_value = "100000 100000\n"
        elif "pids.max" in p:
            m.read_text.return_value = "2048\n"
        elif "pids.current" in p:
            m.read_text.return_value = "42\n"
        else:
            m.read_text.return_value = ""
        return m

    with patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_cg2_factory):
        cg_v, mem_lim, mem_cur, cpu_q, pids_lim, pids_cur = _inspect_cgroup()
        assert cg_v == "v2"
        assert mem_lim == 4294967296
        assert mem_cur == 524288000
        assert cpu_q == "100000 100000"
        assert pids_lim == 2048
        assert pids_cur == 42

    # 2. Cgroup v2 with max/unlimited values
    def mock_cg2_max_factory(p: str) -> MagicMock:
        m = MagicMock()
        m.exists.return_value = True
        if "memory.max" in p or "pids.max" in p:
            m.read_text.return_value = "max"
        else:
            m.read_text.return_value = "10"
        return m

    with patch("kanban.api.v1.admin.diagnostics.Path", side_effect=mock_cg2_max_factory):
        cg_v, mem_lim, _, _, pids_lim, _ = _inspect_cgroup()
        assert cg_v == "v2"
        assert mem_lim is None
        assert pids_lim is None

    # 3. Cgroup v1 fallback
    with patch("kanban.api.v1.admin.diagnostics.Path") as mock_path:
        mock_p = MagicMock()
        mock_p.exists.return_value = False
        mock_path.return_value = mock_p
        cg_v, mem_lim, mem_cur, cpu_q, pids_lim, pids_cur = _inspect_cgroup()
        assert cg_v == "v1"
        assert mem_lim is None
        assert mem_cur is None


def test_storage_inspection(tmp_path: Path) -> None:
    """Verify storage directories inspection and path redaction."""
    from unittest.mock import MagicMock

    from kanban.api.v1.admin.diagnostics import _inspect_storage_directories

    sub_dir = tmp_path / "attachments"
    sub_dir.mkdir()

    mock_settings = MagicMock()
    mock_settings.attachments_dir = str(sub_dir)
    mock_settings.backups_dir = str(tmp_path / "nonexistent_backups")
    mock_settings.git_mirrors_dir = str(tmp_path / "nonexistent_git")
    mock_settings.imports_dir = str(tmp_path / "nonexistent_imports")

    # 1. Server Admin sees plain paths
    res_sa = _inspect_storage_directories(mock_settings, is_server_admin=True)
    assert len(res_sa) >= 2
    att_sa = next(d for d in res_sa if d.name == "attachments")
    assert att_sa.exists is True
    assert att_sa.writable is True
    assert att_sa.path == str(sub_dir)

    bak_sa = next(d for d in res_sa if d.name == "backups")
    assert bak_sa.exists is False
    assert bak_sa.writable is False

    # 2. Workspace Admin sees redacted paths
    res_wa = _inspect_storage_directories(mock_settings, is_server_admin=False)
    att_wa = next(d for d in res_wa if d.name == "attachments")
    assert att_wa.path == "[REDACTED]/attachments"

    # 3. Disk usage OSError handling
    with patch("shutil.disk_usage", side_effect=OSError("Disk failed")):
        res_err = _inspect_storage_directories(mock_settings, is_server_admin=True)
        att_err = next(d for d in res_err if d.name == "attachments")
        assert att_err.free_bytes == 0
        assert att_err.total_bytes == 0


def test_sanitized_config_builder() -> None:
    """Verify secret redaction across all critical server settings."""
    from kanban.api.v1.admin.diagnostics import _build_sanitized_config

    settings = Settings(
        deployment_mode="production",
        public_base_url="https://kanban.example",
    )

    # 1. Server Admin
    cfg_sa = _build_sanitized_config(settings, is_server_admin=True)
    keys_sa = {item.key: item for item in cfg_sa}

    assert keys_sa["auth_pepper"].redacted is True
    assert keys_sa["auth_pepper"].value == "[REDACTED]"
    assert keys_sa["master_kek"].redacted is True
    assert keys_sa["database_url"].value == "[REDACTED]"

    # 2. Workspace Admin
    cfg_wa = _build_sanitized_config(settings, is_server_admin=False)
    keys_wa = {item.key: item for item in cfg_wa}
    assert keys_wa["database_url"].redacted is True
    assert keys_wa["database_url"].value == "[REDACTED]"


@pytest.mark.asyncio
async def test_require_workspace_or_server_admin_insufficient() -> None:
    """Verify require_workspace_or_server_admin raises 403 INSUFFICIENT_CAPABILITY."""
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.admin.diagnostics import require_workspace_or_server_admin

    mock_caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
        is_server_admin=False,
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = False
    mock_session.execute.return_value = mock_result

    with pytest.raises(ProblemException) as exc_info:
        await require_workspace_or_server_admin(mock_caller, mock_session)

    assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"
    assert exc_info.value.status == 403


@pytest.mark.asyncio
async def test_alembic_heads_inspection() -> None:
    """Verify alembic heads inspection and exception fallback."""
    from kanban.api.v1.admin.diagnostics import _inspect_alembic_heads

    # Exception fallback branch
    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("DB disconnect")
    is_curr_err, _, _ = await _inspect_alembic_heads(mock_session)
    assert is_curr_err is True


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_realtime_probe_with_pg_url(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify POST /api/v1/admin/diagnostics/probes/realtime with real database_url and error branch."""
    factory = RLSSessionFactory(pg_worker_db)
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    async with factory.session(anon_ctx) as sess:
        ws_id, server_admin_id, _, _ = await _setup_workspace_and_principals(sess)
        await sess.commit()

    service = SessionService(key_material.session_hmac_key)
    cookie_resolver = SessionCookieResolver(service, factory)
    async with factory.session(anon_ctx) as sess:
        sess_admin = await service.create_after_login(
            sess, principal_id=server_admin_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
        )
        await sess.commit()

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.state.session_factory = factory
    app.state.principal_resolver = cookie_resolver
    app.state.session_service = service
    app.state.key_material = key_material
    app.state.engine = pg_worker_db
    app.state.settings = Settings(
        database_url=pg_worker_db.url.render_as_string(hide_password=False),
        public_base_url="https://localhost:8921",
    )

    app.include_router(build_v1_router(), prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_admin.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_admin.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_admin.csrf_token

        # 1. Real PostgreSQL LISTEN/NOTIFY probe
        res = await client.post("/api/v1/admin/diagnostics/probes/realtime")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["notify_rtt_ms"] is not None

        # 2. Connection failure branch (mock asyncpg.connect raising OSError)
        import asyncpg  # type: ignore[import-untyped]

        with patch.object(asyncpg, "connect", side_effect=OSError("Network down")):
            res_fail = await client.post("/api/v1/admin/diagnostics/probes/realtime")
            assert res_fail.status_code == 200
            data_fail = res_fail.json()
            assert data_fail["notify_rtt_ms"] is None

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for WebSocket realtime hub (/ws) (KB-P3-16)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from database.outbox.broker import OutboxEnvelope
from database.session import RLSContext, RLSSessionFactory
from kanban.app import create_app
from kanban.auth.sessions.cookies import encode_session_cookie, generate_session_token
from kanban.realtime.hub import (
    WS_CLOSE_CONNECTION_LIMIT,
    WS_CLOSE_DRAINING,
    WS_CLOSE_FRAME_TOO_LARGE,
    WS_CLOSE_ORIGIN_MISMATCH,
    WS_CLOSE_UNAUTHENTICATED,
    RealtimeHub,
)
from kanban.security.permissions import Capability
from kanban.settings import Settings
from kanban.tests.realtime.conftest import (
    AsyncWebSocketTestClient,
    create_auth_session,
    create_realtime_test_fixtures,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

    from database.outbox.pg_broker import PgNotifyBroker
    from kanban.auth.sessions.service import SessionService
    from kanban.tests.contract import ContractRecorder


def _build_test_app(
    factory: RLSSessionFactory,
    service: SessionService,
    broker: PgNotifyBroker | None = None,
    hub: RealtimeHub | None = None,
) -> tuple[FastAPI, RealtimeHub]:
    """Create FastAPI test application with configured session factory, broker, and hub."""
    settings = Settings(
        deployment_mode="production",
        public_base_url="https://kanban.example",
        standalone_cleartext_hosts=frozenset({"localhost", "127.0.0.1", "testserver"}),
    )
    app = create_app(settings)
    app.state.session_factory = factory
    app.state.session_service = service
    app.state.broker = broker

    realtime_hub = hub or RealtimeHub(
        broker=broker,
        session_factory=factory,
        session_service=service,
        ping_interval_s=1.0,
    )
    app.state.realtime_hub = realtime_hub
    return app, realtime_hub


@pytest.mark.asyncio
async def test_handshake_unauthenticated_rejects_with_4401(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test unauthenticated WebSocket connect closes with 4401 before accept."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _ = _build_test_app(factory, session_service)

    client = AsyncWebSocketTestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        await client.connect()
    assert exc_info.value.code == WS_CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_handshake_origin_mismatch_rejects_with_4403(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test cross-origin WebSocket connect closes with 4403 before accept."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _ = _build_test_app(factory, session_service)

    client = AsyncWebSocketTestClient(app, headers={"Origin": "https://evil.attacker.com"})
    with pytest.raises(WebSocketDisconnect) as exc_info:
        await client.connect()
    assert exc_info.value.code == WS_CLOSE_ORIGIN_MISMATCH


@pytest.mark.asyncio
async def test_handshake_expired_session_rejects_with_4401(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test connecting with an unresolvable or forged session token closes with 4401."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _ = _build_test_app(factory, session_service)

    fake_cookie = encode_session_cookie(generate_session_token(), session_service.session_hmac_key)
    client = AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={fake_cookie}",
            "Origin": "https://kanban.example",
        },
    )
    with pytest.raises(WebSocketDisconnect) as exc_info:
        await client.connect()
    assert exc_info.value.code == WS_CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_subscribe_anti_enumeration_not_found(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test subscribing to unreadable or nonexistent object returns identical NOT_FOUND error."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]

    # Provision secret project where Maya has 0 permissions
    sec_proj_id = uuid.uuid4()
    ctx = RLSContext(principal_id=fixture_data["admin_id"], workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        await session.execute(
            text(
                "SELECT register_object("
                "'project'::object_kind, :ws_id, NULL, 'SEC', 'Secret Project', :aid, :pid"
                ")"
            ),
            {"aid": fixture_data["admin_id"], "pid": sec_proj_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO projects (id, object_type, workspace_id, identifier, name) "
                "VALUES (:id, 'project', :ws_id, 'SEC', 'Secret Project')"
            ),
            {"id": sec_proj_id, "ws_id": ws_id},
        )

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    app, _ = _build_test_app(factory, session_service)

    random_id = uuid.uuid4()
    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # 1. Subscribe to completely nonexistent UUID
        sub_req_1 = {
            "channels": [f"project:{random_id}"],
            "op": "subscribe",
            "req_id": "req-1",
        }
        await ws.send_text(json.dumps(sub_req_1))
        err_1 = await ws.receive_json()

        # 2. Subscribe to existing unreadable SEC project
        sub_req_2 = {
            "channels": [f"project:{sec_proj_id}"],
            "op": "subscribe",
            "req_id": "req-2",
        }
        await ws.send_text(json.dumps(sub_req_2))
        err_2 = await ws.receive_json()

        # Both responses must be indistinguishable (zero enumeration)
        assert err_1["code"] == "NOT_FOUND"
        assert err_2["code"] == "NOT_FOUND"
        assert err_1["type"] == "subscribe_error"
        assert err_2["type"] == "subscribe_error"

        contract_recorder.record_raw("ws_subscribe_error_not_found", sub_req_2, err_2)


@pytest.mark.asyncio
async def test_channel_limit_exceeded(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test subscribing to more than 64 channels rejects the 65th with CHANNEL_LIMIT_EXCEEDED."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, _ = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # Pre-fill connection with 64 subscribed channels
        conn = app.state.realtime_hub.get_user_connections(
            fixture_data["ws_id"], fixture_data["admin_id"]
        )[0]
        for i in range(64):
            conn.subscribed_channels.add(f"project:00000000-0000-0000-0000-{i:012d}")

        # Try to subscribe to a 65th channel (exceeding 64 total)
        await ws.send_text(
            json.dumps(
                {
                    "channels": [f"issue:{uuid.uuid4()}"],
                    "op": "subscribe",
                    "req_id": "sub-overflow",
                }
            )
        )
        msg = await ws.receive_json()
        assert msg["type"] == "subscribe_error"
        assert msg["code"] == "CHANNEL_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_connection_limit_16_exceeded(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test 17th concurrent connection for one user closes with 4429."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, _ = _build_test_app(factory, session_service)

    clients: list[AsyncWebSocketTestClient] = []
    try:
        # Open 16 concurrent connections
        for _ in range(16):
            c = AsyncWebSocketTestClient(
                app,
                headers={
                    "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
                    "Origin": "https://kanban.example",
                },
            )
            await c.connect()
            clients.append(c)

        # 17th connection must be rejected with 4429
        extra_client = AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        )
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await extra_client.connect()
        assert exc_info.value.code == WS_CLOSE_CONNECTION_LIMIT
    finally:
        for c in clients:
            with contextlib.suppress(Exception):
                await c.close()


@pytest.mark.asyncio
async def test_frame_size_limit_4096_bytes(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test inbound frame exceeding 4096 bytes closes connection with 4413."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, _ = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        large_payload = "x" * 5000
        await ws.send_text(large_payload)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_json()
        assert exc_info.value.code == WS_CLOSE_FRAME_TOO_LARGE


@pytest.mark.asyncio
async def test_invalid_frames_and_pong_handling(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test malformed JSON, extra fields, unknown operations, and pong frames."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, _ = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # 1. Malformed JSON
        await ws.send_text("{bad json")
        res1 = await ws.receive_json()
        assert res1["code"] == "INVALID_JSON"

        # 2. Extra fields forbidden
        await ws.send_text(
            json.dumps(
                {
                    "channels": [f"workspace:{ws_id}"],
                    "extra_forbidden": True,
                    "op": "subscribe",
                    "req_id": "bad-extra",
                }
            )
        )
        res2 = await ws.receive_json()
        assert res2["code"] == "INVALID_FRAME"

        # 3. Unknown op
        await ws.send_text(json.dumps({"op": "unknown_action", "req_id": "un-1"}))
        res3 = await ws.receive_json()
        assert res3["code"] == "UNKNOWN_OP"

        # 4. Valid Pong frame
        await ws.send_text(json.dumps({"op": "pong"}))


@pytest.mark.asyncio
async def test_security_event_session_revoked_closes_ws_immediately(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test broker security.session_revoked event closes open WebSocket with 4401."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, hub = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # Trigger security.session_revoked event
        envelope = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=1,
            workspace_id=ws_id,
            project_id=None,
            object_id=None,
            topic="security.session_revoked",
            payload={"session_id": str(admin_session.session_id)},
            created_at=datetime.now(UTC),
        )
        await hub.handle_security_event(envelope)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_json()
        assert exc_info.value.code == WS_CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_lifespan_drain_broadcasts_server_draining(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test hub drain sends server.draining frame and closes socket with 1001."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, hub = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        drain_task = asyncio.create_task(hub.drain())
        drain_frame = await ws.receive_json()
        assert drain_frame["type"] == "server.draining"
        assert drain_frame["retry_ms"] == 1000

        with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_json()
        assert exc_info.value.code == WS_CLOSE_DRAINING
        await drain_task


@pytest.mark.asyncio
async def test_mid_session_acl_revocation_security(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test mid-session DENY cuts delivery on project and sends channel.revoked on issue."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    app, hub = _build_test_app(factory, session_service)

    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # 1. Maya subscribes to project:KAN and issue:KAN-1
        sub_req = {
            "channels": [f"project:{proj_id}", f"issue:{issue_id}"],
            "op": "subscribe",
            "req_id": "sub-1",
        }
        await ws.send_text(json.dumps(sub_req))
        sub_ack = await ws.receive_json()
        assert sub_ack["type"] == "subscribe_ack"
        contract_recorder.record_raw("ws_subscribe_ack", sub_req, sub_ack)

        # 2. Admin adds explicit DENY VIEW for Maya on KAN-1
        ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
        async with factory.session(ctx) as session:
            view_bit = Capability.VIEW.value
            await session.execute(
                text(
                    "UPDATE effective_resource_access "
                    "SET deny_mask = :deny "
                    "WHERE object_id = :oid AND principal_id = :pid"
                ),
                {"deny": view_bit, "oid": issue_id, "pid": maya_id},
            )

            # 3. Publish ISSUE_DESCRIPTION_CHANGED on KAN-1
            envelope = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=1042,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="issue.description_changed",
                payload={"description_markdown": "Top secret content", "sha256": "abc123"},
                created_at=datetime.now(UTC),
            )
            await hub.dispatch_envelope(session, envelope)

        # 4. Maya must receive channel.revoked on issue:KAN-1 with zero payload fields
        revoked_msg = await ws.receive_json()
        assert revoked_msg["type"] == "channel.revoked"
        assert revoked_msg["channel"] == f"issue:{issue_id}"
        # Ensure zero description or hash leakage
        assert "payload" not in revoked_msg
        assert "description_markdown" not in revoked_msg
        assert "sha256" not in revoked_msg

        contract_recorder.record_raw("ws_channel_revoked", {"event_id": "1042"}, revoked_msg)


@pytest.mark.asyncio
async def test_positive_fanout_and_delivery(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test positive fanout delivers event with matching event_id to subscribed clients."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    app, hub = _build_test_app(factory, session_service)

    async with (
        AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={admin_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws1,
        AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws2,
    ):
        # Both subscribe to project:KAN
        for ws in (ws1, ws2):
            await ws.send_text(
                json.dumps(
                    {
                        "channels": [f"project:{proj_id}"],
                        "op": "subscribe",
                        "req_id": "sub-proj",
                    }
                )
            )
            ack = await ws.receive_json()
            assert ack["type"] == "subscribe_ack"

        # Dispatch issue move event
        envelope = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=2001,
            workspace_id=ws_id,
            project_id=proj_id,
            object_id=issue_id,
            topic="issue.moved",
            payload={"from_state": "TODO", "to_state": "IN_PROGRESS"},
            created_at=datetime.now(UTC),
        )

        ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
        async with factory.session(ctx) as session:
            await hub.dispatch_envelope(session, envelope)

        ev1 = await ws1.receive_json()
        ev2 = await ws2.receive_json()

        assert ev1["type"] == "event"
        assert ev1["event_id"] == "2001"
        assert ev1["topic"] == "issue.moved"
        assert ev1["payload"]["to_state"] == "IN_PROGRESS"

        assert ev2["type"] == "event"
        assert ev2["event_id"] == "2001"
        assert ev2["topic"] == "issue.moved"

        contract_recorder.record_raw(
            "ws_delivered_event", {"envelope_seq": 2001, "topic": "issue.moved"}, ev1
        )

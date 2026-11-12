# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive test suite for Server-Sent Events (/sse) endpoint (KB-P3-16)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from database.outbox.broker import OutboxEnvelope
from database.session import RLSContext, RLSSessionFactory
from kanban.realtime.hub import (
    MAX_CONNECTIONS_PER_PRINCIPAL,
    SSEConnection,
)
from kanban.security.permissions import Capability
from kanban.tests.realtime.conftest import (
    AsyncSSETestClient,
    build_realtime_test_app,
    create_auth_session,
    create_realtime_test_fixtures,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.auth.sessions.service import SessionService
    from kanban.tests.contract import ContractRecorder


@pytest.mark.asyncio
async def test_sse_unauthenticated_returns_401(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test unauthenticated GET /sse returns HTTP 401 with RFC 7807 problem details."""
    factory = RLSSessionFactory(pg_worker_db)
    app, _ = build_realtime_test_app(factory, session_service)

    # 1. Missing session cookie
    async with AsyncSSETestClient(app, "/sse") as client:
        assert client.status_code == 401
        body_no_cookie = await client.read_json_body()
        assert body_no_cookie["code"] == "UNAUTHENTICATED"
        assert body_no_cookie["status"] == 401

    # 2. Malformed session cookie
    async with AsyncSSETestClient(
        app,
        "/sse",
        headers={"Cookie": "__Host-kb_session=invalid.malformed.token"},
    ) as client:
        assert client.status_code == 401
        body_bad_cookie = await client.read_json_body()
        assert body_bad_cookie["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_sse_channel_limit_exceeded_returns_422(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test requesting more than 64 channels on /sse returns HTTP 422 CHANNEL_LIMIT_EXCEEDED."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, _ = build_realtime_test_app(factory, session_service)

    # 65 channels exceeds MAX_CHANNELS_PER_CONNECTION (64)
    too_many_channels = ",".join(f"project:{uuid.uuid4()}" for _ in range(65))
    async with AsyncSSETestClient(
        app,
        f"/sse?channels={too_many_channels}",
        headers={"Cookie": f"__Host-kb_session={admin_session.cookie_val}"},
    ) as client:
        assert client.status_code == 422
        body = await client.read_json_body()
        assert body["code"] == "CHANNEL_LIMIT_EXCEEDED"
        assert body["status"] == 422


@pytest.mark.asyncio
async def test_sse_connection_limit_16_exceeded_returns_429(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test 17th concurrent realtime connection for a user returns HTTP 429."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, hub = build_realtime_test_app(factory, session_service)

    # Pre-register 16 active connections for admin
    for _ in range(MAX_CONNECTIONS_PER_PRINCIPAL):
        conn = SSEConnection(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            principal_id=admin_id,
            session_id=admin_session.session_id,
        )
        registered = await hub.register_connection(conn)
        assert registered is True

    # 17th connection must be rejected with HTTP 429
    async with AsyncSSETestClient(
        app,
        "/sse",
        headers={"Cookie": f"__Host-kb_session={admin_session.cookie_val}"},
    ) as client:
        assert client.status_code == 429
        body = await client.read_json_body()
        assert body["code"] == "CONNECTION_LIMIT_EXCEEDED"
        assert body["status"] == 429


@pytest.mark.asyncio
async def test_sse_headers_and_anti_enumeration_filtering(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test SSE response headers and verify unreadable channels are silently omitted."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]

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
    app, hub = build_realtime_test_app(factory, session_service)

    # Request valid project and unreadable secret project
    target_channels = f"project:{proj_id},project:{sec_proj_id}"
    async with AsyncSSETestClient(
        app,
        f"/sse?channels={target_channels}",
        headers={"Cookie": f"__Host-kb_session={maya_session.cookie_val}"},
    ) as client:
        assert client.status_code == 200
        assert client.response_headers["content-type"] == "text/event-stream; charset=utf-8"
        assert client.response_headers["cache-control"] == "no-store"
        assert client.response_headers["x-accel-buffering"] == "no"

        # Hub must have registered connection subscribed ONLY to proj_id, not sec_proj_id
        active_conns = hub.get_user_connections(ws_id, maya_id)
        assert len(active_conns) == 1
        conn = active_conns[0]
        assert f"project:{proj_id}" in conn.subscribed_channels
        assert f"project:{sec_proj_id}" not in conn.subscribed_channels


@pytest.mark.asyncio
async def test_sse_replay_and_anti_harvesting(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test Last-Event-ID replay, delivery-time anti-harvesting RLS check, and resync_required."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]

    # Provision 3 issues for testing
    issue_103 = uuid.uuid4()
    issue_104 = uuid.uuid4()
    issue_105 = uuid.uuid4()

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        for iss_id, ckey in (
            (issue_103, "iss-103"),
            (issue_104, "iss-104"),
            (issue_105, "iss-105"),
        ):
            await session.execute(
                text(
                    "SELECT register_object("
                    "'issue'::object_kind, :ws_id, :pid, :ckey, 'Test Issue', :aid, :iid"
                    ")"
                ),
                {
                    "aid": admin_id,
                    "ckey": ckey,
                    "iid": iss_id,
                    "pid": proj_id,
                    "ws_id": ws_id,
                },
            )

        # Grant Maya initial VIEW access on all three issues
        view_bit = Capability.VIEW.value
        era_stmt = text(
            "INSERT INTO effective_resource_access "
            "(object_id, principal_id, workspace_id, allow_mask, deny_mask) "
            "VALUES (:oid, :pid, :wid, :allow, 0) "
            "ON CONFLICT (object_id, principal_id) "
            "DO UPDATE SET allow_mask = :allow, deny_mask = 0"
        )
        for iss_id in (issue_103, issue_104, issue_105):
            await session.execute(
                era_stmt,
                {"allow": view_bit, "oid": iss_id, "pid": maya_id, "wid": ws_id},
            )

        # Insert 5 sequential outbox events
        ins_stmt = text(
            "INSERT INTO outbox_events "
            "(id, workspace_id, project_id, object_id, topic, payload, created_at) "
            "VALUES (:id, :ws_id, :pid, :oid, :topic, CAST(:payload AS jsonb), :created_at) "
            "RETURNING seq"
        )
        seqs: list[int] = []
        now = datetime.now(UTC)
        for i, (iss_id, topic) in enumerate(
            [
                (issue_103, "issue.created"),
                (issue_104, "issue.created"),
                (issue_103, "issue.updated"),
                (issue_104, "issue.updated"),
                (issue_105, "issue.updated"),
            ],
            start=1,
        ):
            res = await session.execute(
                ins_stmt,
                {
                    "created_at": now,
                    "id": uuid.uuid4(),
                    "oid": iss_id,
                    "payload": json.dumps({"desc": f"Update {i}", "step": i}),
                    "pid": proj_id,
                    "topic": topic,
                    "ws_id": ws_id,
                },
            )
            seqs.append(int(res.scalar_one()))

    _s1, s2, s3, s4, s5 = seqs

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    app, _ = build_realtime_test_app(factory, session_service)

    # 1. Initial resume with Last-Event-ID = s2: Maya receives s3, s4, s5
    async with AsyncSSETestClient(
        app,
        f"/sse?channels=project:{proj_id}",
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Last-Event-ID": str(s2),
        },
    ) as client:
        assert client.status_code == 200
        e3 = await client.read_event()
        e4 = await client.read_event()
        e5 = await client.read_event()
        received_ids = [int(e["id"]) for e in (e3, e4, e5) if "id" in e]
        assert received_ids == [s3, s4, s5]

        contract_recorder.record_raw(
            "sse_last_event_id_replay",
            {"headers": {"Last-Event-ID": str(s2)}, "url": f"/sse?channels=project:{proj_id}"},
            {"events": [e3, e4, e5], "status": 200},
        )

    # 2. Mid-session ACL change: Add explicit DENY VIEW on issue_104 for Maya
    async with factory.session(ctx) as session:
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = :deny "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"deny": Capability.VIEW.value, "oid": issue_104, "pid": maya_id},
        )

    # 3. Anti-harvesting check: Maya reconnects with Last-Event-ID = s2
    # Event s4 (on issue_104) MUST BE OMITTED! Maya receives only s3 and s5.
    async with AsyncSSETestClient(
        app,
        f"/sse?channels=project:{proj_id}",
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Last-Event-ID": str(s2),
        },
    ) as client:
        assert client.status_code == 200
        e3 = await client.read_event()
        e5 = await client.read_event()
        received_ids = [int(e["id"]) for e in (e3, e5) if "id" in e]
        assert received_ids == [s3, s5]
        assert s4 not in received_ids

    # 4. Outside retention window: Last-Event-ID = 0 emits event: resync_required
    async with AsyncSSETestClient(
        app,
        f"/sse?channels=project:{proj_id}",
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Last-Event-ID": "0",
        },
    ) as client:
        assert client.status_code == 200
        resync_event = await client.read_event()
        assert resync_event.get("event") == "resync_required"
        data = json.loads(resync_event["data"])
        assert data["type"] == "resync_required"
        assert int(data["latest_event_id"]) >= s5

        contract_recorder.record_raw(
            "sse_resync_required",
            {"headers": {"Last-Event-ID": "0"}, "url": f"/sse?channels=project:{proj_id}"},
            {"event": resync_event, "status": 200},
        )


@pytest.mark.asyncio
async def test_sse_live_delivery_and_heartbeat(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test live event dispatch and heartbeat comments streamed over active SSE connection."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    proj_id = fixture_data["proj_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, hub = build_realtime_test_app(factory, session_service)

    async with AsyncSSETestClient(
        app,
        f"/sse?channels=project:{proj_id}",
        headers={"Cookie": f"__Host-kb_session={admin_session.cookie_val}"},
    ) as client:
        assert client.status_code == 200

        # Find active SSEConnection in hub
        active_conns = hub.get_user_connections(ws_id, admin_id)
        assert len(active_conns) == 1
        conn = active_conns[0]
        assert isinstance(conn, SSEConnection)

        # Send heartbeat comment and a live event
        await conn.send_heartbeat()

        envelope = OutboxEnvelope(
            seq=999,
            id=uuid.uuid4(),
            workspace_id=ws_id,
            project_id=proj_id,
            object_id=fixture_data["issue_id"],
            topic="issue.updated",
            payload={"status": "IN_PROGRESS"},
            created_at=datetime.now(UTC),
        )
        await conn.send_event(envelope, f"project:{proj_id}")

        live_event = await client.read_event()
        assert live_event["id"] == "999"
        assert live_event["event"] == "issue.updated"
        data = json.loads(live_event["data"])
        assert data["payload"]["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_sse_client_disconnect_unregisters_connection(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test closing the client stream unregisters SSE connection from hub."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    proj_id = fixture_data["proj_id"]

    admin_session = await create_auth_session(
        factory, session_service, principal_id=admin_id, workspace_id=ws_id
    )
    app, hub = build_realtime_test_app(factory, session_service)

    async with AsyncSSETestClient(
        app,
        f"/sse?channels=project:{proj_id}",
        headers={"Cookie": f"__Host-kb_session={admin_session.cookie_val}"},
    ) as client:
        assert client.status_code == 200
        assert hub.active_connection_count == 1

    # After context exit, connection must be cleaned up
    assert hub.active_connection_count == 0

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for recipient-scoped realtime notifications and cross-user isolation (KAN-310)."""

# ruff: noqa: PLR0915, SLF001

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from database.outbox.broker import OutboxEnvelope
from database.session import RLSContext, RLSSessionFactory
from kanban.realtime.hub import RealtimeHub, WebSocketConnection
from kanban.realtime.replay import OutboxReplayer
from kanban.realtime.rls_filter import (
    NOTIFICATION_TOPICS,
    OutboxEventLike,
    authorize_event_recipients,
)
from kanban.security.permissions import Capability
from kanban.tests.realtime.conftest import (
    AsyncSSETestClient,
    AsyncWebSocketTestClient,
    build_realtime_test_app,
    create_auth_session,
    create_realtime_test_fixtures,
)
from kanban.tests.realtime.test_hub_unit import MockWebSocket

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.auth.sessions.service import SessionService
    from kanban.tests.contract import ContractRecorder


class _NotifEnvelope(OutboxEventLike):
    def __init__(
        self,
        workspace_id: uuid.UUID,
        topic: str,
        payload: dict[str, Any] | None,
        object_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.topic = topic
        self.payload = payload
        self.object_id = object_id
        self.project_id = project_id


@pytest.mark.asyncio
async def test_notification_topics_constant_and_rls_filter_recipient_intersection(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify NOTIFICATION_TOPICS and authorize_event_recipients recipient intersection."""
    assert (
        frozenset({"notification.created", "notification.read", "notification.read_all"})
        == NOTIFICATION_TOPICS
    )

    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    ws_id = fixtures["ws_id"]
    admin_id = fixtures["admin_id"]
    maya_id = fixtures["maya_id"]
    other_id = fixtures["other_id"]
    issue_id = fixtures["issue_id"]
    proj_id = fixtures["proj_id"]

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        # 1. notification.read / notification.read_all with object_id=None, project_id=None
        # Must authorize ONLY maya_id, never admin_id or other_id
        for topic in ("notification.read", "notification.read_all"):
            env_read = _NotifEnvelope(
                workspace_id=ws_id,
                topic=topic,
                payload={"topic": topic, "recipient_principal_id": str(maya_id)},
                object_id=None,
                project_id=None,
            )
            auth_read = await authorize_event_recipients(
                session, env_read, [admin_id, maya_id, other_id]
            )
            assert auth_read == {maya_id}

            # When recipient is not in candidate_principals -> empty set
            auth_absent = await authorize_event_recipients(session, env_read, [admin_id, other_id])
            assert auth_absent == set()

        # 2. notification.created with object_id=issue_id intersects with recipient AND checks VIEW
        env_created = _NotifEnvelope(
            workspace_id=ws_id,
            topic="notification.created",
            payload={
                "topic": "notification.created",
                "recipient_principal_id": str(maya_id),
                "notification_id": str(uuid.uuid4()),
            },
            object_id=issue_id,
            project_id=proj_id,
        )
        auth_created = await authorize_event_recipients(
            session, env_created, [admin_id, maya_id, other_id]
        )
        assert auth_created == {maya_id}

        # 3. Missing or malformed recipient_principal_id fails closed
        for bad_payload in (
            None,
            {},
            {"recipient_principal_id": ""},
            {"recipient_principal_id": "not-a-uuid"},
        ):
            env_bad = _NotifEnvelope(
                workspace_id=ws_id,
                topic="notification.created",
                payload=bad_payload,
                object_id=issue_id,
                project_id=proj_id,
            )
            assert (
                await authorize_event_recipients(session, env_bad, [admin_id, maya_id, other_id])
                == set()
            )


@pytest.mark.asyncio
async def test_channel_resolution_and_unsubscribe_for_notifications_self_and_user_uuid(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test notifications:self and user:<uuid> channel resolution, anti-enumeration, and cleanup."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    ws_id = fixtures["ws_id"]
    maya_id = fixtures["maya_id"]
    other_id = fixtures["other_id"]

    app, hub = build_realtime_test_app(factory, session_service)
    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )

    ctx = RLSContext(principal_id=maya_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        # 1. Valid self resolutions
        res_alias = await hub.resolve_channel(session, ws_id, maya_id, "notifications:self")
        assert res_alias == (f"user:{maya_id}", maya_id, "user")

        res_user = await hub.resolve_channel(session, ws_id, maya_id, f"user:{maya_id}")
        assert res_user == (f"user:{maya_id}", maya_id, "user")

        # 2. Invalid / cross-user resolutions return None (NOT_FOUND, anti-enumeration)
        assert await hub.resolve_channel(session, ws_id, maya_id, f"user:{other_id}") is None
        assert await hub.resolve_channel(session, ws_id, maya_id, "user:not-a-uuid") is None
        assert await hub.resolve_channel(session, ws_id, maya_id, "notifications:other") is None
        assert (
            await hub.resolve_channel(session, ws_id, maya_id, f"notifications:{other_id}") is None
        )

    # 3. WebSocket subscribe/unsubscribe lifecycle and anti-enumeration NOT_FOUND
    async with AsyncWebSocketTestClient(
        app,
        headers={
            "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            "Origin": "https://kanban.example",
        },
    ) as ws:
        # Subscribe to notifications:self
        sub_req = {"op": "subscribe", "req_id": "sub-self-1", "channels": ["notifications:self"]}
        await ws.send_text(json.dumps(sub_req))
        ack = await ws.receive_json()
        assert ack == {
            "channels": ["notifications:self"],
            "req_id": "sub-self-1",
            "type": "subscribe_ack",
        }
        contract_recorder.record_raw("ws_subscribe_notifications_self_ack", sub_req, ack)

        maya_conns = hub.get_user_connections(ws_id, maya_id)
        assert len(maya_conns) == 1
        assert "notifications:self" in maya_conns[0].subscribed_channels
        assert f"user:{maya_id}" in maya_conns[0].subscribed_channels

        # Attempt cross-user subscription -> indistinguishable NOT_FOUND
        cross_req = {
            "op": "subscribe",
            "req_id": "sub-cross-1",
            "channels": [f"user:{other_id}", "notifications:all"],
        }
        await ws.send_text(json.dumps(cross_req))
        err1 = await ws.receive_json()
        err2 = await ws.receive_json()
        assert err1 == {
            "channel": f"user:{other_id}",
            "code": "NOT_FOUND",
            "req_id": "sub-cross-1",
            "type": "subscribe_error",
        }
        assert err2 == {
            "channel": "notifications:all",
            "code": "NOT_FOUND",
            "req_id": "sub-cross-1",
            "type": "subscribe_error",
        }
        contract_recorder.record_raw("ws_subscribe_cross_user_not_found", cross_req, [err1, err2])

        # Unsubscribe notifications:self removes both notifications:self and user:<maya_id>
        unsub_req = {
            "op": "unsubscribe",
            "req_id": "unsub-self-1",
            "channels": ["notifications:self"],
        }
        await ws.send_text(json.dumps(unsub_req))
        unsub_ack = await ws.receive_json()
        assert unsub_ack == {
            "channels": ["notifications:self"],
            "req_id": "unsub-self-1",
            "type": "unsubscribe_ack",
        }
        assert "notifications:self" not in maya_conns[0].subscribed_channels
        assert f"user:{maya_id}" not in maya_conns[0].subscribed_channels

        # Subscribe directly to user:<maya_id> and unsubscribe via user:<maya_id>
        await ws.send_text(
            json.dumps(
                {"op": "subscribe", "req_id": "sub-direct-1", "channels": [f"user:{maya_id}"]}
            )
        )
        ack_direct = await ws.receive_json()
        assert ack_direct["type"] == "subscribe_ack"
        assert f"user:{maya_id}" in maya_conns[0].subscribed_channels

        await ws.send_text(
            json.dumps(
                {"op": "unsubscribe", "req_id": "unsub-direct-1", "channels": [f"user:{maya_id}"]}
            )
        )
        unsub_direct = await ws.receive_json()
        assert unsub_direct["type"] == "unsubscribe_ack"
        assert f"user:{maya_id}" not in maya_conns[0].subscribed_channels


@pytest.mark.asyncio
async def test_shared_channel_leak_regression_and_multi_tab_fanout(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Verify notification.* events deliver ONLY to recipient and never leak on shared channels."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    ws_id = fixtures["ws_id"]
    maya_id = fixtures["maya_id"]
    other_id = fixtures["other_id"]
    proj_id = fixtures["proj_id"]
    issue_id = fixtures["issue_id"]

    app, hub = build_realtime_test_app(factory, session_service)
    maya_sess = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    other_sess = await create_auth_session(
        factory, session_service, principal_id=other_id, workspace_id=ws_id
    )

    async with (
        AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_sess.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws_maya_tab1,
        AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_sess.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws_maya_tab2,
        AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={other_sess.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws_other,
    ):
        # Maya Tab 1 subscribes to notifications:self + shared workspace/project/issue channels
        shared_plus_self = [
            f"workspace:{ws_id}",
            f"project:{proj_id}",
            "project:KAN",
            f"issue:{issue_id}",
            "issue:KAN-1",
            "notifications:self",
        ]
        await ws_maya_tab1.send_text(
            json.dumps({"op": "subscribe", "req_id": "m1", "channels": shared_plus_self})
        )
        assert (await ws_maya_tab1.receive_json())["type"] == "subscribe_ack"

        # Maya Tab 2 subscribes ONLY to canonical user:<maya_id>
        await ws_maya_tab2.send_text(
            json.dumps({"op": "subscribe", "req_id": "m2", "channels": [f"user:{maya_id}"]})
        )
        assert (await ws_maya_tab2.receive_json())["type"] == "subscribe_ack"

        # Other user (also holding VIEW on project & issue) subscribes to ALL shared channels
        # PLUS their own notifications:self
        await ws_other.send_text(
            json.dumps({"op": "subscribe", "req_id": "o1", "channels": shared_plus_self})
        )
        assert (await ws_other.receive_json())["type"] == "subscribe_ack"

        ctx = RLSContext(principal_id=fixtures["admin_id"], workspace_id=ws_id, aal_level=1)
        notif_id = uuid.uuid4()
        async with factory.session(ctx) as session:
            # 1. Dispatch notification.created for Maya (bound to proj_id and issue_id)
            env_created = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=701,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="notification.created",
                payload={
                    "topic": "notification.created",
                    "recipient_principal_id": str(maya_id),
                    "notification_id": str(notif_id),
                },
                created_at=datetime.now(UTC),
            )
            await hub.dispatch_envelope(session, env_created)

            msg_m1 = await ws_maya_tab1.receive_json(timeout_seconds=2.0)
            msg_m2 = await ws_maya_tab2.receive_json(timeout_seconds=2.0)
            assert msg_m1["type"] == "event"
            assert msg_m1["topic"] == "notification.created"
            assert msg_m1["channel"] == "notifications:self"
            assert msg_m1["payload"]["notification_id"] == str(notif_id)
            assert msg_m2["type"] == "event"
            assert msg_m2["topic"] == "notification.created"
            assert msg_m2["channel"] == f"user:{maya_id}"
            contract_recorder.record_raw("ws_notification_created_frame", {"seq": 701}, msg_m1)

            # Other user MUST receive 0 frames
            with pytest.raises(TimeoutError):
                await ws_other.receive_json(timeout_seconds=0.25)

            # 2. Dispatch notification.read for Maya (project_id=None, object_id=None)
            env_read = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=702,
                workspace_id=ws_id,
                project_id=None,
                object_id=None,
                topic="notification.read",
                payload={
                    "topic": "notification.read",
                    "recipient_principal_id": str(maya_id),
                    "notification_id": str(notif_id),
                },
                created_at=datetime.now(UTC),
            )
            await hub.dispatch_envelope(session, env_read)

            read_m1 = await ws_maya_tab1.receive_json(timeout_seconds=2.0)
            read_m2 = await ws_maya_tab2.receive_json(timeout_seconds=2.0)
            assert read_m1["topic"] == "notification.read"
            assert read_m1["channel"] == "notifications:self"
            assert read_m2["topic"] == "notification.read"
            assert read_m2["channel"] == f"user:{maya_id}"
            contract_recorder.record_raw("ws_notification_read_frame", {"seq": 702}, read_m1)

            with pytest.raises(TimeoutError):
                await ws_other.receive_json(timeout_seconds=0.25)

            # 3. Dispatch notification.read_all for Maya (project_id=None, object_id=None)
            env_read_all = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=703,
                workspace_id=ws_id,
                project_id=None,
                object_id=None,
                topic="notification.read_all",
                payload={
                    "topic": "notification.read_all",
                    "recipient_principal_id": str(maya_id),
                    "marked_count": 3,
                },
                created_at=datetime.now(UTC),
            )
            await hub.dispatch_envelope(session, env_read_all)

            ra_m1 = await ws_maya_tab1.receive_json(timeout_seconds=2.0)
            ra_m2 = await ws_maya_tab2.receive_json(timeout_seconds=2.0)
            assert ra_m1["topic"] == "notification.read_all"
            assert ra_m1["payload"]["marked_count"] == 3
            assert ra_m2["topic"] == "notification.read_all"
            contract_recorder.record_raw("ws_notification_read_all_frame", {"seq": 703}, ra_m1)

            with pytest.raises(TimeoutError):
                await ws_other.receive_json(timeout_seconds=0.25)


@pytest.mark.asyncio
async def test_notification_live_dispatch_requires_user_channel_and_enforces_view_and_workspace(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test notification.* never routes via project/issue/workspace and checks VIEW/workspace."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    ws_id = fixtures["ws_id"]
    admin_id = fixtures["admin_id"]
    maya_id = fixtures["maya_id"]
    proj_id = fixtures["proj_id"]
    issue_id = fixtures["issue_id"]

    hub = RealtimeHub(session_factory=factory)

    # 1. Maya connected in ws_id subscribed ONLY to workspace/project/issue (not notifications:self)
    ws_shared_only = MockWebSocket()
    conn_shared_only = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=ws_shared_only,  # type: ignore[arg-type]
        workspace_id=ws_id,
        principal_id=maya_id,
        session_id=uuid.uuid4(),
        subscribed_channels={
            f"workspace:{ws_id}",
            f"project:{proj_id}",
            f"issue:{issue_id}",
        },
    )
    await hub.register_connection(conn_shared_only)

    # 2. Same principal connected in a DIFFERENT workspace (ws_2) subscribed to notifications:self
    ws_other_workspace = MockWebSocket()
    conn_other_ws = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=ws_other_workspace,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        principal_id=maya_id,
        session_id=uuid.uuid4(),
        subscribed_channels={"notifications:self", f"user:{maya_id}"},
    )
    await hub.register_connection(conn_other_ws)

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        env = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=801,
            workspace_id=ws_id,
            project_id=proj_id,
            object_id=issue_id,
            topic="notification.created",
            payload={
                "topic": "notification.created",
                "recipient_principal_id": str(maya_id),
                "notification_id": str(uuid.uuid4()),
            },
            created_at=datetime.now(UTC),
        )
        await hub.dispatch_envelope(session, env)
        assert ws_shared_only.sent_texts == []
        assert ws_other_workspace.sent_texts == []

        # 3. Malformed or missing recipient_principal_id delivers 0 frames
        conn_shared_only.subscribed_channels.add("notifications:self")
        for bad_payload in ({}, {"recipient_principal_id": "invalid-uuid"}):
            bad_env = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=802,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="notification.created",
                payload=bad_payload,
                created_at=datetime.now(UTC),
            )
            await hub.dispatch_envelope(session, bad_env)
        assert ws_shared_only.sent_texts == []

        # 4. Post-commit VIEW revocation on issue_id suppresses notification.created delivery
        # without revoking notifications:self channel
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = :deny "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"deny": Capability.VIEW.value, "oid": issue_id, "pid": maya_id},
        )
        await hub.dispatch_envelope(session, env)
        assert ws_shared_only.sent_texts == []
        assert "notifications:self" in conn_shared_only.subscribed_channels


@pytest.mark.asyncio
async def test_replay_and_sse_notification_recipient_isolation(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
    contract_recorder: ContractRecorder,
) -> None:
    """Test OutboxReplayer and SSE /sse Last-Event-ID replay enforce recipient & VIEW isolation."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    ws_id = fixtures["ws_id"]
    admin_id = fixtures["admin_id"]
    maya_id = fixtures["maya_id"]
    other_id = fixtures["other_id"]
    proj_id = fixtures["proj_id"]
    issue_id = fixtures["issue_id"]

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    notif1_id = uuid.uuid4()
    async with factory.session(ctx) as session:
        ins_stmt = text(
            "INSERT INTO outbox_events "
            "(id, workspace_id, project_id, object_id, topic, payload, created_at) "
            "VALUES (:id, :ws_id, :pid, :oid, :topic, CAST(:payload AS jsonb), :created_at) "
            "RETURNING seq"
        )
        now = datetime.now(UTC)
        # Anchor event seq0
        s0 = int(
            (
                await session.execute(
                    ins_stmt,
                    {
                        "created_at": now,
                        "id": uuid.uuid4(),
                        "oid": issue_id,
                        "payload": json.dumps({"issue_key": "KAN-1"}),
                        "pid": proj_id,
                        "topic": "issue.updated",
                        "ws_id": ws_id,
                    },
                )
            ).scalar_one()
        )
        # s1: notification.created for Maya
        s1 = int(
            (
                await session.execute(
                    ins_stmt,
                    {
                        "created_at": now,
                        "id": uuid.uuid4(),
                        "oid": issue_id,
                        "payload": json.dumps(
                            {
                                "notification_id": str(notif1_id),
                                "recipient_principal_id": str(maya_id),
                                "topic": "notification.created",
                            }
                        ),
                        "pid": proj_id,
                        "topic": "notification.created",
                        "ws_id": ws_id,
                    },
                )
            ).scalar_one()
        )
        # s2: notification.read for Maya
        s2 = int(
            (
                await session.execute(
                    ins_stmt,
                    {
                        "created_at": now,
                        "id": uuid.uuid4(),
                        "oid": None,
                        "payload": json.dumps(
                            {
                                "notification_id": str(notif1_id),
                                "recipient_principal_id": str(maya_id),
                                "topic": "notification.read",
                            }
                        ),
                        "pid": None,
                        "topic": "notification.read",
                        "ws_id": ws_id,
                    },
                )
            ).scalar_one()
        )
        # s3: notification.read_all for Maya
        s3 = int(
            (
                await session.execute(
                    ins_stmt,
                    {
                        "created_at": now,
                        "id": uuid.uuid4(),
                        "oid": None,
                        "payload": json.dumps(
                            {
                                "marked_count": 2,
                                "recipient_principal_id": str(maya_id),
                                "topic": "notification.read_all",
                            }
                        ),
                        "pid": None,
                        "topic": "notification.read_all",
                        "ws_id": ws_id,
                    },
                )
            ).scalar_one()
        )
        # s4: malformed notification row (missing recipient_principal_id)
        _ = int(
            (
                await session.execute(
                    ins_stmt,
                    {
                        "created_at": now,
                        "id": uuid.uuid4(),
                        "oid": None,
                        "payload": json.dumps({"topic": "notification.read_all"}),
                        "pid": None,
                        "topic": "notification.read_all",
                        "ws_id": ws_id,
                    },
                )
            ).scalar_one()
        )

    replayer = OutboxReplayer()
    async with factory.session(ctx) as session:
        # 1. Other user replaying with workspace, project, issue, and notifications:self gets 0
        res_other = await replayer.replay_events(
            session,
            workspace_id=ws_id,
            principal_id=other_id,
            channels=[
                f"workspace:{ws_id}",
                f"project:{proj_id}",
                f"issue:{issue_id}",
                "notifications:self",
                f"user:{other_id}",
            ],
            last_event_id=s0,
        )
        assert res_other.resync_required is False
        assert res_other.events == []

        # 2. Maya replaying ONLY on workspace/project/issue (without notifications:self) gets 0
        res_maya_shared = await replayer.replay_events(
            session,
            workspace_id=ws_id,
            principal_id=maya_id,
            channels=[f"workspace:{ws_id}", f"project:{proj_id}", f"issue:{issue_id}"],
            last_event_id=s0,
        )
        assert res_maya_shared.events == []

        # 3. Maya replaying on notifications:self gets s1, s2, s3
        res_maya_self = await replayer.replay_events(
            session,
            workspace_id=ws_id,
            principal_id=maya_id,
            channels=["notifications:self", f"user:{maya_id}"],
            last_event_id=s0,
        )
        assert [int(e.event_id) for e in res_maya_self.events] == [s1, s2, s3]
        assert all(e.channel == "notifications:self" for e in res_maya_self.events)

        # 4. Maya replaying on canonical user:<maya_id> only gets s1, s2, s3 with user:<maya_id>
        res_maya_user = await replayer.replay_events(
            session,
            workspace_id=ws_id,
            principal_id=maya_id,
            channels=[f"user:{maya_id}"],
            last_event_id=s0,
        )
        assert [int(e.event_id) for e in res_maya_user.events] == [s1, s2, s3]
        assert all(e.channel == f"user:{maya_id}" for e in res_maya_user.events)

        # 5. Revoking Maya's VIEW on issue_id filters out s1 (notification.created) during replay
        # while still replaying s2 and s3 (notification.read / read_all)
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = :deny "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"deny": Capability.VIEW.value, "oid": issue_id, "pid": maya_id},
        )
        res_maya_revoked = await replayer.replay_events(
            session,
            workspace_id=ws_id,
            principal_id=maya_id,
            channels=["notifications:self"],
            last_event_id=s0,
        )
        assert [int(e.event_id) for e in res_maya_revoked.events] == [s2, s3]

        # Restore VIEW for SSE replay check
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = 0 "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"oid": issue_id, "pid": maya_id},
        )

    # 6. End-to-end SSE /sse?channels=notifications:self&last_event_id=<s0> replay
    app, _ = build_realtime_test_app(factory, session_service)
    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    async with AsyncSSETestClient(
        app,
        f"/sse?channels=notifications:self,user:{other_id}&last_event_id={s0}",
        headers={"Cookie": f"__Host-kb_session={maya_session.cookie_val}"},
    ) as sse_client:
        assert sse_client.status_code == 200
        ev1 = await sse_client.read_event()
        ev2 = await sse_client.read_event()
        ev3 = await sse_client.read_event()
        assert [int(ev1["id"]), int(ev2["id"]), int(ev3["id"])] == [s1, s2, s3]
        assert ev1["event"] == "notification.created"
        assert ev2["event"] == "notification.read"
        assert ev3["event"] == "notification.read_all"
        contract_recorder.record_raw(
            "sse_notifications_self_replay",
            {"url": f"/sse?channels=notifications:self&last_event_id={s0}"},
            [ev1, ev2, ev3],
        )


def test_replayer_match_channel_notification_edge_cases() -> None:
    """Test OutboxReplayer._match_notification_channel defensive branches."""
    ws_id = uuid.uuid4()
    pid = uuid.uuid4()
    chans = {"notifications:self", f"user:{pid}", f"workspace:{ws_id}"}

    # Missing principal_id or non-dict payload
    assert OutboxReplayer._match_notification_channel(chans, None, pid) is None
    assert OutboxReplayer._match_notification_channel(chans, {}, None) is None
    # Invalid recipient UUID
    assert (
        OutboxReplayer._match_notification_channel(
            chans, {"recipient_principal_id": "bad-uuid"}, pid
        )
        is None
    )

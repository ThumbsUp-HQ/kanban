# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""End-to-end integration tests for the realtime board and view refresh pipeline (KAN-35).

Validates the full pipeline:
- Non-admin MEMBER / AGENT mutations -> Activity -> Outbox -> Relay -> Broker -> Hub -> WS/SSE
- Subscriptions on human-readable keys (project:KAN, issue:KAN-1, workspace:stickies) and UUIDs
- Negative authorization: unauthorized principals receive 0 frames
- Anti-harvesting: unknown or unauthorized channels return 404 NOT_FOUND (never 403)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from database.outbox.broker import OutboxEnvelope
from database.outbox.relay import OutboxRelay
from database.session import RLSContext, RLSSessionFactory
from kanban.app import create_app
from kanban.realtime.hub import RealtimeHub
from kanban.services.activity import ActivityEventType, record_activity
from kanban.settings import Settings
from kanban.tests.realtime.conftest import (
    AsyncSSETestClient,
    AsyncWebSocketTestClient,
    create_auth_session,
    create_realtime_test_fixtures,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.auth.sessions.service import SessionService


class InMemoryBroker:
    """In-memory RealtimeBroker implementation for testing."""

    def __init__(self) -> None:
        """Initialize in-memory queue."""
        self.queue: asyncio.Queue[OutboxEnvelope] = asyncio.Queue()

    async def publish(self, event: OutboxEnvelope) -> None:
        """Publish event to in-memory queue."""
        await self.queue.put(event)

    async def subscribe(self, topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        """Subscribe and yield events from in-memory queue."""
        del topic_pattern
        while True:
            item = await self.queue.get()
            yield item

    async def close(self) -> None:
        """Close broker resources."""


def _build_test_app_with_broker(
    factory: RLSSessionFactory,
    service: SessionService,
    broker: InMemoryBroker,
) -> tuple[FastAPI, RealtimeHub]:
    """Create test FastAPI application with configured session factory, broker, and hub."""
    settings = Settings(
        deployment_mode="production",
        public_base_url="https://kanban.example",
        standalone_cleartext_hosts=frozenset({"localhost", "127.0.0.1", "testserver"}),
    )
    app = create_app(settings)
    app.state.session_factory = factory
    app.state.session_service = service
    app.state.broker = broker

    realtime_hub = RealtimeHub(
        broker=broker,
        session_factory=factory,
        session_service=service,
        ping_interval_s=60.0,
    )
    app.state.realtime_hub = realtime_hub
    return app, realtime_hub


async def _recv_event(ws: AsyncWebSocketTestClient, expected_topic: str) -> dict[str, Any]:
    """Receive WebSocket messages ignoring pings and other topics until target event arrives."""
    for _ in range(10):
        msg = await ws.receive_json(timeout_seconds=3.0)
        if msg.get("type") == "event" and msg.get("topic") == expected_topic:
            return msg
    err_msg = f"Timed out waiting for event topic: {expected_topic}"
    raise AssertionError(err_msg)


@pytest.mark.asyncio
async def test_e2e_pipeline_non_admin_member_mutation_outbox_relay_hub_websocket(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test full pipeline: Non-admin MEMBER mutation -> Outbox -> Relay -> Broker -> Hub -> WS."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]
    issue_id = fixture_data["issue_id"]

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )

    try:
        async with AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws:
            # 1. Subscribe to human-readable project key
            await ws.send_text(
                json.dumps(
                    {
                        "channels": ["project:KAN"],
                        "op": "subscribe",
                        "req_id": "sub-kan",
                    }
                )
            )
            ack = await ws.receive_json()
            assert ack["type"] == "subscribe_ack"
            assert "project:KAN" in ack["channels"]

            # 2. Non-admin MEMBER (Maya) performs mutation triggering activity
            ctx = RLSContext(principal_id=maya_id, workspace_id=ws_id, aal_level=1)
            async with factory.session(ctx) as session:
                await record_activity(
                    session,
                    workspace_id=ws_id,
                    object_id=issue_id,
                    actor_principal_id=maya_id,
                    event_type=ActivityEventType.ISSUE_STATE_CHANGED,
                    payload={"from_state": "TODO", "to_state": "IN_PROGRESS"},
                )
                await session.commit()

            # 3. Verify OutboxEvent row exists in outbox_events table
            async with factory.session(ctx) as session:
                res = await session.execute(
                    text("SELECT COUNT(*) FROM outbox_events WHERE topic = 'issue.transitioned'")
                )
                count = res.scalar()
                assert count is not None
                assert count >= 1

            # 4. OutboxRelay claims and drains pending outbox batch into broker
            relay = OutboxRelay(
                engine=pg_worker_db,
                listen_dsn=str(pg_worker_db.url),
                broker=broker,
            )
            drained = await relay.drain_once()
            assert drained >= 1

            # 5. Connected WebSocket client receives dispatched event
            event_msg = await _recv_event(ws, "issue.transitioned")
            assert event_msg["type"] == "event"
            assert event_msg["topic"] == "issue.transitioned"
            assert event_msg["channel"] == "project:KAN"
            assert event_msg["payload"]["to_state"] == "IN_PROGRESS"
            assert event_msg["payload"]["issue_key"] == "KAN-1"
    finally:
        await hub.drain()


@pytest.mark.asyncio
async def test_e2e_pipeline_non_admin_agent_mutation_outbox_relay_hub_sse(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test full pipeline: Non-admin AGENT mutation -> Outbox -> Relay -> Broker -> Hub -> SSE."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    agent_id = uuid.uuid4()
    admin_ctx = RLSContext(principal_id=fixture_data["admin_id"], workspace_id=ws_id, aal_level=1)
    async with factory.session(admin_ctx) as session:
        # Create AGENT principal
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'AGENT', :ws_id, 'Test Agent', 'ACTIVE')"
            ),
            {"id": agent_id, "ws_id": ws_id},
        )
        # Grant agent MEMBER role on project
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :pid, 'MEMBER'::rbac_role, 'project', :proj_id)"
            ),
            {"id": uuid.uuid4(), "pid": agent_id, "proj_id": proj_id, "ws_id": ws_id},
        )
        await session.commit()

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    agent_session = await create_auth_session(
        factory, session_service, principal_id=agent_id, workspace_id=ws_id
    )

    try:
        async with AsyncSSETestClient(
            app,
            path="/sse?channel=project:KAN",
            headers={
                "Cookie": f"__Host-kb_session={agent_session.cookie_val}",
            },
        ) as sse:
            # Connect and verify 200 OK stream start
            assert sse.status_code == 200

            # Agent performs mutation
            agent_ctx = RLSContext(principal_id=agent_id, workspace_id=ws_id, aal_level=1)
            async with factory.session(agent_ctx) as session:
                await record_activity(
                    session,
                    workspace_id=ws_id,
                    object_id=issue_id,
                    actor_principal_id=agent_id,
                    event_type=ActivityEventType.ISSUE_RANK_MOVED,
                    payload={"old_rank": "0|hzzzzz:", "new_rank": "0|i00000:"},
                )
                await session.commit()

            # Drain outbox via relay
            relay = OutboxRelay(
                engine=pg_worker_db,
                listen_dsn=str(pg_worker_db.url),
                broker=broker,
            )
            drained = await relay.drain_once()
            assert drained >= 1

            # Read SSE frame
            data = None
            for _ in range(10):
                frame = await sse.read_event(timeout_seconds=3.0)
                if frame.get("event") == "issue.moved":
                    data = json.loads(frame.get("data", "{}"))
                    break
            assert data is not None
            assert data.get("topic") == "issue.moved"
            assert data.get("channel") == "project:KAN"
            assert data.get("payload", {}).get("new_rank") == "0|i00000:"
    finally:
        await hub.drain()


@pytest.mark.asyncio
async def test_e2e_pipeline_uuid_channel_subscription(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test WebSocket subscription on canonical UUID channels (project:<UUID> and issue:<UUID>)."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )

    try:
        async with AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws:
            # Subscribe using UUID formats
            await ws.send_text(
                json.dumps(
                    {
                        "channels": [f"project:{proj_id}", f"issue:{issue_id}"],
                        "op": "subscribe",
                        "req_id": "sub-uuids",
                    }
                )
            )
            ack = await ws.receive_json()
            assert ack["type"] == "subscribe_ack"
            assert f"project:{proj_id}" in ack["channels"]
            assert f"issue:{issue_id}" in ack["channels"]

            # Dispatch envelope directly to test delivery resolution
            envelope = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=101,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="issue.updated",
                payload={"title": "Updated Title", "issue_key": "KAN-1", "project_key": "KAN"},
                created_at=datetime.now(UTC),
            )
            await broker.publish(envelope)

            msg = await _recv_event(ws, "issue.updated")
            assert msg["type"] == "event"
            assert msg["topic"] == "issue.updated"
            assert msg["payload"]["title"] == "Updated Title"
    finally:
        await hub.drain()


@pytest.mark.asyncio
async def test_e2e_pipeline_negative_unauthorized_candidate_zero_frames(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test negative RLS gate: unauthorized principal receives 0 frames upon event dispatch."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    # Create a separate user with NO access to proj_id
    unauth_id = uuid.uuid4()
    admin_ctx = RLSContext(principal_id=fixture_data["admin_id"], workspace_id=ws_id, aal_level=1)
    async with factory.session(admin_ctx) as session:
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Unauthorized User', 'ACTIVE')"
            ),
            {"id": unauth_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, 'Unauthorized', :aid, :uid)"
            ),
            {
                "aid": fixture_data["admin_id"],
                "ckey": f"usr-{unauth_id.hex}",
                "uid": unauth_id,
                "ws_id": ws_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'unauth@example.com')"
            ),
            {"id": unauth_id, "ws_id": ws_id},
        )
        await session.commit()

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )
    unauth_session = await create_auth_session(
        factory, session_service, principal_id=unauth_id, workspace_id=ws_id
    )

    try:
        async with (
            AsyncWebSocketTestClient(
                app,
                headers={
                    "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                    "Origin": "https://kanban.example",
                },
            ) as ws_maya,
            AsyncWebSocketTestClient(
                app,
                headers={
                    "Cookie": f"__Host-kb_session={unauth_session.cookie_val}",
                    "Origin": "https://kanban.example",
                },
            ) as ws_unauth,
        ):
            # Maya subscribes to project:KAN
            await ws_maya.send_text(
                json.dumps({"channels": ["project:KAN"], "op": "subscribe", "req_id": "sub-1"})
            )
            ack_maya = await ws_maya.receive_json()
            assert ack_maya["type"] == "subscribe_ack"

            # Unauth user attempts to subscribe to workspace channel
            await ws_unauth.send_text(
                json.dumps(
                    {"channels": [f"workspace:{ws_id}"], "op": "subscribe", "req_id": "sub-2"}
                )
            )
            ack_unauth = await ws_unauth.receive_json()
            assert ack_unauth["type"] == "subscribe_ack"

            # Dispatch project/issue event
            envelope = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=501,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="issue.transitioned",
                payload={"issue_key": "KAN-1", "project_key": "KAN", "to_state": "DONE"},
                created_at=datetime.now(UTC),
            )
            await broker.publish(envelope)

            # Maya receives the event
            maya_event = await _recv_event(ws_maya, "issue.transitioned")
            assert maya_event["type"] == "event"
            assert maya_event["topic"] == "issue.transitioned"

            # Unauth user must receive 0 frames (timeout waiting for message)
            with pytest.raises(TimeoutError):
                await ws_unauth.receive_json(timeout_seconds=0.5)
    finally:
        await hub.drain()


@pytest.mark.asyncio
async def test_e2e_pipeline_anti_harvesting_not_found(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test anti-harvesting 404-not-403: unknown or unauthorized channels return NOT_FOUND error."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )

    try:
        # 1. WebSocket subscribe error
        async with AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws:
            await ws.send_text(
                json.dumps(
                    {
                        "channels": ["project:DOESNOTEXIST"],
                        "op": "subscribe",
                        "req_id": "sub-invalid",
                    }
                )
            )
            msg = await ws.receive_json()
            assert msg["type"] == "subscribe_error"
            assert msg["code"] == "NOT_FOUND"

        # 2. SSE silently omits non-existent/unauthorized channel (anti-enumeration)
        async with AsyncSSETestClient(
            app,
            path="/sse?channel=project:DOESNOTEXIST",
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
            },
        ) as sse:
            assert sse.status_code == 200
            active_conns = hub.get_user_connections(ws_id, maya_id)
            assert len(active_conns) == 1
            assert "project:DOESNOTEXIST" not in active_conns[0].subscribed_channels
    finally:
        await hub.drain()


@pytest.mark.asyncio
async def test_e2e_pipeline_stickies_and_comments_events(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test stickies and comment events delivered on workspace:stickies and issue channels."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]
    issue_id = fixture_data["issue_id"]

    admin_ctx = RLSContext(principal_id=fixture_data["admin_id"], workspace_id=ws_id, aal_level=1)
    async with factory.session(admin_ctx) as session:
        # Grant Maya WORKSPACE_MEMBER role for workspace-level stickies VIEW capability
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :pid, 'WORKSPACE_MEMBER'::rbac_role, 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "pid": maya_id, "ws_id": ws_id},
        )
        await session.commit()

    broker = InMemoryBroker()
    app, hub = _build_test_app_with_broker(factory, session_service, broker)
    await hub.start()

    maya_session = await create_auth_session(
        factory, session_service, principal_id=maya_id, workspace_id=ws_id
    )

    try:
        async with AsyncWebSocketTestClient(
            app,
            headers={
                "Cookie": f"__Host-kb_session={maya_session.cookie_val}",
                "Origin": "https://kanban.example",
            },
        ) as ws:
            # Subscribe to workspace:stickies and issue:KAN-1
            await ws.send_text(
                json.dumps(
                    {
                        "channels": ["workspace:stickies", "issue:KAN-1"],
                        "op": "subscribe",
                        "req_id": "sub-stickies-comments",
                    }
                )
            )
            ack = await ws.receive_json()
            assert ack["type"] == "subscribe_ack"

            # 1. Dispatch sticky.created (registered in objects)
            sticky_id = uuid.uuid4()
            async with factory.session(admin_ctx) as session:
                await session.execute(
                    text(
                        "SELECT register_object("
                        "'sticky'::object_kind, :ws_id, NULL, :ckey, 'Sticky', :aid, :sid)"
                    ),
                    {
                        "aid": fixture_data["admin_id"],
                        "ckey": f"stk-{sticky_id.hex}",
                        "sid": sticky_id,
                        "ws_id": ws_id,
                    },
                )
                await session.commit()

            envelope_sticky = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=601,
                workspace_id=ws_id,
                project_id=None,
                object_id=sticky_id,
                topic="sticky.created",
                payload={"content": "New sticky note"},
                created_at=datetime.now(UTC),
            )
            await broker.publish(envelope_sticky)

            msg1 = await _recv_event(ws, "sticky.created")
            assert msg1["type"] == "event"
            assert msg1["topic"] == "sticky.created"
            assert msg1["channel"] == "workspace:stickies"

            # 2. Dispatch comment.created
            comment_id = uuid.uuid4()
            envelope_comment = OutboxEnvelope(
                id=uuid.uuid4(),
                seq=602,
                workspace_id=ws_id,
                project_id=proj_id,
                object_id=issue_id,
                topic="comment.created",
                payload={"comment_id": str(comment_id), "issue_key": "KAN-1", "project_key": "KAN"},
                created_at=datetime.now(UTC),
            )
            await broker.publish(envelope_comment)

            msg2 = await _recv_event(ws, "comment.created")
            assert msg2["type"] == "event"
            assert msg2["topic"] == "comment.created"
            assert msg2["channel"] == "issue:KAN-1"
    finally:
        await hub.drain()

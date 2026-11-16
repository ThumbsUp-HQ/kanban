# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and edge-case tests for RealtimeHub, OutboxReplayer, WS, and SSE."""

# ruff: noqa: ARG001, D102, D107, SLF001

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

from database.outbox.broker import OutboxEnvelope
from database.session import RLSContext, RLSSessionFactory
from kanban.api.sse import _resolve_authenticated_session as sse_resolve_session
from kanban.api.ws import (
    WS_CLOSE_FRAME_TOO_LARGE,
    WS_CLOSE_UNAUTHENTICATED,
    is_origin_allowed,
)
from kanban.api.ws import (
    _resolve_authenticated_session as ws_resolve_session,
)
from kanban.auth.sessions.cookies import (
    hash_session_token,
)
from kanban.realtime.hub import WS_CLOSE_DRAINING, RealtimeHub, SSEConnection, WebSocketConnection
from kanban.realtime.replay import OutboxReplayer
from kanban.settings import Settings
from kanban.tests.realtime.conftest import (
    AsyncSSETestClient,
    AsyncWebSocketTestClient,
    build_realtime_test_app,
    create_auth_session,
    create_realtime_test_fixtures,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kanban.auth.sessions.service import SessionService


class MockWebSocket:
    """Mock WebSocket for unit testing WebSocketConnection without full ASGI stack."""

    headers: Headers
    sent_texts: list[str]
    closed_code: int | None
    closed_reason: str | None
    is_closed: bool

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = Headers(headers or {})
        self.sent_texts = []
        self.closed_code = None
        self.closed_reason = None
        self.is_closed = False

    async def send_text(self, data: str) -> None:
        if self.is_closed:
            raise WebSocketDisconnect(1000, "Closed")
        self.sent_texts.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.is_closed = True
        self.closed_code = code
        self.closed_reason = reason


class MockBroker:
    """Mock broker that yields queued envelopes and supports cancellation."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[OutboxEnvelope] = asyncio.Queue()

    async def publish(self, event: OutboxEnvelope) -> None:
        await self.queue.put(event)

    async def subscribe(self, topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        del topic_pattern
        while True:
            item = await self.queue.get()
            yield item

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sse_connection_methods() -> None:
    """Test SSEConnection helper methods."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    s_id = uuid.uuid4()
    obj_id = uuid.uuid4()

    conn = SSEConnection(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        principal_id=p_id,
        session_id=s_id,
    )

    # 1. send_json
    await conn.send_json({"type": "custom", "payload": "hello"})
    msg1 = await conn.queue.get()
    assert msg1 == 'event: custom\ndata: {"payload":"hello","type":"custom"}\n\n'

    # 2. send_heartbeat
    await conn.send_heartbeat()
    msg2 = await conn.queue.get()
    assert msg2 == ": heartbeat\n\n"

    # 3. send_event
    now = datetime.now(UTC)
    env = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=42,
        workspace_id=ws_id,
        project_id=None,
        object_id=obj_id,
        topic="issue.updated",
        payload={"title": "New Title"},
        created_at=now,
    )
    await conn.send_event(env, f"issue:{obj_id}")
    msg3 = await conn.queue.get()
    assert msg3 is not None
    assert "id: 42\nevent: issue.updated\n" in msg3
    assert '"channel":"issue:' in msg3

    # 4. close
    await conn.close(code=1000, reason="Normal")
    msg4 = await conn.queue.get()
    assert msg4 is None

    # 5. Queue full suppression
    tiny_conn = SSEConnection(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        principal_id=p_id,
        session_id=s_id,
    )
    tiny_conn.queue = asyncio.Queue(maxsize=1)
    await tiny_conn.queue.put("full")
    await tiny_conn.send_json({"type": "dropped"})
    await tiny_conn.send_event(env, f"issue:{obj_id}")
    await tiny_conn.send_heartbeat()
    await tiny_conn.close()


@pytest.mark.asyncio
async def test_hub_connection_registration_and_lookup() -> None:
    """Test RealtimeHub registration, connection caps, and unregistration."""
    hub = RealtimeHub()
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()

    mock_ws = MockWebSocket()
    conn1 = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=ws_id,
        principal_id=p_id,
        session_id=uuid.uuid4(),
    )

    # Normal registration
    assert await hub.register_connection(conn1) is True
    assert hub.active_connection_count == 1
    assert hub.get_connection(conn1.id) is conn1
    assert len(hub.get_user_connections(ws_id, p_id)) == 1

    # Nonexistent connection lookup
    assert hub.get_connection(uuid.uuid4()) is None

    # Unregister nonexistent connection
    await hub.unregister_connection(uuid.uuid4())
    assert hub.active_connection_count == 1

    # Unregister existing connection
    await hub.unregister_connection(conn1.id)
    assert hub.active_connection_count == 0
    assert len(hub.get_user_connections(ws_id, p_id)) == 0

    # Registration rejected when draining
    hub._draining = True
    assert await hub.register_connection(conn1) is False


@pytest.mark.asyncio
async def test_hub_channel_viewable_validation(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub.check_channel_viewable validation branches."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub()

    anon_ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(anon_ctx) as session:
        # 1. Invalid channel formats
        assert (
            await hub.check_channel_viewable(
                session, fixtures["ws_id"], fixtures["admin_id"], "invalid_channel"
            )
            is False
        )
        assert (
            await hub.check_channel_viewable(
                session, fixtures["ws_id"], fixtures["admin_id"], "issue:not-a-uuid"
            )
            is False
        )
        assert (
            await hub.check_channel_viewable(
                session, fixtures["ws_id"], fixtures["admin_id"], "issue:abc-def"
            )
            is False
        )

        # 2. Workspace channel
        assert (
            await hub.check_channel_viewable(
                session,
                fixtures["ws_id"],
                fixtures["admin_id"],
                f"workspace:{fixtures['ws_id']}",
            )
            is True
        )
        assert (
            await hub.check_channel_viewable(
                session, fixtures["ws_id"], fixtures["admin_id"], f"workspace:{uuid.uuid4()}"
            )
            is False
        )

        # 3. Nonexistent object in effective_resource_access
        assert (
            await hub.check_channel_viewable(
                session, fixtures["ws_id"], fixtures["admin_id"], f"issue:{uuid.uuid4()}"
            )
            is False
        )


@pytest.mark.asyncio
async def test_hub_unsubscribe_handling() -> None:
    """Test RealtimeHub.handle_unsubscribe frame handling and state updates."""
    hub = RealtimeHub()
    mock_ws = MockWebSocket()
    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        subscribed_channels={"ch1", "ch2", "ch3"},
    )

    await hub.handle_unsubscribe(conn, "req-unsub", ["ch1", "ch3", "ch_nonexistent"])
    assert conn.subscribed_channels == {"ch2"}

    assert len(mock_ws.sent_texts) == 1
    resp = json.loads(mock_ws.sent_texts[0])
    assert resp["type"] == "unsubscribe_ack"
    assert resp["req_id"] == "req-unsub"
    assert sorted(resp["channels"]) == ["ch1", "ch3"]


@pytest.mark.asyncio
async def test_hub_subscribe_with_replay(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub.handle_subscribe with last_event_id replay."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub(session_factory=factory)

    mock_ws = MockWebSocket()
    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=fixtures["ws_id"],
        principal_id=fixtures["admin_id"],
        session_id=uuid.uuid4(),
    )

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )

    # 1. Subscribe with Last-Event-ID when replayer triggers resync_required
    async with factory.session(ctx) as session:
        await session.execute(
            text(
                "INSERT INTO outbox_events (topic, workspace_id, project_id, object_id, payload) "
                "VALUES ('issue.created', :ws_id, :pid, :oid, '{}'::jsonb)"
            ),
            {
                "oid": fixtures["issue_id"],
                "pid": fixtures["proj_id"],
                "ws_id": fixtures["ws_id"],
            },
        )
        await hub.handle_subscribe(
            session,
            conn,
            req_id="sub-1",
            channels=[f"issue:{fixtures['issue_id']}"],
            last_event_id="0",
        )

    assert f"issue:{fixtures['issue_id']}" in conn.subscribed_channels
    assert len(mock_ws.sent_texts) == 2
    ack = json.loads(mock_ws.sent_texts[0])
    assert ack["type"] == "subscribe_ack"
    resync = json.loads(mock_ws.sent_texts[1])
    assert resync["type"] == "resync_required"


@pytest.mark.asyncio
async def test_hub_security_event_handling() -> None:
    """Test RealtimeHub.handle_security_event closes matching sessions or principals."""
    hub = RealtimeHub()
    ws_id = uuid.uuid4()
    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()

    mock_ws1 = MockWebSocket()
    mock_ws2 = MockWebSocket()

    conn1 = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws1,  # type: ignore[arg-type]
        workspace_id=ws_id,
        principal_id=p1,
        session_id=s1,
    )
    conn2 = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws2,  # type: ignore[arg-type]
        workspace_id=ws_id,
        principal_id=p2,
        session_id=s2,
    )

    await hub.register_connection(conn1)
    await hub.register_connection(conn2)

    # Revoke session s1
    env_session = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=1,
        workspace_id=ws_id,
        project_id=None,
        object_id=None,
        topic="security.session_revoked",
        payload={"session_id": str(s1)},
        created_at=datetime.now(UTC),
    )
    await hub.handle_security_event(env_session)

    assert mock_ws1.is_closed is True
    assert mock_ws1.closed_code == WS_CLOSE_UNAUTHENTICATED
    assert mock_ws2.closed_code is None

    # Deactivate principal p2
    env_principal = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=2,
        workspace_id=ws_id,
        project_id=None,
        object_id=None,
        topic="security.principal_deactivated",
        payload={"principal_id": str(p2)},
        created_at=datetime.now(UTC),
    )
    await hub.handle_security_event(env_principal)

    assert mock_ws2.is_closed is True
    assert mock_ws2.closed_code == WS_CLOSE_UNAUTHENTICATED


@pytest.mark.asyncio
async def test_hub_dispatch_envelope_variations(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub.dispatch_envelope channel matching and filtering."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub(session_factory=factory)

    doc_id = uuid.uuid4()
    mock_ws_admin = MockWebSocket()
    conn_admin = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws_admin,  # type: ignore[arg-type]
        workspace_id=fixtures["ws_id"],
        principal_id=fixtures["admin_id"],
        session_id=uuid.uuid4(),
        subscribed_channels={
            f"doc:{doc_id}",
            f"project:{fixtures['proj_id']}",
            f"workspace:{fixtures['ws_id']}",
        },
    )
    await hub.register_connection(conn_admin)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        # 1. Different workspace -> skipped
        other_env = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=1,
            workspace_id=uuid.uuid4(),
            project_id=None,
            object_id=doc_id,
            topic="doc.updated",
            payload={},
            created_at=datetime.now(UTC),
        )
        await hub.dispatch_envelope(session, other_env)
        assert len(mock_ws_admin.sent_texts) == 0

        # 2. Security event routing through dispatch_envelope
        sec_env = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=2,
            workspace_id=fixtures["ws_id"],
            project_id=None,
            object_id=None,
            topic="security.session_revoked",
            payload={"session_id": str(conn_admin.session_id)},
            created_at=datetime.now(UTC),
        )
        await hub.dispatch_envelope(session, sec_env)
        assert mock_ws_admin.is_closed is True


@pytest.mark.asyncio
async def test_hub_drain_and_background_loops() -> None:
    """Test RealtimeHub start, heartbeat, session recheck, and graceful drain."""
    hub = RealtimeHub()
    # Fast intervals for testing
    hub._ping_interval_s = 0.05
    hub._session_check_interval_s = 0.05

    mock_ws = MockWebSocket()
    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    await hub.register_connection(conn)

    # Start loops
    await hub.start()
    # Idempotent start
    await hub.start()

    # Allow heartbeat loop to fire at least once
    await asyncio.sleep(0.08)
    assert any("ping" in text_msg for text_msg in mock_ws.sent_texts)

    # Drain hub
    await hub.drain(timeout_seconds=1.0)
    assert hub.active_connection_count == 0
    assert mock_ws.is_closed is True
    assert mock_ws.closed_code == WS_CLOSE_DRAINING


@pytest.mark.asyncio
async def test_replay_service_unit_edge_cases(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test OutboxReplayer edge cases: invalid IDs, empty channels, retention checks."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    replayer = OutboxReplayer(retention_minutes=30, max_events=2)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        # 1. Invalid last_event_id string
        r1 = await replayer.replay_events(
            session,
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            channels=[f"issue:{fixtures['issue_id']}"],
            last_event_id="invalid",
        )
        assert r1.resync_required is True

        # 2. Negative last_event_id
        r2 = await replayer.replay_events(
            session,
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            channels=[f"issue:{fixtures['issue_id']}"],
            last_event_id=-5,
        )
        assert r2.resync_required is True

        # 3. Empty channels sequence
        r3 = await replayer.replay_events(
            session,
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            channels=[],
            last_event_id="10",
        )
        assert r3.resync_required is False
        assert r3.events == []

        # 4. _match_channel static method tests
        chans = {
            f"issue:{fixtures['issue_id']}",
            "doc:00000000-0000-0000-0000-000000000001",
            f"workspace:{fixtures['ws_id']}",
        }
        assert (
            OutboxReplayer._match_channel(
                chans,
                fixtures["ws_id"],
                None,
                uuid.UUID("00000000-0000-0000-0000-000000000001"),
            )
            == "doc:00000000-0000-0000-0000-000000000001"
        )
        assert (
            OutboxReplayer._match_channel(chans, fixtures["ws_id"], None, None)
            == f"workspace:{fixtures['ws_id']}"
        )
        assert (
            OutboxReplayer._match_channel(chans, uuid.uuid4(), uuid.uuid4(), uuid.uuid4()) is None
        )

        # 5. _check_retention when no rows in retention window
        empty_ws = uuid.uuid4()
        resync, max_seq = await replayer._check_retention(session, empty_ws, 5)
        assert resync is False
        assert max_seq == 5


def test_ws_origin_allowed_unit() -> None:
    """Test is_origin_allowed helper under varied settings and origin values."""
    settings = Settings(
        public_base_url="https://kb.example.com",
        deployment_mode="production",
    )

    # 1. No origin header -> True
    assert is_origin_allowed(None, settings) is True
    assert is_origin_allowed("", settings) is True

    # 2. Localhost / testserver / cleartext hosts -> True
    assert is_origin_allowed("http://localhost:3000", settings) is True
    assert is_origin_allowed("http://testserver", settings) is True

    # 3. Exact host match with correct scheme in production -> True
    assert is_origin_allowed("https://kb.example.com", settings) is True

    # 4. Scheme mismatch in production -> False
    assert is_origin_allowed("http://kb.example.com", settings) is False

    # 5. Host mismatch -> False
    assert is_origin_allowed("https://evil.com", settings) is False

    # 6. Malformed origin
    assert is_origin_allowed("file:///local/path", settings) is False

    # 7. TypeError on non-string origin (hits urlsplit exception)
    assert is_origin_allowed(12345, settings) is False  # type: ignore[arg-type]

    # 8. Standalone same-host origin allowed when block_cleartext_http is False
    standalone_settings = Settings(deployment_mode="standalone")
    assert (
        is_origin_allowed(
            "https://k.hackedyour.info",
            standalone_settings,
            request_host="k.hackedyour.info:443",
        )
        is True
    )
    assert (
        is_origin_allowed(
            "http://192.168.1.101:8921",
            standalone_settings,
            request_host="192.168.1.101:8921",
        )
        is True
    )


@pytest.mark.asyncio
async def test_session_resolution_edge_cases(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test _resolve_authenticated_session failures for WS and SSE endpoints."""
    factory = RLSSessionFactory(pg_worker_db)

    # 1. Missing session_factory or session_service
    assert await ws_resolve_session(None, None, None) is None  # type: ignore[arg-type]
    assert await sse_resolve_session(None, None, None) is None  # type: ignore[arg-type]

    # 2. Invalid cookie or token
    mock_ws = MockWebSocket(headers={"cookie": "bad_cookie=123"})
    assert (
        await ws_resolve_session(
            mock_ws,  # type: ignore[arg-type]
            factory,
            session_service,
        )
        is None
    )

    # 3. Malformed session token format (triggers line 122 parse_session_cookie failure)
    mock_ws2 = MockWebSocket(headers={"cookie": "__Host-kb_session=not-enough-parts"})
    assert await ws_resolve_session(mock_ws2, factory, session_service) is None  # type: ignore[arg-type]

    # 4. SSE session resolution with MFA pending
    fixtures = await create_realtime_test_fixtures(factory)
    ctx = RLSContext(principal_id=fixtures["admin_id"], workspace_id=fixtures["ws_id"], aal_level=1)
    async with factory.session(ctx) as session:
        mfa_session = await session_service.create_after_login(
            session,
            principal_id=fixtures["admin_id"],
            workspace_id=fixtures["ws_id"],
            aal_level=1,
            mfa_pending=True,
        )
    mock_req_mfa = Request(
        scope={
            "type": "http",
            "method": "GET",
            "headers": [
                (b"cookie", f"__Host-kb_session={mfa_session.cookie_val}".encode("latin-1"))
            ],
        }
    )
    assert await sse_resolve_session(mock_req_mfa, factory, session_service) is None


@pytest.mark.asyncio
async def test_ws_frame_parsing_and_error_handling(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test WebSocket frame decoding errors, unknown op, and oversized frames."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    app, _ = build_realtime_test_app(factory, session_service)

    session_obj = await create_auth_session(
        factory,
        session_service,
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
    )
    headers = {"Cookie": f"__Host-kb_session={session_obj.cookie_val}"}

    client = AsyncWebSocketTestClient(app, path="/ws", headers=headers)
    await client.connect()

    # 1. Malformed JSON frame
    await client.send_text("not-json{{{")
    err1 = await client.receive_json()
    assert err1["code"] == "INVALID_JSON"

    # 2. JSON array instead of object
    await client.send_text("[1, 2, 3]")
    err2 = await client.receive_json()
    assert err2["code"] == "INVALID_FRAME"

    # 3. Invalid subscribe schema (missing channels)
    await client.send_text(json.dumps({"op": "subscribe", "req_id": "r1"}))
    err3 = await client.receive_json()
    assert err3["code"] == "INVALID_FRAME"

    # 4. Unknown op
    await client.send_text(json.dumps({"op": "unknown_action", "req_id": "r2"}))
    err4 = await client.receive_json()
    assert err4["code"] == "UNKNOWN_OP"

    # 5. Valid pong frame
    await client.send_text(json.dumps({"op": "pong"}))

    # 6. Invalid unsubscribe schema
    await client.send_text(json.dumps({"op": "unsubscribe", "req_id": "r3"}))
    err5 = await client.receive_json()
    assert err5["code"] == "INVALID_FRAME"

    # 7. Oversized frame (> 4096 bytes) -> triggers WS_CLOSE_FRAME_TOO_LARGE (4413)
    huge_payload = "x" * 5000
    await client.send_text(huge_payload)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        await client.receive_json()
    assert exc_info.value.code == WS_CLOSE_FRAME_TOO_LARGE

    await client.close()


@pytest.mark.asyncio
async def test_hub_broker_listener_loop(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub background broker listener loop receiving and dispatching envelopes."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    broker = MockBroker()
    hub = RealtimeHub(broker=broker, session_factory=factory, session_service=session_service)
    await hub.start()

    mock_ws = MockWebSocket()
    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=fixtures["ws_id"],
        principal_id=fixtures["admin_id"],
        session_id=uuid.uuid4(),
        subscribed_channels={f"workspace:{fixtures['ws_id']}"},
    )
    await hub.register_connection(conn)

    # Queue an envelope in broker
    env = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=101,
        workspace_id=fixtures["ws_id"],
        project_id=None,
        object_id=None,
        topic="workspace.updated",
        payload={"name": "Updated"},
        created_at=datetime.now(UTC),
    )
    await broker.queue.put(env)
    await asyncio.sleep(0.05)

    assert len(mock_ws.sent_texts) == 1
    assert "workspace.updated" in mock_ws.sent_texts[0]

    await hub.drain(timeout_seconds=0.5)


@pytest.mark.asyncio
async def test_hub_heartbeat_loop_with_sse_and_ws() -> None:
    """Test RealtimeHub periodic heartbeat loop sending pings to WS and heartbeats to SSE."""
    hub = RealtimeHub(ping_interval_s=0.02)
    mock_ws = MockWebSocket()
    ws_conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    sse_conn = SSEConnection(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    await hub.register_connection(ws_conn)
    await hub.register_connection(sse_conn)

    await hub.start()
    await asyncio.sleep(0.05)

    # Check WS got ping
    assert any("ping" in m for m in mock_ws.sent_texts)
    # Check SSE got heartbeat
    sse_msg = await sse_conn.queue.get()
    assert sse_msg == ": heartbeat\n\n"

    await hub.drain(0.5)


@pytest.mark.asyncio
async def test_hub_session_recheck_loop(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub background session recheck loop disconnecting revoked sessions."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    session_obj = await create_auth_session(
        factory,
        session_service,
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
    )
    token_sha256 = hash_session_token(session_obj.token)

    hub = RealtimeHub(
        session_factory=factory,
        session_service=session_service,
        session_check_interval_s=0.02,
    )
    mock_ws = MockWebSocket()
    conn = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws,  # type: ignore[arg-type]
        workspace_id=fixtures["ws_id"],
        principal_id=fixtures["admin_id"],
        session_id=session_obj.session_id,
        token_sha256=token_sha256,
    )
    await hub.register_connection(conn)
    await hub.start()

    # Revoke session via session_service.logout
    anon_ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("session",),
        aal_level=1,
    )
    async with factory.session(anon_ctx) as session:
        await session_service.logout(session, session_obj.session_id)

    # Allow session recheck loop to run
    await asyncio.sleep(0.06)

    assert mock_ws.is_closed is True
    assert mock_ws.closed_code == WS_CLOSE_UNAUTHENTICATED
    assert hub.active_connection_count == 0

    await hub.drain(0.5)


@pytest.mark.asyncio
async def test_hub_dispatch_envelope_doc_revocation(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub mid-session permission revocation on doc channel."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub(session_factory=factory, session_service=session_service)

    doc_id = uuid.uuid4()
    mock_ws_maya = MockWebSocket()
    conn_maya = WebSocketConnection(
        id=uuid.uuid4(),
        websocket=mock_ws_maya,  # type: ignore[arg-type]
        workspace_id=fixtures["ws_id"],
        principal_id=fixtures["maya_id"],
        session_id=uuid.uuid4(),
        subscribed_channels={f"doc:{doc_id}", f"project:{fixtures['proj_id']}"},
    )
    await hub.register_connection(conn_maya)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        doc_env = OutboxEnvelope(
            id=uuid.uuid4(),
            seq=201,
            workspace_id=fixtures["ws_id"],
            project_id=fixtures["proj_id"],
            object_id=doc_id,
            topic="doc.updated",
            payload={"title": "Secret Doc"},
            created_at=datetime.now(UTC),
        )
        await hub.dispatch_envelope(session, doc_env)

        assert f"doc:{doc_id}" not in conn_maya.subscribed_channels
        assert len(mock_ws_maya.sent_texts) == 1
        revoked_msg = json.loads(mock_ws_maya.sent_texts[0])
        assert revoked_msg["type"] == "channel.revoked"
        assert revoked_msg["channel"] == f"doc:{doc_id}"


@pytest.mark.asyncio
async def test_hub_subscribe_with_replay_events_dispatch(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub subscribe with replay sending individual missed events."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub(session_factory=factory, session_service=session_service)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        ins_stmt = text(
            "INSERT INTO outbox_events (topic, workspace_id, project_id, object_id, payload) "
            "VALUES ('issue.updated', :ws_id, :pid, :oid, '{\"v\": 1}'::jsonb) "
            "RETURNING seq"
        )
        res1 = await session.execute(
            ins_stmt,
            {
                "oid": fixtures["issue_id"],
                "pid": fixtures["proj_id"],
                "ws_id": fixtures["ws_id"],
            },
        )
        seq1 = int(res1.scalar_one())

        res2 = await session.execute(
            ins_stmt,
            {
                "oid": fixtures["issue_id"],
                "pid": fixtures["proj_id"],
                "ws_id": fixtures["ws_id"],
            },
        )
        seq2 = int(res2.scalar_one())

        mock_ws = MockWebSocket()
        conn = WebSocketConnection(
            id=uuid.uuid4(),
            websocket=mock_ws,  # type: ignore[arg-type]
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            session_id=uuid.uuid4(),
        )

        await hub.handle_subscribe(
            session,
            conn,
            req_id="sub-replay",
            channels=[f"issue:{fixtures['issue_id']}"],
            last_event_id=str(seq1),
        )

        assert len(mock_ws.sent_texts) == 2
        ack = json.loads(mock_ws.sent_texts[0])
        assert ack["type"] == "subscribe_ack"
        replayed = json.loads(mock_ws.sent_texts[1])
        assert replayed["type"] == "event"
        assert replayed["event_id"] == str(seq2)


@pytest.mark.asyncio
async def test_outbox_replayer_retention_and_capacity_edges(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test OutboxReplayer max_events limit and channel matching branches."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    replayer = OutboxReplayer(retention_minutes=30, max_events=2)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        seqs = []
        for _ in range(4):
            res = await session.execute(
                text(
                    "INSERT INTO outbox_events "
                    "(topic, workspace_id, project_id, object_id, payload) "
                    "VALUES ('issue.created', :ws_id, :pid, :oid, '{\"i\": 1}'::jsonb) "
                    "RETURNING seq"
                ),
                {
                    "oid": fixtures["issue_id"],
                    "pid": fixtures["proj_id"],
                    "ws_id": fixtures["ws_id"],
                },
            )
            seqs.append(int(res.scalar_one()))

        # With max_events=2 and 3 events following seqs[0], triggers line 264
        r = await replayer.replay_events(
            session,
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            channels=[f"issue:{fixtures['issue_id']}"],
            last_event_id=seqs[0],
        )
        assert r.resync_required is True

        # Test line 195: event for an object the client did not subscribe to
        replayer_large = OutboxReplayer(retention_minutes=30, max_events=100)
        r2 = await replayer_large.replay_events(
            session,
            workspace_id=fixtures["ws_id"],
            principal_id=fixtures["admin_id"],
            channels=[f"doc:{uuid.uuid4()}"],
            last_event_id=seqs[0],
        )
        assert r2.resync_required is False
        assert len(r2.events) == 0

        assert (
            OutboxReplayer._match_channel(
                {f"issue:{fixtures['issue_id']}"},
                fixtures["ws_id"],
                fixtures["proj_id"],
                fixtures["issue_id"],
            )
            == f"issue:{fixtures['issue_id']}"
        )


@pytest.mark.asyncio
async def test_ws_and_sse_auto_init_and_mfa_pending(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test MFA pending rejection and auto-initialization of RealtimeHub."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)

    # 1. MFA pending session rejects
    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        mfa_session = await session_service.create_after_login(
            session,
            principal_id=fixtures["admin_id"],
            workspace_id=fixtures["ws_id"],
            aal_level=1,
            mfa_pending=True,
        )

    mock_ws = MockWebSocket(headers={"cookie": f"__Host-kb_session={mfa_session.cookie_val}"})
    assert await ws_resolve_session(mock_ws, factory, session_service) is None  # type: ignore[arg-type]

    # 2. Auto-initialize hub when app.state.realtime_hub is None
    app, _ = build_realtime_test_app(factory, session_service)
    app.state.realtime_hub = None

    valid_session = await create_auth_session(
        factory,
        session_service,
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
    )
    client = AsyncWebSocketTestClient(
        app,
        headers={"Cookie": f"__Host-kb_session={valid_session.cookie_val}"},
    )
    await client.connect()
    assert app.state.realtime_hub is not None
    await client.close()
    await app.state.realtime_hub.drain(0.5)

    # 3. SSE auto-initialize hub when app.state.realtime_hub is None
    app.state.realtime_hub = None
    sse_client = AsyncSSETestClient(
        app,
        headers={"Cookie": f"__Host-kb_session={valid_session.cookie_val}"},
    )
    await sse_client.connect()
    assert sse_client.status_code == 200
    assert app.state.realtime_hub is not None
    await sse_client.close()
    await app.state.realtime_hub.drain(0.5)


@pytest.mark.asyncio
async def test_hub_drain_timeout_branch() -> None:
    """Test RealtimeHub drain timeout branch when tasks cannot complete in time."""
    hub = RealtimeHub()
    await hub.start()

    async def hanging_task() -> None:
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            await asyncio.sleep(100)

    # Replace listener task with hanging task
    hub._listener_task = asyncio.create_task(hanging_task())
    await hub.drain(timeout_seconds=0.01)
    hub._listener_task.cancel()


@pytest.mark.asyncio
async def test_hub_check_channel_viewable_allow_and_deny(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test RealtimeHub.check_channel_viewable allow and deny bitmask logic."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    hub = RealtimeHub()

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        # 1. Allowed object (issue KAN-1 viewable by admin)
        assert (
            await hub.check_channel_viewable(
                session,
                fixtures["ws_id"],
                fixtures["admin_id"],
                f"issue:{fixtures['issue_id']}",
            )
            is True
        )

        # 2. Denied object (deny_mask & 1 != 0)
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = 1 "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"oid": fixtures["issue_id"], "pid": fixtures["admin_id"]},
        )
        assert (
            await hub.check_channel_viewable(
                session,
                fixtures["ws_id"],
                fixtures["admin_id"],
                f"issue:{fixtures['issue_id']}",
            )
            is False
        )


@pytest.mark.asyncio
async def test_outbox_replayer_overall_max_retention_branch(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test OutboxReplayer._check_retention overall_max fallback branch."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    replayer = OutboxReplayer(retention_minutes=30)

    ctx = RLSContext(
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
        token_scopes=("realtime",),
        aal_level=1,
    )
    async with factory.session(ctx) as session:
        # Insert event older than 30 minutes
        await session.execute(
            text(
                "INSERT INTO outbox_events "
                "(topic, workspace_id, project_id, object_id, payload, created_at) "
                "VALUES ('issue.aged', :ws_id, :pid, :oid, '{}'::jsonb, "
                "clock_timestamp() - interval '2 hours')"
            ),
            {
                "oid": fixtures["issue_id"],
                "pid": fixtures["proj_id"],
                "ws_id": fixtures["ws_id"],
            },
        )

        # last_seq=0 is less than overall_max, so resync_required=True
        resync, max_seq = await replayer._check_retention(session, fixtures["ws_id"], 0)
        assert resync is True
        assert max_seq > 0


@pytest.mark.asyncio
async def test_ws_additional_frame_handling(
    pg_worker_db: AsyncEngine,
    session_service: SessionService,
) -> None:
    """Test valid unsubscribe op, pong schema rejection, and binary frame bypass."""
    factory = RLSSessionFactory(pg_worker_db)
    fixtures = await create_realtime_test_fixtures(factory)
    app, hub = build_realtime_test_app(factory, session_service)

    valid_session = await create_auth_session(
        factory,
        session_service,
        principal_id=fixtures["admin_id"],
        workspace_id=fixtures["ws_id"],
    )
    client = AsyncWebSocketTestClient(
        app,
        headers={"Cookie": f"__Host-kb_session={valid_session.cookie_val}"},
    )
    await client.connect()

    # 1. Valid unsubscribe op
    await client.send_text(
        json.dumps({"channels": ["ch1"], "op": "unsubscribe", "req_id": "unsub-1"})
    )
    res1 = await client.receive_json()
    assert res1["type"] == "unsubscribe_ack"

    # 2. Invalid pong schema (fails validation, ignored)
    await client.send_text(json.dumps({"extra": 123, "op": "pong"}))

    # 3. Binary frame with text=None
    await client.in_q.put({"bytes": b"binary", "text": None, "type": "websocket.receive"})

    # 4. Valid subscribe op
    await client.send_text(
        json.dumps(
            {
                "channels": [f"issue:{fixtures['issue_id']}"],
                "op": "subscribe",
                "req_id": "sub-1",
            }
        )
    )
    res2 = await client.receive_json()
    assert res2["type"] == "subscribe_ack"

    await client.close()
    await hub.drain(0.5)

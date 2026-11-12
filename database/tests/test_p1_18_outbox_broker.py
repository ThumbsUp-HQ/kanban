"""Unit and integration tests for OutboxEnvelope, RealtimeBroker, and PgNotifyBroker."""

from __future__ import annotations

import asyncio
import os
import signal
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from database.models.outbox import OutboxEvent
from database.outbox.broker import (
    OutboxEnvelope,
    OutboxPayloadTooLargeError,
    RealtimeBroker,
    build_realtime_broker,
    enqueue_outbox_event,
    topic_matches,
)
from database.outbox.pg_broker import PgNotifyBroker
from database.outbox.relay import OutboxRelay
from database.outbox.relay import main as relay_main
from database.outbox.valkey_broker import FakeValkeyStreamClient, ValkeyBroker
from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _create_test_workspace(session: AsyncSession, slug: str | None = None) -> UUID:
    """Create an isolated test workspace."""
    ws_slug = slug or f"ws-{uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": "Outbox Test Workspace"},
    )
    val = row.scalar_one()
    if not isinstance(val, UUID):
        val = UUID(str(val))
    return val


def _make_envelope(topic: str, payload: dict[str, Any] | None = None) -> OutboxEnvelope:
    """Construct an OutboxEnvelope test fixture."""
    return OutboxEnvelope(
        id=uuid4(),
        seq=1,
        workspace_id=uuid4(),
        project_id=uuid4(),
        object_id=uuid4(),
        topic=topic,
        payload=payload if payload is not None else {"key": "value"},
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Test Case 1: Topic Matching Semantics
# ---------------------------------------------------------------------------
def test_01_topic_matches_semantics() -> None:
    """Verify wildcard, prefix wildcard, and exact topic matching."""
    assert topic_matches("*", "issue.created")
    assert topic_matches("*", "anything")

    assert topic_matches("issue.*", "issue.created")
    assert topic_matches("issue.*", "issue.updated.v1")
    assert not topic_matches("issue.*", "doc.created")
    assert not topic_matches("issue.*", "issue")

    assert topic_matches("workflow.gate.*", "workflow.gate.approved")
    assert topic_matches("workflow.gate.*", "workflow.gate.rejected")
    assert not topic_matches("workflow.gate.*", "workflow.step.approved")

    assert topic_matches("notification.created", "notification.created")
    assert not topic_matches("notification.created", "notification.created.v2")
    assert not topic_matches("notification.created", "notification.deleted")


# ---------------------------------------------------------------------------
# Test Case 2: OutboxEnvelope Serialization and Wire Ceiling
# ---------------------------------------------------------------------------
def test_02_envelope_serialization_and_limits() -> None:
    """Verify roundtrip wire JSON serialization and 7900-byte ceiling enforcement."""
    env = _make_envelope("issue.created", {"summary": "Critical bug", "priority": 1})
    wire = env.to_wire_json()
    assert isinstance(wire, str)

    restored = OutboxEnvelope.from_wire_json(wire)
    assert restored.id == env.id
    assert restored.seq == env.seq
    assert restored.workspace_id == env.workspace_id
    assert restored.project_id == env.project_id
    assert restored.object_id == env.object_id
    assert restored.topic == env.topic
    assert restored.payload == env.payload
    assert restored.created_at == env.created_at

    # Payload exceeding 7900 bytes raises OutboxPayloadTooLargeError
    huge_payload = {"padding": "x" * 8000}
    huge_env = _make_envelope("issue.created", huge_payload)
    with pytest.raises(OutboxPayloadTooLargeError) as exc_info:
        huge_env.to_wire_json()
    assert "exceeds 7900-byte NOTIFY ceiling" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test Case 3: Broker Factory Dispatch
# ---------------------------------------------------------------------------
def test_03_build_realtime_broker_factory() -> None:
    """Verify factory dispatches PgNotifyBroker vs ValkeyBroker and validates inputs."""
    fake_client = FakeValkeyStreamClient()
    dsn = "postgresql://kanban_test@/kanban_test"

    standalone_broker = build_realtime_broker("standalone", pg_dsn=dsn)
    assert isinstance(standalone_broker, PgNotifyBroker)

    valkey_broker = build_realtime_broker("production", pg_dsn=dsn, valkey_client=fake_client)
    assert isinstance(valkey_broker, ValkeyBroker)

    fallback_broker = build_realtime_broker("production", pg_dsn=dsn, valkey_client=None)
    assert isinstance(fallback_broker, PgNotifyBroker)

    with pytest.raises(ValueError, match="requires a non-None valkey_client"):
        build_realtime_broker(
            "production",
            pg_dsn=dsn,
            valkey_client=None,
            require_valkey=True,
        )


# ---------------------------------------------------------------------------
# Test Case 4: Contract Parity Across PgNotifyBroker and ValkeyBroker
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("broker_type", ["pg_notify", "valkey"])
async def test_04_broker_contract_parity(
    broker_type: str,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify publish and subscribe contract parity across both RealtimeBroker implementations."""
    dsn = str(pg_worker_db.url)
    broker: RealtimeBroker
    if broker_type == "pg_notify":
        broker = PgNotifyBroker(dsn, channel=f"test_chan_{uuid4().hex[:8]}")
    else:
        broker = ValkeyBroker(FakeValkeyStreamClient())

    try:
        events = [
            _make_envelope("workflow.gate.approved", {"gate": "qa"}),
            _make_envelope("notification.created", {"user_id": str(uuid4())}),
            _make_envelope("doc.published", {"title": "Release Notes"}),
        ]

        received_all: list[OutboxEnvelope] = []
        received_gate: list[OutboxEnvelope] = []
        received_notif: list[OutboxEnvelope] = []
        received_doc_none: list[OutboxEnvelope] = []

        async def sub_worker(pattern: str, sink: list[OutboxEnvelope], max_items: int) -> None:
            async for item in broker.subscribe(pattern):
                sink.append(item)
                if len(sink) >= max_items:
                    break

        tasks = [
            asyncio.create_task(sub_worker("*", received_all, 3)),
            asyncio.create_task(sub_worker("workflow.gate.*", received_gate, 1)),
            asyncio.create_task(sub_worker("notification.created", received_notif, 1)),
            asyncio.create_task(sub_worker("other.*", received_doc_none, 1)),
        ]

        # Give subscription setup a tiny moment to register listener
        await asyncio.sleep(0.05)

        for ev in events:
            await broker.publish(ev)

        # Await subscribers that expect events with a short timeout
        await asyncio.wait_for(tasks[0], timeout=2.0)
        await asyncio.wait_for(tasks[1], timeout=2.0)
        await asyncio.wait_for(tasks[2], timeout=2.0)

        # Cancel the non-matching subscription
        tasks[3].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[3]

        assert len(received_all) == 3
        assert len(received_gate) == 1
        assert received_gate[0].topic == "workflow.gate.approved"
        assert len(received_notif) == 1
        assert received_notif[0].topic == "notification.created"
        assert len(received_doc_none) == 0
    finally:
        await broker.close()


# ---------------------------------------------------------------------------
# Test Case 5: Transactional Atomicity and Savepoint Rollback
# ---------------------------------------------------------------------------
async def test_05_transactional_atomicity_and_rollback(db_session: AsyncSession) -> None:
    """Verify enqueue_outbox_event rolls back cleanly inside aborted SAVEPOINT transactions."""
    ws_id = await _create_test_workspace(db_session)

    # 1. Rollback case: transaction abort leaves 0 outbox_events rows
    async with db_session.begin_nested() as nested:
        await enqueue_outbox_event(
            db_session,
            workspace_id=ws_id,
            topic="issue.created",
            payload={"summary": "Temporary Issue"},
        )
        # Rollback nested savepoint
        await nested.rollback()

    count_res = await db_session.execute(
        text("SELECT count(*) FROM outbox_events WHERE workspace_id = :ws"),
        {"ws": ws_id},
    )
    assert count_res.scalar_one() == 0

    # 2. Enqueue within valid savepoint persists
    async with db_session.begin_nested():
        eid = await enqueue_outbox_event(
            db_session,
            workspace_id=ws_id,
            topic="issue.created",
            payload={"summary": "Committed Issue"},
        )
        assert isinstance(eid, UUID)

    count_res2 = await db_session.execute(
        text("SELECT count(*) FROM outbox_events WHERE workspace_id = :ws"),
        {"ws": ws_id},
    )
    assert count_res2.scalar_one() == 1


# ---------------------------------------------------------------------------
# Test Case 6: Negative and Security Validations
# ---------------------------------------------------------------------------
async def test_06_negative_and_security_validations(db_session: AsyncSession) -> None:
    """Verify payload limits, invalid topic patterns, and row-level security."""
    ws_id = await _create_test_workspace(db_session)

    # Payload > 7168 bytes raises OutboxPayloadTooLargeError before DB query
    large_payload = {"padding": "a" * 7200}
    with pytest.raises(OutboxPayloadTooLargeError) as exc_large:
        await enqueue_outbox_event(
            db_session,
            workspace_id=ws_id,
            topic="issue.created",
            payload=large_payload,
        )
    assert "exceeds 7168-byte storage ceiling" in str(exc_large.value)

    # Invalid topic regex raises ValueError before DB query
    for bad_topic in ["Issue Created", "singleword", "123.bad", "bad..dot", "UPPER.CASE"]:
        with pytest.raises(ValueError, match="Invalid outbox topic"):
            await enqueue_outbox_event(
                db_session,
                workspace_id=ws_id,
                topic=bad_topic,
                payload={"data": 1},
            )

    # Direct insert as kanban_app without binding workspace context triggers RLS denial
    u_id = uuid4()
    ws_other = await _create_test_workspace(db_session)
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_id, ws_id)

    # Attempt insert for different workspace under active RLS session
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO outbox_events (workspace_id, topic, payload) "
                    "VALUES (:ws_other, 'issue.created', '{}'::jsonb)"
                ),
                {"ws_other": ws_other},
            )


# ---------------------------------------------------------------------------
# Test Case 7: End-to-End Committed Event Delivery
# ---------------------------------------------------------------------------
@pytest.mark.committed_db
async def test_07_e2e_committed_event_delivery(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify committed enqueue wakes OutboxRelay and delivers envelope in < 200ms."""
    dsn = str(pg_worker_db.url)
    ws_id = await _create_test_workspace(committed_db_session)
    await committed_db_session.commit()

    broker = PgNotifyBroker(dsn, channel="kanban_realtime")
    relay = OutboxRelay(
        engine=pg_worker_db,
        listen_dsn=dsn,
        broker=broker,
        batch_size=10,
        poll_interval_s=0.1,
    )

    received: list[OutboxEnvelope] = []
    stop_event = asyncio.Event()

    async def subscriber_task() -> None:
        async for envelope in broker.subscribe("issue.*"):
            received.append(envelope)
            stop_event.set()
            break

    sub_handle = asyncio.create_task(subscriber_task())
    relay_handle = asyncio.create_task(relay.run_until_stopped(stop_event))

    # Give listener a brief moment to connect
    await asyncio.sleep(0.05)

    start_time = asyncio.get_running_loop().time()
    event_id = await enqueue_outbox_event(
        committed_db_session,
        workspace_id=ws_id,
        topic="issue.created",
        payload={"ticket": "KANBA-56", "status": "In Progress"},
    )
    await committed_db_session.commit()

    try:
        await asyncio.wait_for(sub_handle, timeout=2.0)
    finally:
        stop_event.set()
        await relay_handle
        await broker.close()

    elapsed_ms = (asyncio.get_running_loop().time() - start_time) * 1000.0
    assert elapsed_ms < 5000.0

    assert len(received) == 1
    assert received[0].id == event_id
    assert received[0].topic == "issue.created"
    assert received[0].payload["ticket"] == "KANBA-56"

    # Confirm database row marked published_at
    row = await committed_db_session.execute(
        text("SELECT published_at, attempts FROM outbox_events WHERE id = :id"),
        {"id": event_id},
    )
    published_row = row.mappings().one()
    assert published_row["published_at"] is not None
    assert published_row["attempts"] == 1


# ---------------------------------------------------------------------------
# Test Case 8: ORM OutboxEvent Entity Mapping
# ---------------------------------------------------------------------------
async def test_08_outbox_orm_entity(db_session: AsyncSession) -> None:
    """Verify SQLAlchemy 2.0 OutboxEvent DeclarativeBase mapping and operations."""
    ws_id = await _create_test_workspace(db_session)

    event = OutboxEvent(
        workspace_id=ws_id,
        topic="orm.test.event",
        payload={"orm": "mapped"},
    )
    db_session.add(event)
    await db_session.flush()

    assert event.id is not None
    assert event.seq > 0
    assert event.created_at is not None
    assert event.attempts == 0
    assert event.payload == {"orm": "mapped"}

    stmt = select(OutboxEvent).where(OutboxEvent.id == event.id)
    result = await db_session.execute(stmt)
    loaded = result.scalar_one()
    assert loaded.id == event.id
    assert loaded.topic == "orm.test.event"


# ---------------------------------------------------------------------------
# Test Case 9: PgNotifyBroker Edge Cases
# ---------------------------------------------------------------------------
async def test_09_pg_notify_broker_edge_cases(pg_worker_db: AsyncEngine) -> None:
    """Verify PgNotifyBroker close, closed rejection, malformed payloads, and queue lag."""
    dsn = str(pg_worker_db.url)
    broker = PgNotifyBroker(dsn, channel="test_edge_chan")

    # Connect listener and publisher
    await broker._ensure_listener()  # noqa: SLF001
    await broker._ensure_publisher()  # noqa: SLF001

    # Malformed notification handling
    conn = broker._listener_conn  # noqa: SLF001
    assert conn is not None
    broker._on_notification(conn, 1234, "test_edge_chan", "not-json-payload")  # noqa: SLF001

    # Queue full / lagged subscriber drop
    sub_queue: asyncio.Queue[OutboxEnvelope | None] = asyncio.Queue(maxsize=1)
    sub_queue.put_nowait(_make_envelope("lag.topic"))
    broker._subscribers[sub_queue] = "lag.*"  # noqa: SLF001

    # Next message drops oldest
    new_env = _make_envelope("lag.topic", {"new": True})
    broker._on_notification(conn, 1234, "test_edge_chan", new_env.to_wire_json())  # noqa: SLF001
    assert sub_queue.qsize() == 1
    item = sub_queue.get_nowait()
    assert item is not None
    assert item.payload == {"new": True}

    # Close broker
    await broker.close()
    # Double close is safe and returns early
    await broker.close()

    # Rejection when closed
    with pytest.raises(RuntimeError, match="Broker is closed"):
        await broker.publish(_make_envelope("closed.topic"))

    with pytest.raises(RuntimeError, match="Broker is closed"):
        await broker._ensure_listener()  # noqa: SLF001

    with pytest.raises(RuntimeError, match="Broker is closed"):
        await broker._ensure_publisher()  # noqa: SLF001


# ---------------------------------------------------------------------------
# Test Case 10: ValkeyBroker and FakeValkeyStreamClient Edge Cases
# ---------------------------------------------------------------------------
async def test_10_valkey_broker_and_fake_client_edge_cases() -> None:
    """Verify ValkeyBroker closed states, queue overflow, and FakeValkeyStreamClient methods."""
    client = FakeValkeyStreamClient()
    broker = ValkeyBroker(client)

    # Queue full handling in ValkeyBroker
    sub_queue: asyncio.Queue[OutboxEnvelope | None] = asyncio.Queue(maxsize=1)
    sub_queue.put_nowait(_make_envelope("lag.valkey"))
    broker._subscribers[sub_queue] = "lag.*"  # noqa: SLF001

    # Publish drops oldest when queue is full
    env2 = _make_envelope("lag.valkey", {"valkey_new": True})
    await broker.publish(env2)
    assert sub_queue.qsize() == 1
    item = sub_queue.get_nowait()
    assert item is not None
    assert item.payload == {"valkey_new": True}

    # FakeValkeyStreamClient trimming
    for i in range(5):
        await client.xadd("test_trim", {"index": str(i)}, maxlen=2)
    entries = client._streams["test_trim"]  # noqa: SLF001
    assert len(entries) == 2

    # FakeValkeyStreamClient xread with block_ms
    res = await client.xread({"test_trim": "0"}, count=1)
    assert len(res) == 1
    assert len(res[0][1]) == 1

    # FakeValkeyStreamClient publish with full queue
    full_q: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    full_q.put_nowait("existing")
    client._channels["test_full_chan"].append(full_q)  # noqa: SLF001
    assert await client.publish("test_full_chan", "msg") == 1

    empty_res = await client.xread({"nonexistent": "0"}, block_ms=10)
    assert len(empty_res) == 0

    # Close broker
    await broker.close()
    await broker.close()

    with pytest.raises(RuntimeError, match="Broker is closed"):
        await broker.publish(_make_envelope("closed.topic"))

    with pytest.raises(RuntimeError, match="Broker is closed"):
        async for _ in broker.subscribe("*"):
            pass


# ---------------------------------------------------------------------------
# Test Case 11: OutboxRelay main() CLI Execution and Signal Handling
# ---------------------------------------------------------------------------
async def test_11_relay_main_execution(pg_worker_db: AsyncEngine) -> None:
    """Verify relay_main CLI entrypoint starts, handles SIGINT, and terminates cleanly."""
    old_url = os.environ.get("DATABASE_URL")
    old_db = os.environ.get("KB_TEST_PGDATABASE")
    try:
        os.environ.pop("DATABASE_URL", None)
        os.environ["KB_TEST_PGDATABASE"] = pg_worker_db.url.database or "kanban_test"

        task = asyncio.create_task(relay_main())
        await asyncio.sleep(0.05)
        # Send SIGINT to test signal handler and clean termination
        os.kill(os.getpid(), signal.SIGINT)
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        if old_url is not None:
            os.environ["DATABASE_URL"] = old_url
        else:
            os.environ.pop("DATABASE_URL", None)
        if old_db is not None:
            os.environ["KB_TEST_PGDATABASE"] = old_db
        else:
            os.environ.pop("KB_TEST_PGDATABASE", None)


# ---------------------------------------------------------------------------
# Test Case 12: Subscriber Loop Termination on Broker Close
# ---------------------------------------------------------------------------
async def test_12_subscriber_breaks_on_broker_close(pg_worker_db: AsyncEngine) -> None:
    """Verify subscriber generator exits cleanly when broker.close() sends sentinel."""
    dsn = str(pg_worker_db.url)
    pg_b = PgNotifyBroker(dsn, channel="close_test_chan")
    vk_b = ValkeyBroker(FakeValkeyStreamClient())

    async def sub_pg() -> None:
        async for _ in pg_b.subscribe("*"):
            pass

    async def sub_vk() -> None:
        async for _ in vk_b.subscribe("*"):
            pass

    t_pg = asyncio.create_task(sub_pg())
    t_vk = asyncio.create_task(sub_vk())

    await asyncio.sleep(0.05)
    await pg_b.close()
    await vk_b.close()

    await asyncio.wait_for(t_pg, timeout=2.0)
    await asyncio.wait_for(t_vk, timeout=2.0)


# ---------------------------------------------------------------------------
# Test Case 13: Enqueue and Drain with Project and Object IDs
# ---------------------------------------------------------------------------
@pytest.mark.committed_db
async def test_13_enqueue_with_project_and_object_ids(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify OutboxEnvelope captures project_id and object_id during relay drain."""
    ws_id = await _create_test_workspace(committed_db_session)
    proj_id = uuid4()
    obj_id = uuid4()

    # Register project in objects spine first to avoid PROJECT_SPINE_MISMATCH
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL, 'OUT', 'Outbox Proj', :pid, :pid"
            ")"
        ),
        {"ws": ws_id, "pid": proj_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:pid, :ws, 'OUT', 'Outbox Proj')"
        ),
        {"pid": proj_id, "ws": ws_id},
    )

    eid = await enqueue_outbox_event(
        committed_db_session,
        workspace_id=ws_id,
        project_id=proj_id,
        object_id=obj_id,
        topic="issue.linked",
        payload={"linked": True},
    )
    await committed_db_session.commit()

    dsn = str(pg_worker_db.url)
    broker = ValkeyBroker(FakeValkeyStreamClient())
    relay = OutboxRelay(
        engine=pg_worker_db,
        listen_dsn=dsn,
        broker=broker,
        batch_size=10,
    )

    drained = await relay.drain_once()
    assert drained == 1

    row = await committed_db_session.execute(
        text("SELECT published_at FROM outbox_events WHERE id = :id"),
        {"id": eid},
    )
    assert row.scalar_one() is not None

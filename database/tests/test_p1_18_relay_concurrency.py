"""Concurrency and poison-pill resilience tests for OutboxRelay and SKIP LOCKED."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.outbox.broker import (
    OutboxEnvelope,
    RealtimeBroker,
    enqueue_outbox_event,
)
from database.outbox.relay import OutboxRelay

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class MockRecordingBroker(RealtimeBroker):
    """Test broker recording published envelopes with thread-safe counters."""

    def __init__(self, failing_ids: set[UUID] | None = None) -> None:
        """Initialize recording broker with optional set of failing event IDs."""
        self.published_events: list[OutboxEnvelope] = []
        self._failing_ids = failing_ids or set()
        self._lock = asyncio.Lock()

    async def publish(self, event: OutboxEnvelope) -> None:
        """Record publication or raise injected transient error."""
        if event.id in self._failing_ids:
            msg = f"Simulated transport failure for event {event.id}"
            raise RuntimeError(msg)
        async with self._lock:
            self.published_events.append(event)

    async def subscribe(self, _topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        """No-op subscription generator for mock broker."""
        empty: tuple[OutboxEnvelope, ...] = ()
        for item in empty:
            yield item

    async def close(self) -> None:
        """No-op close."""


async def _create_test_workspace(session: AsyncSession, slug: str | None = None) -> UUID:
    """Create an isolated test workspace."""
    ws_slug = slug or f"ws-relay-{uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": "Relay Concurrency Workspace"},
    )
    val = row.scalar_one()
    if not isinstance(val, UUID):
        val = UUID(str(val))
    return val


# ---------------------------------------------------------------------------
# Test Case 1: Batch Size Constraint Check
# ---------------------------------------------------------------------------
async def test_01_claim_batch_size_validation(db_session: AsyncSession) -> None:
    """Verify claim_outbox_batch rejects invalid batch size outside 1..500 bounds."""
    for invalid_size in [0, -1, 501, 1000]:
        with pytest.raises(DBAPIError) as exc_info:
            async with db_session.begin_nested():
                await db_session.execute(
                    text("SELECT * FROM claim_outbox_batch(:bs)"),
                    {"bs": invalid_size},
                )
        assert "p_batch_size must be between 1 and 500" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test Case 2: Concurrency Stress with FOR UPDATE SKIP LOCKED
# ---------------------------------------------------------------------------
@pytest.mark.committed_db
async def test_02_relay_concurrency_skip_locked(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify 4 concurrent workers drain 60 events with zero duplicate claims."""
    ws_id = await _create_test_workspace(committed_db_session)

    # Enqueue 60 events
    event_ids: list[UUID] = []
    for i in range(60):
        eid = await enqueue_outbox_event(
            committed_db_session,
            workspace_id=ws_id,
            topic="issue.updated",
            payload={"index": i, "token": uuid4().hex},
        )
        event_ids.append(eid)
    await committed_db_session.commit()

    dsn = str(pg_worker_db.url)
    broker = MockRecordingBroker()

    # Create 4 concurrent relays sharing the same recording broker
    relays = [
        OutboxRelay(
            engine=pg_worker_db,
            listen_dsn=dsn,
            broker=broker,
            batch_size=10,
        )
        for _ in range(4)
    ]

    async def worker_loop(relay: OutboxRelay) -> None:
        # Each worker attempts multiple drain passes until database is empty
        for _ in range(20):
            drained = await relay.drain_once()
            if drained == 0:
                await asyncio.sleep(0.01)

    # Run 4 workers concurrently
    await asyncio.gather(*(worker_loop(r) for r in relays))

    # All 60 events published
    published_ids = [e.id for e in broker.published_events]
    assert len(published_ids) == 60

    # Zero duplicate claims
    assert len(set(published_ids)) == 60
    assert set(published_ids) == set(event_ids)

    # Every row in outbox_events has published_at set and attempts == 1
    rows_res = await committed_db_session.execute(
        text(
            "SELECT id, published_at, dead_lettered_at, attempts "
            "FROM outbox_events WHERE workspace_id = :ws"
        ),
        {"ws": ws_id},
    )
    rows = rows_res.mappings().all()
    assert len(rows) == 60
    for r in rows:
        assert r["published_at"] is not None
        assert r["dead_lettered_at"] is None
        assert r["attempts"] == 1


# ---------------------------------------------------------------------------
# Test Case 3: Poison-Pill and Dead-Letter Transition
# ---------------------------------------------------------------------------
@pytest.mark.committed_db
async def test_03_poison_pill_dead_letter_resilience(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify poison pill event does not block batch, and dead-letters after 5 attempts."""
    ws_id = await _create_test_workspace(committed_db_session)

    # Enqueue event A (bad) and event B (healthy)
    eid_bad = await enqueue_outbox_event(
        committed_db_session,
        workspace_id=ws_id,
        topic="issue.corrupted",
        payload={"corrupt": True},
    )
    eid_good = await enqueue_outbox_event(
        committed_db_session,
        workspace_id=ws_id,
        topic="issue.healthy",
        payload={"healthy": True},
    )
    await committed_db_session.commit()

    dsn = str(pg_worker_db.url)
    broker = MockRecordingBroker(failing_ids={eid_bad})
    relay = OutboxRelay(
        engine=pg_worker_db,
        listen_dsn=dsn,
        broker=broker,
        batch_size=10,
        max_attempts=5,
    )

    # First drain pass: claims both events
    # eid_good succeeds and is marked published_at; eid_bad fails and attempts = 1
    drained = await relay.drain_once()
    assert drained == 2

    # Check eid_good is published immediately
    good_row = await committed_db_session.execute(
        text("SELECT published_at, dead_lettered_at FROM outbox_events WHERE id = :id"),
        {"id": eid_good},
    )
    r_good = good_row.mappings().one()
    assert r_good["published_at"] is not None
    assert r_good["dead_lettered_at"] is None

    # Check eid_bad has attempts = 1, last_error populated, dead_lettered_at is None
    bad_row = await committed_db_session.execute(
        text(
            "SELECT attempts, last_error, dead_lettered_at, published_at "
            "FROM outbox_events WHERE id = :id"
        ),
        {"id": eid_bad},
    )
    r_bad = bad_row.mappings().one()
    assert r_bad["attempts"] == 1
    assert r_bad["published_at"] is None
    assert r_bad["dead_lettered_at"] is None
    assert "Simulated transport failure" in str(r_bad["last_error"])

    # Simulate 4 subsequent retry attempts by resetting next_attempt_at in the past
    for expected_attempt in range(2, 6):
        # Reset next_attempt_at so claim_outbox_batch picks it up
        await committed_db_session.execute(
            text(
                "UPDATE outbox_events "
                "SET next_attempt_at = clock_timestamp() - interval '1 second' "
                "WHERE id = :id"
            ),
            {"id": eid_bad},
        )
        await committed_db_session.commit()

        drained_retry = await relay.drain_once()
        assert drained_retry == 1

        chk = await committed_db_session.execute(
            text("SELECT attempts, dead_lettered_at FROM outbox_events WHERE id = :id"),
            {"id": eid_bad},
        )
        chk_row = chk.mappings().one()
        assert chk_row["attempts"] == expected_attempt

        if expected_attempt < 5:
            assert chk_row["dead_lettered_at"] is None
        else:
            # 5th attempt triggers dead_lettered_at
            assert chk_row["dead_lettered_at"] is not None

    # Verify subsequent claim skips eid_bad completely
    await committed_db_session.execute(
        text(
            "UPDATE outbox_events "
            "SET next_attempt_at = clock_timestamp() - interval '1 second' "
            "WHERE id = :id"
        ),
        {"id": eid_bad},
    )
    await committed_db_session.commit()

    drained_after_dead = await relay.drain_once()
    assert drained_after_dead == 0

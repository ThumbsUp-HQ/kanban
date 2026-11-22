"""Transactional OutboxRelay worker polling with SKIP LOCKED and PG NOTIFY wakeup."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from typing import TYPE_CHECKING, Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.outbox.broker import (
    OutboxEnvelope,
    RealtimeBroker,
    build_realtime_broker,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("database.outbox.relay")


class OutboxRelay:
    """Relay worker moving events from outbox_events to RealtimeBroker via SKIP LOCKED."""

    def __init__(  # noqa: PLR0913
        self,
        engine: AsyncEngine,
        listen_dsn: str,
        broker: RealtimeBroker,
        *,
        batch_size: int = 100,
        poll_interval_s: float = 1.0,
        max_attempts: int = 5,
    ) -> None:
        """Initialize outbox relay with database engine, notification DSN, and target broker."""
        self._engine = engine
        self._listen_dsn = listen_dsn.replace("postgresql+asyncpg://", "postgresql://")
        self._broker = broker
        self._batch_size = batch_size
        self._poll_interval_s = poll_interval_s
        self._max_attempts = max_attempts
        self._running = False

    @property
    def is_running(self) -> bool:
        """Whether the relay worker is actively running."""
        return self._running

    async def get_diagnostics_snapshot(self) -> dict[str, Any]:
        """Return diagnostic status of outbox relay worker and pending event queue."""
        pending_count = 0
        dead_letter_count = 0
        try:
            async with self._engine.begin() as conn:
                res = await conn.execute(
                    text("SELECT status, count(*) as cnt FROM outbox_events GROUP BY status")
                )
                for row in res.mappings().all():
                    s = str(row["status"]).lower()
                    cnt = int(row["cnt"])
                    if s in ("pending", "processing"):
                        pending_count += cnt
                    elif s in ("failed", "dead_letter", "dead_lettered"):
                        dead_letter_count += cnt
        except Exception:
            logger.debug("Could not count outbox events", exc_info=True)

        return {
            "outbox_relay_running": self._running,
            "batch_size": self._batch_size,
            "poll_interval_s": self._poll_interval_s,
            "max_attempts": self._max_attempts,
            "outbox_pending_count": pending_count,
            "outbox_dead_letter_count": dead_letter_count,
        }

    async def get_status(self) -> dict[str, Any]:
        """Alias for get_diagnostics_snapshot."""
        return await self.get_diagnostics_snapshot()

    async def drain_once(self) -> int:
        """Claim a batch of pending events, publish to broker, and update database state."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("SELECT * FROM claim_outbox_batch(:bs)"),
                {"bs": self._batch_size},
            )
            rows = result.mappings().all()

        if not rows:
            return 0

        succeeded_ids: list[UUID] = []
        failed_items: list[tuple[UUID, str]] = []

        for row in rows:
            event_id = UUID(str(row["id"]))

            envelope = OutboxEnvelope(
                id=event_id,
                seq=int(row["seq"]),
                workspace_id=UUID(str(row["workspace_id"])),
                project_id=UUID(str(row["project_id"])) if row.get("project_id") else None,
                object_id=UUID(str(row["object_id"])) if row.get("object_id") else None,
                topic=str(row["topic"]),
                payload=dict(row["payload"]),
                created_at=row["created_at"],
            )

            try:
                await self._broker.publish(envelope)
                succeeded_ids.append(event_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error publishing outbox event %s on topic %s: %s",
                    event_id,
                    envelope.topic,
                    exc,
                )
                failed_items.append((event_id, str(exc)))

        if succeeded_ids:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text("SELECT mark_outbox_published(:ids)"),
                    {"ids": succeeded_ids},
                )

        if failed_items:
            for fid, err_msg in failed_items:
                async with self._engine.begin() as conn:
                    is_dead_lettered = await conn.scalar(
                        text("SELECT mark_outbox_failed(:id, :err, :max_att)"),
                        {"id": fid, "err": err_msg, "max_att": self._max_attempts},
                    )
                    if is_dead_lettered:
                        logger.error(
                            "OUTBOX_EVENT_DEAD_LETTERED: "
                            "Event %s dead-lettered after %d attempts: %s",
                            fid,
                            self._max_attempts,
                            err_msg,
                        )

        return len(rows)

    async def run_until_stopped(self, stop_event: asyncio.Event) -> None:
        """Run relay polling loop until stop_event is set, waking on outbox_wakeup NOTIFY."""
        wakeup_event = asyncio.Event()

        def on_wakeup(
            _conn: asyncpg.Connection,
            _pid: int,
            _channel: str,
            _payload: str,
        ) -> None:
            wakeup_event.set()

        listener_conn: asyncpg.Connection | None = None
        self._running = True
        try:
            listener_conn = await asyncpg.connect(self._listen_dsn)
            await listener_conn.add_listener("outbox_wakeup", on_wakeup)
            logger.info("OutboxRelay listening on outbox_wakeup")

            while not stop_event.is_set():
                processed = await self.drain_once()
                if processed > 0:
                    continue

                wakeup_event.clear()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wakeup_event.wait(), timeout=self._poll_interval_s)
        finally:
            self._running = False
            if listener_conn is not None and not listener_conn.is_closed():
                try:
                    await listener_conn.remove_listener("outbox_wakeup", on_wakeup)
                    await listener_conn.close()
                except Exception:
                    logger.debug("Error closing relay listener connection", exc_info=True)


class _DatabaseOutboxFormatter(logging.Formatter):
    """Stdlib-only log formatter attaching semantic status icons without upward imports."""

    def format(self, record: logging.LogRecord) -> str:
        icon = (
            "👍"
            if record.levelno < logging.WARNING
            else ("⛔" if record.levelno < logging.ERROR else "❌")
        )
        msg = super().format(record)
        if not msg.startswith(("👍", "⛔", "❌")):
            return f"{icon} {msg}"
        return msg


async def main(stop_event: asyncio.Event | None = None) -> None:
    """CLI entrypoint for running outbox relay as standalone service."""
    from database.testing.pg_harness import build_dsn  # noqa: PLC0415

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        _DatabaseOutboxFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    pg_dsn = os.environ.get("DATABASE_URL")
    if not pg_dsn:
        pg_dsn = build_dsn(
            database=os.environ.get("KB_TEST_PGDATABASE", "kanban"),
            host=os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock"),  # noqa: S108
            user=os.environ.get("KB_TEST_PGUSER", "kanban_test"),
        )

    engine = create_async_engine(pg_dsn)
    broker = build_realtime_broker("standalone", pg_dsn=pg_dsn)
    relay = OutboxRelay(
        engine=engine,
        listen_dsn=pg_dsn,
        broker=broker,
        batch_size=int(os.environ.get("KB_RELAY_BATCH_SIZE", "100")),
        poll_interval_s=float(os.environ.get("KB_RELAY_POLL_INTERVAL", "1.0")),
    )

    if stop_event is None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

    try:
        await relay.run_until_stopped(stop_event)
    finally:
        await broker.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

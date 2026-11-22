"""PostgreSQL LISTEN/NOTIFY implementation of RealtimeBroker."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import asyncpg  # type: ignore[import-untyped]

from database.outbox.broker import OutboxEnvelope, RealtimeBroker, topic_matches

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger("database.outbox.pg_broker")

DEFAULT_CHANNEL = "kanban_realtime"
MAX_QUEUE_SIZE = 1024


class PgNotifyBroker(RealtimeBroker):
    """Zero-Valkey standalone broker using PostgreSQL LISTEN/NOTIFY."""

    def __init__(self, pg_dsn: str, channel: str = DEFAULT_CHANNEL) -> None:
        """Initialize PostgreSQL notify broker with DSN and target channel."""
        self._dsn = pg_dsn.replace("postgresql+asyncpg://", "postgresql://")
        self._channel = channel
        self._listener_conn: asyncpg.Connection | None = None
        self._publisher_conn: asyncpg.Connection | None = None
        self._subscribers: dict[asyncio.Queue[OutboxEnvelope | None], str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    def get_diagnostics_snapshot(self) -> dict[str, Any]:
        """Return diagnostic status of PostgreSQL LISTEN/NOTIFY connections and subscribers."""
        listener_connected = self._listener_conn is not None and not self._listener_conn.is_closed()
        publisher_connected = (
            self._publisher_conn is not None and not self._publisher_conn.is_closed()
        )
        return {
            "broker_kind": "pg_notify",
            "channel": self._channel,
            "listener_connected": listener_connected,
            "publisher_connected": publisher_connected,
            "subscribers_count": len(self._subscribers),
            "closed": self._closed,
        }

    def get_status(self) -> dict[str, Any]:
        """Alias for get_diagnostics_snapshot."""
        return self.get_diagnostics_snapshot()

    async def _ensure_listener(self) -> asyncpg.Connection:
        async with self._lock:
            if self._closed:
                msg = "Broker is closed"
                raise RuntimeError(msg)
            if self._listener_conn is None or self._listener_conn.is_closed():
                conn = await asyncpg.connect(self._dsn)
                await conn.add_listener(self._channel, self._on_notification)
                self._listener_conn = conn
            return self._listener_conn

    async def _ensure_publisher(self) -> asyncpg.Connection:
        async with self._lock:
            if self._closed:
                msg = "Broker is closed"
                raise RuntimeError(msg)
            if self._publisher_conn is None or self._publisher_conn.is_closed():
                self._publisher_conn = await asyncpg.connect(self._dsn)
            return self._publisher_conn

    def _on_notification(
        self,
        _connection: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        """Handle incoming NOTIFY payload and route to matching subscriber queues."""
        try:
            envelope = OutboxEnvelope.from_wire_json(payload)
        except Exception:
            logger.exception("Failed to deserialize wire JSON from notify payload")
            return

        for queue, pattern in list(self._subscribers.items()):
            if topic_matches(pattern, envelope.topic):
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                    logger.warning(
                        "REALTIME_SUBSCRIBER_LAGGED: dropped oldest envelope for topic %s",
                        envelope.topic,
                    )
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(envelope)

    async def publish(self, event: OutboxEnvelope) -> None:
        """Publish an OutboxEnvelope over PostgreSQL NOTIFY."""
        if self._closed:
            msg = "Broker is closed"
            raise RuntimeError(msg)
        wire_json = event.to_wire_json()
        conn = await self._ensure_publisher()
        await conn.execute("SELECT pg_notify($1, $2)", self._channel, wire_json)

    async def subscribe(self, topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        """Subscribe to envelopes matching the topic pattern."""
        await self._ensure_listener()
        queue: asyncio.Queue[OutboxEnvelope | None] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subscribers[queue] = topic_pattern
        try:
            while not self._closed:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            self._subscribers.pop(queue, None)

    async def close(self) -> None:
        """Close connections and release subscribers."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True

            for queue in list(self._subscribers.keys()):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)
            self._subscribers.clear()

            if self._listener_conn is not None and not self._listener_conn.is_closed():
                try:
                    await self._listener_conn.remove_listener(self._channel, self._on_notification)
                    await self._listener_conn.close()
                except Exception:
                    logger.debug("Error closing listener connection", exc_info=True)
                self._listener_conn = None

            if self._publisher_conn is not None and not self._publisher_conn.is_closed():
                try:
                    await self._publisher_conn.close()
                except Exception:
                    logger.debug("Error closing publisher connection", exc_info=True)
                self._publisher_conn = None

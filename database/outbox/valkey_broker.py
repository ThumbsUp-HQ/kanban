"""Valkey Stream and PubSub implementation of RealtimeBroker."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from database.outbox.broker import OutboxEnvelope, RealtimeBroker, topic_matches

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

logger = logging.getLogger("database.outbox.valkey_broker")

DEFAULT_STREAM = "kb:outbox:stream"
DEFAULT_PUBSUB_PREFIX = "kb:rt:"
MAX_QUEUE_SIZE = 1024


@runtime_checkable
class ValkeyStreamClient(Protocol):
    """Protocol for Valkey/Redis client operations required by ValkeyBroker."""

    async def xadd(
        self,
        stream: str,
        fields: Mapping[str, str],
        *,
        maxlen: int = 100_000,
    ) -> str:
        """Append an entry to a Valkey stream."""
        ...

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a pubsub channel."""
        ...

    async def xread(
        self,
        streams: Mapping[str, str],
        *,
        count: int = 100,
        block_ms: int = 1000,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        """Read entries from one or more streams."""
        ...


class ValkeyBroker(RealtimeBroker):
    """Multi-replica production broker backed by Valkey Streams and PubSub."""

    def __init__(
        self,
        client: ValkeyStreamClient,
        *,
        stream_name: str = DEFAULT_STREAM,
        pubsub_prefix: str = DEFAULT_PUBSUB_PREFIX,
    ) -> None:
        """Initialize broker with stream client, target stream, and pubsub prefix."""
        self._client = client
        self._stream_name = stream_name
        self._pubsub_prefix = pubsub_prefix
        self._subscribers: dict[asyncio.Queue[OutboxEnvelope | None], str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def publish(self, event: OutboxEnvelope) -> None:
        """Publish an OutboxEnvelope to Valkey Stream and PubSub channel."""
        if self._closed:
            msg = "Broker is closed"
            raise RuntimeError(msg)

        wire_json = event.to_wire_json()
        await self._client.xadd(
            self._stream_name,
            {"event": wire_json, "topic": event.topic},
            maxlen=100_000,
        )
        channel = f"{self._pubsub_prefix}{event.topic}"
        await self._client.publish(channel, wire_json)

        # Dispatch to active local subscribers
        for queue, pattern in list(self._subscribers.items()):
            if topic_matches(pattern, event.topic):
                if queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                    logger.warning(
                        "REALTIME_SUBSCRIBER_LAGGED: dropped oldest envelope for topic %s",
                        event.topic,
                    )
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    async def subscribe(self, topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        """Subscribe to envelopes matching the topic pattern."""
        if self._closed:
            msg = "Broker is closed"
            raise RuntimeError(msg)

        queue: asyncio.Queue[OutboxEnvelope | None] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        async with self._lock:
            self._subscribers[queue] = topic_pattern

        try:
            while not self._closed:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            async with self._lock:
                self._subscribers.pop(queue, None)

    async def close(self) -> None:
        """Close broker and wake pending subscriber loops."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True

            for queue in list(self._subscribers.keys()):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)
            self._subscribers.clear()


class FakeValkeyStreamClient:
    """In-memory mock of ValkeyStreamClient for testing without external Valkey."""

    def __init__(self) -> None:
        """Initialize in-memory streams and channel subscribers."""
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
        self._channels: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._seq = 0
        self._lock = asyncio.Lock()

    async def xadd(
        self,
        stream: str,
        fields: Mapping[str, str],
        *,
        maxlen: int = 100_000,
    ) -> str:
        """Append entry to in-memory stream with millisecond-seq ID."""
        async with self._lock:
            self._seq += 1
            entry_id = f"{int(time.time() * 1000)}-{self._seq}"
            entry = (entry_id, {k: str(v) for k, v in fields.items()})
            stream_list = self._streams[stream]
            stream_list.append(entry)
            if len(stream_list) > maxlen:
                del stream_list[:-maxlen]
            return entry_id

    async def publish(self, channel: str, message: str) -> int:
        """Publish message to registered channel queues."""
        async with self._lock:
            subscribers = self._channels.get(channel, [])
            for q in subscribers:
                with contextlib.suppress(asyncio.QueueFull):
                    q.put_nowait(message)
            return len(subscribers)

    async def xread(
        self,
        streams: Mapping[str, str],
        *,
        count: int = 100,
        block_ms: int = 1000,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        """Read entries newer than the specified stream ID."""
        results: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
        async with self._lock:
            for stream_name, last_id in streams.items():
                entries = self._streams.get(stream_name, [])
                matched: list[tuple[str, dict[str, str]]] = []
                for eid, fields in entries:
                    if last_id == "0" or eid > last_id:
                        matched.append((eid, dict(fields)))
                        if len(matched) >= count:
                            break
                if matched:
                    results.append((stream_name, matched))
        if not results and block_ms > 0:
            await asyncio.sleep(min(block_ms / 1000.0, 0.05))
        return results

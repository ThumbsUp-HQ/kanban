"""RealtimeBroker protocol, OutboxEnvelope, and enqueue helper."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import insert

from database.models.outbox import OutboxEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from database.outbox.valkey_broker import ValkeyStreamClient

_TOPIC_REGEX = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_TOPIC_LENGTH = 128
MAX_PAYLOAD_BYTES = 7168
MAX_WIRE_BYTES = 7900


class OutboxPayloadTooLargeError(ValueError):
    """Raised when an outbox event payload exceeds PostgreSQL storage or notify limits."""


@dataclass(frozen=True, slots=True)
class OutboxEnvelope:
    """Immutable wire envelope for reliable domain event fanout."""

    id: UUID
    seq: int
    workspace_id: UUID
    project_id: UUID | None
    object_id: UUID | None
    topic: str
    payload: dict[str, Any]
    created_at: datetime

    def to_wire_json(self) -> str:
        """Serialize envelope to compact deterministic JSON, validating wire size."""
        doc = {
            "created_at": self.created_at.isoformat(),
            "id": str(self.id),
            "object_id": str(self.object_id) if self.object_id is not None else None,
            "payload": self.payload,
            "project_id": str(self.project_id) if self.project_id is not None else None,
            "seq": self.seq,
            "topic": self.topic,
            "workspace_id": str(self.workspace_id),
        }
        raw = json.dumps(doc, separators=(",", ":"), sort_keys=True)
        raw_bytes = raw.encode("utf-8")
        if len(raw_bytes) > MAX_WIRE_BYTES:
            msg = (
                f"Outbox envelope wire size ({len(raw_bytes)} bytes) "
                f"exceeds {MAX_WIRE_BYTES}-byte NOTIFY ceiling"
            )
            raise OutboxPayloadTooLargeError(msg)
        return raw

    @classmethod
    def from_wire_json(cls, raw: str) -> OutboxEnvelope:
        """Deserialize envelope from compact JSON string."""
        data = json.loads(raw)
        return cls(
            id=UUID(data["id"]),
            seq=int(data["seq"]),
            workspace_id=UUID(data["workspace_id"]),
            project_id=UUID(data["project_id"]) if data.get("project_id") else None,
            object_id=UUID(data["object_id"]) if data.get("object_id") else None,
            topic=str(data["topic"]),
            payload=dict(data.get("payload", {})),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


def topic_matches(pattern: str, topic: str) -> bool:
    """Match topic against exact name, wildcard '*', or segment prefix wildcard."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return topic.startswith(prefix + ".")
    return pattern == topic


@runtime_checkable
class RealtimeBroker(Protocol):
    """Protocol for event fanout brokers (PgNotifyBroker and ValkeyBroker)."""

    async def publish(self, event: OutboxEnvelope) -> None:
        """Publish an outbox envelope to subscribers."""
        ...

    def subscribe(self, topic_pattern: str = "*") -> AsyncIterator[OutboxEnvelope]:
        """Subscribe to events matching a topic pattern."""
        ...

    async def close(self) -> None:
        """Release underlying connections and resources."""
        ...


async def enqueue_outbox_event(  # noqa: PLR0913
    session: AsyncSession,
    *,
    workspace_id: UUID,
    topic: str,
    payload: Mapping[str, Any],
    project_id: UUID | None = None,
    object_id: UUID | None = None,
) -> UUID:
    """Validate and atomically insert an outbox event in the caller's active transaction."""
    if not _TOPIC_REGEX.match(topic) or len(topic) > MAX_TOPIC_LENGTH:
        msg = f"Invalid outbox topic: {topic!r}"
        raise ValueError(msg)

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_bytes = payload_json.encode("utf-8")
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        msg = (
            f"Payload size ({len(payload_bytes)} bytes) "
            f"exceeds {MAX_PAYLOAD_BYTES}-byte storage ceiling"
        )
        raise OutboxPayloadTooLargeError(msg)

    event_id = uuid.uuid4()
    await session.execute(
        insert(OutboxEvent).values(
            id=event_id,
            workspace_id=workspace_id,
            project_id=project_id,
            object_id=object_id,
            topic=topic,
            payload=payload,
        )
    )
    return event_id


def build_realtime_broker(
    deployment_mode: Literal["standalone", "production"],
    *,
    pg_dsn: str,
    valkey_client: ValkeyStreamClient | None = None,
    require_valkey: bool = False,
) -> RealtimeBroker:
    """Construct RealtimeBroker implementation based on deployment mode and client availability."""
    if deployment_mode == "production" and require_valkey and valkey_client is None:
        msg = "Production mode with require_valkey=True requires a non-None valkey_client"
        raise ValueError(msg)

    if deployment_mode == "standalone" or valkey_client is None:
        from database.outbox.pg_broker import PgNotifyBroker  # noqa: PLC0415

        return PgNotifyBroker(pg_dsn)

    from database.outbox.valkey_broker import ValkeyBroker  # noqa: PLC0415

    return ValkeyBroker(valkey_client)

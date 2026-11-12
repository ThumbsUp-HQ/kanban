"""Shared activity-writing helper used by every Phase 3 API ticket (S7.2 8c/8f/8p, S12.2).

Contract:
    - ``record_activity`` appends exactly one immutable row to ``activity_records`` through the
      KB-P1-12 ``append_activity()`` function (hash-chained), inside the caller's transaction.
    - Payloads are capped at 16384 bytes of serialized JSON. They MUST NOT carry Markdown bodies;
      callers reference bodies by ``sha256`` hex digest only.
    - Listeners run in registration order after each insert. A listener exception propagates and
      aborts the insert (fail closed): the insert and listener calls share one SAVEPOINT.

Failure modes:
    - ``ActivityPayloadTooLarge``: serialized payload exceeds ``MAX_PAYLOAD_BYTES``.
    - Any exception raised by a registered listener propagates unchanged after rollback of the
      savepoint that contained the insert.

Performance: one round trip for the object-kind lookup and one for ``append_activity``; listener
cost is the caller's responsibility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, cast

from sqlalchemy import text

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

type JSONValue = str | int | float | bool | Sequence[JSONValue] | Mapping[str, JSONValue] | None

MAX_PAYLOAD_BYTES: Final[int] = 16384


class ActivityPayloadTooLarge(ValueError):  # noqa: N818  # Domain name mandated by KB-P3-01a
    """Raised when a serialized activity payload exceeds ``MAX_PAYLOAD_BYTES``."""


class ActivityObjectNotFound(LookupError):  # noqa: N818  # Domain name mirrors ActivityPayloadTooLarge
    """Raised when ``object_id`` is not visible in the caller's RLS session."""


class ActivityCategory(StrEnum):
    """Display grouping for activity events."""

    COMMENT = "COMMENT"
    HISTORY = "HISTORY"
    GATE = "GATE"
    SYSTEM = "SYSTEM"


class ActivityEventType(StrEnum):
    """Registered activity event types. Later tickets append members and a category."""

    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    MODULE_DEFAULTS_CHANGED = "MODULE_DEFAULTS_CHANGED"
    DOC_CREATED = "DOC_CREATED"
    DOC_UPDATED = "DOC_UPDATED"
    DOC_TRASHED = "DOC_TRASHED"
    PAGE_CREATED = "PAGE_CREATED"
    PAGE_UPDATED = "PAGE_UPDATED"
    PAGE_MOVED = "PAGE_MOVED"
    PAGE_VERSION_RESTORED = "PAGE_VERSION_RESTORED"
    PAGE_TRASHED = "PAGE_TRASHED"


EVENT_CATEGORY: Final[Mapping[ActivityEventType, ActivityCategory]] = MappingProxyType(
    {
        ActivityEventType.PROJECT_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.PROJECT_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.MODULE_DEFAULTS_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.DOC_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.DOC_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.DOC_TRASHED: ActivityCategory.HISTORY,
        ActivityEventType.PAGE_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.PAGE_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.PAGE_MOVED: ActivityCategory.HISTORY,
        ActivityEventType.PAGE_VERSION_RESTORED: ActivityCategory.HISTORY,
        ActivityEventType.PAGE_TRASHED: ActivityCategory.HISTORY,
    }
)


@dataclass(frozen=True, slots=True)
class ActivityEnvelope:
    """Persisted activity event delivered to in-transaction listeners."""

    activity_id: uuid.UUID
    workspace_id: uuid.UUID
    object_id: uuid.UUID
    actor_principal_id: uuid.UUID
    event_type: ActivityEventType
    category: ActivityCategory
    payload: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class EphemeralEnvelope:
    """Non-persisted event (for example rank-only moves) delivered to listeners."""

    workspace_id: uuid.UUID
    object_id: uuid.UUID
    actor_principal_id: uuid.UUID
    event_type: str
    payload: Mapping[str, JSONValue]


type ActivityListener = Callable[
    [AsyncSession, ActivityEnvelope | EphemeralEnvelope], Awaitable[None]
]

_listeners: list[ActivityListener] = []


def register_activity_listener(fn: ActivityListener) -> None:
    """Register an in-transaction listener invoked in registration order."""
    _listeners.append(fn)


def clear_activity_listeners() -> None:
    """Remove every registered listener (test isolation helper)."""
    _listeners.clear()


def _serialized_size(payload: Mapping[str, JSONValue]) -> int:
    """Return the byte length of ``payload`` rendered like PostgreSQL ``jsonb::text``.

    PostgreSQL's CHECK constraint measures ``jsonb::text`` which uses ``", "`` and ``": "``
    separators, so the application cap is measured the same way and is never looser.
    """
    rendered = json.dumps(dict(payload), separators=(", ", ": "), ensure_ascii=False)
    return len(rendered.encode("utf-8"))


async def _notify(session: AsyncSession, envelope: ActivityEnvelope | EphemeralEnvelope) -> None:
    """Invoke every listener in registration order; exceptions propagate (fail closed)."""
    for listener in tuple(_listeners):
        await listener(session, envelope)


async def record_activity(  # noqa: PLR0913  # Keyword-only API mandated by KB-P3-01a
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    object_id: uuid.UUID,
    actor_principal_id: uuid.UUID,
    event_type: ActivityEventType,
    payload: Mapping[str, JSONValue],
) -> uuid.UUID:
    """Append one activity row in the caller's transaction and notify listeners."""
    if _serialized_size(payload) > MAX_PAYLOAD_BYTES:
        msg = f"Activity payload exceeds {MAX_PAYLOAD_BYTES} bytes"
        raise ActivityPayloadTooLarge(msg)

    async with session.begin_nested():
        kind = (
            await session.execute(
                text("SELECT object_type::text FROM objects WHERE id = :oid"),
                {"oid": object_id},
            )
        ).scalar_one_or_none()
        if kind is None:
            msg = "Activity object is not visible"
            raise ActivityObjectNotFound(msg)

        activity_id = (
            await session.execute(
                text(
                    "SELECT append_activity("
                    "  :ws, :oid, CAST(:kind AS object_kind), :actor, :etype,"
                    "  CAST(:payload AS jsonb)"
                    ")"
                ),
                {
                    "ws": workspace_id,
                    "oid": object_id,
                    "kind": kind,
                    "actor": actor_principal_id,
                    "etype": event_type.value,
                    "payload": json.dumps(dict(payload), ensure_ascii=False),
                },
            )
        ).scalar_one()

        await _notify(
            session,
            ActivityEnvelope(
                activity_id=activity_id,
                workspace_id=workspace_id,
                object_id=object_id,
                actor_principal_id=actor_principal_id,
                event_type=event_type,
                category=EVENT_CATEGORY[event_type],
                payload=payload,
            ),
        )
    return cast("uuid.UUID", activity_id)


async def emit_ephemeral_event(session: AsyncSession, envelope: EphemeralEnvelope) -> None:
    """Deliver an ephemeral envelope to listeners without writing ``activity_records``."""
    await _notify(session, envelope)

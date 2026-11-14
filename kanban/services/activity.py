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
    AGENT_GATE = "AGENT_GATE"
    GATE = "AGENT_GATE"
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
    AGENT_DEFINITION_CREATED = "AGENT_DEFINITION_CREATED"
    AGENT_DEFINITION_UPDATED = "AGENT_DEFINITION_UPDATED"
    AGENT_DEFINITION_DELETED = "AGENT_DEFINITION_DELETED"
    ISSUE_CREATED = "ISSUE_CREATED"
    ISSUE_FIELD_CHANGED = "ISSUE_FIELD_CHANGED"
    ISSUE_DESCRIPTION_CHANGED = "ISSUE_DESCRIPTION_CHANGED"
    ISSUE_STATE_CHANGED = "ISSUE_STATE_CHANGED"
    ISSUE_LABELS_CHANGED = "ISSUE_LABELS_CHANGED"
    STATE_CREATED = "STATE_CREATED"
    STATE_UPDATED = "STATE_UPDATED"
    STATE_DELETED = "STATE_DELETED"
    PRIORITY_CREATED = "PRIORITY_CREATED"
    PRIORITY_UPDATED = "PRIORITY_UPDATED"
    PRIORITY_DELETED = "PRIORITY_DELETED"
    LABEL_CREATED = "LABEL_CREATED"
    LABEL_UPDATED = "LABEL_UPDATED"
    LABEL_DELETED = "LABEL_DELETED"
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    MODULE_CREATED = "MODULE_CREATED"
    MODULE_UPDATED = "MODULE_UPDATED"
    MODULE_DELETED = "MODULE_DELETED"
    ISSUE_MODULES_CHANGED = "ISSUE_MODULES_CHANGED"
    ISSUE_MODULE_ADDED = "ISSUE_MODULE_ADDED"
    ISSUE_MODULE_REMOVED = "ISSUE_MODULE_REMOVED"
    LOCAL_ADMIN_LOGIN_SUCCEEDED = "LOCAL_ADMIN_LOGIN_SUCCEEDED"
    LOCAL_ADMIN_LOGIN_FAILED = "LOCAL_ADMIN_LOGIN_FAILED"
    ASSIGNEE_ADDED = "ASSIGNEE_ADDED"
    ASSIGNEE_REMOVED = "ASSIGNEE_REMOVED"
    COMMENT_CREATED = "COMMENT_CREATED"
    COMMENT_EDITED = "COMMENT_EDITED"
    COMMENT_DELETED = "COMMENT_DELETED"
    MENTION_ACCESS_ACKNOWLEDGED = "MENTION_ACCESS_ACKNOWLEDGED"
    LINK_CREATED = "LINK_CREATED"
    LINK_DELETED = "LINK_DELETED"
    MFA_VERIFIED = "MFA_VERIFIED"
    MFA_FAILED = "MFA_FAILED"
    RECOVERY_CODE_USED = "RECOVERY_CODE_USED"
    RECOVERY_CODES_REGENERATED = "RECOVERY_CODES_REGENERATED"
    CYCLE_CREATED = "CYCLE_CREATED"
    CYCLE_UPDATED = "CYCLE_UPDATED"
    CYCLE_STATUS_CHANGED = "CYCLE_STATUS_CHANGED"
    CYCLE_ACTIVATED = "CYCLE_ACTIVATED"
    CYCLE_COMPLETED = "CYCLE_COMPLETED"
    CYCLE_DELETED = "CYCLE_DELETED"
    ISSUE_CYCLE_CHANGED = "ISSUE_CYCLE_CHANGED"
    VIEW_CREATED = "VIEW_CREATED"
    VIEW_UPDATED = "VIEW_UPDATED"
    VIEW_DELETED = "VIEW_DELETED"
    ISSUE_RANK_MOVED = "ISSUE_RANK_MOVED"
    ISSUE_MOVED = "ISSUE_MOVED"
    WIP_HARD_LIMIT_OVERRIDDEN = "WIP_HARD_LIMIT_OVERRIDDEN"
    WIP_LIMIT_OVERRIDDEN = "WIP_LIMIT_OVERRIDDEN"
    BOARD_COLUMN_REBALANCED = "BOARD_COLUMN_REBALANCED"
    ISSUE_ARCHIVED = "ISSUE_ARCHIVED"
    ISSUE_UNARCHIVED = "ISSUE_UNARCHIVED"
    ISSUE_TRASHED = "ISSUE_TRASHED"
    ISSUE_RESTORED = "ISSUE_RESTORED"
    ISSUE_PURGED = "ISSUE_PURGED"
    CREATOR_OVERRIDDEN = "CREATOR_OVERRIDDEN"
    MCP_KEY_MINTED = "MCP_KEY_MINTED"
    MCP_KEY_REVOKED = "MCP_KEY_REVOKED"
    STICKY_CREATED = "STICKY_CREATED"
    STICKY_UPDATED = "STICKY_UPDATED"
    STICKY_RECOLORED = "STICKY_RECOLORED"
    STICKY_PROMOTION_SNOOZED = "STICKY_PROMOTION_SNOOZED"
    STICKY_PROMOTED_TO_DOC = "STICKY_PROMOTED_TO_DOC"
    STICKY_UNARCHIVED_COPY = "STICKY_UNARCHIVED_COPY"
    STICKY_TRASHED = "STICKY_TRASHED"
    WEBAUTHN_REGISTERED = "WEBAUTHN_REGISTERED"
    WEBAUTHN_VERIFIED = "WEBAUTHN_VERIFIED"
    WEBAUTHN_DELETED = "WEBAUTHN_DELETED"
    WEBAUTHN_SIGN_COUNT_REGRESSION = "WEBAUTHN_SIGN_COUNT_REGRESSION"
    ISSUE_COPIED = "ISSUE_COPIED"
    SYNC_HOOK_REJECTED = "SYNC_HOOK_REJECTED"
    HOOK_FAIL_OPEN_WARN = "HOOK_FAIL_OPEN_WARN"
    GATE_PENDING = "GATE_PENDING"
    GATE_APPROVED = "GATE_APPROVED"
    GATE_REJECTED = "GATE_REJECTED"
    GATE_TIMED_OUT = "GATE_TIMED_OUT"
    GATE_CANCELLED = "GATE_CANCELLED"
    CUSTOM_FIELD_CREATED = "CUSTOM_FIELD_CREATED"
    CUSTOM_FIELD_UPDATED = "CUSTOM_FIELD_UPDATED"
    CUSTOM_FIELD_DELETED = "CUSTOM_FIELD_DELETED"
    EMERGENCY_BREAK_GLASS_INVOKED = "EMERGENCY_BREAK_GLASS_INVOKED"


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
        ActivityEventType.AGENT_DEFINITION_CREATED: ActivityCategory.SYSTEM,
        ActivityEventType.AGENT_DEFINITION_UPDATED: ActivityCategory.SYSTEM,
        ActivityEventType.AGENT_DEFINITION_DELETED: ActivityCategory.SYSTEM,
        ActivityEventType.ISSUE_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_FIELD_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_DESCRIPTION_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_STATE_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_LABELS_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.STATE_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.STATE_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.STATE_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.PRIORITY_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.PRIORITY_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.PRIORITY_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.LABEL_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.LABEL_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.LABEL_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.ATTACHMENT_UPLOADED: ActivityCategory.HISTORY,
        ActivityEventType.MODULE_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.MODULE_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.MODULE_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_MODULES_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_MODULE_ADDED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_MODULE_REMOVED: ActivityCategory.HISTORY,
        ActivityEventType.LOCAL_ADMIN_LOGIN_SUCCEEDED: ActivityCategory.SYSTEM,
        ActivityEventType.LOCAL_ADMIN_LOGIN_FAILED: ActivityCategory.SYSTEM,
        ActivityEventType.ASSIGNEE_ADDED: ActivityCategory.HISTORY,
        ActivityEventType.ASSIGNEE_REMOVED: ActivityCategory.HISTORY,
        ActivityEventType.COMMENT_CREATED: ActivityCategory.COMMENT,
        ActivityEventType.COMMENT_EDITED: ActivityCategory.COMMENT,
        ActivityEventType.COMMENT_DELETED: ActivityCategory.COMMENT,
        ActivityEventType.MENTION_ACCESS_ACKNOWLEDGED: ActivityCategory.COMMENT,
        ActivityEventType.LINK_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.LINK_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.MFA_VERIFIED: ActivityCategory.SYSTEM,
        ActivityEventType.MFA_FAILED: ActivityCategory.SYSTEM,
        ActivityEventType.RECOVERY_CODE_USED: ActivityCategory.SYSTEM,
        ActivityEventType.RECOVERY_CODES_REGENERATED: ActivityCategory.SYSTEM,
        ActivityEventType.CYCLE_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.CYCLE_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.CYCLE_STATUS_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.CYCLE_ACTIVATED: ActivityCategory.HISTORY,
        ActivityEventType.CYCLE_COMPLETED: ActivityCategory.HISTORY,
        ActivityEventType.CYCLE_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_CYCLE_CHANGED: ActivityCategory.HISTORY,
        ActivityEventType.VIEW_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.VIEW_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.VIEW_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_RANK_MOVED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_MOVED: ActivityCategory.HISTORY,
        ActivityEventType.WIP_HARD_LIMIT_OVERRIDDEN: ActivityCategory.HISTORY,
        ActivityEventType.WIP_LIMIT_OVERRIDDEN: ActivityCategory.HISTORY,
        ActivityEventType.BOARD_COLUMN_REBALANCED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_ARCHIVED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_UNARCHIVED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_TRASHED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_RESTORED: ActivityCategory.HISTORY,
        ActivityEventType.ISSUE_PURGED: ActivityCategory.HISTORY,
        ActivityEventType.CREATOR_OVERRIDDEN: ActivityCategory.HISTORY,
        ActivityEventType.MCP_KEY_MINTED: ActivityCategory.SYSTEM,
        ActivityEventType.MCP_KEY_REVOKED: ActivityCategory.SYSTEM,
        ActivityEventType.STICKY_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_RECOLORED: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_PROMOTION_SNOOZED: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_PROMOTED_TO_DOC: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_UNARCHIVED_COPY: ActivityCategory.HISTORY,
        ActivityEventType.STICKY_TRASHED: ActivityCategory.HISTORY,
        ActivityEventType.WEBAUTHN_REGISTERED: ActivityCategory.SYSTEM,
        ActivityEventType.WEBAUTHN_VERIFIED: ActivityCategory.SYSTEM,
        ActivityEventType.WEBAUTHN_DELETED: ActivityCategory.SYSTEM,
        ActivityEventType.WEBAUTHN_SIGN_COUNT_REGRESSION: ActivityCategory.SYSTEM,
        ActivityEventType.ISSUE_COPIED: ActivityCategory.HISTORY,
        ActivityEventType.SYNC_HOOK_REJECTED: ActivityCategory.AGENT_GATE,
        ActivityEventType.HOOK_FAIL_OPEN_WARN: ActivityCategory.AGENT_GATE,
        ActivityEventType.GATE_PENDING: ActivityCategory.AGENT_GATE,
        ActivityEventType.GATE_APPROVED: ActivityCategory.AGENT_GATE,
        ActivityEventType.GATE_REJECTED: ActivityCategory.AGENT_GATE,
        ActivityEventType.GATE_TIMED_OUT: ActivityCategory.AGENT_GATE,
        ActivityEventType.GATE_CANCELLED: ActivityCategory.AGENT_GATE,
        ActivityEventType.CUSTOM_FIELD_CREATED: ActivityCategory.HISTORY,
        ActivityEventType.CUSTOM_FIELD_UPDATED: ActivityCategory.HISTORY,
        ActivityEventType.CUSTOM_FIELD_DELETED: ActivityCategory.HISTORY,
        ActivityEventType.EMERGENCY_BREAK_GLASS_INVOKED: ActivityCategory.SYSTEM,
    }
)


@dataclass(frozen=True, slots=True)
class ActivityEnvelope:
    """Persisted activity event delivered to in-transaction listeners."""

    activity_id: uuid.UUID
    workspace_id: uuid.UUID
    object_id: uuid.UUID | None
    actor_principal_id: uuid.UUID | None
    event_type: ActivityEventType
    category: ActivityCategory
    payload: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class EphemeralEnvelope:
    """Non-persisted event (for example rank-only moves) delivered to listeners."""

    workspace_id: uuid.UUID
    object_id: uuid.UUID | None
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
    object_id: uuid.UUID | None = None,
    actor_principal_id: uuid.UUID | None = None,
    event_type: ActivityEventType,
    payload: Mapping[str, JSONValue],
) -> uuid.UUID:
    """Append one activity row in the caller's transaction and notify listeners."""
    if _serialized_size(payload) > MAX_PAYLOAD_BYTES:
        msg = f"Activity payload exceeds {MAX_PAYLOAD_BYTES} bytes"
        raise ActivityPayloadTooLarge(msg)

    async with session.begin_nested():
        kind: str | None = None
        if object_id is not None:
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

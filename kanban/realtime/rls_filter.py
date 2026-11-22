# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Delivery-time Row-Level Security (RLS) authorization and redaction filter (KB-P3-16)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence
    from collections.abc import Set as AbstractSet

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "EXTERNAL_COLLABORATOR_REDACTED",
    "NOTIFICATION_TOPICS",
    "OutboxEventLike",
    "authorize_event_recipients",
    "redact_event_payload",
]

NOTIFICATION_TOPICS: Final[frozenset[str]] = frozenset(
    {
        "notification.created",
        "notification.read",
        "notification.read_all",
    }
)

EXTERNAL_COLLABORATOR_REDACTED: Final[dict[str, Any]] = {
    "redacted": True,
    "label": "1 External Collaborator",
}


@runtime_checkable
class OutboxEventLike(Protocol):
    """Protocol matching domain outbox events and envelopes."""

    workspace_id: uuid.UUID
    object_id: uuid.UUID | None
    project_id: uuid.UUID | None


def redact_event_payload(payload: dict[str, Any], *, is_visible: bool = True) -> dict[str, Any]:
    """Redact actor metadata in outbox event payload when outside recipient visibility boundary.

    Spec S3.4: Replaces actor object with standard {"redacted": True, "label": "1 External
    Collaborator"} placeholder and eliminates actor identifiers from the top level.
    """
    if is_visible:
        return dict(payload)

    redacted = dict(payload)
    if "actor" in redacted:
        redacted["actor"] = dict(EXTERNAL_COLLABORATOR_REDACTED)

    # Cleanse any direct actor identifier leakage
    for sensitive_key in (
        "actor_principal_id",
        "actor_id",
        "actor_email",
        "actor_handle",
        "actor_name",
    ):
        redacted.pop(sensitive_key, None)

    return redacted


def _filter_notification_candidates(
    event: OutboxEventLike | object,
    candidate_principals: Sequence[uuid.UUID] | AbstractSet[uuid.UUID],
) -> set[uuid.UUID]:
    """Intersect candidates with recipient_principal_id for notification events."""
    topic: str | None = getattr(event, "topic", None)
    raw_payload: Any = getattr(event, "payload", None)
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}

    is_notif = (
        isinstance(topic, str)
        and (topic in NOTIFICATION_TOPICS or topic.startswith("notification."))
    ) or "recipient_principal_id" in payload
    if not is_notif:
        return set(candidate_principals)

    recipient_raw = payload.get("recipient_principal_id")
    if not recipient_raw:
        return set()
    try:
        recipient_uuid = uuid.UUID(str(recipient_raw))
    except (ValueError, TypeError, AttributeError):
        return set()
    return set(candidate_principals) & {recipient_uuid}


async def authorize_event_recipients(
    session: AsyncSession,
    event: OutboxEventLike | object,
    candidate_principals: Sequence[uuid.UUID] | AbstractSet[uuid.UUID],
) -> set[uuid.UUID]:
    """Verify delivery-time VIEW access for candidate principals on an event's target object.

    Spec S3.3 / KB-P3-16: Runs one batched query against effective_resource_access evaluating
    (allow_mask & 1) = 1 AND (deny_mask & 1) = 0 on event.object_id (or project_id) for the
    event's workspace.
    """
    if not candidate_principals:
        return set()

    candidates_set = _filter_notification_candidates(event, candidate_principals)
    if not candidates_set:
        return set()

    object_id: uuid.UUID | None = getattr(event, "object_id", None)
    workspace_id: uuid.UUID | None = getattr(event, "workspace_id", None)
    project_id: uuid.UUID | None = getattr(event, "project_id", None)

    target_id = object_id if object_id is not None else project_id
    if target_id is None:
        # Event is not bound to a specific object or project; return remaining candidate principals.
        return candidates_set

    if workspace_id is None:
        ws_val = await session.scalar(
            text("SELECT workspace_id FROM objects WHERE id = :obj_id"),
            {"obj_id": target_id},
        )
        if ws_val is not None:
            workspace_id = uuid.UUID(str(ws_val))

    authorized: set[uuid.UUID] = set()
    ws_str = str(workspace_id) if workspace_id is not None else ""

    for candidate in candidates_set:
        if ws_str:
            await session.execute(
                text(
                    "SELECT set_config('app.workspace_id', :ws_id, true), "
                    "       set_config('app.principal_id', :pid, true)"
                ),
                {"ws_id": ws_str, "pid": str(candidate)},
            )
        else:
            await session.execute(
                text("SELECT set_config('app.principal_id', :pid, true)"),
                {"pid": str(candidate)},
            )

        has_view = bool(
            await session.scalar(
                text("SELECT app_has_object_capability(:obj_id, 1)"),
                {"obj_id": target_id},
            )
        )

        if has_view:
            authorized.add(candidate)

    return authorized

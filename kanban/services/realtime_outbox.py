"""Realtime domain outbox activity listener.

Translates domain activity events (issues, comments, stickies, links) into
transactional OutboxEvent rows within the same database transaction.
Ensures zero mutation of Issue.updated_at or resource versions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from database.models import Issue, Project
from database.outbox.broker import enqueue_outbox_event
from kanban.services.activity import (
    ActivityEnvelope,
    ActivityEventType,
    EphemeralEnvelope,
    register_activity_listener,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("kanban.services.realtime_outbox")

_registered = False

_TOPIC_MAP: dict[str, tuple[str, bool]] = {
    ActivityEventType.ISSUE_CREATED.value: ("issue.created", False),
    ActivityEventType.ISSUE_STATE_CHANGED.value: ("issue.transitioned", False),
    ActivityEventType.WORK_COMPLETED.value: ("issue.transitioned", False),
    ActivityEventType.ISSUE_RANK_MOVED.value: ("issue.moved", False),
    ActivityEventType.ISSUE_MOVED.value: ("issue.moved", False),
    ActivityEventType.ISSUE_TRASHED.value: ("issue.deleted", False),
    ActivityEventType.ISSUE_PURGED.value: ("issue.deleted", False),
    ActivityEventType.ISSUE_FIELD_CHANGED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_DESCRIPTION_CHANGED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_LABELS_CHANGED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_MODULES_CHANGED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_MODULE_ADDED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_MODULE_REMOVED.value: ("issue.updated", False),
    ActivityEventType.ASSIGNEE_ADDED.value: ("issue.updated", False),
    ActivityEventType.ASSIGNEE_REMOVED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_CYCLE_CHANGED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_ARCHIVED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_UNARCHIVED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_RESTORED.value: ("issue.updated", False),
    ActivityEventType.ISSUE_COPIED.value: ("issue.updated", False),
    ActivityEventType.LINK_CREATED.value: ("issue.updated", False),
    ActivityEventType.LINK_DELETED.value: ("issue.updated", False),
    ActivityEventType.WIP_HARD_LIMIT_OVERRIDDEN.value: ("issue.updated", False),
    ActivityEventType.WIP_LIMIT_OVERRIDDEN.value: ("issue.updated", False),
    ActivityEventType.COMMENT_CREATED.value: ("comment.created", False),
    ActivityEventType.COMMENT_EDITED.value: ("comment.updated", False),
    "COMMENT_UPDATED": ("comment.updated", False),
    ActivityEventType.COMMENT_DELETED.value: ("comment.deleted", False),
    ActivityEventType.STICKY_CREATED.value: ("sticky.created", True),
    ActivityEventType.STICKY_UNARCHIVED_COPY.value: ("sticky.created", True),
    ActivityEventType.STICKY_UPDATED.value: ("sticky.updated", True),
    ActivityEventType.STICKY_RECOLORED.value: ("sticky.updated", True),
    ActivityEventType.STICKY_PROMOTED_TO_DOC.value: ("sticky.promoted", True),
    "STICKY_PROMOTED": ("sticky.promoted", True),
    ActivityEventType.STICKY_TRASHED.value: ("sticky.deleted", True),
    "STICKY_DELETED": ("sticky.deleted", True),
}


def _extract_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    return None


async def _resolve_issue_context(
    session: AsyncSession,
    object_id: UUID | None,
    raw_payload: dict[str, Any],
    ev_type: str,
) -> tuple[UUID | None, str | None]:
    project_id: UUID | None = None
    issue_key: str | None = None

    if object_id is not None:
        cached_issue = cast("Any", session.identity_map).get((Issue, (object_id,)))
        if cached_issue is not None:
            project_id = cached_issue.project_id
            seq_id = getattr(cached_issue, "sequence_id", None)
            if seq_id is not None:
                cached_proj = cast("Any", session.identity_map).get((Project, (project_id,)))
                if cached_proj is not None and getattr(cached_proj, "identifier", None):
                    issue_key = f"{cached_proj.identifier}-{seq_id}"

    if issue_key is None and object_id is not None:
        stmt = (
            select(Issue.project_id, Issue.sequence_id, Project.identifier)
            .join(Project, Project.id == Issue.project_id)
            .where(Issue.id == object_id)
        )
        row = (await session.execute(stmt)).first()
        if row is not None:
            project_id = row[0]
            issue_key = f"{row[2]}-{row[1]}"

    if issue_key is None:
        issue_key = _extract_string(raw_payload, "key", "issue_key", "issueKey")

    if (
        project_id is None
        and object_id is not None
        and ev_type == ActivityEventType.ISSUE_PURGED.value
    ):
        project_id = object_id

    return project_id, issue_key


async def handle_activity_event(
    session: AsyncSession, envelope: ActivityEnvelope | EphemeralEnvelope
) -> None:
    """In-transaction activity listener translating mutations into outbox events."""
    ev_type = (
        envelope.event_type.value
        if hasattr(envelope.event_type, "value")
        else str(envelope.event_type)
    )

    mapping = _TOPIC_MAP.get(ev_type)
    if mapping is None:
        return

    topic, is_sticky = mapping
    workspace_id = envelope.workspace_id
    raw_payload = dict(envelope.payload) if envelope.payload else {}

    if is_sticky:
        sticky_payload = {
            "id": str(envelope.object_id) if envelope.object_id else "",
            **raw_payload,
        }
        await enqueue_outbox_event(
            session,
            workspace_id=workspace_id,
            project_id=None,
            object_id=envelope.object_id,
            topic=topic,
            payload=sticky_payload,
        )
        return

    project_id, issue_key = await _resolve_issue_context(
        session, envelope.object_id, raw_payload, ev_type
    )

    project_key = (
        issue_key.split("-", 1)[0]
        if issue_key and "-" in issue_key
        else _extract_string(raw_payload, "project_key", "projectKey") or ""
    )

    outbox_payload = {
        "key": issue_key or "",
        "issue_key": issue_key or "",
        "project_key": project_key,
        **{k: v for k, v in raw_payload.items() if k not in ("key", "issue_key", "project_key")},
    }

    await enqueue_outbox_event(
        session,
        workspace_id=workspace_id,
        project_id=project_id,
        object_id=envelope.object_id,
        topic=topic,
        payload=outbox_payload,
    )


def register_realtime_outbox_listener() -> None:
    """Register the realtime outbox activity listener idempotently."""
    global _registered  # noqa: PLW0603
    if not _registered:
        register_activity_listener(handle_activity_event)
        _registered = True


def clear_realtime_outbox_listener() -> None:
    """Reset registration status for hermetic test suites."""
    global _registered  # noqa: PLW0603
    _registered = False

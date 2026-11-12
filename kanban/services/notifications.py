# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Notifications service and activity listener (S7.2 8l, S2.2, S2.4; KB-P3-06).

Manages user notifications, keyset pagination, read state, auto-subscriptions on activity,
and reliable notification delivery via outbox_events without sensitive data leakage.
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, tuple_, update

from database.models import (
    ActivityRecord,
    EffectiveResourceAccess,
    Issue,
    IssueSubscription,
    Notification,
    ObjectRecord,
    OutboxEvent,
    Principal,
    Project,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.notifications import (
    NotificationActorSummary,
    NotificationIssueSummary,
    NotificationItem,
    NotificationListResponse,
)
from kanban.services.activity import (
    ActivityEnvelope,
    ActivityEventType,
    EphemeralEnvelope,
    _listeners,
    register_activity_listener,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_RECIPIENTS: Final[int] = 500
MAX_PAGE_LIMIT: Final[int] = 100


def encode_cursor(created_at: datetime, notif_id: uuid.UUID) -> str:
    """Encode (created_at, id) into a URL-safe base64 keyset cursor."""
    raw = f"{created_at.isoformat()}|{notif_id}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii")


def decode_cursor(cursor_str: str) -> tuple[datetime, uuid.UUID]:
    """Decode a URL-safe base64 keyset cursor into (created_at, id)."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("ascii")).decode("ascii")
        dt_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(dt_str), uuid.UUID(id_str)
    except Exception as exc:
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Invalid Cursor",
            detail="Malformed or invalid pagination cursor",
        ) from exc


async def list_notifications(
    session: AsyncSession,
    caller: PrincipalContext,
    *,
    unread: bool = False,
    cursor: str | None = None,
    limit: int = 30,
) -> NotificationListResponse:
    """List notifications for the calling user with keyset pagination."""
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ProblemException(
            code="INVALID_LIMIT",
            status=422,
            title="Invalid Limit",
            detail=f"Limit must be between 1 and {MAX_PAGE_LIMIT}",
        )

    stmt = (
        select(
            Notification,
            Issue.id.label("issue_id"),
            Issue.sequence_id,
            Issue.summary,
            Project.identifier.label("proj_ident"),
            ObjectRecord.canonical_key.label("actor_handle"),
            Principal.display_name.label("actor_display_name"),
        )
        .join(Issue, Issue.id == Notification.issue_id)
        .join(Project, Project.id == Issue.project_id)
        .outerjoin(ActivityRecord, ActivityRecord.id == Notification.activity_record_id)
        .outerjoin(Principal, Principal.id == ActivityRecord.actor_id)
        .outerjoin(ObjectRecord, ObjectRecord.id == ActivityRecord.actor_id)
        .where(Notification.recipient_principal_id == caller.principal_id)
    )

    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))

    if cursor:
        cursor_dt, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Notification.created_at, Notification.id) < (cursor_dt, cursor_id))

    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)

    result = await session.execute(stmt)
    rows = result.all()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items: list[NotificationItem] = []
    for r in page_rows:
        notif = r[0]
        issue_id = r[1]
        seq_id = r[2]
        summary = r[3]
        proj_ident = r[4]
        handle = r[5]
        display_name = r[6]

        actor_summary = (
            NotificationActorSummary(handle=handle, display_name=display_name)
            if handle is not None or display_name is not None
            else NotificationActorSummary(redacted=True, label="1 External Collaborator")
        )

        items.append(
            NotificationItem(
                id=notif.id,
                issue=NotificationIssueSummary(
                    id=issue_id,
                    key=f"{proj_ident}-{seq_id}",
                    summary=summary,
                ),
                event_type=notif.event_type,
                actor=actor_summary,
                created_at=notif.created_at,
                read_at=notif.read_at,
            )
        )

    next_cursor: str | None = None
    if has_more and items:
        last_item = items[-1]
        next_cursor = encode_cursor(last_item.created_at, last_item.id)

    return NotificationListResponse(items=items, next_cursor=next_cursor)


async def mark_notification_read(
    session: AsyncSession, caller: PrincipalContext, notification_id: uuid.UUID
) -> None:
    """Mark a single notification as read if owned by the caller."""
    stmt = select(Notification).where(Notification.id == notification_id)
    notif = (await session.execute(stmt)).scalars().first()

    if notif is None or notif.recipient_principal_id != caller.principal_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=404,
            title="Notification Not Found",
            detail="Notification not found",
        )

    if notif.read_at is None:
        notif.read_at = datetime.now(UTC)
        await session.flush()


async def mark_all_read(session: AsyncSession, caller: PrincipalContext) -> int:
    """Mark all unread notifications for the caller as read and return marked count."""
    now = datetime.now(UTC)
    stmt = (
        update(Notification)
        .where(
            Notification.recipient_principal_id == caller.principal_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    result = await session.execute(stmt)
    await session.flush()
    return int(result.rowcount)


async def handle_activity_event(
    session: AsyncSession, envelope: ActivityEnvelope | EphemeralEnvelope
) -> None:
    """In-transaction activity listener for auto-subscriptions and notification dispatch."""
    if isinstance(envelope, EphemeralEnvelope):
        return
    if envelope.object_id is None:
        return

    # Check if target object is an issue
    issue_stmt = select(Issue.id, Issue.project_id, Issue.created_by_id).where(
        Issue.id == envelope.object_id
    )
    issue_row = (await session.execute(issue_stmt)).first()
    if issue_row is None:
        return

    issue_id, project_id, created_by_id = issue_row

    # 1. Auto-subscribe rules
    await _handle_auto_subscribe(session, envelope, issue_id, created_by_id)

    # 2. Notification delivery via outbox
    await _deliver_notifications(session, envelope, issue_id, project_id)


async def _handle_auto_subscribe(
    session: AsyncSession,
    envelope: ActivityEnvelope,
    issue_id: uuid.UUID,
    created_by_id: uuid.UUID | None,
) -> None:
    """Evaluate auto-subscribe rules for creator, assignee, and mentioned viewers."""
    ev_type = (
        envelope.event_type.value
        if hasattr(envelope.event_type, "value")
        else str(envelope.event_type)
    )

    if ev_type == ActivityEventType.ISSUE_CREATED.value:
        await _handle_creator_subscribe(session, envelope, issue_id, created_by_id)
    elif ev_type == ActivityEventType.ASSIGNEE_ADDED.value:
        await _handle_assignee_subscribe(session, envelope, issue_id)
    elif ev_type == ActivityEventType.COMMENT_CREATED.value:
        await _handle_mention_subscribe(session, envelope, issue_id)


async def _handle_creator_subscribe(
    session: AsyncSession,
    envelope: ActivityEnvelope,
    issue_id: uuid.UUID,
    created_by_id: uuid.UUID | None,
) -> None:
    """Auto-subscribe the creator on issue creation."""
    creator_id = created_by_id if created_by_id is not None else envelope.actor_principal_id
    if creator_id is not None:
        await _auto_subscribe_principal(
            session, issue_id, creator_id, envelope.workspace_id, "CREATOR"
        )


async def _handle_assignee_subscribe(
    session: AsyncSession,
    envelope: ActivityEnvelope,
    issue_id: uuid.UUID,
) -> None:
    """Auto-subscribe an added principal assignee holding VIEW capability."""
    if envelope.payload.get("kind") != "principal" or not envelope.payload.get("principal_id"):
        return
    try:
        assignee_pid = uuid.UUID(str(envelope.payload["principal_id"]))
        if await _principal_has_view(session, assignee_pid, issue_id):
            await _auto_subscribe_principal(
                session, issue_id, assignee_pid, envelope.workspace_id, "ASSIGNEE"
            )
    except (ValueError, TypeError):
        pass


async def _handle_mention_subscribe(
    session: AsyncSession,
    envelope: ActivityEnvelope,
    issue_id: uuid.UUID,
) -> None:
    """Auto-subscribe mentioned users holding VIEW capability."""
    mentioned = envelope.payload.get("mentioned_principal_ids") or []
    if not isinstance(mentioned, list):
        return
    for pid_val in mentioned:
        try:
            m_pid = uuid.UUID(str(pid_val))
            if await _principal_has_view(session, m_pid, issue_id):
                await _auto_subscribe_principal(
                    session, issue_id, m_pid, envelope.workspace_id, "MENTION"
                )
        except (ValueError, TypeError):
            continue


async def _principal_has_view(
    session: AsyncSession, principal_id: uuid.UUID, issue_id: uuid.UUID
) -> bool:
    """Return True if principal currently holds VIEW capability on the issue."""
    era_stmt = select(EffectiveResourceAccess.principal_id).where(
        EffectiveResourceAccess.object_id == issue_id,
        EffectiveResourceAccess.principal_id == principal_id,
        (EffectiveResourceAccess.allow_mask.op("&")(1) == 1),
        (EffectiveResourceAccess.deny_mask.op("&")(1) == 0),
    )
    return (await session.execute(era_stmt)).first() is not None


async def _auto_subscribe_principal(
    session: AsyncSession,
    issue_id: uuid.UUID,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    source: str,
) -> None:
    """Subscribe principal if no subscription or tombstone exists."""
    sub_stmt = select(IssueSubscription.unsubscribed_at).where(
        IssueSubscription.issue_id == issue_id,
        IssueSubscription.principal_id == principal_id,
    )
    existing = (await session.execute(sub_stmt)).first()

    if existing is not None:
        # If tombstone (unsubscribed_at is not null), do not auto-resubscribe
        return

    sub = IssueSubscription(
        issue_id=issue_id,
        principal_id=principal_id,
        workspace_id=workspace_id,
        source=source,
        is_muted=False,
        muted_event_types=[],
        unsubscribed_at=None,
    )
    session.add(sub)
    await session.flush()


async def _deliver_notifications(
    session: AsyncSession,
    envelope: ActivityEnvelope,
    issue_id: uuid.UUID,
    project_id: uuid.UUID | None,
) -> None:
    """Deliver notifications and outbox_events to eligible subscribers holding VIEW."""
    sub_stmt = (
        select(IssueSubscription.principal_id, IssueSubscription.muted_event_types)
        .where(
            IssueSubscription.issue_id == issue_id,
            IssueSubscription.unsubscribed_at.is_(None),
        )
        .order_by(IssueSubscription.created_at.asc())
    )
    subscribers = (await session.execute(sub_stmt)).all()

    candidates: list[uuid.UUID] = []
    for sub_pid, muted_types in subscribers:
        # Exclude actor (actor never notifies self)
        if envelope.actor_principal_id and sub_pid == envelope.actor_principal_id:
            continue
        # Exclude muted event types
        if muted_types and envelope.event_type in muted_types:
            continue
        candidates.append(sub_pid)

    if not candidates:
        return

    # Check live VIEW capability in effective_resource_access
    era_stmt = select(EffectiveResourceAccess.principal_id).where(
        EffectiveResourceAccess.object_id == issue_id,
        EffectiveResourceAccess.principal_id.in_(candidates),
        (EffectiveResourceAccess.allow_mask.op("&")(1) == 1),
        (EffectiveResourceAccess.deny_mask.op("&")(1) == 0),
    )
    authorized_set = set((await session.execute(era_stmt)).scalars().all())
    eligible = [p for p in candidates if p in authorized_set]

    if not eligible:
        return

    if len(eligible) > MAX_NOTIFICATION_RECIPIENTS:
        logger.warning(
            "Max notification recipients exceeded for issue %s: %d > %d",
            issue_id,
            len(eligible),
            MAX_NOTIFICATION_RECIPIENTS,
        )
        eligible = eligible[:MAX_NOTIFICATION_RECIPIENTS]

    now = datetime.now(UTC)
    for rec_id in eligible:
        notif_id = uuid.uuid4()

        notif = Notification(
            id=notif_id,
            workspace_id=envelope.workspace_id,
            recipient_principal_id=rec_id,
            issue_id=issue_id,
            activity_record_id=envelope.activity_id,
            event_type=(
                envelope.event_type.value
                if hasattr(envelope.event_type, "value")
                else str(envelope.event_type)
            ),
            created_at=now,
            read_at=None,
        )
        session.add(notif)

        # Transactional outbox event (payload contains ids only, zero issue summary/body text)
        outbox_ev = OutboxEvent(
            workspace_id=envelope.workspace_id,
            project_id=project_id,
            object_id=issue_id,
            topic="notification.created",
            payload={
                "topic": "notification.created",
                "recipient_principal_id": str(rec_id),
                "notification_id": str(notif_id),
            },
        )
        session.add(outbox_ev)

    await session.flush()


def register_notifications_listener() -> None:
    """Register the notifications activity listener if not already registered."""
    if handle_activity_event not in _listeners:
        register_activity_listener(handle_activity_event)

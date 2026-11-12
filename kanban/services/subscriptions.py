# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue subscriptions service (S7.2 8l, KB-P3-06).

Manages personal issue subscriptions, per-event mute lists, and unsubscribed_at tombstones.
Zero activity records are emitted for personal subscription preferences.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from database.models import IssueSubscription
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.notifications import (
    SubscriptionPatch,
    SubscriptionPut,
    SubscriptionResponse,
)
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext


async def get_subscription(
    session: AsyncSession, caller: PrincipalContext, issue_ref: str
) -> SubscriptionResponse:
    """Return the caller's subscription status for the referenced issue."""
    issue = await resolve_issue_ref(session, caller, issue_ref)

    stmt = select(IssueSubscription).where(
        IssueSubscription.issue_id == issue.id,
        IssueSubscription.principal_id == caller.principal_id,
    )
    sub = (await session.execute(stmt)).scalars().first()

    if sub is None or sub.unsubscribed_at is not None:
        return SubscriptionResponse(
            subscribed=False,
            muted_event_types=[],
            source=None,
        )

    return SubscriptionResponse(
        subscribed=True,
        muted_event_types=list(sub.muted_event_types or []),
        source=sub.source.lower(),
    )


async def subscribe_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    payload: SubscriptionPut | None = None,
) -> SubscriptionResponse:
    """Idempotently subscribe the caller to the referenced issue."""
    issue = await resolve_issue_ref(session, caller, issue_ref)

    stmt = select(IssueSubscription).where(
        IssueSubscription.issue_id == issue.id,
        IssueSubscription.principal_id == caller.principal_id,
    )
    sub = (await session.execute(stmt)).scalars().first()

    muted = payload.muted_event_types if payload and payload.muted_event_types is not None else None

    if sub is not None:
        sub.unsubscribed_at = None
        sub.source = "MANUAL"
        if muted is not None:
            sub.muted_event_types = list(muted)
    else:
        sub = IssueSubscription(
            issue_id=issue.id,
            principal_id=caller.principal_id,
            workspace_id=issue.workspace_id,
            source="MANUAL",
            is_muted=False,
            muted_event_types=list(muted or []),
            unsubscribed_at=None,
        )
        session.add(sub)

    await session.flush()
    return SubscriptionResponse(
        subscribed=True,
        muted_event_types=list(sub.muted_event_types or []),
        source=sub.source.lower(),
    )


async def patch_subscription(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    payload: SubscriptionPatch,
) -> SubscriptionResponse:
    """Update muted event types for an active subscription."""
    issue = await resolve_issue_ref(session, caller, issue_ref)

    stmt = select(IssueSubscription).where(
        IssueSubscription.issue_id == issue.id,
        IssueSubscription.principal_id == caller.principal_id,
    )
    sub = (await session.execute(stmt)).scalars().first()

    if sub is None or sub.unsubscribed_at is not None:
        raise ProblemException(
            code="NOT_SUBSCRIBED",
            status=409,
            title="Not Subscribed",
            detail="User is not subscribed to this issue",
        )

    sub.muted_event_types = list(payload.muted_event_types)
    await session.flush()

    return SubscriptionResponse(
        subscribed=True,
        muted_event_types=list(sub.muted_event_types or []),
        source=sub.source.lower(),
    )


async def unsubscribe_issue(
    session: AsyncSession, caller: PrincipalContext, issue_ref: str
) -> None:
    """Idempotently unsubscribe the caller, recording a tombstone to prevent auto-resubscribe."""
    issue = await resolve_issue_ref(session, caller, issue_ref)

    stmt = select(IssueSubscription).where(
        IssueSubscription.issue_id == issue.id,
        IssueSubscription.principal_id == caller.principal_id,
    )
    sub = (await session.execute(stmt)).scalars().first()

    now = datetime.now(UTC)
    if sub is not None:
        sub.unsubscribed_at = now
    else:
        sub = IssueSubscription(
            issue_id=issue.id,
            principal_id=caller.principal_id,
            workspace_id=issue.workspace_id,
            source="MANUAL",
            is_muted=False,
            muted_event_types=[],
            unsubscribed_at=now,
        )
        session.add(sub)

    await session.flush()

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for notifications and subscriptions (KB-P3-06)."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import select, text

from database.models import (
    Issue,
    IssueSubscription,
    Notification,
    OutboxEvent,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.notifications import (
    SubscriptionPut,
)
from kanban.services.activity import (
    ActivityCategory,
    ActivityEnvelope,
    ActivityEventType,
    EphemeralEnvelope,
    clear_activity_listeners,
    record_activity,
)
from kanban.services.notifications import (
    decode_cursor,
    handle_activity_event,
    list_notifications,
    mark_all_read,
    mark_notification_read,
    register_notifications_listener,
)
from kanban.services.subscriptions import (
    subscribe_issue,
    unsubscribe_issue,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_role_binding,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.committed_db


async def _setup_env(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str]:
    """Seed workspace, creator, member, project, and issue."""
    ws_id = await create_workspace(session, name=f"WS-{uuid.uuid4().hex[:8]}")
    creator_id = await create_user(
        session, ws_id, handle=f"@creator_{uuid.uuid4().hex[:6]}", display_name="Creator User"
    )
    member_id = await create_user(
        session, ws_id, handle=f"@member_{uuid.uuid4().hex[:6]}", display_name="Member User"
    )

    project_id = await create_project(
        session, ws_id, identifier="NTF", name="NTF Project", created_by_id=creator_id
    )

    # Bind roles: creator is PROJECT_ADMIN, member is MEMBER
    await add_role_binding(
        session,
        ws_id,
        creator_id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=project_id,
    )
    await add_role_binding(
        session, ws_id, member_id, role="MEMBER", scope_type="project", project_id=project_id
    )
    await rebuild_era(session, ws_id)

    # Resolve default workflow state and priority
    state_res = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": project_id}
    )
    state_id = state_res.scalar_one()

    prio_res = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": project_id}
    )
    prio_id = prio_res.scalar_one()

    # Allocate issue sequence and create issue
    seq_id = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": project_id})
    ).scalar_one()
    issue_key = f"NTF-{seq_id}"
    issue_id = await create_registered_object(
        session,
        ws_id,
        kind="issue",
        key=issue_key,
        title="Test Notification Issue",
        project_id=project_id,
        created_by_id=creator_id,
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, state_id, "
            "priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :p, :seq, :st, :pr, 'Test Notification Issue', "
            ":creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "p": project_id,
            "seq": seq_id,
            "st": state_id,
            "pr": prio_id,
            "creator": creator_id,
        },
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    return ws_id, creator_id, member_id, issue_id, issue_key


# ---------------------------------------------------------------------------
# Test Case 1: Auto-subscribe Creator & Delivery on Activity (KB-P3-06 Req 1, 6)
# ---------------------------------------------------------------------------
async def test_case_1_auto_subscribe_creator_and_comment_delivery(
    committed_db_session: AsyncSession,
) -> None:
    """Creator is auto-subscribed on ISSUE_CREATED.

    Another user's comment creates 1 notification and 1 outbox row with zero text leakage.
    """
    session = committed_db_session
    ws_id, creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    # 1. Trigger ISSUE_CREATED activity
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.ISSUE_CREATED,
        payload={"created_by_id": str(creator_id)},
    )
    await session.commit()

    # Verify creator is auto-subscribed with source="CREATOR"
    sub_res = await session.execute(
        select(IssueSubscription).where(
            IssueSubscription.issue_id == issue_id,
            IssueSubscription.principal_id == creator_id,
        )
    )
    sub = sub_res.scalar_one_or_none()
    assert sub is not None
    assert sub.source == "CREATOR"
    assert sub.unsubscribed_at is None
    assert sub.muted_event_types == []

    # 2. Member posts comment (COMMENT_CREATED activity)
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"body_markdown": "Secret sensitive information in comment"},
    )
    await session.commit()

    # 3. Check notifications: exactly 1 notification for creator
    notifs = (
        (await session.execute(select(Notification).where(Notification.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(notifs) == 1
    notif = notifs[0]
    assert notif.recipient_principal_id == creator_id
    assert notif.event_type == "COMMENT_CREATED"
    assert notif.read_at is None

    # Check actor exclusion: 0 notifications for member (actor)
    member_notifs = [n for n in notifs if n.recipient_principal_id == member_id]
    assert len(member_notifs) == 0

    # 4. Check outbox: exactly 1 outbox_events row with topic "notification.created"
    outbox_rows = (
        (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.object_id == issue_id,
                    OutboxEvent.topic == "notification.created",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox_rows) == 1
    ob = outbox_rows[0]
    assert ob.payload["topic"] == "notification.created"
    assert ob.payload["recipient_principal_id"] == str(creator_id)
    assert ob.payload["notification_id"] == str(notif.id)

    # STRICT ZERO LEAKAGE REQUIREMENT: payload contains NO summary, body, or title keys
    assert "summary" not in ob.payload
    assert "body" not in ob.payload
    assert "title" not in ob.payload
    assert "body_markdown" not in ob.payload


# ---------------------------------------------------------------------------
# Test Case 2: Security & Revoked VIEW / Free-Text Assignee (KB-P3-06 Req 2)
# ---------------------------------------------------------------------------
async def test_case_2_security_revoked_view_and_free_text(
    committed_db_session: AsyncSession,
) -> None:
    """Revoked VIEW receives no notification.

    Free-text assignee produces no subscription; foreign read returns 404.
    """
    session = committed_db_session
    ws_id, creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    # 1. Free-text assignee produces zero subscriptions
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "free_text", "display_name": "External Vendor"},
    )
    await session.commit()
    # Confirm only creator is subscribed (no free-text assignee subscription)
    subs = (
        (
            await session.execute(
                select(IssueSubscription).where(IssueSubscription.issue_id == issue_id)
            )
        )
        .scalars()
        .all()
    )
    sub_principal_ids = {s.principal_id for s in subs}
    assert sub_principal_ids == {creator_id}

    # 2. Subscribe member explicitly
    member_ctx = PrincipalContext(
        principal_id=member_id, workspace_id=ws_id, token_scopes=("session",)
    )

    await subscribe_issue(session, member_ctx, str(issue_id))
    await session.commit()

    # 3. Explicit DENY on VIEW for member
    await add_acl_entry(
        session,
        ws_id,
        issue_id,
        member_id,
        effect="DENY",
        capability_mask=1,
        created_by_id=creator_id,
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    # 4. Trigger comment by creator -> Member has NO VIEW (explicit DENY)
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"body_markdown": "Test"},
    )
    await session.commit()

    notifs = (
        (
            await session.execute(
                select(Notification).where(Notification.recipient_principal_id == member_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) == 0

    # 5. Foreign read 404
    # Seed a notification for creator
    dummy_notif_id = uuid.uuid4()
    notif = Notification(
        id=dummy_notif_id,
        workspace_id=ws_id,
        recipient_principal_id=creator_id,
        issue_id=issue_id,
        activity_record_id=uuid.uuid4(),
        event_type="ISSUE_STATE_CHANGED",
        created_at=datetime.now(UTC),
        read_at=None,
    )
    session.add(notif)
    await session.commit()

    # Member attempting to read creator's notification raises 404 ProblemException
    with pytest.raises(ProblemException) as exc_info:
        await mark_notification_read(session, member_ctx, dummy_notif_id)
    assert exc_info.value.status == 404
    assert exc_info.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test Case 3: Mute Specific Event Types (KB-P3-06 Req 3)
# ---------------------------------------------------------------------------
async def test_case_3_mute_suppresses_specific_events(
    committed_db_session: AsyncSession,
) -> None:
    """Muting COMMENT_CREATED suppresses comments but delivers ISSUE_STATE_CHANGED."""
    session = committed_db_session
    ws_id, creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    creator_ctx = PrincipalContext(
        principal_id=creator_id, workspace_id=ws_id, token_scopes=("session",)
    )

    # Subscribe creator with COMMENT_CREATED muted
    await subscribe_issue(
        session,
        creator_ctx,
        str(issue_id),
        SubscriptionPut(muted_event_types=["COMMENT_CREATED"]),
    )
    await session.commit()

    # 1. Member posts comment -> Suppressed by mute!
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"body_markdown": "Muted comment"},
    )
    await session.commit()

    notifs1 = (
        (
            await session.execute(
                select(Notification).where(Notification.recipient_principal_id == creator_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs1) == 0

    # 2. Member changes issue state -> Delivered!
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        payload={"state": "IN_PROGRESS"},
    )
    await session.commit()

    notifs2 = (
        (
            await session.execute(
                select(Notification).where(Notification.recipient_principal_id == creator_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs2) == 1
    assert notifs2[0].event_type == "ISSUE_STATE_CHANGED"


# ---------------------------------------------------------------------------
# Test Case 4: Actor Exclusion and Tombstone Invariant (KB-P3-06 Req 4)
# ---------------------------------------------------------------------------
async def test_case_4_actor_exclusion_and_tombstone(
    committed_db_session: AsyncSession,
) -> None:
    """Actor never notifies self.

    After explicit unsubscribe tombstone, assignment or mention never re-subscribes.
    """
    session = committed_db_session
    ws_id, creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    creator_ctx = PrincipalContext(
        principal_id=creator_id, workspace_id=ws_id, token_scopes=("session",)
    )

    # 1. Subscribe creator
    await subscribe_issue(session, creator_ctx, str(issue_id))
    await session.commit()

    # 2. Creator makes activity -> Actor exclusion (0 notifications for self)
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        payload={"state": "DONE"},
    )
    await session.commit()
    notifs = (
        (
            await session.execute(
                select(Notification).where(Notification.recipient_principal_id == creator_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notifs) == 0

    # 3. Explicit unsubscribe -> sets tombstone
    await unsubscribe_issue(session, creator_ctx, str(issue_id))
    await session.commit()

    sub = (
        await session.execute(
            select(IssueSubscription).where(
                IssueSubscription.issue_id == issue_id, IssueSubscription.principal_id == creator_id
            )
        )
    ).scalar_one()
    assert sub.unsubscribed_at is not None

    # 4. Member assigns creator -> Tombstone prevents re-subscribe!
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "principal", "principal_id": str(creator_id)},
    )
    await session.commit()

    sub_after_assign = (
        await session.execute(
            select(IssueSubscription).where(
                IssueSubscription.issue_id == issue_id, IssueSubscription.principal_id == creator_id
            )
        )
    ).scalar_one()
    assert sub_after_assign.unsubscribed_at is not None  # Stays unsubscribed!

    # 5. Member mentions creator -> Tombstone prevents re-subscribe!
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"mentioned_principal_ids": [str(creator_id)]},
    )
    await session.commit()

    sub_after_mention = (
        await session.execute(
            select(IssueSubscription).where(
                IssueSubscription.issue_id == issue_id, IssueSubscription.principal_id == creator_id
            )
        )
    ).scalar_one()
    assert sub_after_mention.unsubscribed_at is not None  # Stays unsubscribed!


# ---------------------------------------------------------------------------
# Test Case 5: Mention Auto-Subscribe Rules (KB-P3-06 Req 4, 5)
# ---------------------------------------------------------------------------
async def test_case_5_mention_auto_subscribe(
    committed_db_session: AsyncSession,
) -> None:
    """Mentioned viewers holding VIEW are auto-subscribed with source=MENTION.

    Unauthenticated or inaccessible mentions are skipped.
    """
    session = committed_db_session
    ws_id, _creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    # Get project_id from issue
    project_id = (
        await session.execute(select(Issue.project_id).where(Issue.id == issue_id))
    ).scalar_one()

    # Create charlie (has VIEW) and ghost (no VIEW)
    charlie_id = await create_user(
        session, ws_id, handle=f"@charlie_{uuid.uuid4().hex[:6]}", display_name="Charlie User"
    )
    ghost_id = await create_user(
        session, ws_id, handle=f"@ghost_{uuid.uuid4().hex[:6]}", display_name="Ghost User"
    )
    await add_role_binding(
        session, ws_id, charlie_id, role="MEMBER", scope_type="project", project_id=project_id
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    # Member mentions charlie and ghost
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=member_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"mentioned_principal_ids": [str(charlie_id), str(ghost_id), "not-a-valid-uuid"]},
    )
    await session.commit()

    # Charlie (has VIEW) is auto-subscribed with source="MENTION"
    sub_charlie = (
        await session.execute(
            select(IssueSubscription).where(
                IssueSubscription.issue_id == issue_id, IssueSubscription.principal_id == charlie_id
            )
        )
    ).scalar_one_or_none()
    assert sub_charlie is not None
    assert sub_charlie.source == "MENTION"

    # Ghost (no VIEW) is NOT subscribed
    sub_ghost = (
        await session.execute(
            select(IssueSubscription).where(
                IssueSubscription.issue_id == issue_id, IssueSubscription.principal_id == ghost_id
            )
        )
    ).scalar_one_or_none()
    assert sub_ghost is None


# ---------------------------------------------------------------------------
# Test Case 6: Boundaries, Keyset Pagination, 500 Cap, and Mark All Read (KB-P3-06 Req 5)
# ---------------------------------------------------------------------------
async def test_case_6_boundaries_keyset_and_500_cap(
    committed_db_session: AsyncSession,
) -> None:
    """501 subscribers caps delivery at 500.

    Keyset pagination works; mark-all-read returns correct count.
    """
    session = committed_db_session
    ws_id, creator_id, _member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    creator_ctx = PrincipalContext(
        principal_id=creator_id, workspace_id=ws_id, token_scopes=("session",)
    )

    # 1. Test 501 subscribers cap
    # Bulk insert 501 users and issue subscriptions
    user_ids: list[uuid.UUID] = []
    base_time = datetime.now(UTC) - timedelta(days=10)
    for i in range(501):
        uid = uuid.uuid4()
        user_ids.append(uid)
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, status, display_name) "
                "VALUES (:id, 'USER', :ws, 'ACTIVE', :name)"
            ),
            {"id": uid, "ws": ws_id, "name": f"Bulk User {i}"},
        )
        await session.execute(
            text(
                "INSERT INTO issue_subscriptions "
                "(issue_id, principal_id, workspace_id, source, is_muted, "
                "muted_event_types, created_at) "
                "VALUES (:iss, :p, :ws, 'MANUAL', false, '{}', :ts)"
            ),
            {"iss": issue_id, "p": uid, "ws": ws_id, "ts": base_time + timedelta(seconds=i)},
        )

    # Bulk grant VIEW capability in effective_resource_access for the issue
    for uid in user_ids:
        await session.execute(
            text(
                "INSERT INTO effective_resource_access "
                "(object_id, principal_id, allow_mask, deny_mask, workspace_id) "
                "VALUES (:obj, :p, 1, 0, :ws) "
                "ON CONFLICT (object_id, principal_id) DO UPDATE SET allow_mask = 1, deny_mask = 0"
            ),
            {"obj": issue_id, "p": uid, "ws": ws_id},
        )
    await session.commit()

    # Trigger activity by creator -> Exactly 500 notifications created (capped from 501)
    await record_activity(
        session,
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        payload={"state": "TRIAGED"},
    )
    await session.commit()

    total_notifs = await session.scalar(
        text("SELECT count(*) FROM notifications WHERE issue_id = :iss"), {"iss": issue_id}
    )
    assert total_notifs == 500

    # 2. Test Keyset pagination on creator notifications
    # Seed 5 notifications for creator
    now = datetime.now(UTC)
    for i in range(5):
        session.add(
            Notification(
                id=uuid.uuid4(),
                workspace_id=ws_id,
                recipient_principal_id=creator_id,
                issue_id=issue_id,
                activity_record_id=uuid.uuid4(),
                event_type="COMMENT_CREATED",
                created_at=now + timedelta(seconds=i),
                read_at=None,
            )
        )
    await session.commit()

    # Page 1 (limit=3)
    p1 = await list_notifications(session, creator_ctx, unread=True, limit=3)
    assert len(p1.items) == 3
    assert p1.next_cursor is not None

    # Page 2 with cursor
    p2 = await list_notifications(session, creator_ctx, unread=True, cursor=p1.next_cursor, limit=3)
    assert len(p2.items) == 2
    assert p2.next_cursor is None

    # 3. Test mark_all_read
    marked = await mark_all_read(session, creator_ctx)
    assert marked == 5

    # Confirm unread is now 0
    p_unread = await list_notifications(session, creator_ctx, unread=True, limit=10)
    assert len(p_unread.items) == 0

    # 4. Limit validation: limit=0 or limit=101 raises 422
    with pytest.raises(ProblemException) as exc0:
        await list_notifications(session, creator_ctx, limit=0)
    assert exc0.value.status == 422

    with pytest.raises(ProblemException) as exc101:
        await list_notifications(session, creator_ctx, limit=101)
    assert exc101.value.status == 422


# ---------------------------------------------------------------------------
# Test Case 7: Cursor Edge Cases and Ephemeral Activities
# ---------------------------------------------------------------------------
async def test_case_7_cursor_and_edge_cases(
    committed_db_session: AsyncSession,
) -> None:
    """Verify cursor encode/decode edge cases, ephemeral activity skip, and listener idempotency."""
    session = committed_db_session
    ws_id, creator_id, _member_id, issue_id, _ = await _setup_env(session)

    # 1. EphemeralEnvelope does not trigger notification or error
    e_env = EphemeralEnvelope(
        workspace_id=ws_id,
        object_id=issue_id,
        actor_principal_id=creator_id,
        event_type="issue.reordered",
        payload={},
    )
    await handle_activity_event(session, e_env)  # Should return early cleanly

    # 2. Activity on non-issue object does not trigger notification or error
    non_issue_env = ActivityEnvelope(
        activity_id=uuid.uuid4(),
        workspace_id=ws_id,
        object_id=ws_id,  # Workspace, not issue
        actor_principal_id=creator_id,
        event_type=ActivityEventType.PROJECT_CREATED,
        category=ActivityCategory.SYSTEM,
        payload={},
    )
    await handle_activity_event(session, non_issue_env)  # Should return early cleanly

    # 3. Cursor decoding errors
    with pytest.raises(ProblemException) as exc_b64:
        decode_cursor("not_valid_base64!!!")
    assert exc_b64.value.status == 422

    with pytest.raises(ProblemException) as exc_parts:
        # Valid base64 but single part
        decode_cursor("c2luZ2xlX3BhcnQ=")
    assert exc_parts.value.status == 422

    with pytest.raises(ProblemException) as exc_date:
        # Valid base64, two parts, but invalid ISO date
        decode_cursor(
            "aW52YWxpZC1kYXRlX25vdC1pc286MDE5MmY3YTctNmY0ZC03MmY3LWJmNWMtNWY3YjM5MGEzYTQ2"
        )
    assert exc_date.value.status == 422

    # 4. Listener registration idempotency
    register_notifications_listener()
    register_notifications_listener()  # Multiple calls should not duplicate


# ---------------------------------------------------------------------------
# Test Case 8: Committed DB Outbox Wakeup PG_NOTIFY (KB-P3-06 Req 6)
# ---------------------------------------------------------------------------
async def test_case_8_outbox_wakeup_pg_notify(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Assert pg_notify('outbox_wakeup') fires when a notification is inserted and committed."""
    session = committed_db_session
    ws_id, creator_id, member_id, issue_id, _ = await _setup_env(session)
    clear_activity_listeners()
    register_notifications_listener()

    # Setup asyncpg connection listening on outbox_wakeup
    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")

    wakeup_event = asyncio.Event()

    def on_wakeup(*args: object) -> None:
        del args
        wakeup_event.set()

    conn = await asyncpg.connect(user="kanban_migrator", database=db_name, host=socket_dir)
    try:
        await conn.add_listener("outbox_wakeup", on_wakeup)

        # Trigger notification delivery by having member comment on creator's issue
        creator_ctx = PrincipalContext(
            principal_id=creator_id, workspace_id=ws_id, token_scopes=("session",)
        )
        await subscribe_issue(session, creator_ctx, str(issue_id))
        await session.commit()

        await record_activity(
            session,
            workspace_id=ws_id,
            object_id=issue_id,
            actor_principal_id=member_id,
            event_type=ActivityEventType.COMMENT_CREATED,
            payload={"body_markdown": "Wakeup test comment"},
        )
        await session.commit()

        # Wait for outbox_wakeup NOTIFY
        await asyncio.wait_for(wakeup_event.wait(), timeout=2.0)
        assert wakeup_event.is_set()
    finally:
        await conn.remove_listener("outbox_wakeup", on_wakeup)
        await conn.close()

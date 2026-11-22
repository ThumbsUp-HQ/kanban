# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""API and service tests for notifications and outbox read sync events (KB-P3-06, KAN-310)."""

# ruff: noqa: PLR0915

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import IssueSubscription, Notification, OutboxEvent
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
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

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "summary",
        "description",
        "description_markdown",
        "body",
        "body_markdown",
        "title",
        "key",
        "issue_key",
        "actor",
        "actor_email",
        "actor_handle",
        "actor_name",
        "display_name",
        "email",
        "handle",
    }
)


async def test_notifications_mark_read_and_read_all_emit_idempotent_outbox_events_for_member(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify non-admin MEMBER mark_read and mark_all_read emit idempotent ID-only outbox events."""
    admin = await make_user("notif_outbox_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("notif_outbox_member", workspace_role="WORKSPACE_MEMBER")
    other = await make_user("notif_outbox_other", workspace_role="WORKSPACE_MEMBER")

    _ = await make_project(
        "NTFWS",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", other: "MEMBER"},
    )

    clear_activity_listeners()
    register_notifications_listener()

    # 1. Member creates an issue (auto-subscribed as CREATOR)
    client_member = as_principal(member)
    issue_resp = await client_member.post(
        "/api/v1/projects/NTFWS/issues",
        json={"summary": "Confidential Security Issue Title", "priority": "high"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_data = issue_resp.json()
    issue_id = uuid.UUID(issue_data["id"])

    # 2. Admin posts two comments so Member receives 2 notifications + 2 outbox rows
    client_admin = as_principal(admin)
    for idx in (1, 2):
        c_resp = await client_admin.post(
            f"/api/v1/issues/{issue_data['key']}/comments",
            json={"body_markdown": f"Top secret comment body #{idx}"},
        )
        assert c_resp.status_code == 201, c_resp.text

    # Seed 1 notification for other user to verify isolation on mark_all_read
    other_notif_id = uuid.uuid4()
    api_env.seed.add(
        Notification(
            id=other_notif_id,
            workspace_id=api_env.workspace_id,
            recipient_principal_id=other.id,
            issue_id=issue_id,
            activity_record_id=uuid.uuid4(),
            event_type="COMMENT_CREATED",
            created_at=datetime.now(UTC),
            read_at=None,
        )
    )
    await api_env.seed.commit()

    # 3. Member lists unread notifications via GET /api/v1/notifications
    client_member = as_principal(member)
    list_resp = await client_member.get("/api/v1/notifications?unread=true&limit=10")
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    assert len(items) == 2
    notif_1_id = uuid.UUID(items[0]["id"])
    notif_2_id = uuid.UUID(items[1]["id"])

    # Verify notification.created outbox payloads have zero sensitive keys
    created_outbox = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.created",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(created_outbox) >= 2
    for ob in created_outbox:
        assert set(ob.payload.keys()) == {"topic", "recipient_principal_id", "notification_id"}
        assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(ob.payload.keys())

    # 4. Foreign user attempting to mark Member's notification read gets 404 and emits 0 outbox rows
    client_other = as_principal(other)
    foreign_resp = await client_other.post(f"/api/v1/notifications/{notif_1_id}/read")
    assert foreign_resp.status_code == 404

    read_outbox_before = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.read",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(read_outbox_before) == 0

    # 5. Non-admin MEMBER marks notif_1 as read -> 204 and emits 1 notification.read outbox row
    client_member = as_principal(member)
    mark_resp1 = await client_member.post(f"/api/v1/notifications/{notif_1_id}/read")
    assert mark_resp1.status_code == 204
    contract_recorder.record("notification_mark_read_204", mark_resp1.request, mark_resp1)

    read_outbox_after1 = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.read",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(read_outbox_after1) == 1
    ob_read = read_outbox_after1[0]
    assert ob_read.workspace_id == api_env.workspace_id
    assert ob_read.project_id is None
    assert ob_read.object_id is None
    assert ob_read.payload == {
        "topic": "notification.read",
        "recipient_principal_id": str(member.id),
        "notification_id": str(notif_1_id),
    }
    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(ob_read.payload.keys())

    # 6. Repeat POST /api/v1/notifications/{notif_1_id}/read is idempotent (204, 0 new rows)
    mark_resp1_repeat = await client_member.post(f"/api/v1/notifications/{notif_1_id}/read")
    assert mark_resp1_repeat.status_code == 204

    read_outbox_after_repeat = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.read",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(read_outbox_after_repeat) == 1

    # 7. Non-admin MEMBER calls POST /api/v1/notifications/read-all -> marks remaining 1 unread
    # and emits 1 notification.read_all outbox row
    read_all_resp = await client_member.post("/api/v1/notifications/read-all")
    assert read_all_resp.status_code == 200
    assert read_all_resp.json() == {"marked": 1}
    contract_recorder.record("notification_mark_all_read_200", read_all_resp.request, read_all_resp)

    read_all_outbox = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.read_all",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(read_all_outbox) == 1
    ob_ra = read_all_outbox[0]
    assert ob_ra.workspace_id == api_env.workspace_id
    assert ob_ra.project_id is None
    assert ob_ra.object_id is None
    assert ob_ra.payload == {
        "topic": "notification.read_all",
        "recipient_principal_id": str(member.id),
        "marked_count": 1,
    }
    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(ob_ra.payload.keys())

    # 8. Repeat POST /api/v1/notifications/read-all when 0 unread remain returns marked=0 (0 rows)
    read_all_repeat = await client_member.post("/api/v1/notifications/read-all")
    assert read_all_repeat.status_code == 200
    assert read_all_repeat.json() == {"marked": 0}

    read_all_outbox_repeat = (
        (
            await api_env.seed.execute(
                select(OutboxEvent).where(
                    OutboxEvent.workspace_id == api_env.workspace_id,
                    OutboxEvent.topic == "notification.read_all",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(read_all_outbox_repeat) == 1

    # Verify notif_2 is read and other user's notification is still unread
    api_env.seed.expire_all()
    n2_row = (
        await api_env.seed.execute(select(Notification).where(Notification.id == notif_2_id))
    ).scalar_one()
    assert n2_row.read_at is not None

    other_row = (
        await api_env.seed.execute(select(Notification).where(Notification.id == other_notif_id))
    ).scalar_one()
    assert other_row.read_at is None


async def test_notifications_service_branches_pagination_and_auto_subscriptions(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Exercise notifications service pagination, actor redaction, auto-subscribe, and limits."""
    admin = await make_user("svc_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("svc_member", workspace_role="WORKSPACE_MEMBER")
    mention_user = await make_user("svc_mention", workspace_role="WORKSPACE_MEMBER")
    outsider = await make_user("svc_outsider")

    proj_id = await make_project(
        "NTFS",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", mention_user: "MEMBER"},
    )

    clear_activity_listeners()
    register_notifications_listener()
    register_notifications_listener()

    client_admin = as_principal(admin)
    issue_resp = await client_admin.post(
        "/api/v1/projects/NTFS/issues",
        json={"summary": "Service Branch Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201
    issue_id = uuid.UUID(issue_resp.json()["id"])

    session = api_env.seed

    # 1. Ephemeral and non-issue activity events are ignored cleanly
    await handle_activity_event(
        session,
        EphemeralEnvelope(
            workspace_id=api_env.workspace_id,
            object_id=issue_id,
            actor_principal_id=admin.id,
            event_type="issue.reordered",
            payload={},
        ),
    )
    await handle_activity_event(
        session,
        ActivityEnvelope(
            activity_id=uuid.uuid4(),
            workspace_id=api_env.workspace_id,
            object_id=None,
            actor_principal_id=admin.id,
            event_type=ActivityEventType.PROJECT_CREATED,
            category=ActivityCategory.SYSTEM,
            payload={},
        ),
    )
    await handle_activity_event(
        session,
        ActivityEnvelope(
            activity_id=uuid.uuid4(),
            workspace_id=api_env.workspace_id,
            object_id=proj_id,
            actor_principal_id=admin.id,
            event_type=ActivityEventType.PROJECT_CREATED,
            category=ActivityCategory.SYSTEM,
            payload={},
        ),
    )

    # 2. Auto-subscribe assignee (principal vs invalid vs non-viewer)
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "principal", "principal_id": str(member.id)},
    )
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "principal", "principal_id": "invalid-uuid"},
    )
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "free_text", "display_name": "External"},
    )

    # 3. Auto-subscribe mention (viewer vs non-viewer vs invalid vs non-list)
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={
            "mentioned_principal_ids": [
                str(mention_user.id),
                str(outsider.id),
                "bad-uuid",
            ]
        },
    )
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"mentioned_principal_ids": "not-a-list"},
    )
    await session.commit()

    # Mute COMMENT_CREATED for mention_user and test muted skip
    await session.execute(
        text(
            "UPDATE issue_subscriptions SET muted_event_types = :m "
            "WHERE issue_id = :iss AND principal_id = :pid"
        ),
        {"iss": issue_id, "m": ["COMMENT_CREATED"], "pid": mention_user.id},
    )
    # Tombstone member and verify auto-subscribe respects tombstone
    await session.execute(
        text(
            "UPDATE issue_subscriptions SET unsubscribed_at = now() "
            "WHERE issue_id = :iss AND principal_id = :pid"
        ),
        {"iss": issue_id, "pid": member.id},
    )
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "principal", "principal_id": str(member.id)},
    )
    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={"body_markdown": "Muted for mention_user"},
    )
    await session.commit()

    # 4. Seed notifications without matching ActivityRecord to test redacted external actor fallback
    now = datetime.now(UTC)
    for i in range(4):
        session.add(
            Notification(
                id=uuid.uuid4(),
                workspace_id=api_env.workspace_id,
                recipient_principal_id=admin.id,
                issue_id=issue_id,
                activity_record_id=uuid.uuid4(),
                event_type="ISSUE_STATE_CHANGED",
                created_at=now + timedelta(seconds=i),
                read_at=None,
            )
        )
    await session.commit()

    admin_ctx = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )

    page1 = await list_notifications(session, admin_ctx, unread=True, limit=2)
    assert len(page1.items) == 2
    assert page1.items[0].actor.redacted is True
    assert page1.next_cursor is not None

    page2 = await list_notifications(
        session, admin_ctx, unread=False, cursor=page1.next_cursor, limit=10
    )
    assert len(page2.items) >= 2

    # 5. Validation errors on list_notifications and decode_cursor
    with pytest.raises(ProblemException) as exc_lim:
        await list_notifications(session, admin_ctx, limit=0)
    assert exc_lim.value.status == 422

    with pytest.raises(ProblemException) as exc_cur:
        decode_cursor("invalid_cursor")
    assert exc_cur.value.status == 422

    # 6. Mark all read directly via service
    marked = await mark_all_read(session, admin_ctx)
    assert marked >= 4
    assert await mark_all_read(session, admin_ctx) == 0

    # 7. Missing notification raises 404
    with pytest.raises(ProblemException) as exc_nf:
        await mark_notification_read(session, admin_ctx, uuid.uuid4())
    assert exc_nf.value.status == 404


async def test_notifications_500_recipient_cap_and_no_eligible_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test >500 recipients cap and no-eligible-viewers early exit in _deliver_notifications."""
    admin = await make_user("cap_admin", workspace_role="WORKSPACE_ADMIN")
    no_view_user = await make_user("cap_noview")
    _ = await make_project("NTFC", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    clear_activity_listeners()
    register_notifications_listener()

    client_admin = as_principal(admin)
    issue_resp = await client_admin.post(
        "/api/v1/projects/NTFC/issues",
        json={"summary": "Cap Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201
    issue_id = uuid.UUID(issue_resp.json()["id"])

    session = api_env.seed

    # 1. Subscriber lacks VIEW in effective_resource_access -> eligible is empty
    session.add(
        IssueSubscription(
            issue_id=issue_id,
            principal_id=no_view_user.id,
            workspace_id=api_env.workspace_id,
            source="MANUAL",
            is_muted=False,
            muted_event_types=[],
            unsubscribed_at=None,
        )
    )
    await session.commit()

    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        payload={"state": "IN_PROGRESS"},
    )
    await session.commit()

    # 2. Seed 501 eligible subscribers and verify cap at 500
    base_time = datetime.now(UTC) - timedelta(days=5)
    for i in range(501):
        uid = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, status, display_name) "
                "VALUES (:id, 'USER', :ws, 'ACTIVE', :name)"
            ),
            {"id": uid, "name": f"Cap User {i}", "ws": api_env.workspace_id},
        )
        await session.execute(
            text(
                "INSERT INTO issue_subscriptions "
                "(issue_id, principal_id, workspace_id, source, is_muted, "
                "muted_event_types, created_at) "
                "VALUES (:iss, :p, :ws, 'MANUAL', false, '{}', :ts)"
            ),
            {
                "iss": issue_id,
                "p": uid,
                "ts": base_time + timedelta(seconds=i),
                "ws": api_env.workspace_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO effective_resource_access "
                "(object_id, principal_id, allow_mask, deny_mask, workspace_id) "
                "VALUES (:obj, :p, 1, 0, :ws)"
            ),
            {"obj": issue_id, "p": uid, "ws": api_env.workspace_id},
        )
    await session.commit()

    await record_activity(
        session,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ISSUE_STATE_CHANGED,
        payload={"state": "DONE"},
    )
    await session.commit()

    count = await session.scalar(
        text("SELECT count(*) FROM notifications WHERE issue_id = :iss"),
        {"iss": issue_id},
    )
    assert count == 500

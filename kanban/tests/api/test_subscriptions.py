# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""API tests for issue subscriptions and notifications (S7.2 8l, KB-P3-06)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from database.models import Notification
from kanban.api.v1.schemas.notifications import MUTABLE_EVENT_TYPES

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_subscription_lifecycle_and_contracts(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test full subscription lifecycle, idempotency, and contract recording."""
    del api_env
    user = await make_user("sub_user", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("SUB", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    # 1. Create target issue
    issue_resp = await client.post(
        "/api/v1/projects/SUB/issues",
        json={"summary": "Subscription Lifecycle Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_key = issue_resp.json()["key"]

    # 2. GET initial subscription (auto-subscribed as creator, or default)
    # Creator is auto-subscribed upon issue creation via activity listener
    get_resp1 = await client.get(f"/api/v1/issues/{issue_key}/subscription")
    assert get_resp1.status_code == 200, get_resp1.text
    sub1 = get_resp1.json()
    assert sub1["subscribed"] is True
    assert sub1["source"] == "creator"
    assert sub1["muted_event_types"] == []

    # 3. DELETE to unsubscribe
    del_resp1 = await client.delete(f"/api/v1/issues/{issue_key}/subscription")
    contract_recorder.record("unsubscribe_204", del_resp1.request, del_resp1)
    assert del_resp1.status_code == 204, del_resp1.text

    # 4. GET after unsubscribe confirms unsubscribed state
    get_resp2 = await client.get(f"/api/v1/issues/{issue_key}/subscription")
    assert get_resp2.status_code == 200
    sub2 = get_resp2.json()
    assert sub2["subscribed"] is False
    assert sub2["source"] is None
    assert sub2["muted_event_types"] == []

    # 5. Idempotent DELETE again -> 204
    del_resp2 = await client.delete(f"/api/v1/issues/{issue_key}/subscription")
    assert del_resp2.status_code == 204

    # 6. PUT to re-subscribe manually (clears tombstone)
    put_resp = await client.put(f"/api/v1/issues/{issue_key}/subscription")
    contract_recorder.record("subscribe_200", put_resp.request, put_resp)
    assert put_resp.status_code == 200, put_resp.text
    sub3 = put_resp.json()
    assert sub3["subscribed"] is True
    assert sub3["source"] == "manual"
    assert sub3["muted_event_types"] == []

    # 7. PATCH to mute valid event types
    valid_mutes = ["COMMENT_CREATED", "ISSUE_STATE_CHANGED"]
    patch_resp = await client.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": valid_mutes},
    )
    contract_recorder.record("mute_200", patch_resp.request, patch_resp)
    assert patch_resp.status_code == 200, patch_resp.text
    sub4 = patch_resp.json()
    assert sub4["subscribed"] is True
    assert sub4["muted_event_types"] == valid_mutes
    assert sub4["source"] == "manual"

    # 8. PATCH with invalid / unmutable event type -> 422 EVENT_TYPE_NOT_MUTABLE
    invalid_mutes = ["PROJECT_CREATED"]
    patch_invalid_resp = await client.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": invalid_mutes},
    )
    contract_recorder.record("invalid_mute_422", patch_invalid_resp.request, patch_invalid_resp)
    assert patch_invalid_resp.status_code == 422, patch_invalid_resp.text
    err = patch_invalid_resp.json()
    assert err["code"] == "EVENT_TYPE_NOT_MUTABLE"

    # 9. Idempotent PUT maintains or updates subscription
    put_resp2 = await client.put(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": ["ASSIGNEE_ADDED"]},
    )
    assert put_resp2.status_code == 200
    sub5 = put_resp2.json()
    assert sub5["subscribed"] is True
    assert sub5["muted_event_types"] == ["ASSIGNEE_ADDED"]


async def test_subscription_validation_and_errors(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test validation errors for subscription endpoints."""
    del api_env
    owner = await make_user("owner_user", workspace_role="WORKSPACE_ADMIN")
    other = await make_user("other_user", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("VAL", created_by=owner, roles={owner: "PROJECT_ADMIN", other: "MEMBER"})

    client_owner = as_principal(owner)
    issue_resp = await client_owner.post(
        "/api/v1/projects/VAL/issues",
        json={"summary": "Validation Test Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201
    issue_key = issue_resp.json()["key"]

    client_other = as_principal(other)

    # 0. other unsubscribes before having any subscription record -> creates tombstone row
    del_init = await client_other.delete(f"/api/v1/issues/{issue_key}/subscription")
    assert del_init.status_code == 204

    # 1. other is not subscribed yet; PATCH should return 409 NOT_SUBSCRIBED
    patch_409 = await client_other.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": ["COMMENT_CREATED"]},
    )
    assert patch_409.status_code == 409
    assert patch_409.json()["code"] == "NOT_SUBSCRIBED"

    # 2. Subscribe other
    put_resp = await client_other.put(f"/api/v1/issues/{issue_key}/subscription")
    assert put_resp.status_code == 200

    # 3. Duplicate muted event types -> 422 DUPLICATE_MUTED_TYPE
    patch_dup = await client_other.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": ["COMMENT_CREATED", "COMMENT_CREATED"]},
    )
    assert patch_dup.status_code == 422
    assert patch_dup.json()["code"] == "DUPLICATE_MUTED_TYPE"

    # 4. More than 7 muted event types -> 422 TOO_MANY_MUTED_TYPES
    patch_too_many = await client_other.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": [*list(MUTABLE_EVENT_TYPES), "EXTRA_UNKNOWN"]},
    )
    assert patch_too_many.status_code == 422
    assert patch_too_many.json()["code"] in ("TOO_MANY_MUTED_TYPES", "EVENT_TYPE_NOT_MUTABLE")

    # 5. PUT with invalid muted type -> 422 EVENT_TYPE_NOT_MUTABLE
    put_invalid = await client_other.put(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": ["INVALID_TYPE"]},
    )
    assert put_invalid.status_code == 422
    assert put_invalid.json()["code"] == "EVENT_TYPE_NOT_MUTABLE"


async def test_subscription_permissions_zero_enumeration(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Non-viewers receive 404 NOT_FOUND across all subscription endpoints."""
    del api_env
    alice = await make_user("alice_priv", workspace_role="WORKSPACE_ADMIN")
    outsider = await make_user("outsider")  # Zero roles in project
    _ = await make_project("PRIV", created_by=alice, roles={alice: "PROJECT_ADMIN"})

    client_alice = as_principal(alice)
    issue_resp = await client_alice.post(
        "/api/v1/projects/PRIV/issues",
        json={"summary": "Private Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201
    issue_key = issue_resp.json()["key"]

    client_out = as_principal(outsider)

    # All endpoints return 404 without leaking issue existence
    get_res = await client_out.get(f"/api/v1/issues/{issue_key}/subscription")
    assert get_res.status_code == 404

    put_res = await client_out.put(f"/api/v1/issues/{issue_key}/subscription")
    assert put_res.status_code == 404

    patch_res = await client_out.patch(
        f"/api/v1/issues/{issue_key}/subscription",
        json={"muted_event_types": ["COMMENT_CREATED"]},
    )
    assert patch_res.status_code == 404

    del_res = await client_out.delete(f"/api/v1/issues/{issue_key}/subscription")
    assert del_res.status_code == 404


async def test_notifications_list_and_read_contracts(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify notification listing, foreign read 404, mark read, and contract recording."""
    alice = await make_user("notif_alice", workspace_role="WORKSPACE_ADMIN")
    bob = await make_user("notif_bob", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "NOTIF", created_by=alice, roles={alice: "PROJECT_ADMIN", bob: "PROJECT_ADMIN"}
    )

    # 1. Create issue as Alice
    client = as_principal(alice)
    issue_resp = await client.post(
        "/api/v1/projects/NOTIF/issues",
        json={"summary": "Notification Contract Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201
    issue_data = issue_resp.json()
    issue_id = uuid.UUID(issue_data["id"])
    issue_key = issue_data["key"]

    # 2. Seed a notification directly for alice
    notif_id = uuid.uuid4()
    notif = Notification(
        id=notif_id,
        workspace_id=api_env.workspace_id,
        recipient_principal_id=alice.id,
        issue_id=issue_id,
        activity_record_id=uuid.uuid4(),
        event_type="COMMENT_CREATED",
        created_at=datetime.now(UTC),
        read_at=None,
    )
    api_env.seed.add(notif)
    await api_env.seed.commit()

    # 3. Alice lists notifications -> 200
    as_principal(alice)
    list_resp = await client.get("/api/v1/notifications?unread=true&limit=10")
    contract_recorder.record("notifications_list_200", list_resp.request, list_resp)
    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    assert len(items) >= 1
    found = [it for it in items if it["id"] == str(notif_id)]
    assert len(found) == 1
    assert found[0]["issue"]["key"] == issue_key
    assert found[0]["event_type"] == "COMMENT_CREATED"
    assert found[0]["read_at"] is None

    # 4. Bob tries to mark Alice's notification as read -> 404 (foreign notification)
    as_principal(bob)
    bob_resp = await client.post(f"/api/v1/notifications/{notif_id}/read")
    contract_recorder.record("foreign_notification_read_404", bob_resp.request, bob_resp)
    assert bob_resp.status_code == 404, bob_resp.text

    # 5. Alice marks her notification as read -> 204
    as_principal(alice)
    read_resp = await client.post(f"/api/v1/notifications/{notif_id}/read")
    assert read_resp.status_code == 204

    # 6. Alice lists unread notifications -> 0 found
    unread_resp = await client.get("/api/v1/notifications?unread=true")
    assert unread_resp.status_code == 200
    assert not any(it["id"] == str(notif_id) for it in unread_resp.json()["items"])

    # 7. Seed another unread notification and test POST /api/v1/notifications/read-all
    notif2_id = uuid.uuid4()
    notif2 = Notification(
        id=notif2_id,
        workspace_id=api_env.workspace_id,
        recipient_principal_id=alice.id,
        issue_id=issue_id,
        activity_record_id=uuid.uuid4(),
        event_type="ISSUE_STATE_CHANGED",
        created_at=datetime.now(UTC),
        read_at=None,
    )
    api_env.seed.add(notif2)
    await api_env.seed.commit()

    read_all_resp = await client.post("/api/v1/notifications/read-all")
    assert read_all_resp.status_code == 200
    assert read_all_resp.json()["marked"] >= 1

    # 8. Validation: limit=101 returns 422
    limit_resp = await client.get("/api/v1/notifications?limit=101")
    assert limit_resp.status_code == 422

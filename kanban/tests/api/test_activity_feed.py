# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, PT011, B017, ERA001, F841
"""Comprehensive unit and integration tests for activity feed API (KB-P3-13 / S7.1, S7.2 8j, S12.2, S3.4)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.activity import ActivityRecord
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.activity import RedactedActorSummary
from kanban.security.permissions import Capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.activity_feed import (
    _get_cursor_secret,
    _resolve_actors,
    decode_activity_cursor,
    encode_activity_cursor,
    get_issue_activity,
    get_project_activity,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_role_binding,
    create_agent,
    create_registered_object,
    create_user,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_case_1_positive_4_tab_filtering_and_counts(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Positive 4-tab filtering, counts summary, and comment hydration."""
    admin = await make_user("admin1", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member1", workspace_role="WORKSPACE_MEMBER")
    _ = await make_project(
        "ACTV", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )
    client = as_principal(admin)

    # 1. Create target issue (emits ISSUE_CREATED -> 1 history row)
    issue_resp = await client.post(
        "/api/v1/projects/ACTV/issues",
        json={"summary": "Timeline Feed Target Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_data = issue_resp.json()
    issue_key = issue_data["key"]
    issue_id = uuid.UUID(issue_data["id"])

    # 2. Post Comment 1, then edit it (emits COMMENT_CREATED and COMMENT_EDITED)
    c1_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "First comment to be edited"},
    )
    assert c1_resp.status_code == 201, c1_resp.text
    c1_id = c1_resp.json()["id"]

    c1_edit_resp = await client.patch(
        f"/api/v1/comments/{c1_id}",
        headers={"If-Match": c1_resp.headers["ETag"]},
        json={"body_markdown": "First comment - EDITED version with updates"},
    )
    assert c1_edit_resp.status_code == 200, c1_edit_resp.text

    # Add reaction to Comment 1
    rx_resp = await client.put(f"/api/v1/comments/{c1_id}/reactions/%F0%9F%9A%80")
    assert rx_resp.status_code == 200, rx_resp.text

    # 3. Post Comment 2, then soft-delete it (emits COMMENT_CREATED and COMMENT_DELETED)
    c2_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Second secret comment to be deleted"},
    )
    assert c2_resp.status_code == 201, c2_resp.text
    c2_id = c2_resp.json()["id"]

    c2_del_resp = await client.delete(f"/api/v1/comments/{c2_id}")
    assert c2_del_resp.status_code == 204, c2_del_resp.text

    # 4. History changes: update issue summary (ISSUE_FIELD_CHANGED)
    iss_patch_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        headers={"If-Match": issue_resp.headers["ETag"]},
        json={"summary": "Timeline Feed Target Issue - RENAMED"},
    )
    assert iss_patch_resp.status_code == 200, iss_patch_resp.text

    # 5. History change: append CREATOR_OVERRIDDEN activity
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.CREATOR_OVERRIDDEN,
        payload={
            "from_user_id": str(admin.id),
            "to_user_id": str(member.id),
            "reason": "Administrative creator correction",
        },
    )

    # 6. Two AGENT_GATE rows: GATE_PENDING, GATE_APPROVED
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.GATE_PENDING,
        payload={"hook_name": "sec-review", "from_state": "In Review", "to_state": "Done"},
    )
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.GATE_APPROVED,
        payload={"hook_name": "sec-review", "verdict": "pass", "latency_ms": 145},
    )
    await api_env.seed.commit()

    # Total:
    # Comments: COMMENT_CREATED (c1), COMMENT_EDITED (c1), COMMENT_CREATED (c2), COMMENT_DELETED (c2) -> 4
    # History: ISSUE_CREATED, ISSUE_FIELD_CHANGED, CREATOR_OVERRIDDEN -> 3
    # Gates: GATE_PENDING, GATE_APPROVED -> 2
    # All: 4 + 3 + 2 = 9

    expected_counts = {"all": 9, "comments": 4, "history": 3, "gates": 2}

    # Verify tab=all
    resp_all = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=all")
    contract_recorder.record("tab_all_200", resp_all.request, resp_all)
    assert resp_all.status_code == 200, resp_all.text
    body_all = resp_all.json()
    assert body_all["tab"] == "all"
    assert body_all["counts"] == expected_counts
    assert len(body_all["items"]) == 9

    # Verify tab=comments
    resp_com = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=comments")
    contract_recorder.record("tab_comments_200", resp_com.request, resp_com)
    assert resp_com.status_code == 200, resp_com.text
    body_com = resp_com.json()
    assert body_com["tab"] == "comments"
    assert body_com["counts"] == expected_counts
    assert len(body_com["items"]) == 4
    for it in body_com["items"]:
        assert it["category"] == "COMMENT"

    # Verify active comment hydration in comments tab
    edited_com_item = next(it for it in body_com["items"] if it["event_type"] == "COMMENT_EDITED")
    assert edited_com_item["comment"] is not None
    assert edited_com_item["comment"]["id"] == c1_id
    assert "EDITED version" in edited_com_item["comment"]["body_markdown"]
    assert edited_com_item["comment"]["reactions"][0]["emoji"] == "🚀"

    # Verify soft-deleted comment hydration in comments tab
    del_com_item = next(it for it in body_com["items"] if it["event_type"] == "COMMENT_DELETED")
    assert del_com_item["comment"] is not None
    assert del_com_item["comment"]["deleted"] is True
    assert "body_markdown" not in del_com_item["comment"]
    assert "body_markdown" not in del_com_item["payload"]

    # Verify tab=history
    resp_hist = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=history")
    assert resp_hist.status_code == 200, resp_hist.text
    body_hist = resp_hist.json()
    assert body_hist["tab"] == "history"
    assert body_hist["counts"] == expected_counts
    assert len(body_hist["items"]) == 3
    for it in body_hist["items"]:
        assert it["category"] == "HISTORY"
    assert any(it["event_type"] == "CREATOR_OVERRIDDEN" for it in body_hist["items"])

    # Verify tab=gates
    resp_gates = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=gates")
    contract_recorder.record("tab_gates_200", resp_gates.request, resp_gates)
    assert resp_gates.status_code == 200, resp_gates.text
    body_gates = resp_gates.json()
    assert body_gates["tab"] == "gates"
    assert body_gates["counts"] == expected_counts
    assert len(body_gates["items"]) == 2
    for it in body_gates["items"]:
        assert it["category"] == "AGENT_GATE"


async def test_case_2_deleted_comment_and_redaction_security(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 2: Zero body leakage for deleted comments, collaborator redaction, and anti-enumeration 404."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create issue
    iss_resp = await client.post(
        "/api/v1/projects/SEC/issues",
        json={"summary": "Redaction and Deletion Test", "priority": "urgent"},
    )
    assert iss_resp.status_code == 201
    issue_key = iss_resp.json()["key"]
    issue_id = uuid.UUID(iss_resp.json()["id"])

    # 2. Create comment with sensitive body, then delete it
    secret_text = "SECRET_CREDENTIAL_DATA_LEAK_TEST"
    c_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": f"Sensitive data: {secret_text}"},
    )
    assert c_resp.status_code == 201
    c_id = c_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/comments/{c_id}")
    assert del_resp.status_code == 204

    # 3. Create out-of-boundary external guest collaborator
    ext_user_id = await create_user(
        api_env.seed,
        api_env.workspace_id,
        handle="@ext_guest",
        display_name="External Guest Partner",
        email="external@partner.corp",
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        ext_user_id,
        role="WORKSPACE_GUEST",
        scope_type="workspace",
    )
    # Direct ACL grant on issue
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        issue_id,
        ext_user_id,
        effect="ALLOW",
        capability_mask=Capability.VIEW,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)

    # Record activity where out-of-boundary guest is the actor
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=ext_user_id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={"field": "description", "reason": "guest review"},
    )
    await api_env.seed.commit()

    # 4. Normal member views feed
    member = await make_user("norm_member", workspace_role="WORKSPACE_MEMBER")
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        member.id,
        role="VIEWER",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    member_client = as_principal(member)
    feed_resp = await member_client.get(f"/api/v1/issues/{issue_key}/activity?tab=all")
    assert feed_resp.status_code == 200, feed_resp.text
    feed_body = feed_resp.json()

    # Check zero body leakage
    raw_json_str = feed_resp.text
    assert secret_text not in raw_json_str

    # Check actor redaction
    ext_item = next(it for it in feed_body["items"] if it.get("actor", {}).get("redacted") is True)
    assert ext_item["actor"] == {"redacted": True, "label": "1 External Collaborator"}
    assert "external@partner.corp" not in raw_json_str
    assert "ext_guest" not in raw_json_str
    assert str(ext_user_id) not in raw_json_str

    # 5. Anti-enumeration: non-viewer user gets equalized 404
    non_viewer = await make_user("outsider", workspace_role="WORKSPACE_GUEST")
    non_viewer_client = as_principal(non_viewer)

    resp_non_viewer = await non_viewer_client.get(f"/api/v1/issues/{issue_key}/activity")
    contract_recorder.record("non_viewer_404", resp_non_viewer.request, resp_non_viewer)
    assert resp_non_viewer.status_code == 404

    resp_non_existent = await non_viewer_client.get("/api/v1/issues/SEC-99999/activity")
    assert resp_non_existent.status_code == 404

    p1 = resp_non_viewer.json()
    p2 = resp_non_existent.json()
    p1.pop("request_id", None)
    p2.pop("request_id", None)
    assert p1 == p2


async def test_case_3_project_scoped_rls_filtering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 3: Project-level activity feed filters per-object rows and counts under RLS."""
    admin = await make_user("proj_admin", workspace_role="WORKSPACE_ADMIN")
    reader = await make_user("proj_reader", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "PROJ",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", reader: "MEMBER"},
    )
    client = as_principal(admin)

    # 1. Create Issue 1 (readable by reader)
    i1_resp = await client.post(
        "/api/v1/projects/PROJ/issues",
        json={"summary": "Visible Issue 1", "priority": "low"},
    )
    assert i1_resp.status_code == 201
    i1_id = uuid.UUID(i1_resp.json()["id"])
    i1_key = i1_resp.json()["key"]

    # 2. Create Issue 2 (to be DENIED to reader)
    i2_resp = await client.post(
        "/api/v1/projects/PROJ/issues",
        json={"summary": "Hidden Restricted Issue 2", "priority": "high"},
    )
    assert i2_resp.status_code == 201
    i2_id = uuid.UUID(i2_resp.json()["id"])
    i2_key = i2_resp.json()["key"]

    # Explicit DENY VIEW on Issue 2 for reader
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        i2_id,
        reader.id,
        effect="DENY",
        capability_mask=Capability.VIEW,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)

    # Add comments on both issues
    await client.post(
        f"/api/v1/issues/{i1_key}/comments",
        json={"body_markdown": "Comment on visible issue 1"},
    )
    await client.post(
        f"/api/v1/issues/{i2_key}/comments",
        json={"body_markdown": "Comment on hidden issue 2"},
    )
    await api_env.seed.commit()

    # Admin sees activity from both issues
    admin_feed = await client.get("/api/v1/projects/PROJ/activity?tab=all")
    assert admin_feed.status_code == 200
    admin_body = admin_feed.json()
    admin_issue_ids = {it["payload"].get("issue_id") or it["id"] for it in admin_body["items"]}
    assert admin_body["counts"]["all"] >= 4

    # Reader views project activity
    reader_client = as_principal(reader)
    reader_feed = await reader_client.get("/api/v1/projects/PROJ/activity?tab=all")
    assert reader_feed.status_code == 200, reader_feed.text
    reader_body = reader_feed.json()

    # Zero rows from Issue 2 should appear
    for it in reader_body["items"]:
        # Verify no activity record has object_id == i2_id
        assert str(i2_id) != str(it.get("object_id"))
        assert "Hidden Restricted Issue 2" not in str(it)

    # Issue 2 contributes 0 to counts
    assert reader_body["counts"]["all"] < admin_body["counts"]["all"]


async def test_case_4_hash_chain_exposure(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 4: Cryptographic prev_hash and row_hash exposure and omission."""
    admin = await make_user("auditor", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("HASH", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    iss_resp = await client.post(
        "/api/v1/projects/HASH/issues",
        json={"summary": "Hash Chain Audit Target", "priority": "urgent"},
    )
    assert iss_resp.status_code == 201
    issue_key = iss_resp.json()["key"]
    issue_id = uuid.UUID(iss_resp.json()["id"])

    # 1. Query with include_hashes=true
    resp_hashes = await client.get(f"/api/v1/issues/{issue_key}/activity?include_hashes=true")
    contract_recorder.record("include_hashes_200", resp_hashes.request, resp_hashes)
    assert resp_hashes.status_code == 200, resp_hashes.text
    body_hashes = resp_hashes.json()

    assert len(body_hashes["items"]) > 0
    first_item = body_hashes["items"][0]
    assert "prev_hash" in first_item
    assert "row_hash" in first_item
    assert len(first_item["prev_hash"]) == 64
    assert len(first_item["row_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in first_item["prev_hash"])
    assert all(c in "0123456789abcdef" for c in first_item["row_hash"])

    # Compare with database bytes
    db_rec = await api_env.seed.scalar(
        select(ActivityRecord).where(ActivityRecord.id == uuid.UUID(first_item["id"]))
    )
    assert db_rec is not None
    assert first_item["prev_hash"] == db_rec.prev_hash.hex()
    assert first_item["row_hash"] == db_rec.row_hash.hex()

    # 2. Query with include_hashes=false (default)
    resp_no_hashes = await client.get(f"/api/v1/issues/{issue_key}/activity")
    assert resp_no_hashes.status_code == 200, resp_no_hashes.text
    body_no_hashes = resp_no_hashes.json()
    first_no_hash = body_no_hashes["items"][0]
    assert "prev_hash" not in first_no_hash
    assert "row_hash" not in first_no_hash


async def test_case_5_boundary_and_pagination(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 5: 65 events across partition boundary, keyset pagination, and cursor rejection."""
    admin = await make_user("pager", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("PAGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    iss_resp = await client.post(
        "/api/v1/projects/PAGE/issues",
        json={"summary": "Pagination Test Target Issue", "priority": "none"},
    )
    assert iss_resp.status_code == 201
    issue_key = iss_resp.json()["key"]
    issue_id = uuid.UUID(iss_resp.json()["id"])

    # Ensure activity partitions for October and November 2026 exist
    await api_env.seed.execute(
        text("SELECT ensure_activity_partitions('2026-11-01'::timestamptz, 2, 2)")
    )
    await api_env.seed.commit()

    # Seed 65 activity records:
    # 30 in October 2026, 35 in November 2026
    t_oct = datetime(2026, 10, 31, 23, 50, 0, tzinfo=UTC)
    t_nov = datetime(2026, 11, 1, 0, 5, 0, tzinfo=UTC)

    for i in range(30):
        ts = t_oct + timedelta(seconds=i * 2)
        await api_env.seed.execute(
            text(
                "INSERT INTO activity_records ("
                "  workspace_id, object_id, object_type, actor_id, event_type, payload, recorded_at"
                ") VALUES ("
                "  :ws, :oid, 'issue'::object_kind, :actor, 'ISSUE_FIELD_CHANGED', CAST(:payload AS jsonb), :rec_at"
                ")"
            ),
            {
                "ws": api_env.workspace_id,
                "oid": issue_id,
                "actor": admin.id,
                "payload": f'{{"idx": {i}, "batch": "oct"}}',
                "rec_at": ts,
            },
        )

    for i in range(35):
        ts = t_nov + timedelta(seconds=i * 2)
        await api_env.seed.execute(
            text(
                "INSERT INTO activity_records ("
                "  workspace_id, object_id, object_type, actor_id, event_type, payload, recorded_at"
                ") VALUES ("
                "  :ws, :oid, 'issue'::object_kind, :actor, 'ISSUE_FIELD_CHANGED', CAST(:payload AS jsonb), :rec_at"
                ")"
            ),
            {
                "ws": api_env.workspace_id,
                "oid": issue_id,
                "actor": admin.id,
                "payload": f'{{"idx": {i}, "batch": "nov"}}',
                "rec_at": ts,
            },
        )
    await api_env.seed.commit()

    # 1. Paginate order=desc with limit=25
    seen_desc_ids: list[str] = []
    cursor: str | None = None
    for expected_count in (25, 25, 16):  # 65 + 1 (initial issue_created) = 66
        url = f"/api/v1/issues/{issue_key}/activity?order=desc&limit=25"
        if cursor:
            url += f"&cursor={cursor}"
        page_resp = await client.get(url)
        assert page_resp.status_code == 200, page_resp.text
        page_body = page_resp.json()
        assert len(page_body["items"]) == expected_count
        seen_desc_ids.extend(it["id"] for it in page_body["items"])
        cursor = page_body["next_cursor"]
        if expected_count < 25:
            assert cursor is None
        else:
            assert cursor is not None

    assert len(seen_desc_ids) == 66
    assert len(set(seen_desc_ids)) == 66

    # 2. Paginate order=asc with limit=25
    seen_asc_ids: list[str] = []
    cursor = None
    for expected_count in (25, 25, 16):
        url = f"/api/v1/issues/{issue_key}/activity?order=asc&limit=25"
        if cursor:
            url += f"&cursor={cursor}"
        page_resp = await client.get(url)
        assert page_resp.status_code == 200, page_resp.text
        page_body = page_resp.json()
        assert len(page_body["items"]) == expected_count
        seen_asc_ids.extend(it["id"] for it in page_body["items"])
        cursor = page_body["next_cursor"]
        if expected_count < 25:
            assert cursor is None
        else:
            assert cursor is not None

    assert len(seen_asc_ids) == 66
    assert len(set(seen_asc_ids)) == 66
    assert seen_desc_ids == list(reversed(seen_asc_ids))

    # 3. Validation limits: limit=0 and limit=101 return 422
    resp_l0 = await client.get(f"/api/v1/issues/{issue_key}/activity?limit=0")
    assert resp_l0.status_code == 422

    resp_l101 = await client.get(f"/api/v1/issues/{issue_key}/activity?limit=101")
    assert resp_l101.status_code == 422

    # 4. Mismatched cursor: cursor minted for tab=comments passed to tab=history
    # Seed 1 comment so next_cursor can be minted
    for _ in range(3):
        await client.post(
            f"/api/v1/issues/{issue_key}/comments",
            json={"body_markdown": "Paging comment"},
        )

    com_page = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=comments&limit=1")
    assert com_page.status_code == 200
    com_cursor = com_page.json()["next_cursor"]
    assert com_cursor is not None

    bad_cursor_resp = await client.get(
        f"/api/v1/issues/{issue_key}/activity?tab=history&cursor={com_cursor}"
    )
    contract_recorder.record("invalid_cursor_422", bad_cursor_resp.request, bad_cursor_resp)
    assert bad_cursor_resp.status_code == 422
    assert bad_cursor_resp.json()["code"] == "INVALID_CURSOR"


async def test_case_6_edge_cases_and_branch_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 6: Edge cases, cursor validation errors, linked object masking, and project pagination."""
    admin = await make_user("edge_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("EDGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Cursor secret from environment
    monkeypatch.setenv("KB_CURSOR_SECRET", "custom-secret-key-12345")
    assert _get_cursor_secret() == b"custom-secret-key-12345"
    monkeypatch.delenv("KB_CURSOR_SECRET", raising=False)

    # 2. Cursor unit validation branches
    scope = uuid.uuid4()
    now_dt = datetime.now(UTC)
    rec_id = uuid.uuid4()
    valid_cursor = encode_activity_cursor(scope, "all", "desc", now_dt, rec_id)

    # Roundtrip success
    dec_ts, dec_id = decode_activity_cursor(valid_cursor, scope, "all", "desc")
    assert dec_id == rec_id
    assert abs((dec_ts - now_dt).total_seconds()) < 1.0

    # No dot in cursor
    with pytest.raises(Exception) as exc_info:
        decode_activity_cursor("nodotinthisbase64string", scope, "all", "desc")
    assert getattr(exc_info.value, "status_code", 422) == 422

    # Wrong signature
    corrupted_sig = valid_cursor[:-4] + "AAAA"
    with pytest.raises(Exception):
        decode_activity_cursor(corrupted_sig, scope, "all", "desc")

    # Mismatched scope
    with pytest.raises(Exception):
        decode_activity_cursor(valid_cursor, uuid.uuid4(), "all", "desc")

    # Mismatched tab
    with pytest.raises(Exception):
        decode_activity_cursor(valid_cursor, scope, "comments", "desc")

    # Mismatched order
    with pytest.raises(Exception):
        decode_activity_cursor(valid_cursor, scope, "all", "asc")

    # Corrupted / invalid base64
    with pytest.raises(Exception):
        decode_activity_cursor("@@@@@@", scope, "all", "desc")

    # Wrong segment count
    raw_3 = b"only:three:parts"
    sig_3 = hmac.new(_get_cursor_secret(), raw_3, hashlib.sha256).hexdigest().encode("ascii")
    tok_3 = base64.urlsafe_b64encode(raw_3 + b"." + sig_3).decode().rstrip("=")
    with pytest.raises(Exception):
        decode_activity_cursor(tok_3, scope, "all", "desc")

    # 3. Create target issue for route validation
    iss_resp = await client.post(
        "/api/v1/projects/EDGE/issues",
        json={"summary": "Edge Coverage Target Issue", "priority": "low"},
    )
    assert iss_resp.status_code == 201
    issue_key = iss_resp.json()["key"]
    issue_id = uuid.UUID(iss_resp.json()["id"])

    # 4. Invalid tab and order error responses on issue endpoint (HTTP 422 validation)
    resp_bad_tab = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=unknown")
    assert resp_bad_tab.status_code == 422

    resp_bad_order = await client.get(f"/api/v1/issues/{issue_key}/activity?order=diagonal")
    assert resp_bad_order.status_code == 422

    # 5. Invalid tab and order error responses on project endpoint
    resp_proj_bad_tab = await client.get("/api/v1/projects/EDGE/activity?tab=unknown")
    assert resp_proj_bad_tab.status_code == 422

    resp_proj_bad_order = await client.get("/api/v1/projects/EDGE/activity?order=diagonal")
    assert resp_proj_bad_order.status_code == 422

    # Direct service calls for coverage on service validation branches
    caller_ctx = PrincipalContext(
        principal_id=admin.id, workspace_id=api_env.workspace_id, token_scopes=("session",)
    )
    with pytest.raises(ProblemException) as pe_tab:
        await get_issue_activity(api_env.seed, caller_ctx, issue_key, tab="unknown")
    assert pe_tab.value.code == "INVALID_TAB"

    with pytest.raises(ProblemException) as pe_ord:
        await get_issue_activity(api_env.seed, caller_ctx, issue_key, order="diagonal")
    assert pe_ord.value.code == "INVALID_ORDER"

    with pytest.raises(ProblemException) as pe_ptab:
        await get_project_activity(api_env.seed, caller_ctx, "EDGE", tab="unknown")
    assert pe_ptab.value.code == "INVALID_TAB"

    with pytest.raises(ProblemException) as pe_pord:
        await get_project_activity(api_env.seed, caller_ctx, "EDGE", order="diagonal")
    assert pe_pord.value.code == "INVALID_ORDER"

    # Empty actors check
    empty_actors = await _resolve_actors(api_env.seed, caller_ctx, set())
    assert empty_actors == {}

    # 6. Project-level cursor pagination (desc and asc)
    # Post 2 comments so project has at least 3 activity records
    for i in range(2):
        await client.post(
            f"/api/v1/issues/{issue_key}/comments",
            json={"body_markdown": f"Project paging comment {i}"},
        )

    # Page 1 (desc)
    proj_p1 = await client.get("/api/v1/projects/EDGE/activity?limit=1&order=desc")
    assert proj_p1.status_code == 200
    p1_data = proj_p1.json()
    assert len(p1_data["items"]) == 1
    cursor_desc = p1_data["next_cursor"]
    assert cursor_desc is not None

    # Page 2 (desc) using cursor
    proj_p2 = await client.get(
        f"/api/v1/projects/EDGE/activity?limit=1&order=desc&cursor={cursor_desc}"
    )
    assert proj_p2.status_code == 200
    p2_data = proj_p2.json()
    assert len(p2_data["items"]) == 1
    assert p2_data["items"][0]["id"] != p1_data["items"][0]["id"]

    # Page 1 (asc)
    proj_asc1 = await client.get("/api/v1/projects/EDGE/activity?limit=1&order=asc")
    assert proj_asc1.status_code == 200
    asc1_data = proj_asc1.json()
    cursor_asc = asc1_data["next_cursor"]
    assert cursor_asc is not None

    # Page 2 (asc) using cursor
    proj_asc2 = await client.get(
        f"/api/v1/projects/EDGE/activity?limit=1&order=asc&cursor={cursor_asc}"
    )
    assert proj_asc2.status_code == 200
    assert len(proj_asc2.json()["items"]) == 1

    # 7. Agent actor resolution and display
    agent_id = await create_agent(
        api_env.seed, api_env.workspace_id, "Edge Coverage Bot", principal_type="AGENT"
    )
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=agent_id,
        event_type=ActivityEventType.GATE_APPROVED,
        payload={"gate": "security-review", "model": "gemini-flash"},
    )
    await api_env.seed.commit()

    agent_act_resp = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=gates")
    assert agent_act_resp.status_code == 200
    gates_items = agent_act_resp.json()["items"]
    assert len(gates_items) >= 1
    gate_actor = gates_items[0]["actor"]
    assert gate_actor["type"] == "AGENT"
    assert "edge" in gate_actor["slug"].lower() or "bot" in gate_actor["display_name"].lower()

    # 8. Unreadable linked object masking (LINK_CREATED / LINK_DELETED)
    # Create a secret doc where caller has no capability
    secret_doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="SEC-DOC-1",
        title="Restricted Blueprint",
        project_id=proj_id,
    )
    # Explicit DENY VIEW on secret doc for admin
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        secret_doc_id,
        admin.id,
        effect="DENY",
        capability_mask=Capability.VIEW,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)

    # Record LINK_CREATED referencing secret_doc_id
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.LINK_CREATED,
        payload={
            "source_id": str(issue_id),
            "target_id": str(secret_doc_id),
            "link_type": "BLOCKS",
        },
    )
    await api_env.seed.commit()

    link_act_resp = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=history")
    assert link_act_resp.status_code == 200
    link_item = next(
        it
        for it in link_act_resp.json()["items"]
        if it["event_type"] == ActivityEventType.LINK_CREATED.value
    )
    assert link_item["payload"].get("target") == {"restricted": True, "label": "Restricted Object"}
    assert "target_id" not in link_item["payload"]

    # 9. Project feed comment hydration (active and soft-deleted with reactions)
    c_p_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Comment to be deleted in project"},
    )
    assert c_p_resp.status_code == 201
    c_p_id = c_p_resp.json()["id"]

    await client.put(f"/api/v1/comments/{c_p_id}/reactions/%F0%9F%91%8D")
    await client.delete(f"/api/v1/comments/{c_p_id}")

    proj_comments = await client.get("/api/v1/projects/EDGE/activity?tab=comments")
    assert proj_comments.status_code == 200
    assert len(proj_comments.json()["items"]) >= 2

    # 10. Inactive user + SCRIPT_EPHEMERAL + non-existent actor in _resolve_actors
    ephemeral_id = await create_agent(
        api_env.seed, api_env.workspace_id, "Eph Bot", principal_type="SCRIPT_EPHEMERAL"
    )
    disabled_user_id = await create_user(
        api_env.seed, api_env.workspace_id, handle="@disabled_user", display_name="Disabled User"
    )
    await api_env.seed.execute(
        text("UPDATE principals SET status = 'DISABLED' WHERE id = :id"),
        {"id": disabled_user_id},
    )
    await api_env.seed.commit()

    viewer_user = await make_user("viewer_cover", workspace_role="WORKSPACE_MEMBER")
    viewer_ctx = PrincipalContext(
        principal_id=viewer_user.id, workspace_id=api_env.workspace_id, token_scopes=("session",)
    )
    resolved_edge_actors = await _resolve_actors(
        api_env.seed,
        viewer_ctx,
        {uuid.uuid4(), ephemeral_id, disabled_user_id},
        proj_id,
    )
    assert all(
        isinstance(r, RedactedActorSummary) and r.redacted is True
        for r in resolved_edge_actors.values()
    )

    # 11. Referenced principal redaction in payload (assignee_id)
    await record_activity(
        api_env.seed,
        workspace_id=api_env.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={"assignee_id": str(disabled_user_id), "field": "assignee"},
    )
    await api_env.seed.commit()

    viewer_client = as_principal(viewer_user)
    v_feed = await viewer_client.get(f"/api/v1/issues/{issue_key}/activity?tab=history")
    assert v_feed.status_code == 200
    item_assignee = next(
        it for it in v_feed.json()["items"] if it.get("payload", {}).get("field") == "assignee"
    )
    assert item_assignee["payload"]["assignee_id"] == {
        "redacted": True,
        "label": "1 External Collaborator",
    }

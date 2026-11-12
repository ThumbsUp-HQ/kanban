# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for comments API (KB-P3-05 / S7.2 8k)."""

from __future__ import annotations

import base64
import hashlib
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from sqlalchemy import text

from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.comments import CommentPatch
from kanban.content import ContentNormalizeError
from kanban.security.permissions import Capability
from kanban.services.comments import (
    _batch_reactions,
    _decode_cursor,
    _normalize_comment_body,
    _resolve_authors,
)
from kanban.services.comments import (
    add_reaction as svc_add_rx,
)
from kanban.services.comments import (
    delete_comment as svc_del_com,
)
from kanban.services.comments import (
    delete_reaction as svc_del_rx,
)
from kanban.services.comments import (
    update_comment as svc_upd_com,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:  # noqa: ANN401
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def test_case_1_positive_comments_replies_permalinks_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Post top comment and reply; verify nesting, permalinks and activity."""
    admin = await make_user("alice", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("COMM", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create target issue
    issue_resp = await client.post(
        "/api/v1/projects/COMM/issues",
        json={"summary": "Threading and Comments Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_data = issue_resp.json()
    issue_key = issue_data["key"]
    issue_id = issue_data["id"]

    # 2. Post top-level comment
    top_md = "This is a **top-level** comment with markdown and @alice mention."
    expected_top_sha = hashlib.sha256(top_md.encode("utf-8")).hexdigest()
    resp_top = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": top_md, "parent_comment_id": None},
    )
    contract_recorder.record("create_comment_201", resp_top.request, resp_top)
    assert resp_top.status_code == 201, resp_top.text
    top_comment = resp_top.json()
    assert top_comment["body_markdown"] == top_md
    assert top_comment["parent_comment_id"] is None
    assert top_comment["author_id"] == str(admin.id)
    assert resp_top.headers["ETag"] == f'"{expected_top_sha}"'
    assert resp_top.headers["Location"].startswith(f"/projects/COMM/issues/{issue_key}#comment-")
    assert top_comment["permalink"].startswith(f"/projects/COMM/issues/{issue_key}#comment-")
    assert top_comment["deleted"] is False

    top_cid = top_comment["id"]

    # 3. Post reply to the top-level comment
    reply_md = "This is a depth-1 reply to the top comment."
    expected_reply_sha = hashlib.sha256(reply_md.encode("utf-8")).hexdigest()
    resp_reply = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": reply_md, "parent_comment_id": top_cid},
    )
    contract_recorder.record("create_reply_201", resp_reply.request, resp_reply)
    assert resp_reply.status_code == 201, resp_reply.text
    reply_comment = resp_reply.json()
    assert reply_comment["body_markdown"] == reply_md
    assert reply_comment["parent_comment_id"] == top_cid
    assert resp_reply.headers["ETag"] == f'"{expected_reply_sha}"'

    # 4. List comments and verify nesting
    resp_list = await client.get(f"/api/v1/issues/{issue_key}/comments")
    assert resp_list.status_code == 200, resp_list.text
    list_body = resp_list.json()
    assert len(list_body["items"]) == 1
    listed_top = list_body["items"][0]
    assert listed_top["id"] == top_cid
    assert len(listed_top["replies"]) == 1
    listed_reply = listed_top["replies"][0]
    assert listed_reply["id"] == reply_comment["id"]
    assert listed_reply["parent_comment_id"] == top_cid

    # 5. Verify COMMENT_CREATED activity rows written
    sql_act = (
        "SELECT count(*) FROM activity_records "
        "WHERE object_id = :oid AND event_type = 'COMMENT_CREATED'"
    )
    activity_count = await _count(api_env, sql_act, oid=issue_id)
    assert activity_count == 2


async def test_case_2_mention_access_warning_and_acknowledgement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 2: Mention without VIEW gives 409; ack gives 201; 0 ACL widening."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    maya = await make_user("maya")

    # Project restricted to admin only (maya has no role and no ACL entry)
    _ = await make_project("PRIV", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    issue_resp = await client.post(
        "/api/v1/projects/PRIV/issues",
        json={"summary": "Top Secret Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_key = issue_resp.json()["key"]

    # 1. Mention Maya (in workspace, but lacks VIEW) -> 409 MENTION_ACCESS_WARNING
    warning_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Hey @maya please review this confidential spec."},
    )
    contract_recorder.record("mention_access_warning_409", warning_resp.request, warning_resp)
    assert warning_resp.status_code == 409, warning_resp.text
    problem = warning_resp.json()
    assert problem["code"] == "MENTION_ACCESS_WARNING"
    assert problem["type"] == "https://kanban/problems/mention-access-warning"
    assert "unauthorized_mentions" in problem
    assert any(
        u["handle"] == "maya" and u["principal_id"] == str(maya.id)
        for u in problem["unauthorized_mentions"]
    )

    # Count ACL entries before resubmitting
    acl_count_before = await _count(api_env, "SELECT count(*) FROM resource_acl_entries")

    # 2. Resubmit with acknowledge_mentions containing Maya's principal_id -> 201 Created
    ack_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={
            "body_markdown": "Hey @maya please review this confidential spec.",
            "acknowledge_mentions": [str(maya.id)],
        },
    )
    contract_recorder.record("acknowledged_mention_201", ack_resp.request, ack_resp)
    assert ack_resp.status_code == 201, ack_resp.text
    ack_body = ack_resp.json()
    assert any(
        u["handle"] == "maya" and u["principal_id"] == str(maya.id)
        for u in ack_body["unnotified_mentions"]
    )

    # 3. Assert resource_acl_entries count remains strictly unchanged (zero silent widening!)
    acl_count_after = await _count(api_env, "SELECT count(*) FROM resource_acl_entries")
    assert acl_count_before == acl_count_after


async def test_case_3_mention_enumeration_defense(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 3: External and nonexistent handles return 201 with zero enumeration."""
    ws2_id = await create_workspace(api_env.seed, name="External WS")
    _ = await create_user(
        api_env.seed, ws2_id, handle="@external_user", display_name="External User"
    )
    await api_env.seed.commit()

    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("ENUM", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    issue_resp = await client.post(
        "/api/v1/projects/ENUM/issues",
        json={"summary": "Enumeration Defense Test", "priority": "none"},
    )
    issue_key = issue_resp.json()["key"]

    # Mention external handle and ghost handle
    resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Hello @external_user and @ghost_phantom_handle, welcome."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Zero mentions resolved and zero unnotified mentions
    assert len(body["mentions"]) == 0
    assert len(body["unnotified_mentions"]) == 0


async def test_case_4_mention_parser_and_capacity_rules(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 4: Parser exclusions (code fence, inline code, URL, email) and 51 handles 422."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("PARSE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    issue_resp = await client.post(
        "/api/v1/projects/PARSE/issues",
        json={"summary": "Parser Test", "priority": "none"},
    )
    issue_key = issue_resp.json()["key"]

    # 1. Mention inside code fence, inline code, URL, and email -> should NOT be extracted
    md_tricky = """
    ```
    @admin4 in code fence
    ```
    `@admin4` in inline code
    Check out https://x/@admin4
    And email is test@admin4.com
    """
    resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": md_tricky},
    )
    assert resp.status_code == 201, resp.text
    assert len(resp.json()["mentions"]) == 0

    # 2. 51 distinct handles -> 422 TOO_MANY_MENTIONS
    fifty_one_handles = " ".join(f"@user{i}" for i in range(51))
    resp_51 = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": fifty_one_handles},
    )
    assert resp_51.status_code == 422
    assert resp_51.json()["code"] == "TOO_MANY_MENTIONS"


async def test_case_5_sanitization_boundary_and_threading_depth(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 5: Script stripped; 262144 vs 262145 bytes; depth > 1 rejected with 422."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("BOUND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    issue_resp = await client.post(
        "/api/v1/projects/BOUND/issues",
        json={"summary": "Boundary Test", "priority": "none"},
    )
    issue_key = issue_resp.json()["key"]

    # 1. Hostile <script> tag is stripped by normalizer
    xss_body = "Hello <script>alert(1)</script>world"
    resp_xss = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": xss_body},
    )
    assert resp_xss.status_code == 201
    assert "<script>" not in resp_xss.json()["body_markdown"]

    # 2. 262144 bytes succeeds
    max_body = "A" * 262144
    resp_max = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": max_body},
    )
    assert resp_max.status_code == 201

    # 3. 262145 bytes returns 422 COMMENT_LENGTH
    oversized = "A" * 262145
    resp_over = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": oversized},
    )
    assert resp_over.status_code == 422
    assert resp_over.json()["code"] == "COMMENT_LENGTH"

    # 4. Reply to a reply returns 422 INVALID_PARENT_COMMENT (max depth 1)
    resp_top = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Top level comment"},
    )
    top_id = resp_top.json()["id"]

    resp_r1 = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Depth 1 reply", "parent_comment_id": top_id},
    )
    r1_id = resp_r1.json()["id"]

    resp_r2 = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Depth 2 reply (invalid)", "parent_comment_id": r1_id},
    )
    assert resp_r2.status_code == 422
    assert resp_r2.json()["code"] == "INVALID_PARENT_COMMENT"


async def test_case_6_concurrency_auth_and_soft_delete(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 6: Edit by non-author 403; stale ETag 412; missing If-Match 428."""
    alice = await make_user("alice6", workspace_role="WORKSPACE_MEMBER")
    bob = await make_user("bob6", workspace_role="WORKSPACE_MEMBER")
    stranger = await make_user("stranger6", workspace_role="WORKSPACE_GUEST")

    _ = await make_project(
        "CONC",
        created_by=alice,
        roles={alice: "PROJECT_ADMIN", bob: "MEMBER"},
    )

    client = as_principal(alice)
    issue_resp = await client.post(
        "/api/v1/projects/CONC/issues",
        json={"summary": "Concurrency Test Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_key = issue_resp.json()["key"]

    # Alice posts comment
    post_resp = await client.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Alice original comment"},
    )
    assert post_resp.status_code == 201, post_resp.text
    cid = post_resp.json()["id"]
    correct_etag = post_resp.headers["ETag"]

    # 1. Edit by Bob (non-author) -> 403 NOT_COMMENT_AUTHOR
    client_bob = as_principal(bob)
    resp_bob_edit = await client_bob.patch(
        f"/api/v1/comments/{cid}",
        headers={"If-Match": correct_etag},
        json={"body_markdown": "Bob hijack attempt"},
    )
    assert resp_bob_edit.status_code == 403
    assert resp_bob_edit.json()["code"] == "NOT_COMMENT_AUTHOR"

    # 2. Missing If-Match -> 428 PRECONDITION_REQUIRED
    client_alice = as_principal(alice)
    resp_missing = await client_alice.patch(
        f"/api/v1/comments/{cid}",
        json={"body_markdown": "Alice update attempt without header"},
    )
    assert resp_missing.status_code == 428
    assert resp_missing.json()["code"] == "PRECONDITION_REQUIRED"

    # 3. Stale ETag -> 412 PRECONDITION_FAILED
    resp_stale = await client_alice.patch(
        f"/api/v1/comments/{cid}",
        headers={"If-Match": '"deadbeef12345678"'},
        json={"body_markdown": "Alice stale update attempt"},
    )
    contract_recorder.record("edit_comment_412", resp_stale.request, resp_stale)
    assert resp_stale.status_code == 412
    assert resp_stale.json()["code"] == "PRECONDITION_FAILED"

    # 4. Valid edit by Alice
    resp_ok = await client_alice.patch(
        f"/api/v1/comments/{cid}",
        headers={"If-Match": correct_etag},
        json={"body_markdown": "Alice edited comment content"},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["body_markdown"] == "Alice edited comment content"
    new_etag = resp_ok.headers["ETag"]
    assert new_etag != correct_etag

    # 5. Non-viewer stranger GET comments -> 404 NOT_FOUND
    client_stranger = as_principal(stranger)
    resp_unreadable = await client_stranger.get(f"/api/v1/issues/{issue_key}/comments")
    contract_recorder.record("get_unreadable_comment_404", resp_unreadable.request, resp_unreadable)
    assert resp_unreadable.status_code == 404

    # 6. Soft delete by Alice
    client_alice = as_principal(alice)
    resp_del = await client_alice.delete(f"/api/v1/comments/{cid}")
    assert resp_del.status_code == 204

    # List returns {"id", "deleted": true} with no body
    resp_list = await client_alice.get(f"/api/v1/issues/{issue_key}/comments")
    assert resp_list.status_code == 200
    del_comment = resp_list.json()["items"][0]
    assert del_comment["id"] == cid
    assert del_comment["deleted"] is True
    assert del_comment["body_markdown"] is None

    # Patch on deleted comment returns 409 COMMENT_DELETED
    resp_edit_del = await client_alice.patch(
        f"/api/v1/comments/{cid}",
        headers={"If-Match": new_etag},
        json={"body_markdown": "Trying to edit deleted comment"},
    )
    assert resp_edit_del.status_code == 409
    assert resp_edit_del.json()["code"] == "COMMENT_DELETED"


async def test_case_7_reactions_allowlist_idempotency_and_security(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 7: PUT rocket twice gives count 1; invalid emoji 422; unreadable gives 404."""
    user1 = await make_user("user1", workspace_role="WORKSPACE_MEMBER")
    user2 = await make_user("user2", workspace_role="WORKSPACE_MEMBER")
    stranger = await make_user("stranger7", workspace_role="WORKSPACE_GUEST")

    _ = await make_project(
        "REACT",
        created_by=user1,
        roles={user1: "PROJECT_ADMIN", user2: "MEMBER"},
    )
    client1 = as_principal(user1)

    issue_resp = await client1.post(
        "/api/v1/projects/REACT/issues",
        json={"summary": "Reactions Test Issue", "priority": "none"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_key = issue_resp.json()["key"]

    post_resp = await client1.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "React to this comment!"},
    )
    assert post_resp.status_code == 201, post_resp.text
    cid = post_resp.json()["id"]

    # 1. PUT 🚀 reaction
    resp_r1 = await client1.put(f"/api/v1/comments/{cid}/reactions/%F0%9F%9A%80")
    contract_recorder.record("put_reaction_200", resp_r1.request, resp_r1)
    assert resp_r1.status_code == 200, resp_r1.text
    body_r1 = resp_r1.json()
    assert body_r1["emoji"] == "🚀"
    assert body_r1["count"] == 1
    assert body_r1["reacted_by_me"] is True

    # 2. PUT 🚀 again (idempotent) yields count: 1
    resp_r2 = await client1.put(f"/api/v1/comments/{cid}/reactions/%F0%9F%9A%80")
    assert resp_r2.status_code == 200
    assert resp_r2.json()["count"] == 1

    # 3. User 2 also reacts 🚀 -> count: 2
    client2 = as_principal(user2)
    resp_u2 = await client2.put(f"/api/v1/comments/{cid}/reactions/%F0%9F%9A%80")
    assert resp_u2.status_code == 200
    assert resp_u2.json()["count"] == 2

    # 4. User 1 removes reaction
    client1 = as_principal(user1)
    del_resp = await client1.delete(f"/api/v1/comments/{cid}/reactions/%F0%9F%9A%80")
    assert del_resp.status_code == 204

    # User 1 lists comments -> reactions show count: 1, reacted_by_me: False
    list_resp = await client1.get(f"/api/v1/issues/{issue_key}/comments")
    reactions = list_resp.json()["items"][0]["reactions"]
    assert len(reactions) == 1
    assert reactions[0]["emoji"] == "🚀"
    assert reactions[0]["count"] == 1
    assert reactions[0]["reacted_by_me"] is False

    # 5. PUT 💩 (disallowed emoji) returns 422 EMOJI_NOT_ALLOWED
    resp_bad = await client1.put(f"/api/v1/comments/{cid}/reactions/%F0%9F%92%A9")
    assert resp_bad.status_code == 422
    assert resp_bad.json()["code"] == "EMOJI_NOT_ALLOWED"

    # 6. Reacting on unreadable issue returns 404
    client_stranger = as_principal(stranger)
    resp_unreadable = await client_stranger.put(f"/api/v1/comments/{cid}/reactions/%F0%9F%9A%80")
    assert resp_unreadable.status_code == 404


async def test_comments_pagination_and_cursors(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test pagination cursors, limit clamping, and malformed cursor handling."""
    admin = await make_user("admin_pg", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("CPG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    issue_resp = await client.post(
        "/api/v1/projects/CPG/issues",
        json={"summary": "Pagination Test Issue", "priority": "none"},
    )
    issue_key = issue_resp.json()["key"]

    # Post 3 comments
    _ = (
        await client.post(
            f"/api/v1/issues/{issue_key}/comments", json={"body_markdown": "Comment 1"}
        )
    ).json()["id"]
    _ = (
        await client.post(
            f"/api/v1/issues/{issue_key}/comments", json={"body_markdown": "Comment 2"}
        )
    ).json()["id"]
    c3 = (
        await client.post(
            f"/api/v1/issues/{issue_key}/comments", json={"body_markdown": "Comment 3"}
        )
    ).json()["id"]

    # Fetch with limit=2 -> next_cursor must be present
    p1_resp = await client.get(f"/api/v1/issues/{issue_key}/comments?limit=2")
    assert p1_resp.status_code == 200
    p1 = p1_resp.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    # Fetch page 2 using next_cursor
    p2_resp = await client.get(
        f"/api/v1/issues/{issue_key}/comments?limit=2&cursor={p1['next_cursor']}"
    )
    assert p2_resp.status_code == 200
    p2 = p2_resp.json()
    assert len(p2["items"]) == 1
    assert p2["items"][0]["id"] == c3
    assert p2["next_cursor"] is None

    # Invalid cursor returns 422 INVALID_CURSOR
    bad_cursor_resp = await client.get(
        f"/api/v1/issues/{issue_key}/comments?cursor=bad-cursor-string"
    )
    assert bad_cursor_resp.status_code == 422
    assert bad_cursor_resp.json()["code"] == "INVALID_CURSOR"


async def test_comments_permissions_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test red heart normalize, missing objects, view-only roles, and ack mentions on edit."""
    admin = await make_user("admin_cov", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer_cov")
    _ = await make_project(
        "COV",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", viewer: "VIEWER"},
    )
    client_admin = as_principal(admin)

    # 1. Create issue
    issue_resp = await client_admin.post(
        "/api/v1/projects/COV/issues",
        json={"summary": "Coverage Issue", "priority": "none"},
    )
    issue_data = issue_resp.json()
    issue_key = issue_data["key"]
    issue_id_cov = uuid.UUID(issue_data["id"])

    # Deny COMMENT capability explicitly for viewer
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        issue_id_cov,
        viewer.id,
        effect="DENY",
        capability_mask=Capability.COMMENT,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Post comment
    c1 = (
        await client_admin.post(
            f"/api/v1/issues/{issue_key}/comments", json={"body_markdown": "Comment 1"}
        )
    ).json()["id"]

    # Red heart without variation selector normalize
    heart_resp = await client_admin.put(f"/api/v1/comments/{c1}/reactions/%E2%9D%A4")
    assert heart_resp.status_code == 200
    assert heart_resp.json()["emoji"] == "❤️"

    # View-only caller attempts write operations -> 403 INSUFFICIENT_CAPABILITY
    client_viewer = as_principal(viewer)
    post_as_viewer = await client_viewer.post(
        f"/api/v1/issues/{issue_key}/comments",
        json={"body_markdown": "Viewer comment attempt"},
    )
    assert post_as_viewer.status_code == 403

    react_as_viewer = await client_viewer.put(f"/api/v1/comments/{c1}/reactions/%F0%9F%9A%80")
    assert react_as_viewer.status_code == 403

    del_react_as_viewer = await client_viewer.delete(
        f"/api/v1/comments/{c1}/reactions/%F0%9F%9A%80"
    )
    assert del_react_as_viewer.status_code == 403

    # Delete comment as viewer (not author, not admin) returns 403
    del_as_viewer = await client_viewer.delete(f"/api/v1/comments/{c1}")
    assert del_as_viewer.status_code == 403

    # Non-existent comment IDs return 404
    client_admin = as_principal(admin)
    random_cid = uuid.uuid4()
    assert (
        await client_admin.patch(
            f"/api/v1/comments/{random_cid}",
            headers={"If-Match": '"x"'},
            json={"body_markdown": "test"},
        )
    ).status_code == 404
    assert (await client_admin.delete(f"/api/v1/comments/{random_cid}")).status_code == 404
    assert (
        await client_admin.put(f"/api/v1/comments/{random_cid}/reactions/%F0%9F%9A%80")
    ).status_code == 404
    assert (
        await client_admin.delete(f"/api/v1/comments/{random_cid}/reactions/%F0%9F%9A%80")
    ).status_code == 404

    # Edit comment adding newly acknowledged mention
    maya = await make_user("maya_cov")
    c1_etag = (await client_admin.get(f"/api/v1/issues/{issue_key}/comments")).json()["items"][0][
        "body_sha256"
    ]
    edit_ack_resp = await client_admin.patch(
        f"/api/v1/comments/{c1}",
        headers={"If-Match": f'"{c1_etag}"'},
        json={
            "body_markdown": "Updated comment with @maya_cov mention",
            "acknowledge_mentions": [str(maya.id)],
        },
    )
    assert edit_ack_resp.status_code == 200
    assert any(m["handle"] == "maya_cov" for m in edit_ack_resp.json()["unnotified_mentions"])


async def test_comments_service_internal_branches(
    api_env: ApiEnv,
) -> None:
    """Cover internal fallbacks, normalization errors, empty batch queries, and cursor branches."""
    # 1. Empty sets on batch functions
    assert await _resolve_authors(api_env.seed, set()) == {}
    assert await _batch_reactions(api_env.seed, set(), uuid.uuid4()) == {}

    # 2. _decode_cursor with malformed separator
    no_pipe = base64.urlsafe_b64encode(b"noparts").decode("ascii")
    with pytest.raises(ProblemException) as exc1:
        _decode_cursor(no_pipe)
    assert exc1.value.code == "INVALID_CURSOR"

    # 3. _normalize_comment_body exception mapping
    with patch(
        "kanban.services.comments.normalize_to_markdown",
        side_effect=ContentNormalizeError("CONTENT_TOO_LARGE", "Too large"),
    ):
        with pytest.raises(ProblemException) as exc2:
            _normalize_comment_body("test")
        assert exc2.value.code == "COMMENT_LENGTH"

    with patch(
        "kanban.services.comments.normalize_to_markdown",
        side_effect=ContentNormalizeError("OTHER_ERR", "Invalid"),
    ):
        with pytest.raises(ProblemException) as exc3:
            _normalize_comment_body("test")
        assert exc3.value.code == "INVALID_CONTENT"

    with patch(
        "kanban.services.comments.normalize_to_markdown",
        side_effect=UnicodeEncodeError("utf-8", "test", 0, 1, "reason"),
    ):
        with pytest.raises(ProblemException) as exc4:
            _normalize_comment_body("test")
        assert exc4.value.code == "INVALID_CONTENT"


async def test_comments_service_reply_pagination_and_anti_enumeration(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Cover replies pagination > 200 and caller anti-enumeration 404s."""
    user = await make_user("replier")
    _ = await make_project("REP", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)
    issue_resp = await client.post(
        "/api/v1/projects/REP/issues", json={"summary": "200 replies issue"}
    )
    issue_key = issue_resp.json()["key"]
    issue_id = uuid.UUID(issue_resp.json()["id"])
    parent_id = uuid.UUID(
        (
            await client.post(
                f"/api/v1/issues/{issue_key}/comments", json={"body_markdown": "Parent"}
            )
        ).json()["id"]
    )

    insert_sql = (
        "INSERT INTO issue_comments "
        "(id, workspace_id, issue_id, parent_comment_id, author_id, body_markdown) "
        "SELECT uuidv7(), :ws, :iid, :pid, :aid, 'reply ' || g "
        "FROM generate_series(1, 205) g"
    )
    await api_env.seed.execute(
        text(insert_sql),
        {"ws": api_env.workspace_id, "iid": issue_id, "pid": parent_id, "aid": user.id},
    )
    await api_env.seed.commit()

    list_with_200 = await client.get(f"/api/v1/issues/{issue_key}/comments")
    assert list_with_200.status_code == 200
    top = list_with_200.json()["items"][0]
    assert len(top["replies"]) == 200
    assert top["replies_next_cursor"] is not None

    # Service anti-enumeration 404 when issue is unreadable to caller
    stranger = await make_user("stranger_cov", workspace_role="WORKSPACE_GUEST")
    as_principal(stranger)  # sets resolver.principal
    stranger_ctx = api_env.resolver.principal
    assert stranger_ctx is not None

    # Query valid comment
    c_row = (
        await api_env.seed.execute(
            text("SELECT id FROM issue_comments WHERE issue_id = :iid LIMIT 1"), {"iid": issue_id}
        )
    ).scalar_one()

    # Stranger has no VIEW on REP project
    with pytest.raises(ProblemException) as exc_upd:
        await svc_upd_com(
            api_env.seed,
            stranger_ctx,
            c_row,
            CommentPatch(body_markdown="x"),
            if_match='"x"',
        )
    assert exc_upd.value.status == 404

    with pytest.raises(ProblemException) as exc_del:
        await svc_del_com(api_env.seed, stranger_ctx, c_row)
    assert exc_del.value.status == 404

    with pytest.raises(ProblemException) as exc_rx_add:
        await svc_add_rx(api_env.seed, stranger_ctx, c_row, "🚀")
    assert exc_rx_add.value.status == 404

    with pytest.raises(ProblemException) as exc_rx_del:
        await svc_del_rx(api_env.seed, stranger_ctx, c_row, "🚀")
    assert exc_rx_del.value.status == 404

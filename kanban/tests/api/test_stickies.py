# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Stickies API, complexity heuristics & promote-to-doc (KB-P3-15)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import Doc, ObjectLink, Page, ResourceAclEntry
from kanban.api.problems import ProblemException
from kanban.services.stickies import _decode_cursor, _derive_title, _format_etag
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_group_member,
    add_role_binding,
    create_group,
    create_project,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _setup_project(api_env: ApiEnv, user: SeededUser, identifier: str = "STK") -> uuid.UUID:
    """Create a test project in the workspace."""
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier=identifier,
        name=f"Stickies Project {identifier}",
        created_by_id=user.id,
    )
    await api_env.seed.commit()
    return proj_id


async def test_case_1_crud_and_listing(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 1: CRUD operations, ETag caching, project and workspace keyset listing."""
    admin = await make_user("stk_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="CRUD")

    # 1. Create sticky
    create_payload = {
        "body_markdown": "# Quick Note\nRemember to review database schemas.",
        "color_token": "mint",
        "sort_rank": "a0",
    }
    resp = await client.post(f"/api/v1/projects/{proj_id}/stickies", json=create_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    sticky_id = data["id"]
    etag_v1 = resp.headers["ETag"]
    assert resp.headers["Location"] == f"/api/v1/stickies/{sticky_id}"
    assert data["color_token"] == "mint"
    assert data["sort_rank"] == "a0"
    assert not data["is_promoted_stub"]
    assert data["promoted_to_doc"] is None
    assert "VIEW" in data["capabilities"]
    assert "EDIT" in data["capabilities"]

    # 2. Get sticky with ETag caching and 304
    get_resp = await client.get(f"/api/v1/stickies/{sticky_id}")
    assert get_resp.status_code == 200
    assert get_resp.headers["ETag"] == etag_v1

    # 304 on exact If-None-Match
    cached_resp = await client.get(
        f"/api/v1/stickies/{sticky_id}", headers={"If-None-Match": etag_v1}
    )
    assert cached_resp.status_code == 304

    # 304 on wildcard "*"
    wildcard_resp = await client.get(
        f"/api/v1/stickies/{sticky_id}", headers={"If-None-Match": "*"}
    )
    assert wildcard_resp.status_code == 304

    # 3. Create second sticky to test listing order
    resp2 = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "Second note", "color_token": "coral", "sort_rank": "a1"},
    )
    assert resp2.status_code == 201
    sticky2_id = resp2.json()["id"]

    # 4. List project stickies ordered by sort_rank COLLATE "C"
    list_resp = await client.get(f"/api/v1/projects/{proj_id}/stickies")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 2
    assert items[0]["id"] == sticky_id
    assert items[1]["id"] == sticky2_id

    # 5. Keyset pagination on workspace stickies
    ws_list_resp = await client.get("/api/v1/stickies", params={"limit": 1})
    assert ws_list_resp.status_code == 200
    ws_data = ws_list_resp.json()
    assert len(ws_data["items"]) == 1
    assert ws_data["next_cursor"] is not None

    # Next page
    ws_page2 = await client.get(
        "/api/v1/stickies", params={"cursor": ws_data["next_cursor"], "limit": 1}
    )
    assert ws_page2.status_code == 200
    assert len(ws_page2.json()["items"]) == 1

    # Bad cursor returns 422 INVALID_CURSOR
    bad_cursor_resp = await client.get(
        "/api/v1/stickies", params={"cursor": "not-valid-base64-!!!"}
    )
    assert bad_cursor_resp.status_code == 422
    assert bad_cursor_resp.json()["code"] == "INVALID_CURSOR"

    # 6. Update sticky (recolor and sort_rank) without If-Match
    patch_meta = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"color_token": "lavender", "sort_rank": "b0"},
    )
    assert patch_meta.status_code == 200
    assert patch_meta.json()["color_token"] == "lavender"
    assert patch_meta.json()["sort_rank"] == "b0"

    # 7. Update sticky body with valid If-Match
    patch_body = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"body_markdown": "# Updated Note\nUpdated content."},
        headers={"If-Match": etag_v1},
    )
    assert patch_body.status_code == 200
    new_etag = patch_body.headers["ETag"]
    assert new_etag != etag_v1

    # 8. Delete sticky
    del_resp = await client.delete(f"/api/v1/stickies/{sticky_id}")
    assert del_resp.status_code == 200

    # Getting deleted sticky returns 404
    get_del = await client.get(f"/api/v1/stickies/{sticky_id}")
    assert get_del.status_code == 404

    # Deleted sticky excluded from project listing
    list_after = await client.get(f"/api/v1/projects/{proj_id}/stickies")
    assert list_after.status_code == 200
    assert len(list_after.json()) == 1


async def test_case_2_snooze_lifecycle_and_growth(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 2: Snooze >= 1.5x math, growth tracking, and contract recording."""
    admin = await make_user("stk_snooze_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="SNZ")

    # 1. Sticky of 620 chars (promotion_recommended == True)
    text_620 = "x" * 620
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": text_620, "color_token": "amber"},
    )
    contract_recorder.record("sticky_create_201", create_resp.request, create_resp)
    assert create_resp.status_code == 201, create_resp.text
    data = create_resp.json()
    sticky_id = data["id"]
    etag_620 = create_resp.headers["ETag"]
    assert data["promotion_recommended"] is True
    assert "char_length" in data["triggers"]
    assert data["promotion_snoozed_at_length"] is None

    # 2. Call snooze-promotion -> 200, sets length = 620, promotion_recommended = False
    snooze_resp = await client.post(f"/api/v1/stickies/{sticky_id}/snooze-promotion")
    contract_recorder.record("snooze_200", snooze_resp.request, snooze_resp)
    assert snooze_resp.status_code == 200, snooze_resp.text
    snoozed_data = snooze_resp.json()
    assert snoozed_data["promotion_snoozed_at_length"] == 620
    assert snoozed_data["promotion_recommended"] is False

    # 3. Growth to 929 chars keeps promotion_recommended == False
    text_929 = "x" * 929
    patch_929 = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"body_markdown": text_929},
        headers={"If-Match": etag_620},
    )
    assert patch_929.status_code == 200, patch_929.text
    etag_929 = patch_929.headers["ETag"]
    assert patch_929.json()["promotion_recommended"] is False

    # 4. Growth to 930 chars (620 * 1.5 == 930) flips promotion_recommended == True
    text_930 = "x" * 930
    patch_930 = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"body_markdown": text_930},
        headers={"If-Match": etag_929},
    )
    assert patch_930.status_code == 200, patch_930.text
    assert patch_930.json()["promotion_recommended"] is True


async def test_case_3_atomic_promotion_and_verbatim_acl_proof(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 3: Atomic promotion, verbatim ACL copy, stub & already-promoted guard."""
    admin = await make_user("stk_prom_admin", workspace_role="WORKSPACE_ADMIN")
    maya = await make_user("maya", workspace_role="WORKSPACE_MEMBER")
    bob = await make_user("bob", workspace_role="WORKSPACE_MEMBER")

    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="ACL")

    # Bind bob to the project so he has base VIEW on project
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        bob.id,
        "MEMBER",
        scope_type="project",
        project_id=proj_id,
    )

    # Create Contractors group with member bob
    contractors_group_id = await create_group(api_env.seed, api_env.workspace_id, "Contractors")
    await add_group_member(api_env.seed, api_env.workspace_id, contractors_group_id, bob.id)
    await api_env.seed.commit()

    # 1. Create sticky as admin
    as_principal(admin)
    sticky_body = "# Auth Studio Notes\n## Decisions\nUse WebAuthn with Argon2id."
    create_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": sticky_body, "color_token": "sky"},
    )
    assert create_resp.status_code == 201
    sticky_id = uuid.UUID(create_resp.json()["id"])

    # 2. Attach direct ALLOW (VIEW|EDIT = 5) for maya
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        sticky_id,
        maya.id,
        effect="ALLOW",
        capability_mask=5,
        created_by_id=admin.id,
    )

    # 3. Attach explicit DENY (VIEW = 1) for Contractors group
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        sticky_id,
        contractors_group_id,
        effect="DENY",
        capability_mask=1,
        created_by_id=admin.id,
    )
    await api_env.seed.commit()
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 4. Call promote-to-doc as admin
    as_principal(admin)
    promote_payload = {"title": "Auth Studio Architecture"}
    promote_resp = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json=promote_payload,
    )
    contract_recorder.record("promote_to_doc_201", promote_resp.request, promote_resp)
    assert promote_resp.status_code == 201, promote_resp.text
    promoted_data = promote_resp.json()
    assert promoted_data["is_promoted_stub"] is True
    assert promoted_data["promoted_to_doc"] is not None
    assert promoted_data["promoted_to_doc"]["title"] == "Auth Studio Architecture"
    doc_id = uuid.UUID(promoted_data["promoted_to_doc"]["id"])

    # 5. Verify docs, pages, and object_links in DB
    doc_in_db = (
        await api_env.seed.execute(select(Doc).where(Doc.id == doc_id))
    ).scalar_one_or_none()
    assert doc_in_db is not None
    assert doc_in_db.title == "Auth Studio Architecture"
    assert doc_in_db.workspace_id == api_env.workspace_id
    assert doc_in_db.project_id == proj_id

    page_in_db = (
        await api_env.seed.execute(select(Page).where(Page.doc_id == doc_id))
    ).scalar_one_or_none()
    assert page_in_db is not None
    assert page_in_db.body_markdown == sticky_body

    link_in_db = (
        await api_env.seed.execute(
            select(ObjectLink).where(
                ObjectLink.source_id == sticky_id,
                ObjectLink.target_id == doc_id,
                ObjectLink.link_type == "PROMOTED_TO_DOC",
            )
        )
    ).scalar_one_or_none()
    assert link_in_db is not None

    # 6. Verify verbatim ACL copy: query direct ACLs on sticky, doc, and page
    sticky_acls = (
        await api_env.seed.execute(
            select(
                ResourceAclEntry.principal_id,
                ResourceAclEntry.effect,
                ResourceAclEntry.capability_mask,
            )
            .where(ResourceAclEntry.object_id == sticky_id)
            .order_by(ResourceAclEntry.principal_id.asc(), ResourceAclEntry.effect.asc())
        )
    ).all()
    assert len(sticky_acls) == 2

    doc_acls = (
        await api_env.seed.execute(
            select(
                ResourceAclEntry.principal_id,
                ResourceAclEntry.effect,
                ResourceAclEntry.capability_mask,
            )
            .where(ResourceAclEntry.object_id == doc_id)
            .order_by(ResourceAclEntry.principal_id.asc(), ResourceAclEntry.effect.asc())
        )
    ).all()
    assert len(doc_acls) == 2
    assert doc_acls == sticky_acls

    page_acls = (
        await api_env.seed.execute(
            select(
                ResourceAclEntry.principal_id,
                ResourceAclEntry.effect,
                ResourceAclEntry.capability_mask,
            )
            .where(ResourceAclEntry.object_id == page_in_db.id)
            .order_by(ResourceAclEntry.principal_id.asc(), ResourceAclEntry.effect.asc())
        )
    ).all()
    assert len(page_acls) == 2
    assert page_acls == sticky_acls

    # 7. Serializer stub check via GET /api/v1/stickies/{id}
    stub_resp = await client.get(f"/api/v1/stickies/{sticky_id}")
    contract_recorder.record("stub_serializer_200", stub_resp.request, stub_resp)
    assert stub_resp.status_code == 200
    stub_data = stub_resp.json()
    assert stub_data["is_promoted_stub"] is True
    assert stub_data["promoted_to_doc_id"] == str(doc_id)
    assert stub_data["promoted_to_doc"]["id"] == str(doc_id)
    assert not stub_data["promoted_to_doc"]["restricted"]

    # 8. Contractors member (bob) gets 404 on the new doc (explicit DENY works!)
    bob_client = as_principal(bob)
    bob_doc_resp = await bob_client.get(f"/api/v1/docs/{doc_id}")
    assert bob_doc_resp.status_code == 404

    # 9. Second call to promote-to-doc returns 409 ALREADY_PROMOTED (as admin)
    as_principal(admin)
    dup_promote = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json={"title": "Duplicate Promotion"},
    )
    contract_recorder.record("already_promoted_409", dup_promote.request, dup_promote)
    assert dup_promote.status_code == 409
    assert dup_promote.json()["code"] == "ALREADY_PROMOTED"

    # 10. Snooze on already promoted sticky returns 409 ALREADY_PROMOTED
    snooze_dup = await client.post(f"/api/v1/stickies/{sticky_id}/snooze-promotion")
    assert snooze_dup.status_code == 409
    assert snooze_dup.json()["code"] == "ALREADY_PROMOTED"


async def test_case_4_cross_scope_guard_stub_readonly_and_unarchive_copy(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 4: Cross-scope guard, promoted stub read-only body, and unarchive-copy."""
    admin = await make_user("stk_cross_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    proj1_id = await _setup_project(api_env, admin, identifier="PRJA")
    proj2_id = await _setup_project(api_env, admin, identifier="PRJB")

    # 1. Create a doc in Project B
    doc_b_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj2_id), "title": "Project B Doc", "body_markdown": "Doc in B"},
    )
    assert doc_b_resp.status_code == 201
    doc_b_id = doc_b_resp.json()["id"]

    # 2. Create sticky in Project A
    stk_resp = await client.post(
        f"/api/v1/projects/{proj1_id}/stickies",
        json={"body_markdown": "# Scope Sticky\nWill stay in A.", "color_token": "slate"},
    )
    assert stk_resp.status_code == 201
    sticky_id = stk_resp.json()["id"]
    etag_orig = stk_resp.headers["ETag"]

    # 3. Promote into Project B Doc -> returns 422 CROSS_SCOPE_PROMOTION_FORBIDDEN
    cross_resp = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json={"title": "Cross Doc", "parent_doc_id": doc_b_id},
    )
    assert cross_resp.status_code == 422
    assert cross_resp.json()["code"] == "CROSS_SCOPE_PROMOTION_FORBIDDEN"

    # Assert 0 pages created under doc_b
    pages_count = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM pages WHERE doc_id = :d_id"),
            {"d_id": doc_b_id},
        )
    ).scalar_one()
    assert pages_count == 0

    # 4. Calling unarchive-copy on unpromoted sticky returns 409 NOT_PROMOTED
    unprom_copy = await client.post(f"/api/v1/stickies/{sticky_id}/unarchive-copy")
    assert unprom_copy.status_code == 409
    assert unprom_copy.json()["code"] == "NOT_PROMOTED"

    # 5. Successfully promote sticky in Project A
    prom_ok = await client.post(
        f"/api/v1/stickies/{sticky_id}/promote-to-doc",
        json={"title": "Valid Doc in A"},
    )
    assert prom_ok.status_code == 201

    # 6. Attempt PATCH body on promoted stub -> returns 409 STICKY_PROMOTED_READONLY
    patch_promoted = await client.patch(
        f"/api/v1/stickies/{sticky_id}",
        json={"body_markdown": "Mutated body"},
        headers={"If-Match": etag_orig},
    )
    assert patch_promoted.status_code == 409
    assert patch_promoted.json()["code"] == "STICKY_PROMOTED_READONLY"

    # 7. Call unarchive-copy -> returns 201 with new unpromoted sticky
    unarchive_resp = await client.post(f"/api/v1/stickies/{sticky_id}/unarchive-copy")
    contract_recorder.record("unarchive_copy_201", unarchive_resp.request, unarchive_resp)
    assert unarchive_resp.status_code == 201, unarchive_resp.text
    clone_data = unarchive_resp.json()
    assert clone_data["id"] != sticky_id
    assert not clone_data["is_promoted_stub"]
    assert clone_data["promoted_to_doc_id"] is None
    assert clone_data["color_token"] == "slate"
    assert "Scope Sticky" in clone_data["body_markdown"]

    # 8. Unarchived clone's body CAN be edited
    clone_id = clone_data["id"]
    clone_etag = unarchive_resp.headers["ETag"]
    patch_clone = await client.patch(
        f"/api/v1/stickies/{clone_id}",
        json={"body_markdown": "# Editable Clone\nI am free to edit."},
        headers={"If-Match": clone_etag},
    )
    assert patch_clone.status_code == 200
    assert "Editable Clone" in patch_clone.json()["body_markdown"]


async def test_case_5_boundaries_and_sanitization(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 5: Boundaries, invalid color, 64KB limit, hidden DOM pruning, & ETag errors."""
    admin = await make_user("stk_bnd_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="BND")

    # 1. Invalid color token -> 422
    bad_color_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "Note", "color_token": "red"},
    )
    assert bad_color_resp.status_code == 422

    # 2. 65536 bytes accepted -> 201
    exact_body = "x" * 65536
    ok_size_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": exact_body, "color_token": "amber"},
    )
    assert ok_size_resp.status_code == 201

    # 3. 65537 bytes -> 422 STICKY_TOO_LARGE
    too_large_body = "x" * 65537
    too_large_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": too_large_body, "color_token": "amber"},
    )
    assert too_large_resp.status_code == 422
    assert too_large_resp.json()["code"] == "STICKY_TOO_LARGE"

    # 4. Hidden DOM <div style="font-size:0">evil</div> pruned on write
    hidden_dom_input = 'Hello world <div style="font-size:0">evil prompt injection</div> text'
    hidden_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": hidden_dom_input, "color_token": "mint"},
    )
    assert hidden_resp.status_code == 201
    assert "evil prompt injection" not in hidden_resp.json()["body_markdown"]
    assert "Hello world" in hidden_resp.json()["body_markdown"]
    stk_id = hidden_resp.json()["id"]

    # 5. PATCH without If-Match when editing body -> 428 PRECONDITION_REQUIRED
    missing_etag = await client.patch(
        f"/api/v1/stickies/{stk_id}",
        json={"body_markdown": "new content"},
    )
    assert missing_etag.status_code == 428
    assert missing_etag.json()["code"] == "PRECONDITION_REQUIRED"

    # 6. PATCH with stale If-Match -> 412 PRECONDITION_FAILED
    stale_etag = await client.patch(
        f"/api/v1/stickies/{stk_id}",
        json={"body_markdown": "new content"},
        headers={"If-Match": '"0000000000000000000000000000000000000000000000000000000000000000"'},
    )
    assert stale_etag.status_code == 412
    assert stale_etag.json()["code"] == "PRECONDITION_FAILED"


async def test_case_6_promote_to_existing_doc_and_nested_page(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 6: Promote sticky into existing parent doc and nested page hierarchy."""
    admin = await make_user("stk_nest_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="NEST")

    # 1. Create a parent doc in project
    doc_resp = await client.post(
        "/api/v1/docs",
        json={
            "project_id": str(proj_id),
            "title": "Main Project Doc",
            "body_markdown": "# Main Doc",
        },
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["id"]

    # 2. Create sticky 1 and promote under parent doc (no parent page -> root page under doc)
    stk1_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "# Child Section 1\nContent 1", "color_token": "mint"},
    )
    assert stk1_resp.status_code == 201
    stk1_id = stk1_resp.json()["id"]

    prom1_resp = await client.post(
        f"/api/v1/stickies/{stk1_id}/promote-to-doc",
        json={"parent_doc_id": doc_id},
    )
    assert prom1_resp.status_code == 201, prom1_resp.text
    prom1_data = prom1_resp.json()
    assert prom1_data["is_promoted_stub"] is True
    assert prom1_data["promoted_to_doc_id"] == doc_id
    assert prom1_data["promoted_to_doc"]["title"] == "Main Project Doc"

    # Find the page created under doc
    page1 = (
        await api_env.seed.execute(
            select(Page).where(Page.doc_id == uuid.UUID(doc_id), Page.title == "Child Section 1")
        )
    ).scalar_one()

    # 3. Create sticky 2 and promote under page 1
    stk2_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "Nested Sub-bullet", "color_token": "lavender"},
    )
    assert stk2_resp.status_code == 201
    stk2_id = stk2_resp.json()["id"]

    prom2_resp = await client.post(
        f"/api/v1/stickies/{stk2_id}/promote-to-doc",
        json={"parent_doc_id": doc_id, "parent_page_id": str(page1.id)},
    )
    assert prom2_resp.status_code == 201, prom2_resp.text

    page2 = (
        await api_env.seed.execute(
            select(Page).where(Page.doc_id == uuid.UUID(doc_id), Page.parent_page_id == page1.id)
        )
    ).scalar_one()
    assert page2.parent_page_id == page1.id


async def test_case_7_coverage_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 7: Comprehensive edge cases, not-found paths, filter flags, and formatters."""
    admin = await make_user("stk_cov_admin", workspace_role="WORKSPACE_ADMIN")
    restricted_user = await make_user("stk_restricted", workspace_role="WORKSPACE_MEMBER")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin, identifier="COV")

    random_id = uuid.uuid4()

    # 1. 404 paths for missing sticky
    assert (await client.get(f"/api/v1/stickies/{random_id}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/stickies/{random_id}", json={"color_token": "mint"})
    ).status_code == 404
    assert (await client.delete(f"/api/v1/stickies/{random_id}")).status_code == 404
    assert (await client.post(f"/api/v1/stickies/{random_id}/snooze-promotion")).status_code == 404
    assert (await client.post(f"/api/v1/stickies/{random_id}/unarchive-copy")).status_code == 404

    # 2. include_promoted=False in list_project_stickies
    s1_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "Note 1", "color_token": "amber"},
    )
    s1_id = s1_resp.json()["id"]
    s2_resp = await client.post(
        f"/api/v1/projects/{proj_id}/stickies",
        json={"body_markdown": "Note 2", "color_token": "sky"},
    )
    s2_id = s2_resp.json()["id"]

    # Promote s1
    prom_res = await client.post(f"/api/v1/stickies/{s1_id}/promote-to-doc", json={})
    assert prom_res.status_code == 201

    # list with include_promoted=False -> only s2 returned
    list_active = await client.get(
        f"/api/v1/projects/{proj_id}/stickies", params={"include_promoted": False}
    )
    assert list_active.status_code == 200
    ids = [item["id"] for item in list_active.json()]
    assert s1_id not in ids
    assert s2_id in ids

    # 3. If-Match wildcard "*" allows updating body
    patch_wildcard = await client.patch(
        f"/api/v1/stickies/{s2_id}",
        json={"body_markdown": "Updated via wildcard"},
        headers={"If-Match": "*"},
    )
    assert patch_wildcard.status_code == 200

    # 4. Unarchive copy on sticky with NO direct ACLs
    unarch_resp = await client.post(f"/api/v1/stickies/{s1_id}/unarchive-copy")
    assert unarch_resp.status_code == 201

    # 5. Restricted target doc in stub serializer
    # Deny restricted_user on the doc created by promoting s1
    promoted_doc_id = prom_res.json()["promoted_to_doc_id"]
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        uuid.UUID(promoted_doc_id),
        restricted_user.id,
        effect="DENY",
        capability_mask=1,
        created_by_id=admin.id,
    )
    await api_env.seed.commit()
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Restricted user views sticky -> doc summary has restricted: true
    rest_client = as_principal(restricted_user)
    stk_rest_resp = await rest_client.get(f"/api/v1/stickies/{s1_id}")
    assert stk_rest_resp.status_code == 200
    assert stk_rest_resp.json()["promoted_to_doc"]["restricted"] is True
    assert stk_rest_resp.json()["promoted_to_doc"]["title"] is None

    # 6. PAGE_PARENT_DOC_MISMATCH when parent_page belongs to different doc
    doc_other_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Other Doc", "body_markdown": "Other Doc"},
    )
    assert doc_other_resp.status_code == 201
    doc_other_id = doc_other_resp.json()["id"]

    page_other_resp = await client.post(
        f"/api/v1/docs/{doc_other_id}/pages",
        json={"title": "Page in other doc", "body_markdown": "Page body"},
    )
    assert page_other_resp.status_code == 201
    page_other_id = page_other_resp.json()["id"]

    # Try to promote sticky into doc1 but with parent_page_id from doc_other
    # First create a target doc in proj_id
    doc_target_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Target Doc", "body_markdown": "Target Doc"},
    )
    assert doc_target_resp.status_code == 201
    doc_target_id = doc_target_resp.json()["id"]

    mismatch_resp = await client.post(
        f"/api/v1/stickies/{s2_id}/promote-to-doc",
        json={"parent_doc_id": doc_target_id, "parent_page_id": page_other_id},
    )
    assert mismatch_resp.status_code == 422
    assert mismatch_resp.json()["code"] == "PAGE_PARENT_DOC_MISMATCH"


def test_stickies_service_internal_helpers() -> None:
    """Exercise service-level helper branches directly for 100% coverage."""
    assert _derive_title(None, "") == "Untitled Sticky"
    assert _derive_title(None, "   ") == "Untitled Sticky"
    assert _derive_title("Explicit Title", "") == "Explicit Title"
    assert _derive_title(None, "- list item line") == "list item line"
    assert _format_etag(None) == '""'

    # Decode cursor with non-split content raises INVALID_CURSOR
    one_part_b64 = base64.urlsafe_b64encode(b"just-one-part").decode("ascii")
    with pytest.raises(ProblemException) as exc_info:
        _decode_cursor(one_part_b64)
    assert exc_info.value.code == "INVALID_CURSOR"

# Copyright 2026 Kanban Platform Contributors
"""Comprehensive API integration tests for Docs, hierarchical Pages, versions, moves & outlines."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.tests.security.helpers import (
    create_project,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _setup_project(api_env: ApiEnv, user: SeededUser) -> uuid.UUID:
    """Create a test project in the workspace."""
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="DOCS",
        name="Docs Test Project",
        created_by_id=user.id,
    )
    await api_env.seed.commit()
    return proj_id


async def test_case_1_positive_lifecycle(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Positive lifecycle: doc 201 + pages P1->P2->P3, versions, and restore."""
    admin = await make_user("doc_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    # 1. Create Doc
    create_doc_payload = {
        "project_id": str(proj_id),
        "title": "Architecture Guide",
        "body_markdown": "# Overview\nThis is the core architecture guide.",
    }
    resp = await client.post("/api/v1/docs", json=create_doc_payload)
    contract_recorder.record("create_doc_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    doc_data = resp.json()
    doc_id = doc_data["id"]
    doc_ckey = doc_data["canonical_key"]
    assert "ETag" in resp.headers
    doc_etag = resp.headers["ETag"]
    assert resp.headers["Location"] == f"/api/v1/docs/{doc_ckey}"
    assert doc_data["title"] == "Architecture Guide"
    assert "VIEW" in doc_data["capabilities"]
    assert "EDIT" in doc_data["capabilities"]

    # 2. List Docs
    list_resp = await client.get("/api/v1/docs", params={"project": str(proj_id)})
    contract_recorder.record("list_docs_200", list_resp.request, list_resp)
    assert list_resp.status_code == 200
    docs_list = list_resp.json()
    assert len(docs_list) == 1
    assert docs_list[0]["id"] == doc_id

    # 3. Get Doc with ETag and 304 caching
    get_doc_resp = await client.get(f"/api/v1/docs/{doc_ckey}")
    contract_recorder.record("get_doc_200", get_doc_resp.request, get_doc_resp)
    assert get_doc_resp.status_code == 200
    assert get_doc_resp.headers["ETag"] == doc_etag

    cached_doc_resp = await client.get(
        f"/api/v1/docs/{doc_ckey}", headers={"If-None-Match": doc_etag}
    )
    assert cached_doc_resp.status_code == 304

    # 4. Create Page P1 (Root page)
    p1_resp = await client.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={
            "title": "System Components",
            "body_markdown": (
                "# Components\n## Database\nPostgres 16 details.\n## API\nFastAPI details."
            ),
        },
    )
    contract_recorder.record("create_page_201", p1_resp.request, p1_resp)
    assert p1_resp.status_code == 201, p1_resp.text
    p1_data = p1_resp.json()
    p1_id = p1_data["id"]
    p1_ckey = p1_data["canonical_key"]
    assert p1_ckey.endswith("/system-components")
    assert len(p1_data["outline"]) == 3
    assert p1_data["outline"][0]["anchor"] == "components"
    assert p1_data["outline"][1]["anchor"] == "database"
    assert p1_data["outline"][2]["anchor"] == "api"
    assert len(p1_data["breadcrumbs"]) == 2
    assert p1_data["breadcrumbs"][0]["id"] == doc_id
    assert p1_data["breadcrumbs"][1]["id"] == p1_id

    # 5. Create Page P2 under P1
    p2_resp = await client.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={
            "parent_page_id": p1_id,
            "title": "Database Engine",
            "body_markdown": "# Initial DB Body",
        },
    )
    assert p2_resp.status_code == 201, p2_resp.text
    p2_data = p2_resp.json()
    p2_id = p2_data["id"]
    p2_etag_v1 = p2_resp.headers["ETag"]
    assert len(p2_data["breadcrumbs"]) == 3
    assert p2_data["breadcrumbs"][0]["id"] == doc_id
    assert p2_data["breadcrumbs"][1]["id"] == p1_id
    assert p2_data["breadcrumbs"][2]["id"] == p2_id
    assert p2_data["version_seq"] == 1

    # 6. Create Page P3 under P2
    p3_resp = await client.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={
            "parent_page_id": p2_id,
            "title": "Row-Level Security",
            "body_markdown": "# RLS Policies",
        },
    )
    assert p3_resp.status_code == 201, p3_resp.text
    p3_data = p3_resp.json()
    p3_id = p3_data["id"]
    assert len(p3_data["breadcrumbs"]) == 4
    assert p3_data["breadcrumbs"][0]["id"] == doc_id
    assert p3_data["breadcrumbs"][1]["id"] == p1_id
    assert p3_data["breadcrumbs"][2]["id"] == p2_id
    assert p3_data["breadcrumbs"][3]["id"] == p3_id

    # 7. Get Doc Tree (P1 -> P2 -> P3)
    tree_resp = await client.get(f"/api/v1/docs/{doc_ckey}/tree")
    contract_recorder.record("get_doc_tree_200", tree_resp.request, tree_resp)
    assert tree_resp.status_code == 200
    tree = tree_resp.json()
    assert len(tree) == 1
    assert tree[0]["id"] == p1_id
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == p2_id
    assert len(tree[0]["children"][0]["children"]) == 1
    assert tree[0]["children"][0]["children"][0]["id"] == p3_id

    # 8. Update P2 Body under If-Match (Version 1 -> Version 2)
    p2_update_1 = await client.patch(
        f"/api/v1/pages/{p2_id}",
        json={"body_markdown": "# Updated DB Body V2"},
        headers={"If-Match": p2_etag_v1},
    )
    contract_recorder.record("update_page_200", p2_update_1.request, p2_update_1)
    assert p2_update_1.status_code == 200, p2_update_1.text
    p2_etag_v2 = p2_update_1.headers["ETag"]
    assert p2_update_1.json()["version_seq"] == 2

    # 9. Update P2 Body again under If-Match (Version 2 -> Version 3)
    p2_update_2 = await client.patch(
        f"/api/v1/pages/{p2_id}",
        json={"body_markdown": "# Updated DB Body V3"},
        headers={"If-Match": p2_etag_v2},
    )
    assert p2_update_2.status_code == 200, p2_update_2.text
    p2_etag_v3 = p2_update_2.headers["ETag"]
    assert p2_update_2.json()["version_seq"] == 3

    # 10. List P2 Historical Versions
    versions_resp = await client.get(f"/api/v1/pages/{p2_id}/versions")
    contract_recorder.record("list_page_versions_200", versions_resp.request, versions_resp)
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 2
    # Newest historical first
    assert versions[0]["version_seq"] == 2
    assert versions[1]["version_seq"] == 1
    assert versions[1]["body_markdown"] == "# Initial DB Body"

    # 11. Get Single Historical Version
    v1_resp = await client.get(f"/api/v1/pages/{p2_id}/versions/1")
    contract_recorder.record("get_page_version_200", v1_resp.request, v1_resp)
    assert v1_resp.status_code == 200
    assert v1_resp.json()["body_markdown"] == "# Initial DB Body"

    # 12. Restore Version 1 under If-Match -> yields version_seq 4 with version 1 content
    restore_resp = await client.post(
        f"/api/v1/pages/{p2_id}/versions/1/restore",
        headers={"If-Match": p2_etag_v3},
    )
    contract_recorder.record("restore_page_version_200", restore_resp.request, restore_resp)
    assert restore_resp.status_code == 200, restore_resp.text
    restored_data = restore_resp.json()
    assert restored_data["version_seq"] == 4
    assert restored_data["body_markdown"] == "# Initial DB Body"

    # 13. Verify GET Page returns version_seq 4
    get_p2_resp = await client.get(f"/api/v1/pages/{p2_id}")
    contract_recorder.record("get_page_200", get_p2_resp.request, get_p2_resp)
    assert get_p2_resp.status_code == 200
    assert get_p2_resp.json()["version_seq"] == 4
    assert get_p2_resp.json()["body_markdown"] == "# Initial DB Body"


async def test_case_2_tree_move_and_dag_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 2: Tree move, cycle detection (409), depth guard (422), and doc mismatch."""
    admin = await make_user("dag_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    # Create Doc 1
    d1_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Doc 1", "body_markdown": ""},
    )
    d1_ckey = d1_resp.json()["canonical_key"]

    # Create P1 -> P2 -> P3 in Doc 1
    p1 = (
        await client.post(
            f"/api/v1/docs/{d1_ckey}/pages", json={"title": "Page 1", "body_markdown": ""}
        )
    ).json()
    p2 = (
        await client.post(
            f"/api/v1/docs/{d1_ckey}/pages",
            json={"parent_page_id": p1["id"], "title": "Page 2", "body_markdown": ""},
        )
    ).json()
    p3 = (
        await client.post(
            f"/api/v1/docs/{d1_ckey}/pages",
            json={"parent_page_id": p2["id"], "title": "Page 3", "body_markdown": ""},
        )
    ).json()

    # Move P2 to document root (parent_page_id: None)
    move_resp = await client.post(
        f"/api/v1/pages/{p2['id']}/move",
        json={"parent_page_id": None},
    )
    contract_recorder.record("move_page_200", move_resp.request, move_resp)
    assert move_resp.status_code == 200, move_resp.text
    moved_p2 = move_resp.json()
    assert moved_p2["parent_page_id"] is None
    assert len(moved_p2["breadcrumbs"]) == 2
    assert moved_p2["breadcrumbs"][1]["id"] == p2["id"]

    # Verify P3 was rebased automatically under P2
    p3_check = (await client.get(f"/api/v1/pages/{p3['id']}")).json()
    assert p3_check["parent_page_id"] == p2["id"]
    assert len(p3_check["breadcrumbs"]) == 3
    assert p3_check["breadcrumbs"][1]["id"] == p2["id"]
    assert p3_check["breadcrumbs"][2]["id"] == p3["id"]

    # Cycle Detection: Moving P2 under P3 must return 409 PAGE_CYCLE
    cycle_resp = await client.post(
        f"/api/v1/pages/{p2['id']}/move",
        json={"parent_page_id": p3["id"]},
    )
    assert cycle_resp.status_code == 409, cycle_resp.text
    assert cycle_resp.json()["code"] == "PAGE_CYCLE"

    # Parent Doc Mismatch: Create Doc 2, try to move P2 under Doc 2's page
    d2_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Doc 2", "body_markdown": ""},
    )
    d2_ckey = d2_resp.json()["canonical_key"]
    d2_p1 = (
        await client.post(
            f"/api/v1/docs/{d2_ckey}/pages", json={"title": "Doc2 Page 1", "body_markdown": ""}
        )
    ).json()

    mismatch_resp = await client.post(
        f"/api/v1/pages/{p2['id']}/move",
        json={"parent_page_id": d2_p1["id"]},
    )
    assert mismatch_resp.status_code == 422, mismatch_resp.text
    assert mismatch_resp.json()["code"] == "PAGE_PARENT_DOC_MISMATCH"

    # Max Depth Exceeded (depth cannot exceed 10)
    # Current chain: P2 (depth 1) -> P3 (depth 2)
    # Add depth 3 through 10
    parent_id = p3["id"]
    for depth in range(3, 11):
        add_resp = await client.post(
            f"/api/v1/docs/{d1_ckey}/pages",
            json={"parent_page_id": parent_id, "title": f"Depth {depth}", "body_markdown": ""},
        )
        assert add_resp.status_code == 201, f"Failed at depth {depth}: {add_resp.text}"
        parent_id = add_resp.json()["id"]

    # Now parent_id is at depth 10. Attempting to add depth 11 must fail
    # with 422 PAGE_MAX_DEPTH_EXCEEDED
    depth_11_resp = await client.post(
        f"/api/v1/docs/{d1_ckey}/pages",
        json={"parent_page_id": parent_id, "title": "Depth 11", "body_markdown": ""},
    )
    assert depth_11_resp.status_code == 422, depth_11_resp.text
    assert depth_11_resp.json()["code"] == "PAGE_MAX_DEPTH_EXCEEDED"


async def test_lexorank_sibling_ordering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Base-62 Lexorank sibling positioning with after_page_id and before_page_id."""
    admin = await make_user("rank_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    doc_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Rank Doc", "body_markdown": ""},
    )
    doc_ckey = doc_resp.json()["canonical_key"]

    # 1. Create page A
    pa = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages", json={"title": "Page A", "body_markdown": ""}
        )
    ).json()

    # 2. Create page B
    pb = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages", json={"title": "Page B", "body_markdown": ""}
        )
    ).json()
    assert pa["sort_rank"] < pb["sort_rank"]

    # 3. Create page C after B
    pc = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages",
            json={"after_page_id": pb["id"], "title": "Page C", "body_markdown": ""},
        )
    ).json()
    assert pb["sort_rank"] < pc["sort_rank"]

    # 4. Create page M between A and B
    pm = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages",
            json={
                "after_page_id": pa["id"],
                "before_page_id": pb["id"],
                "title": "Page M",
                "body_markdown": "",
            },
        )
    ).json()
    assert pa["sort_rank"] < pm["sort_rank"] < pb["sort_rank"]

    # 5. Move C before A
    move_c = (
        await client.post(
            f"/api/v1/pages/{pc['id']}/move",
            json={"before_page_id": pa["id"]},
        )
    ).json()
    assert move_c["sort_rank"] < pa["sort_rank"]


async def test_concurrency_and_boundaries(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 5: Concurrency (ETag/If-Match), size limits, and title length validation."""
    admin = await make_user("boundary_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    doc_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Boundary Doc", "body_markdown": ""},
    )
    doc_ckey = doc_resp.json()["canonical_key"]

    page_resp = await client.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={"title": "Boundary Page", "body_markdown": "Init"},
    )
    page_id = page_resp.json()["id"]
    current_etag = page_resp.headers["ETag"]

    # 1. PATCH body without If-Match returns 428 PRECONDITION_REQUIRED
    p_no_etag = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"body_markdown": "New Body Without Header"},
    )
    assert p_no_etag.status_code == 428, p_no_etag.text
    assert p_no_etag.json()["code"] == "PRECONDITION_REQUIRED"

    # 2. PATCH body with stale If-Match returns 412 PRECONDITION_FAILED with current_etag
    p_stale_etag = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"body_markdown": "New Body With Bad Header"},
        headers={"If-Match": '"0000000000000000000000000000000000000000000000000000000000000000"'},
    )
    assert p_stale_etag.status_code == 412, p_stale_etag.text
    problem = p_stale_etag.json()
    assert problem["code"] == "PRECONDITION_FAILED"
    assert problem["current_etag"] == current_etag

    # 3. Title length: 500 characters succeeds, 501 fails with TITLE_LENGTH
    t_500 = "a" * 500
    t_501 = "a" * 501
    p_500 = await client.patch(f"/api/v1/pages/{page_id}", json={"title": t_500})
    assert p_500.status_code == 200
    assert p_500.json()["title"] == t_500

    p_501 = await client.patch(f"/api/v1/pages/{page_id}", json={"title": t_501})
    assert p_501.status_code == 422
    assert p_501.json()["code"] in ("TITLE_LENGTH", "VALIDATION_FAILED")

    # Zero-length / whitespace-only title fails with TITLE_LENGTH
    p_empty = await client.patch(f"/api/v1/pages/{page_id}", json={"title": "   \u200b   "})
    assert p_empty.status_code == 422
    assert p_empty.json()["code"] == "TITLE_LENGTH"

    # 4. Body size: 1 MiB (1,048,576 bytes) succeeds, 1,048,577 bytes fails
    fresh_etag = p_500.headers["ETag"]
    valid_1mib = "x" * 1_048_576
    p_1mib = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"body_markdown": valid_1mib},
        headers={"If-Match": fresh_etag},
    )
    assert p_1mib.status_code == 200, p_1mib.text

    overflow_etag = p_1mib.headers["ETag"]
    invalid_1mib = "x" * 1_048_577
    p_overflow = await client.patch(
        f"/api/v1/pages/{page_id}",
        json={"body_markdown": invalid_1mib},
        headers={"If-Match": overflow_etag},
    )
    assert p_overflow.status_code == 422
    assert p_overflow.json()["code"] == "BODY_TOO_LARGE"


async def test_security_and_restricted_ancestor_masking(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 4: Security 404 timing floors and restricted ancestor masking (zero leakage)."""
    admin = await make_user("sec_admin", workspace_role="WORKSPACE_ADMIN")
    restricted_user = await make_user("sec_guest", workspace_role="WORKSPACE_MEMBER")
    client_admin = as_principal(admin)
    client_guest = as_principal(restricted_user)
    proj_id = await _setup_project(api_env, admin)

    # 1. Create Doc & Pages under Admin
    doc_resp = await client_admin.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Secret Doc", "body_markdown": "# Top Secret"},
    )
    doc_ckey = doc_resp.json()["canonical_key"]

    p1_resp = await client_admin.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={"title": "Restricted Parent", "body_markdown": "# Parent Content"},
    )
    p1 = p1_resp.json()
    p1_id = uuid.UUID(p1["id"])

    p2_resp = await client_admin.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={"parent_page_id": str(p1_id), "title": "Public Child", "body_markdown": "# Child"},
    )
    p2 = p2_resp.json()
    p2_id = uuid.UUID(p2["id"])

    # 2. Deny P1 explicitly to restricted_user, but grant VIEW on P2 in ACL
    await api_env.seed.execute(
        text(
            "INSERT INTO resource_acl_entries "
            "(workspace_id, object_id, principal_id, effect, capability_mask) "
            "VALUES (:ws, :p1, :u, 'DENY', 1), (:ws, :p2, :u, 'ALLOW', 1)"
        ),
        {
            "ws": api_env.workspace_id,
            "p1": p1_id,
            "p2": p2_id,
            "u": restricted_user.id,
        },
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 3. Guest GET P1 directly returns 404 (not 403, indistinguishable from non-existent)
    guest_p1 = await client_guest.get(f"/api/v1/pages/{p1_id}")
    assert guest_p1.status_code == 404

    # 4. Guest GET P2 succeeds, but P1 in breadcrumbs is masked with zero leakage
    guest_p2 = await client_guest.get(f"/api/v1/pages/{p2_id}")
    assert guest_p2.status_code == 200, guest_p2.text
    p2_data = guest_p2.json()
    assert len(p2_data["breadcrumbs"]) == 3

    # Visible doc
    b0 = p2_data["breadcrumbs"][0]
    assert b0["restricted"] is False
    assert b0["title"] == "Secret Doc"

    # Masked ancestor
    b1 = p2_data["breadcrumbs"][1]
    assert b1["restricted"] is True
    assert b1["label"] == "🔒 Restricted Page"
    assert b1["id"] is None
    assert b1["canonical_key"] is None
    assert b1["title"] is None
    assert b1["slug"] is None

    # Visible child
    b2 = p2_data["breadcrumbs"][2]
    assert b2["restricted"] is False
    assert b2["id"] == str(p2_id)
    assert b2["title"] == "Public Child"

    # 5. Guest GET Doc Tree masks P1 while showing P2 underneath
    tree_resp = await client_guest.get(f"/api/v1/docs/{doc_ckey}/tree")
    assert tree_resp.status_code == 200
    tree_nodes = tree_resp.json()
    assert len(tree_nodes) == 1
    t0 = tree_nodes[0]
    assert t0["restricted"] is True
    assert t0["label"] == "🔒 Restricted Page"
    assert t0["id"] is None
    assert t0["title"] is None
    assert len(t0["children"]) == 1
    assert t0["children"][0]["id"] == str(p2_id)
    assert t0["children"][0]["title"] == "Public Child"


async def test_soft_delete_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test soft-delete of pages and documents cascades to child pages."""
    admin = await make_user("del_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    doc_resp = await client.post(
        "/api/v1/docs",
        json={"project_id": str(proj_id), "title": "Delete Doc", "body_markdown": ""},
    )
    doc_ckey = doc_resp.json()["canonical_key"]

    p1 = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages", json={"title": "P1", "body_markdown": ""}
        )
    ).json()
    p2 = (
        await client.post(
            f"/api/v1/docs/{doc_ckey}/pages",
            json={"parent_page_id": p1["id"], "title": "P2", "body_markdown": ""},
        )
    ).json()

    # Delete page P1 -> cascades to P2
    del_page = await client.delete(f"/api/v1/pages/{p1['id']}")
    contract_recorder.record("delete_page_200", del_page.request, del_page)
    assert del_page.status_code == 200
    assert del_page.json() == {"status": "deleted"}

    # Subsequent GET returns 404
    assert (await client.get(f"/api/v1/pages/{p1['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/pages/{p2['id']}")).status_code == 404

    # Delete Doc
    del_doc = await client.delete(f"/api/v1/docs/{doc_ckey}")
    contract_recorder.record("delete_doc_200", del_doc.request, del_doc)
    assert del_doc.status_code == 200
    assert del_doc.json() == {"status": "deleted"}

    # Subsequent GET Doc returns 404
    assert (await client.get(f"/api/v1/docs/{doc_ckey}")).status_code == 404


async def test_doc_patch_and_etag_caching(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test PATCH doc metadata/body, wildcard If-Match, and page 304 caching."""
    admin = await make_user("patch_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    doc_resp = await client.post(
        "/api/v1/docs",
        json={
            "project_id": str(proj_id),
            "title": "Patch Target Doc",
            "body_markdown": "# Initial",
        },
    )
    doc = doc_resp.json()
    doc_id = doc["id"]
    doc_ckey = doc["canonical_key"]
    initial_etag = doc_resp.headers["ETag"]

    # PATCH doc with wildcard If-Match
    patch_resp = await client.patch(
        f"/api/v1/docs/{doc_ckey}",
        json={"title": "Updated Title", "body_markdown": "# New Body Markdown"},
        headers={"If-Match": "*"},
    )
    contract_recorder.record("update_doc_200", patch_resp.request, patch_resp)
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["title"] == "Updated Title"
    assert patched["body_markdown"] == "# New Body Markdown"
    assert patch_resp.headers["ETag"] != initial_etag

    # PATCH doc title only (no If-Match required)
    patch_title_only = await client.patch(
        f"/api/v1/docs/{doc_ckey}",
        json={"title": "Updated Title Only"},
    )
    assert patch_title_only.status_code == 200
    assert patch_title_only.json()["title"] == "Updated Title Only"
    etag_title_only = patch_title_only.headers["ETag"]

    # PATCH doc body only (with If-Match)
    patch_body_only = await client.patch(
        f"/api/v1/docs/{doc_ckey}",
        json={"body_markdown": "# Only Body Markdown Updated"},
        headers={"If-Match": etag_title_only},
    )
    assert patch_body_only.status_code == 200
    assert patch_body_only.json()["body_markdown"] == "# Only Body Markdown Updated"

    # PATCH doc body without If-Match -> 428 PRECONDITION_REQUIRED
    patch_doc_no_etag = await client.patch(
        f"/api/v1/docs/{doc_ckey}",
        json={"body_markdown": "# Should Fail Without Header"},
    )
    assert patch_doc_no_etag.status_code == 428
    assert patch_doc_no_etag.json()["code"] == "PRECONDITION_REQUIRED"

    # PATCH doc body with stale If-Match -> 412 PRECONDITION_FAILED
    patch_doc_stale_etag = await client.patch(
        f"/api/v1/docs/{doc_ckey}",
        json={"body_markdown": "# Should Fail With Stale Header"},
        headers={"If-Match": initial_etag},
    )
    assert patch_doc_stale_etag.status_code == 412
    assert patch_doc_stale_etag.json()["code"] == "PRECONDITION_FAILED"

    # Resolve doc by UUID
    get_by_uuid = await client.get(f"/api/v1/docs/{doc_id}")
    assert get_by_uuid.status_code == 200
    assert get_by_uuid.json()["id"] == doc_id

    # Create page and test page 304 caching with If-None-Match
    page_resp = await client.post(
        f"/api/v1/docs/{doc_ckey}/pages",
        json={"title": "Cached Page", "body_markdown": "Cacheable content"},
    )
    p_data = page_resp.json()
    p_id = p_data["id"]
    p_etag = page_resp.headers["ETag"]

    # PATCH page title only (no If-Match required)
    page_title_only = await client.patch(
        f"/api/v1/pages/{p_id}",
        json={"title": "Cached Page Title Only"},
    )
    assert page_title_only.status_code == 200
    assert page_title_only.json()["title"] == "Cached Page Title Only"
    p_etag_after_title = page_title_only.headers["ETag"]

    # PATCH page body only (with If-Match)
    page_body_only = await client.patch(
        f"/api/v1/pages/{p_id}",
        json={"body_markdown": "Cacheable content modified"},
        headers={"If-Match": p_etag_after_title},
    )
    assert page_body_only.status_code == 200
    assert page_body_only.json()["body_markdown"] == "Cacheable content modified"
    p_etag = page_body_only.headers["ETag"]

    cached_page = await client.get(
        f"/api/v1/pages/{p_id}",
        headers={"If-None-Match": p_etag},
    )
    assert cached_page.status_code == 304

    # Resolve page by canonical key with and without docs/ prefix
    p_ckey = p_data["canonical_key"]
    get_by_ckey = await client.get(f"/api/v1/pages/{p_ckey}")
    assert get_by_ckey.status_code == 200


async def test_workspace_level_docs_and_duplicate_slugs(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test workspace-level documents (project_id=None) and duplicate slug allocation."""
    admin = await make_user("ws_doc_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Create workspace-level doc (project_id is None)
    d1 = (
        await client.post(
            "/api/v1/docs",
            json={"project_id": None, "title": "Company Handbook", "body_markdown": ""},
        )
    ).json()
    assert d1["project_id"] is None
    assert d1["canonical_key"] == "docs/company-handbook"

    # 2. List docs without project param returns workspace-level docs
    list_ws = await client.get("/api/v1/docs")
    assert list_ws.status_code == 200
    assert any(d["id"] == d1["id"] for d in list_ws.json())

    # 3. Create second doc with duplicate title -> suffix -1
    d2 = (
        await client.post(
            "/api/v1/docs",
            json={"project_id": None, "title": "Company Handbook", "body_markdown": ""},
        )
    ).json()
    assert d2["canonical_key"] == "docs/company-handbook-1"

    # 4. Duplicate page slugs in same doc
    p1 = (
        await client.post(
            f"/api/v1/docs/{d1['canonical_key']}/pages",
            json={"title": "Benefits", "body_markdown": ""},
        )
    ).json()
    assert p1["canonical_key"] == "docs/company-handbook/benefits"

    p2 = (
        await client.post(
            f"/api/v1/docs/{d1['canonical_key']}/pages",
            json={"title": "Benefits", "body_markdown": ""},
        )
    ).json()
    assert p2["canonical_key"] == "docs/company-handbook/benefits-1"


async def test_version_history_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test pagination, 404 on missing version/restore, and invalid parent_page_id."""
    admin = await make_user("history_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id = await _setup_project(api_env, admin)

    doc = (
        await client.post(
            "/api/v1/docs",
            json={"project_id": str(proj_id), "title": "History Doc", "body_markdown": ""},
        )
    ).json()

    # Create page with non-existent parent_page_id -> 404
    bad_parent = await client.post(
        f"/api/v1/docs/{doc['canonical_key']}/pages",
        json={"parent_page_id": str(uuid.uuid4()), "title": "Orphan Page", "body_markdown": ""},
    )
    assert bad_parent.status_code == 404

    # Create valid page
    page_resp = await client.post(
        f"/api/v1/docs/{doc['canonical_key']}/pages",
        json={"title": "Versioned Page", "body_markdown": "V1"},
    )
    p_id = page_resp.json()["id"]
    etag = page_resp.headers["ETag"]

    # Create 3 versions
    for i in range(2, 5):
        up = await client.patch(
            f"/api/v1/pages/{p_id}",
            json={"body_markdown": f"V{i}"},
            headers={"If-Match": etag},
        )
        assert up.status_code == 200
        etag = up.headers["ETag"]

    # List with cursor pagination
    list_paged = await client.get(
        f"/api/v1/pages/{p_id}/versions",
        params={"cursor": 3, "limit": 2},
    )
    assert list_paged.status_code == 200
    paged_versions = list_paged.json()
    assert len(paged_versions) == 2
    assert [v["version_seq"] for v in paged_versions] == [2, 1]

    # Non-existent version seq returns 404
    v_missing = await client.get(f"/api/v1/pages/{p_id}/versions/999")
    assert v_missing.status_code == 404

    # Restore missing If-Match returns 428
    r_no_header = await client.post(f"/api/v1/pages/{p_id}/versions/1/restore")
    assert r_no_header.status_code == 428

    # Restore stale If-Match returns 412
    r_stale_header = await client.post(
        f"/api/v1/pages/{p_id}/versions/1/restore",
        headers={"If-Match": '"0000000000000000000000000000000000000000000000000000000000000000"'},
    )
    assert r_stale_header.status_code == 412

    # Restore non-existent version seq returns 404
    r_missing = await client.post(
        f"/api/v1/pages/{p_id}/versions/999/restore",
        headers={"If-Match": etag},
    )
    assert r_missing.status_code == 404

    # Non-existent doc and page refs return 404
    assert (await client.get(f"/api/v1/docs/{uuid.uuid4()}")).status_code == 404
    assert (await client.get(f"/api/v1/pages/{uuid.uuid4()}")).status_code == 404

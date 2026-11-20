# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for auto-created root doc on fresh project with zero existing docs (KAN-9 Problem 1)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import ObjectRecord
from kanban.services.docs import _auto_create_root_doc
from kanban.tests.security.helpers import (
    create_project,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _setup_fresh_project(
    api_env: ApiEnv, user: SeededUser, identifier: str = "FRESH"
) -> tuple[uuid.UUID, str]:
    """Create a fresh test project with zero existing docs."""
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier=identifier,
        name=f"Fresh Project {identifier}",
        created_by_id=user.id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    return proj_id, identifier


async def test_get_project_docs_tree_fresh_project_no_500(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GET /api/v1/projects/:key/docs/tree on fresh project with 0 docs returns 200."""
    admin = await make_user("tree_fresh_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id, proj_key = await _setup_fresh_project(api_env, admin, identifier="TREE0")

    # Call project tree endpoint
    resp = await client.get(f"/api/v1/projects/{proj_key}/docs/tree")
    assert resp.status_code == 200
    assert resp.json() == []

    # Also test GET /api/v1/docs/:key/tree
    resp_doc_tree = await client.get(f"/api/v1/docs/{proj_key}/tree")
    assert resp_doc_tree.status_code == 200
    assert isinstance(resp_doc_tree.json(), list)

    # Verify auto-created root doc exists and has valid creator
    async with api_env.seed.begin_nested():
        obj_row = (
            await api_env.seed.execute(
                select(ObjectRecord.id, ObjectRecord.created_by_id).where(
                    ObjectRecord.project_id == proj_id,
                    ObjectRecord.object_type == "doc",
                    ObjectRecord.workspace_id == api_env.workspace_id,
                )
            )
        ).first()
        assert obj_row is not None
        assert obj_row.created_by_id == admin.id


async def test_post_project_docs_pages_fresh_project_auto_creates_root_doc(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """POST /api/v1/projects/:key/docs/pages on fresh project auto-creates root doc and page."""
    admin = await make_user("page_fresh_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id, proj_key = await _setup_fresh_project(api_env, admin, identifier="PAGE0")

    page_payload = {
        "title": "Welcome Page",
        "body_markdown": "# Welcome\nFirst page in fresh project.",
    }
    resp = await client.post(f"/api/v1/projects/{proj_key}/docs/pages", json=page_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "Welcome Page"
    assert data["doc_id"] is not None

    # Check root doc in DB has valid creator
    doc_uuid = uuid.UUID(data["doc_id"])
    async with api_env.seed.begin_nested():
        root_doc_obj = await api_env.seed.get(ObjectRecord, doc_uuid)
        assert root_doc_obj is not None
        assert root_doc_obj.created_by_id == admin.id
        assert root_doc_obj.project_id == proj_id


async def test_auto_create_root_doc_fallback_resolution(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """_auto_create_root_doc resolves creator from explicit arg, GUC, and project fallback."""
    admin = await make_user("fallback_admin", workspace_role="WORKSPACE_ADMIN")
    other_user = await make_user("other_creator", workspace_role="WORKSPACE_ADMIN")
    proj_id, proj_key = await _setup_fresh_project(api_env, admin, identifier="FALLB")

    # 1. Caller principal explicit
    doc_id1 = await _auto_create_root_doc(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        proj_key,
        caller_principal_id=other_user.id,
    )
    obj1 = await api_env.seed.get(ObjectRecord, doc_id1)
    assert obj1 is not None
    assert obj1.created_by_id == other_user.id

    # 2. GUC fallback when caller_principal_id is None
    proj_id2, proj_key2 = await _setup_fresh_project(api_env, admin, identifier="FALL2")
    await api_env.seed.execute(
        text("SELECT set_config('app.principal_id', :pid, true)"),
        {"pid": str(other_user.id)},
    )
    doc_id2 = await _auto_create_root_doc(
        api_env.seed,
        api_env.workspace_id,
        proj_id2,
        proj_key2,
        caller_principal_id=None,
    )
    obj2 = await api_env.seed.get(ObjectRecord, doc_id2)
    assert obj2 is not None
    assert obj2.created_by_id == other_user.id

    # 3. Project creator fallback when both caller_principal_id and GUC are None
    proj_id3, proj_key3 = await _setup_fresh_project(api_env, admin, identifier="FALL3")
    await api_env.seed.execute(text("SELECT set_config('app.principal_id', '', true)"))
    doc_id3 = await _auto_create_root_doc(
        api_env.seed,
        api_env.workspace_id,
        proj_id3,
        proj_key3,
        caller_principal_id=None,
    )
    obj3 = await api_env.seed.get(ObjectRecord, doc_id3)
    assert obj3 is not None
    assert obj3.created_by_id == admin.id


async def test_resolve_doc_id_with_existing_doc_and_project_uuid(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """_resolve_doc_id returns existing root doc and supports project UUID."""
    admin = await make_user("exist_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    proj_id, proj_key = await _setup_fresh_project(api_env, admin, identifier="EXIST")

    # 1. First call creates root doc and page
    p1 = await client.post(
        f"/api/v1/projects/{proj_key}/docs/pages",
        json={"title": "Page 1", "body_markdown": "Body 1"},
    )
    assert p1.status_code == 201
    doc_id = p1.json()["doc_id"]

    # 2. Second call with project identifier re-uses existing doc (covers line 335)
    p2 = await client.post(
        f"/api/v1/projects/{proj_key}/docs/pages",
        json={"title": "Page 2", "body_markdown": "Body 2"},
    )
    assert p2.status_code == 201
    assert p2.json()["doc_id"] == doc_id

    # 3. Call with project UUID directly (covers line 301 and 335)
    p3 = await client.post(
        f"/api/v1/docs/{proj_id}/pages",
        json={"title": "Page 3", "body_markdown": "Body 3"},
    )
    assert p3.status_code == 201
    assert p3.json()["doc_id"] == doc_id

    # 4. Resolve page_id when ref is doc UUID (covers lines 387, 420-439)
    await api_env.seed.commit()
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    get_root_page = await client.get(f"/api/v1/pages/{doc_id}")
    assert get_root_page.status_code == 200
    assert get_root_page.json()["id"] == p1.json()["id"]

    # Also verify get_doc works on root doc
    get_doc_resp = await client.get(f"/api/v1/docs/{doc_id}")
    assert get_doc_resp.status_code == 200
    assert get_doc_resp.json()["id"] == str(doc_id)


async def test_docs_service_not_found_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Tests 404 not_found branches across docs endpoints."""
    admin = await make_user("notfound_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    fake_id = uuid.uuid4()

    # GET doc 404 (line 622)
    resp = await client.get(f"/api/v1/docs/{fake_id}")
    assert resp.status_code == 404

    # PATCH doc 404 (line 685)
    resp = await client.patch(
        f"/api/v1/docs/{fake_id}",
        json={"title": "New Title"},
        headers={"If-Match": "*"},
    )
    assert resp.status_code == 404

    # POST page with nonexistent parent_page_id (line 881)
    _proj_id, proj_key = await _setup_fresh_project(api_env, admin, identifier="NFPAR")
    p1 = await client.post(
        f"/api/v1/projects/{proj_key}/docs/pages",
        json={"title": "Root Page", "body_markdown": "Content"},
    )
    assert p1.status_code == 201
    doc_id = p1.json()["doc_id"]

    resp = await client.post(
        f"/api/v1/docs/{doc_id}/pages",
        json={"title": "Child Page", "parent_page_id": str(fake_id)},
    )
    assert resp.status_code == 404

    # PATCH page 404 (line 1182)
    resp = await client.patch(
        f"/api/v1/docs/pages/{fake_id}",
        json={"title": "New Title"},
        headers={"If-Match": "*"},
    )
    assert resp.status_code == 404

    # DELETE page 404 (line 1235)
    resp = await client.delete(
        f"/api/v1/docs/pages/{fake_id}",
        headers={"If-Match": "*"},
    )
    assert resp.status_code == 404

    # GET page history 404 (line 1410)
    resp = await client.get(f"/api/v1/docs/pages/{fake_id}/history")
    assert resp.status_code == 404

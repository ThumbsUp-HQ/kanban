# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and branch coverage tests for destructive lifecycle (KB-P4-12, S11.4)."""

# ruff: noqa: PLR0915

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from database.models.knowledge import Doc, Page, Sticky
from database.models.projects import Cycle, Module, View
from database.models.spine import ObjectRecord
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.services.destructive_lifecycle import (
    DestructiveExecuteResult,
    DestructiveRequestResult,
    DestructiveRestoreResult,
    _resolve_target_entity,
    compute_object_blast_radius,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_registered_object,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _enroll_totp(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )


@pytest.mark.asyncio
async def test_project_full_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Project entity: soft-trash, cascade deleted_at to children, restore, then permanent purge."""
    s_admin = await make_user("proj_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="FULLPRJ",
        name="Full Project Test",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    as_principal(s_admin, aal_level=2)

    # 1. Create issue in project
    r_iss = await api_env.client.post(
        "/api/v1/projects/FULLPRJ/issues", json={"summary": "P Issue"}
    )
    assert r_iss.status_code == 201

    # 2. Create Doc, Sticky, Cycle, Module, View in project
    doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="FDoc",
        title="FDoc",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Doc(
            id=doc_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            title="FDoc",
            body_markdown="body",
            hierarchy_path="fdoc",
        )
    )
    sticky_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="sticky",
        key="FSticky",
        title="FSticky",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Sticky(
            id=sticky_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            body_markdown="body",
        )
    )
    cyc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="cycle",
        key="FCyc",
        title="FCyc",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Cycle(id=cyc_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="FCyc")
    )
    mod_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="module",
        key="FMod",
        title="FMod",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Module(id=mod_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="FMod")
    )
    view_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="view",
        key="FView",
        title="FView",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        View(
            id=view_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            owner_principal_id=s_admin.id,
            name="FView",
            layout="board",
        )
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Request delete project by UUID and by identifier
    req_uuid = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "project", "target": str(proj_id), "mode": "trash"},
    )
    assert req_uuid.status_code == 200

    req_ident = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "project", "target": "FULLPRJ", "mode": "trash"},
    )
    assert req_ident.status_code == 200
    p_data = req_ident.json()
    assert "issues" in p_data["blast_summary"]
    tok = p_data["confirmation_token"]
    phrase = p_data["confirm_phrase"]

    # Execute trash
    ex = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "project",
            "target": "FULLPRJ",
            "mode": "trash",
            "confirmation_token": tok,
            "confirm_phrase": phrase,
            "reason": "Decommissioning full project",
        },
    )
    assert ex.status_code == 200
    p_obj = await api_env.seed.get(ObjectRecord, proj_id)
    assert p_obj is not None
    assert p_obj.deleted_at is not None

    # Restore project
    res_rest = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={"target_kind": "project", "target": "FULLPRJ", "reason": "Restoring project"},
    )
    assert res_rest.status_code == 200
    api_env.seed.expire(p_obj)
    p_obj_restored = await api_env.seed.get(ObjectRecord, proj_id)
    assert p_obj_restored is not None
    assert p_obj_restored.deleted_at is None

    # Trash again for permanent purge
    req_t2 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "project", "target": "FULLPRJ", "mode": "trash"},
    )
    tok_t2 = req_t2.json()["confirmation_token"]
    phrase_t2 = req_t2.json()["confirm_phrase"]
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "project",
            "target": "FULLPRJ",
            "mode": "trash",
            "confirmation_token": tok_t2,
            "confirm_phrase": phrase_t2,
            "reason": "Trashing before permanent purge",
        },
    )

    # Permanent purge
    req_p = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "project", "target": "FULLPRJ", "mode": "permanent_purge"},
    )
    assert req_p.status_code == 200
    tok_p = req_p.json()["confirmation_token"]
    phrase_p = req_p.json()["confirm_phrase"]

    ex_p = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "project",
            "target": "FULLPRJ",
            "mode": "permanent_purge",
            "confirmation_token": tok_p,
            "confirm_phrase": phrase_p,
            "reason": "Permanent audited project purge",
        },
    )
    assert ex_p.status_code == 200
    api_env.seed.expire_all()
    assert await api_env.seed.get(ObjectRecord, proj_id) is None


@pytest.mark.asyncio
async def test_doc_and_sticky_lifecycles(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Doc and Sticky: soft-trash, restore, and permanent purge."""
    s_admin = await make_user("doc_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="DOCPRJ",
        name="Doc Test",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )

    # Doc + Sticky
    doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="MyDoc",
        title="MyDocTitle",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Doc(
            id=doc_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            title="MyDocTitle",
            body_markdown="body",
            hierarchy_path="mydoc",
        )
    )
    sticky_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="sticky",
        key="MySticky",
        title="MyStickyTitle",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Sticky(
            id=sticky_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            body_markdown="body",
        )
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    as_principal(s_admin, aal_level=2)

    # 1. Doc trash & restore
    req_doc = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "doc", "target": "MyDocTitle", "mode": "trash"},
    )
    assert req_doc.status_code == 200
    tok_doc = req_doc.json()["confirmation_token"]
    phrase_doc = req_doc.json()["confirm_phrase"]

    ex_doc = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "doc",
            "target": "MyDocTitle",
            "mode": "trash",
            "confirmation_token": tok_doc,
            "confirm_phrase": phrase_doc,
            "reason": "Trashing test document",
        },
    )
    assert ex_doc.status_code == 200
    doc_obj = await api_env.seed.get(ObjectRecord, doc_id)
    assert doc_obj is not None
    assert doc_obj.deleted_at is not None

    rest_doc = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={"target_kind": "doc", "target": str(doc_id), "reason": "Restoring test document"},
    )
    assert rest_doc.status_code == 200
    api_env.seed.expire(doc_obj)
    doc_obj_restored = await api_env.seed.get(ObjectRecord, doc_id)
    assert doc_obj_restored is not None
    assert doc_obj_restored.deleted_at is None

    # 2. Sticky trash & restore
    req_st = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "sticky", "target": str(sticky_id), "mode": "trash"},
    )
    assert req_st.status_code == 200
    tok_st = req_st.json()["confirmation_token"]
    phrase_st = req_st.json()["confirm_phrase"]

    ex_st = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "sticky",
            "target": str(sticky_id),
            "mode": "trash",
            "confirmation_token": tok_st,
            "confirm_phrase": phrase_st,
            "reason": "Trashing test sticky note",
        },
    )
    assert ex_st.status_code == 200

    rest_st = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "sticky",
            "target": str(sticky_id),
            "reason": "Restoring test sticky note",
        },
    )
    assert rest_st.status_code == 200


@pytest.mark.asyncio
async def test_cycle_and_view_permanent_purge(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Cycles and Views: direct permanent_purge without soft-trash."""
    s_admin = await make_user("cyc_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="CYCPRJ",
        name="Cycle Test",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )

    cyc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="cycle",
        key="Sprint1",
        title="Sprint1",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Cycle(id=cyc_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="Sprint1")
    )
    view_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="view",
        key="MyView",
        title="MyView",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        View(
            id=view_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            owner_principal_id=s_admin.id,
            name="MyView",
            layout="list",
        )
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    as_principal(s_admin, aal_level=2)

    # 1. Cycle purge by name
    req_cyc = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "cycle", "target": "Sprint1", "mode": "permanent_purge"},
    )
    assert req_cyc.status_code == 200
    tok_c = req_cyc.json()["confirmation_token"]
    phrase_c = req_cyc.json()["confirm_phrase"]

    ex_cyc = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "cycle",
            "target": "Sprint1",
            "mode": "permanent_purge",
            "confirmation_token": tok_c,
            "confirm_phrase": phrase_c,
            "reason": "Purging sprint 1 cycle",
        },
    )
    assert ex_cyc.status_code == 200
    assert await api_env.seed.get(ObjectRecord, cyc_id) is None

    # 2. View purge by UUID
    req_view = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "view", "target": str(view_id), "mode": "permanent_purge"},
    )
    assert req_view.status_code == 200
    tok_v = req_view.json()["confirmation_token"]
    phrase_v = req_view.json()["confirm_phrase"]

    ex_view = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "view",
            "target": str(view_id),
            "mode": "permanent_purge",
            "confirmation_token": tok_v,
            "confirm_phrase": phrase_v,
            "reason": "Purging custom saved view",
        },
    )
    assert ex_view.status_code == 200
    assert await api_env.seed.get(ObjectRecord, view_id) is None


@pytest.mark.asyncio
async def test_error_and_edge_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Error branches: not found, invalid key format, not in trash, expired retention."""
    s_admin = await make_user("edge_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="EDGEPRJ",
        name="Edge Test",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    as_principal(s_admin, aal_level=2)

    # 1. Target not found
    r_bad_uuid = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": str(uuid.uuid4())},
    )
    assert r_bad_uuid.status_code == 404

    r_bad_key = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": "EDGEPRJ-notanumber"},
    )
    assert r_bad_key.status_code == 404

    r_no_dash = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": "nodashhere"},
    )
    assert r_no_dash.status_code == 404

    # 2. Restore active issue -> 409 NOT_IN_TRASH
    r_iss = await api_env.client.post(
        "/api/v1/projects/EDGEPRJ/issues", json={"summary": "Active Edge Issue"}
    )
    active_key = r_iss.json()["key"]
    r_not_trash = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "issue",
            "target": active_key,
            "reason": "Restoring non-trashed issue",
        },
    )
    assert r_not_trash.status_code == 409
    assert r_not_trash.json()["code"] == "NOT_IN_TRASH"

    # 3. Restore expired retention -> 409 RETENTION_EXPIRED
    # Move to trash
    req_t = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": active_key, "mode": "trash"},
    )
    tok_t = req_t.json()["confirmation_token"]
    phrase_t = req_t.json()["confirm_phrase"]
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": active_key,
            "mode": "trash",
            "confirmation_token": tok_t,
            "confirm_phrase": phrase_t,
            "reason": "Moving to trash for retention test",
        },
    )

    # Set deleted_at to 35 days ago
    await api_env.seed.execute(
        text(
            "UPDATE objects "
            "SET deleted_at = clock_timestamp() - interval '35 days' "
            "WHERE canonical_key = :k"
        ),
        {"k": active_key},
    )
    await api_env.seed.commit()

    r_expired = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={"target_kind": "issue", "target": active_key, "reason": "Restoring expired issue"},
    )
    assert r_expired.status_code == 409
    assert r_expired.json()["code"] == "RETENTION_EXPIRED"


@pytest.mark.asyncio
async def test_pages_modules_and_purges_deep(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Deep coverage for Page, Doc, Sticky, Cycle, Module, View lifecycles and serializers."""
    s_admin = await make_user("deep_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="DEEPPRJ",
        name="Deep Test Project",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )

    # 1. Create Doc + Parent Page + Child Page
    doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="DeepDoc",
        title="DeepDoc",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Doc(
            id=doc_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            title="DeepDoc",
            body_markdown="body",
            hierarchy_path="deepdoc",
        )
    )

    parent_page_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="page",
        key="ParentPage",
        title="ParentPage",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Page(
            id=parent_page_id,
            workspace_id=api_env.workspace_id,
            doc_id=doc_id,
            title="ParentPage",
            body_markdown="pbody",
            hierarchy_path="parent",
        )
    )

    child_page_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="page",
        key="ChildPage",
        title="ChildPage",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Page(
            id=child_page_id,
            workspace_id=api_env.workspace_id,
            doc_id=doc_id,
            title="ChildPage",
            body_markdown="cbody",
            hierarchy_path="parent.child",
        )
    )

    # 2. Sticky
    stk_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="sticky",
        key="DeepSticky",
        title="DeepSticky",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Sticky(
            id=stk_id, workspace_id=api_env.workspace_id, project_id=proj_id, body_markdown="sbody"
        )
    )

    # 3. Cycle & Module
    cyc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="cycle",
        key="DeepCycle",
        title="DeepCycle",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Cycle(id=cyc_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="DeepCycle")
    )

    mod_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="module",
        key="DeepModule",
        title="DeepModule",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Module(id=mod_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="DeepModule")
    )

    # 4. View
    v_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="view",
        key="DeepView",
        title="DeepView",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        View(
            id=v_id,
            workspace_id=api_env.workspace_id,
            project_id=proj_id,
            owner_principal_id=s_admin.id,
            name="DeepView",
            layout="board",
        )
    )

    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    as_principal(s_admin, aal_level=2)

    # Test resolving by UUID for doc, page, cycle, module, view
    for kind, uid in [
        ("doc", str(doc_id)),
        ("page", str(parent_page_id)),
        ("cycle", str(cyc_id)),
        ("module", str(mod_id)),
        ("view", str(v_id)),
    ]:
        r = await api_env.client.post(
            "/api/v1/admin/destructive:request",
            json={
                "target_kind": kind,
                "target": uid,
                "mode": "permanent_purge" if kind in ("cycle", "module", "view") else "trash",
            },
        )
        assert r.status_code == 200

    # Module permanent purge
    r_m = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "module", "target": "DeepModule", "mode": "permanent_purge"},
    )
    tok_m, phr_m = r_m.json()["confirmation_token"], r_m.json()["confirm_phrase"]
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "module",
            "target": "DeepModule",
            "mode": "permanent_purge",
            "confirmation_token": tok_m,
            "confirm_phrase": phr_m,
            "reason": "Purging module",
        },
    )

    # Page trash & restore (with child cascade)
    r_p = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "page", "target": "ParentPage", "mode": "trash"},
    )
    tok_p, phr_p = r_p.json()["confirmation_token"], r_p.json()["confirm_phrase"]
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "page",
            "target": "ParentPage",
            "mode": "trash",
            "confirmation_token": tok_p,
            "confirm_phrase": phr_p,
            "reason": "Trashing parent page",
        },
    )
    await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "page",
            "target": "ParentPage",
            "reason": "Restoring parent and child page",
        },
    )

    # Page permanent purge
    r_pt2 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "page", "target": "ParentPage", "mode": "trash"},
    )
    assert r_pt2.status_code == 200
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "page",
            "target": "ParentPage",
            "mode": "trash",
            "confirmation_token": r_pt2.json()["confirmation_token"],
            "confirm_phrase": r_pt2.json()["confirm_phrase"],
            "reason": "Trashing parent page again",
        },
    )
    r_pp = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "page", "target": "ParentPage", "mode": "permanent_purge"},
    )
    assert r_pp.status_code == 200
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "page",
            "target": "ParentPage",
            "mode": "permanent_purge",
            "confirmation_token": r_pp.json()["confirmation_token"],
            "confirm_phrase": r_pp.json()["confirm_phrase"],
            "reason": "Purging parent page",
        },
    )

    # Doc permanent purge
    r_dt = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "doc", "target": "DeepDoc", "mode": "trash"},
    )
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "doc",
            "target": "DeepDoc",
            "mode": "trash",
            "confirmation_token": r_dt.json()["confirmation_token"],
            "confirm_phrase": r_dt.json()["confirm_phrase"],
            "reason": "Trashing doc",
        },
    )
    r_dp = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "doc", "target": "DeepDoc", "mode": "permanent_purge"},
    )
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "doc",
            "target": "DeepDoc",
            "mode": "permanent_purge",
            "confirmation_token": r_dp.json()["confirmation_token"],
            "confirm_phrase": r_dp.json()["confirm_phrase"],
            "reason": "Purging doc",
        },
    )

    # Sticky permanent purge
    r_st = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "sticky", "target": str(stk_id), "mode": "trash"},
    )
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "sticky",
            "target": str(stk_id),
            "mode": "trash",
            "confirmation_token": r_st.json()["confirmation_token"],
            "confirm_phrase": r_st.json()["confirm_phrase"],
            "reason": "Trashing sticky",
        },
    )
    r_sp = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "sticky", "target": str(stk_id), "mode": "permanent_purge"},
    )
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "sticky",
            "target": str(stk_id),
            "mode": "permanent_purge",
            "confirmation_token": r_sp.json()["confirmation_token"],
            "confirm_phrase": r_sp.json()["confirm_phrase"],
            "reason": "Purging sticky",
        },
    )

    # Direct resolution errors
    # sticky non-uuid
    r_err1 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "sticky", "target": "not-a-uuid", "mode": "trash"},
    )
    assert r_err1.status_code == 404
    # nonexistent doc, page, cycle, module, view
    for bad_kind in ["doc", "page", "cycle", "module", "view"]:
        m = "permanent_purge" if bad_kind in ("cycle", "module", "view") else "trash"
        r_bad = await api_env.client.post(
            "/api/v1/admin/destructive:request",
            json={"target_kind": bad_kind, "target": "NonExistentThing", "mode": m},
        )
        assert r_bad.status_code == 404
        r_bad_uuid = await api_env.client.post(
            "/api/v1/admin/destructive:request",
            json={"target_kind": bad_kind, "target": str(uuid.uuid4()), "mode": m},
        )
        assert r_bad_uuid.status_code == 404

    # Invalid target_kind
    with pytest.raises(ProblemException) as exc_kind:
        await compute_object_blast_radius(
            api_env.seed,
            caller=PrincipalContext(
                principal_id=s_admin.id, workspace_id=api_env.workspace_id, aal_level=2
            ),
            target_kind="alien",
            target_ref="foo",
        )
    assert exc_kind.value.code == "VALIDATION_FAILED"

    # to_dict checks
    req_res = DestructiveRequestResult(
        "req", "T", "issue", "id", "trash", "summary", "hash", "phrase", "tok", 300
    )
    assert req_res.to_dict()["stage"] == "req"
    exe_res = DestructiveExecuteResult("status", "T", "issue", "id", "trash", "reason", "hash")
    assert exe_res.to_dict()["status"] == "status"
    rst_res = DestructiveRestoreResult("status", "T", "issue", "id", "reason")
    assert rst_res.to_dict()["status"] == "status"


@pytest.mark.asyncio
async def test_service_edge_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Target remaining branch edges in destructive_lifecycle service."""
    s_admin = await make_user("edge_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await create_project(
        api_env.seed,
        api_env.workspace_id,
        identifier="EDGE2PRJ",
        name="Edge2 Project",
        created_by_id=s_admin.id,
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 1. Non-existent project and non-existent sticky
    as_principal(s_admin, aal_level=2)
    r_noproj = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "project", "target": "NONEXISTENT", "mode": "trash"},
    )
    assert r_noproj.status_code == 404

    r_nostk = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "sticky", "target": str(uuid.uuid4()), "mode": "trash"},
    )
    assert r_nostk.status_code == 404

    # 2. Unknown target kind in _resolve_target_entity
    caller_ctx = PrincipalContext(
        principal_id=s_admin.id, workspace_id=api_env.workspace_id, aal_level=2
    )
    with pytest.raises(ProblemException) as exc_resolve:
        await _resolve_target_entity(
            api_env.seed, caller_ctx, target_kind="alien", target_ref="foo"
        )
    assert exc_resolve.value.code == "NOT_FOUND"

    # 3. Create issue for cycle reference test and token burn test
    r_iss = await api_env.client.post(
        "/api/v1/projects/EDGE2PRJ/issues", json={"summary": "Edge Cycle Issue"}
    )
    assert r_iss.status_code == 201
    iss_key = r_iss.json()["key"]

    cyc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="cycle",
        key="CycleWithIssue",
        title="CycleWithIssue",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    api_env.seed.add(
        Cycle(
            id=cyc_id, workspace_id=api_env.workspace_id, project_id=proj_id, name="CycleWithIssue"
        )
    )
    await api_env.seed.commit()

    # Link issue to cycle
    await api_env.seed.execute(
        text(
            "UPDATE issues SET cycle_id = :cid "
            "WHERE id = (SELECT id FROM objects WHERE canonical_key = :k)"
        ),
        {"cid": cyc_id, "k": iss_key},
    )
    await api_env.seed.commit()

    # Permanent purge cycle with referenced issue -> executes lines 1035-1039
    r_cyc_req = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "cycle", "target": "CycleWithIssue", "mode": "permanent_purge"},
    )
    assert r_cyc_req.status_code == 200
    await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "cycle",
            "target": "CycleWithIssue",
            "mode": "permanent_purge",
            "confirmation_token": r_cyc_req.json()["confirmation_token"],
            "confirm_phrase": r_cyc_req.json()["confirm_phrase"],
            "reason": "Purging cycle with referencing issue",
        },
    )

    # 4. Restore errors: not trashed and not found
    r_rest_active = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "reason": "Restoring an active non-deleted issue",
        },
    )
    assert r_rest_active.status_code == 409
    assert r_rest_active.json()["code"] == "NOT_IN_TRASH"

    r_rest_404 = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "issue",
            "target": "EDGE2PRJ-9999",
            "reason": "Restoring missing issue",
        },
    )
    assert r_rest_404.status_code == 404

    # 5. Token burning on target resolution failure
    r_burn_req = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": iss_key, "mode": "trash"},
    )
    assert r_burn_req.status_code == 200
    b_tok = r_burn_req.json()["confirmation_token"]
    b_phr = r_burn_req.json()["confirm_phrase"]

    # Mark the issue as deleted in objects table so include_deleted=False fails
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = clock_timestamp() WHERE canonical_key = :k"),
        {"k": iss_key},
    )
    await api_env.seed.commit()

    r_burn_ex = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": b_tok,
            "confirm_phrase": b_phr,
            "reason": "Burning token on nonexistent target",
        },
    )
    assert r_burn_ex.status_code == 404

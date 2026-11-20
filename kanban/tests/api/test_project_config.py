# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Project configuration API tests: workflow states, priorities & labels (KB-P3-01b)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from database.models import WorkflowTransitionExecution, WorkflowTransitionHook
from kanban.tests.security.helpers import add_role_binding, rebuild_era
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, **params: object) -> int:
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def _seed_issue(  # noqa: PLR0913, PLR0917
    api_env: ApiEnv,
    proj_id: str,
    pref: str,
    admin_uid: uuid.UUID,
    state_id: str,
    priority_id: str,
    summary: str = "Test Issue",
) -> uuid.UUID:
    """Seed an issue using proper sequence allocation and spine registration."""
    ws_id = (
        await api_env.seed.execute(
            text("SELECT workspace_id FROM projects WHERE id = :p"), {"p": proj_id}
        )
    ).scalar_one()
    seq_val = (
        await api_env.seed.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    issue_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :creator, :id)"
        ),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"{pref}-{seq_val}",
            "title": summary,
            "creator": admin_uid,
            "id": issue_id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, :st, :pr, :title, :creator, :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq_val,
            "st": state_id,
            "pr": priority_id,
            "title": summary,
            "creator": admin_uid,
        },
    )
    await api_env.seed.commit()
    return issue_id


async def _setup_project_with_roles(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    identifier: str = "CONF",
) -> tuple[str, str, SeededUser, SeededUser, SeededUser, SeededUser, httpx.AsyncClient]:
    """Seed a project and return (proj_id, identifier, admin, editor, viewer, outsider, client)."""
    admin = await make_user(f"adm_{identifier.lower()}", workspace_role="WORKSPACE_ADMIN")
    editor = await make_user(f"edt_{identifier.lower()}")
    viewer = await make_user(f"viw_{identifier.lower()}")
    outsider = await make_user(f"out_{identifier.lower()}")

    client = as_principal(admin)

    # Create project as admin
    resp = await client.post(
        "/api/v1/projects",
        json={"identifier": identifier, "name": f"Config Project {identifier}"},
    )
    assert resp.status_code == 201, resp.text
    proj_id = resp.json()["id"]

    # Bind roles
    ws_id = admin.workspace_id
    await add_role_binding(api_env.seed, ws_id, editor.id, "MEMBER", project_id=uuid.UUID(proj_id))
    await add_role_binding(api_env.seed, ws_id, viewer.id, "VIEWER", project_id=uuid.UUID(proj_id))
    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    return proj_id, identifier, admin, editor, viewer, outsider, client


# ---------------------------------------------------------------------------
# Mandatory Feature Test Cases
# ---------------------------------------------------------------------------


async def test_case_1_admin_creates_state_with_wip_limits_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Admin creates started state with wip_soft_limit=3, wip_hard_limit=5."""
    proj_id, pref, admin, _, viewer, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC1"
    )

    as_principal(admin)
    resp = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={
            "name": "In Review",
            "group": "started",
            "color_hex": "#3B82F6",
            "sort_order": 30,
            "is_default": False,
            "wip_soft_limit": 3,
            "wip_hard_limit": 5,
        },
    )
    contract_recorder.record("create_state_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "In Review"
    assert body["group"] == "started"
    assert body["color_hex"] == "#3B82F6"
    assert body["wip_soft_limit"] == 3
    assert body["wip_hard_limit"] == 5
    assert body["issue_count"] == 0
    state_id = body["id"]
    assert resp.headers["Location"] == f"/api/v1/projects/{pref}/states/{state_id}"

    # GET .../states returns it with issue_count: 0
    as_principal(viewer)
    list_resp = await client.get(f"/api/v1/projects/{pref}/states")
    assert list_resp.status_code == 200
    states = list_resp.json()
    created_state = next((s for s in states if s["id"] == state_id), None)
    assert created_state is not None
    assert created_state["issue_count"] == 0

    # STATE_CREATED activity row exists
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :p "
            "  AND event_type = 'STATE_CREATED' AND payload->>'state_id' = :sid",
            p=proj_id,
            sid=state_id,
        )
        == 1
    )


async def test_case_2_capability_and_anti_enumeration_discipline(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: EDIT user POST states -> 403; non-member -> 404; label id cross-project -> 404."""
    _, p1_ref, admin1, edit1, _, outsider, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC2A"
    )
    _, p2_ref, admin2, _, _, _, _ = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC2B"
    )

    # 1. EDIT user tries to POST /states -> 403 INSUFFICIENT_CAPABILITY
    as_principal(edit1)
    resp_403 = await client.post(
        f"/api/v1/projects/{p1_ref}/states",
        json={"name": "Forbidden State", "group": "started", "color_hex": "#10B981"},
    )
    contract_recorder.record("post_state_edit_user_403", resp_403.request, resp_403)
    assert resp_403.status_code == 403
    assert resp_403.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 2. Non-member (outsider) tries to access project -> equalized 404 NOT_FOUND
    as_principal(outsider)
    resp_404 = await client.get(f"/api/v1/projects/{p1_ref}/states")
    assert resp_404.status_code == 404
    assert resp_404.json()["code"] == "NOT_FOUND"

    # 3. Create a label in project 2
    as_principal(admin2)
    l2_resp = await client.post(
        f"/api/v1/projects/{p2_ref}/labels",
        json={"name": "backend", "color_hex": "#6366F1"},
    )
    assert l2_resp.status_code == 201
    l2_id = l2_resp.json()["id"]

    # Patch label from project 2 via project 1 path -> equalized 404 NOT_FOUND
    as_principal(admin1)
    cross_resp = await client.patch(
        f"/api/v1/projects/{p1_ref}/labels/{l2_id}",
        json={"name": "renamed"},
    )
    contract_recorder.record("cross_project_id_404", cross_resp.request, cross_resp)
    assert cross_resp.status_code == 404
    assert cross_resp.json()["code"] == "NOT_FOUND"


async def test_case_3_exclusive_group_and_label_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Creating label type:bug with group type succeeds; group Type! returns 422."""
    _, pref, _, edit_user, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC3"
    )

    # EDIT user creates label with valid exclusive group -> 201
    as_principal(edit_user)
    resp_ok = await client.post(
        f"/api/v1/projects/{pref}/labels",
        json={"name": "type:bug", "color_hex": "#EF4444", "exclusive_group": "type"},
    )
    contract_recorder.record("create_label_edit_user_201", resp_ok.request, resp_ok)
    assert resp_ok.status_code == 201, resp_ok.text
    body = resp_ok.json()
    assert body["name"] == "type:bug"
    assert body["exclusive_group"] == "type"

    # Invalid exclusive group regex (contains uppercase and exclamation mark) -> 422
    resp_bad = await client.post(
        f"/api/v1/projects/{pref}/labels",
        json={"name": "type:feature", "color_hex": "#3B82F6", "exclusive_group": "Type!"},
    )
    assert resp_bad.status_code == 422


async def test_case_4_boundary_state_transitions_and_migrations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: WIP bounds, deleting only completed state 409, in-use state migration."""
    proj_id, pref, admin, _, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC4"
    )
    as_principal(admin)

    # 1. wip_soft_limit > wip_hard_limit returns 422
    resp_inv_wip = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={
            "name": "Invalid WIP",
            "group": "started",
            "color_hex": "#EF4444",
            "wip_soft_limit": 6,
            "wip_hard_limit": 5,
        },
    )
    contract_recorder.record("wip_invalid_422", resp_inv_wip.request, resp_inv_wip)
    assert resp_inv_wip.status_code == 422

    # 2. 999 accepted, 1000 rejected
    resp_999 = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={
            "name": "Bound 999",
            "group": "started",
            "color_hex": "#10B981",
            "wip_soft_limit": 999,
            "wip_hard_limit": 999,
        },
    )
    assert resp_999.status_code == 201

    resp_1000 = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={
            "name": "Bound 1000",
            "group": "started",
            "color_hex": "#10B981",
            "wip_soft_limit": 1000,
        },
    )
    assert resp_1000.status_code == 422

    # 3. Deleting the only completed state returns 409 LAST_STATE_IN_GROUP
    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    done_state = next(s for s in states if s["group"] == "completed")
    resp_last = await client.delete(f"/api/v1/projects/{pref}/states/{done_state['id']}")
    assert resp_last.status_code == 409
    assert resp_last.json()["code"] == "LAST_STATE_IN_GROUP"

    # 4. Deleting an in-use state without migrate_to returns 409 STATE_IN_USE
    # Seed an issue into an unstarted state
    todo_state = next(s for s in states if s["group"] == "unstarted" and not s["is_default"])
    target_state = next(s for s in states if s["group"] == "started")

    # Get priority ID
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    prio_id = prios[0]["id"]

    issue_id = await _seed_issue(
        api_env,
        proj_id,
        pref,
        admin.id,
        todo_state["id"],
        prio_id,
        "Test Issue 1",
    )

    # Attempt delete without migrate_to -> 409 STATE_IN_USE
    del_in_use = await client.delete(f"/api/v1/projects/{pref}/states/{todo_state['id']}")
    contract_recorder.record("delete_state_in_use_409", del_in_use.request, del_in_use)
    assert del_in_use.status_code == 409
    assert del_in_use.json()["code"] == "STATE_IN_USE"

    # Attempt delete with valid migrate_to -> 204 and moves issues
    del_migrated = await client.delete(
        f"/api/v1/projects/{pref}/states/{todo_state['id']}?migrate_to={target_state['id']}"
    )
    assert del_migrated.status_code == 204

    # Verify issue state updated
    new_st = (
        await api_env.seed.execute(
            text("SELECT state_id FROM issues WHERE id = :id"), {"id": issue_id}
        )
    ).scalar_one()
    assert str(new_st) == target_state["id"]

    # Verify ISSUE_FIELD_CHANGED activity recorded
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :iss "
            "  AND event_type = 'ISSUE_FIELD_CHANGED' AND payload->>'field' = 'state_id'",
            iss=issue_id,
        )
        == 1
    )


async def test_case_5_default_invariants_and_priority_management(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 5: Setting second default leaves one is_default=true; delete default -> 409."""
    _, pref, admin, editor, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="TC5"
    )
    as_principal(admin)

    # 1. Priorities: create a new default priority
    prio_resp = await client.post(
        f"/api/v1/projects/{pref}/priorities",
        json={
            "slug": "blocker",
            "label": "Blocker",
            "emoji": "🧯",
            "color_hex": "#B91C1C",
            "sort_order": 0,
            "is_default": True,
        },
    )
    assert prio_resp.status_code == 201
    blocker_id = prio_resp.json()["id"]

    # Assert exactly one priority has is_default = True
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    defaults = [p for p in prios if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == blocker_id

    # 2. Deleting default priority returns 409 DEFAULT_PRIORITY
    del_default = await client.delete(f"/api/v1/projects/{pref}/priorities/{blocker_id}")
    assert del_default.status_code == 409
    assert del_default.json()["code"] == "DEFAULT_PRIORITY"

    # 3. Priority patch by EDIT user returns 403
    as_principal(editor)
    patch_edit = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{blocker_id}",
        json={"label": "Super Blocker"},
    )
    contract_recorder.record("patch_priority_edit_user_403", patch_edit.request, patch_edit)
    assert patch_edit.status_code == 403
    assert patch_edit.json()["code"] == "INSUFFICIENT_CAPABILITY"


# ---------------------------------------------------------------------------
# Additional Depth & Branch Coverage Tests
# ---------------------------------------------------------------------------


async def test_state_crud_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Comprehensive branch coverage for states CRUD, duplicate name, patching, and default."""
    _proj_id, pref, admin, _, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="STCRUD"
    )
    as_principal(admin)

    # 1. Duplicate state name returns 409 STATE_NAME_TAKEN
    resp_dup = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={"name": "Todo", "group": "unstarted", "color_hex": "#94A3B8"},
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["code"] == "STATE_NAME_TAKEN"

    # 2. Patch state fields
    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    target_state = states[0]
    patch_resp = await client.patch(
        f"/api/v1/projects/{pref}/states/{target_state['id']}",
        json={
            "name": "Backlog Renamed",
            "color_hex": "#64748B",
            "sort_order": 99,
            "wip_soft_limit": 2,
            "wip_hard_limit": 4,
        },
    )
    assert patch_resp.status_code == 200
    p_body = patch_resp.json()
    assert p_body["name"] == "Backlog Renamed"
    assert p_body["color_hex"] == "#64748B"
    assert p_body["sort_order"] == 99
    assert p_body["wip_soft_limit"] == 2
    assert p_body["wip_hard_limit"] == 4

    # Patch with invalid conflicting WIP limits
    patch_bad_wip = await client.patch(
        f"/api/v1/projects/{pref}/states/{target_state['id']}",
        json={"wip_soft_limit": 10},  # soft 10 > hard 4
    )
    assert patch_bad_wip.status_code == 422

    # Patch duplicate name on another state
    patch_dup = await client.patch(
        f"/api/v1/projects/{pref}/states/{states[1]['id']}",
        json={"name": "Backlog Renamed"},
    )
    assert patch_dup.status_code == 409
    assert patch_dup.json()["code"] == "STATE_NAME_TAKEN"

    # Patch default state
    patch_def = await client.patch(
        f"/api/v1/projects/{pref}/states/{states[1]['id']}",
        json={"is_default": True},
    )
    assert patch_def.status_code == 200
    assert patch_def.json()["is_default"] is True

    # 3. Delete default state -> 409 DEFAULT_STATE
    del_def = await client.delete(f"/api/v1/projects/{pref}/states/{states[1]['id']}")
    assert del_def.status_code == 409
    assert del_def.json()["code"] == "DEFAULT_STATE"

    # 4. Migrate to same state -> 422 MIGRATE_TARGET_INVALID
    del_same = await client.delete(
        f"/api/v1/projects/{pref}/states/{states[0]['id']}?migrate_to={states[0]['id']}"
    )
    assert del_same.status_code == 422
    assert del_same.json()["code"] == "MIGRATE_TARGET_INVALID"

    # 5. Migrate to invalid target UUID -> 422 MIGRATE_TARGET_INVALID
    del_fake = await client.delete(
        f"/api/v1/projects/{pref}/states/{states[0]['id']}?migrate_to={uuid.uuid4()}"
    )
    assert del_fake.status_code == 422
    assert del_fake.json()["code"] == "MIGRATE_TARGET_INVALID"


async def test_priority_crud_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Comprehensive branch coverage for priorities CRUD, duplicates, and migration."""
    proj_id, pref, admin, _, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="PRCRUD"
    )
    as_principal(admin)

    # 1. Duplicate slug returns 409 PRIORITY_SLUG_TAKEN
    resp_dup = await client.post(
        f"/api/v1/projects/{pref}/priorities",
        json={
            "slug": "urgent",
            "label": "Urgent",
            "color_hex": "#EF4444",
            "sort_order": 1,
        },
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["code"] == "PRIORITY_SLUG_TAKEN"

    # 2. Patch priority
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    prio_to_patch = next(p for p in prios if not p["is_default"])
    patch_resp = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}",
        json={
            "label": "Urgent Escalated",
            "emoji": "🔥",
            "color_hex": "#DC2626",
            "sort_order": 2,
        },
    )
    assert patch_resp.status_code == 200
    p_body = patch_resp.json()
    assert p_body["label"] == "Urgent Escalated"
    assert p_body["emoji"] == "🔥"
    assert p_body["color_hex"] == "#DC2626"

    # Patch slug specifically to verify slug update branch
    patch_slug = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}",
        json={"slug": "urgent-super"},
    )
    assert patch_slug.status_code == 200
    assert patch_slug.json()["slug"] == "urgent-super"

    # Patch with duplicate slug on another priority
    patch_dup_slug = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}",
        json={"slug": "none"},
    )
    assert patch_dup_slug.status_code == 409
    assert patch_dup_slug.json()["code"] == "PRIORITY_SLUG_TAKEN"

    # 3. Delete in-use priority without migrate_to
    # Seed an issue with prio_to_patch
    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    state_id = states[0]["id"]
    iss_id = await _seed_issue(
        api_env,
        proj_id,
        pref,
        admin.id,
        state_id,
        prio_to_patch["id"],
        "Priority Test Issue",
    )

    del_in_use = await client.delete(f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}")
    assert del_in_use.status_code == 409
    assert del_in_use.json()["code"] == "PRIORITY_IN_USE"

    # Delete with invalid migrate_to (same priority) -> 422
    del_same = await client.delete(
        f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}?migrate_to={prio_to_patch['id']}"
    )
    assert del_same.status_code == 422
    assert del_same.json()["code"] == "MIGRATE_TARGET_INVALID"

    # Delete with valid migrate_to -> 204
    target_prio = next(p for p in prios if p["id"] != prio_to_patch["id"])
    del_ok = await client.delete(
        f"/api/v1/projects/{pref}/priorities/{prio_to_patch['id']}?migrate_to={target_prio['id']}"
    )
    assert del_ok.status_code == 204

    # Verify issue priority updated
    new_pr = (
        await api_env.seed.execute(
            text("SELECT priority_id FROM issues WHERE id = :id"), {"id": iss_id}
        )
    ).scalar_one()
    assert str(new_pr) == target_prio["id"]


async def test_label_crud_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Comprehensive branch coverage for labels CRUD, duplicates, patching, and detach on delete."""
    proj_id, pref, admin, edit_user, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="LBLCRUD"
    )

    # 1. Create labels as edit user
    as_principal(edit_user)
    l1 = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "frontend", "color_hex": "#3B82F6", "exclusive_group": "tier"},
        )
    ).json()

    await client.post(
        f"/api/v1/projects/{pref}/labels",
        json={"name": "backend", "color_hex": "#10B981", "exclusive_group": "tier"},
    )

    # Duplicate name -> 409 LABEL_NAME_TAKEN
    dup_resp = await client.post(
        f"/api/v1/projects/{pref}/labels",
        json={"name": "frontend", "color_hex": "#000000"},
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["code"] == "LABEL_NAME_TAKEN"

    # List labels ordered by name as admin
    as_principal(admin)
    list_resp = await client.get(f"/api/v1/projects/{pref}/labels")
    assert list_resp.status_code == 200
    labels = list_resp.json()
    names = [lbl["name"] for lbl in labels]
    assert names == sorted(names)

    # 2. Patch label
    patch_resp = await client.patch(
        f"/api/v1/projects/{pref}/labels/{l1['id']}",
        json={"name": "frontend-ui", "color_hex": "#2563EB", "exclusive_group": "domain"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "frontend-ui"
    assert patch_resp.json()["color_hex"] == "#2563EB"
    assert patch_resp.json()["exclusive_group"] == "domain"

    # Patch with duplicate name -> 409
    patch_dup = await client.patch(
        f"/api/v1/projects/{pref}/labels/{l1['id']}",
        json={"name": "backend"},
    )
    assert patch_dup.status_code == 409
    assert patch_dup.json()["code"] == "LABEL_NAME_TAKEN"

    # 3. Delete label detaches from issue_labels
    # Attach l1 to an issue
    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()

    iss_id = await _seed_issue(
        api_env,
        proj_id,
        pref,
        admin.id,
        states[0]["id"],
        prios[0]["id"],
        "Label Test Issue",
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:iss, :lbl)"),
        {"iss": iss_id, "lbl": l1["id"]},
    )
    await api_env.seed.commit()

    # Assert issue_labels row exists
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :iss AND label_id = :lbl",
            iss=iss_id,
            lbl=l1["id"],
        )
        == 1
    )

    # Delete label
    del_resp = await client.delete(f"/api/v1/projects/{pref}/labels/{l1['id']}")
    assert del_resp.status_code == 204

    # Assert issue_labels row was removed
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :iss AND label_id = :lbl",
            iss=iss_id,
            lbl=l1["id"],
        )
        == 0
    )


async def test_schema_validators_and_direct_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify schema validators for WIP limits and emoji constraints."""
    _, pref, admin, _, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="SCHEM"
    )
    as_principal(admin)

    # 1. StatePatch with invalid WIP limits (soft > hard) returns 422
    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    resp_patch_wip = await client.patch(
        f"/api/v1/projects/{pref}/states/{states[0]['id']}",
        json={"wip_soft_limit": 10, "wip_hard_limit": 5},
    )
    assert resp_patch_wip.status_code == 422

    # 2. PriorityCreate with invalid emoji length (empty or > 8)
    resp_prio_emoji_long = await client.post(
        f"/api/v1/projects/{pref}/priorities",
        json={
            "slug": "toolong",
            "label": "Too Long Emoji",
            "emoji": "123456789",
            "color_hex": "#EF4444",
        },
    )
    assert resp_prio_emoji_long.status_code == 422

    resp_prio_emoji_empty = await client.post(
        f"/api/v1/projects/{pref}/priorities",
        json={
            "slug": "emptyemoji",
            "label": "Empty Emoji",
            "emoji": "",
            "color_hex": "#EF4444",
        },
    )
    assert resp_prio_emoji_empty.status_code == 422

    # 3. PriorityPatch with invalid emoji length
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    resp_patch_emoji_long = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{prios[0]['id']}",
        json={"emoji": "123456789"},
    )
    assert resp_patch_emoji_long.status_code == 422

    resp_patch_emoji_empty = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{prios[0]['id']}",
        json={"emoji": ""},
    )
    assert resp_patch_emoji_empty.status_code == 422


async def test_full_branch_coverage_and_404_preconditions(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Exercise remaining branches: 404s, group changes, default clearing, and migration limits."""
    proj_id, pref, admin, _, _, _, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="BRANCH"
    )
    as_principal(admin)

    # 1. State: create with is_default=True clears previous default
    states_before = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    prev_default = next(s for s in states_before if s["is_default"])

    create_def_state = await client.post(
        f"/api/v1/projects/{pref}/states",
        json={
            "name": "New Default State",
            "group": "unstarted",
            "color_hex": "#3B82F6",
            "is_default": True,
        },
    )
    assert create_def_state.status_code == 201
    new_def_state_id = create_def_state.json()["id"]

    # Verify previous default was cleared
    states_after = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    prev_st_updated = next(s for s in states_after if s["id"] == prev_default["id"])
    assert prev_st_updated["is_default"] is False
    new_st_updated = next(s for s in states_after if s["id"] == new_def_state_id)
    assert new_st_updated["is_default"] is True

    # 2. State: nonexistent ID -> 404 on PATCH and DELETE
    fake_id = uuid.uuid4()
    assert (
        await client.patch(
            f"/api/v1/projects/{pref}/states/{fake_id}",
            json={"name": "Ghost"},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pref}/states/{fake_id}")).status_code == 404

    # 3. State: patch changing group and clearing wip limits to None
    patch_grp = await client.patch(
        f"/api/v1/projects/{pref}/states/{new_def_state_id}",
        json={
            "group": "started",
            "wip_soft_limit": None,
            "wip_hard_limit": None,
        },
    )
    assert patch_grp.status_code == 200
    assert patch_grp.json()["group"] == "started"

    # 4. State: patch with no changes
    patch_noop = await client.patch(
        f"/api/v1/projects/{pref}/states/{new_def_state_id}",
        json={},
    )
    assert patch_noop.status_code == 200

    # 5. Priority: nonexistent ID -> 404 on PATCH and DELETE
    assert (
        await client.patch(
            f"/api/v1/projects/{pref}/priorities/{fake_id}",
            json={"label": "Ghost"},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pref}/priorities/{fake_id}")).status_code == 404

    # 6. Priority: patch with no changes, and patch updating sort_order and clearing emoji
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    non_def_prio = next(p for p in prios if not p["is_default"])
    p_noop = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{non_def_prio['id']}",
        json={},
    )
    assert p_noop.status_code == 200

    p_patch_details = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{non_def_prio['id']}",
        json={"sort_order": 77, "emoji": None},
    )
    assert p_patch_details.status_code == 200
    assert p_patch_details.json()["sort_order"] == 77
    assert p_patch_details.json()["emoji"] is None

    # 7. Priority: patch setting is_default=True clears previous default
    prev_def_prio = next(p for p in prios if p["is_default"])
    p_set_def = await client.patch(
        f"/api/v1/projects/{pref}/priorities/{non_def_prio['id']}",
        json={"is_default": True},
    )
    assert p_set_def.status_code == 200
    assert p_set_def.json()["is_default"] is True

    prios_after = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()
    old_def_refetched = next(p for p in prios_after if p["id"] == prev_def_prio["id"])
    assert old_def_refetched["is_default"] is False

    # 8. Label: nonexistent ID -> 404 on PATCH and DELETE
    assert (
        await client.patch(
            f"/api/v1/projects/{pref}/labels/{fake_id}",
            json={"name": "Ghost"},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pref}/labels/{fake_id}")).status_code == 404

    # 9. Label: create, patch clearing exclusive_group to None, patch noop
    l_create = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "scoped-lbl", "color_hex": "#10B981", "exclusive_group": "group1"},
        )
    ).json()
    l_id = l_create["id"]

    l_noop = await client.patch(f"/api/v1/projects/{pref}/labels/{l_id}", json={})
    assert l_noop.status_code == 200

    l_clear_grp = await client.patch(
        f"/api/v1/projects/{pref}/labels/{l_id}",
        json={"exclusive_group": None},
    )
    assert l_clear_grp.status_code == 200
    assert l_clear_grp.json()["exclusive_group"] is None

    # 10. MIGRATION_TOO_LARGE: > 500 issues on delete state and priority
    # Create throwaway state and priority to hold 501 issues
    st_overflow = (
        await client.post(
            f"/api/v1/projects/{pref}/states",
            json={"name": "Overflow State", "group": "started", "color_hex": "#F59E0B"},
        )
    ).json()
    st_target = (
        await client.post(
            f"/api/v1/projects/{pref}/states",
            json={"name": "Target State", "group": "started", "color_hex": "#10B981"},
        )
    ).json()

    pr_overflow = (
        await client.post(
            f"/api/v1/projects/{pref}/priorities",
            json={
                "slug": "overflowprio",
                "label": "Overflow Prio",
                "color_hex": "#DC2626",
                "sort_order": 90,
            },
        )
    ).json()
    pr_target = prios_after[0]

    # Bulk insert 501 issues in the committed session
    proj_uuid = uuid.UUID(proj_id)
    ws_id = (
        await api_env.seed.execute(
            text("SELECT workspace_id FROM projects WHERE id = :p"), {"p": proj_uuid}
        )
    ).scalar_one()

    await api_env.seed.execute(text("SET LOCAL session_replication_role = 'replica'"))
    await api_env.seed.execute(
        text("UPDATE projects SET issue_seq_counter = 2000 WHERE id = :p"),
        {"p": proj_uuid},
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO objects "
            "(id, object_type, workspace_id, project_id, canonical_key, "
            "display_title, created_by_id) "
            "SELECT uuidv7(), 'issue'::object_kind, :ws, :p, :pref || '-' || (1000 + i), "
            "'Bulk ' || i, :creator "
            "FROM generate_series(1, 501) AS i"
        ),
        {"ws": ws_id, "p": proj_uuid, "pref": pref, "creator": admin.id},
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues "
            "(id, workspace_id, project_id, sequence_id, summary, state_id, "
            "priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "SELECT o.id, :ws, :p, (1000 + i), 'Bulk ' || i, :st, :pr, "
            ":creator, :creator, '0|hzzzzz:', 'top'::ltree "
            "FROM generate_series(1, 501) AS i "
            "JOIN objects o ON o.canonical_key = :pref || '-' || (1000 + i) "
            "AND o.project_id = :p"
        ),
        {
            "ws": ws_id,
            "p": proj_uuid,
            "pref": pref,
            "st": uuid.UUID(st_overflow["id"]),
            "pr": uuid.UUID(pr_overflow["id"]),
            "creator": admin.id,
        },
    )
    await api_env.seed.execute(text("SET LOCAL session_replication_role = 'origin'"))
    await api_env.seed.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"),
        {"ws": ws_id},
    )
    await api_env.seed.commit()

    # Attempt delete state with > 500 issues -> 409 MIGRATION_TOO_LARGE
    del_st_overflow = await client.delete(
        f"/api/v1/projects/{pref}/states/{st_overflow['id']}?migrate_to={st_target['id']}"
    )
    assert del_st_overflow.status_code == 409
    assert del_st_overflow.json()["code"] == "MIGRATION_TOO_LARGE"

    # Attempt delete priority with > 500 issues -> 409 MIGRATION_TOO_LARGE
    del_pr_overflow = await client.delete(
        f"/api/v1/projects/{pref}/priorities/{pr_overflow['id']}?migrate_to={pr_target['id']}"
    )
    assert del_pr_overflow.status_code == 409
    assert del_pr_overflow.json()["code"] == "MIGRATION_TOO_LARGE"


async def test_state_reverse_audit_impact_and_deletion_guards(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify state audit-impact blast radius, blocking reasons, and atomic migration (KAN-29)."""
    proj_id, pref, admin, _editor, viewer, _outsider, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="STREV"
    )
    as_principal(admin)

    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    default_state = next(s for s in states if s["is_default"])
    st_from = next(s for s in states if s["group"] == "unstarted" and not s["is_default"])
    st_to = next(s for s in states if s["group"] == "started")
    st_replacement = next(s for s in states if s["group"] == "backlog")
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()

    # Seed issues in st_from
    iss_1 = await _seed_issue(
        api_env, proj_id, pref, admin.id, st_from["id"], prios[0]["id"], "Audit Issue 1"
    )
    iss_2 = await _seed_issue(
        api_env, proj_id, pref, admin.id, st_from["id"], prios[0]["id"], "Audit Issue 2"
    )

    # Add enabled hook referencing st_from -> st_to
    hook_id = uuid.uuid4()
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=b"\x00" * 32,
        from_state_id=uuid.UUID(st_from["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
    )
    hook = WorkflowTransitionHook(
        id=hook_id,
        workspace_id=admin.workspace_id,
        project_id=uuid.UUID(proj_id),
        from_state_id=uuid.UUID(st_from["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
        sort_rank="0|hzzzzz:",
        name="Security Validator",
        hook_kind="sync_validator",
        is_enabled=True,
        wasm_module_sha256=b"\x00" * 32,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=manifest_sha,
    )
    api_env.seed.add(hook)

    # Add disabled hook referencing st_from
    disabled_hook_id = uuid.uuid4()
    dis_manifest_sha = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=b"\x00" * 32,
        from_state_id=uuid.UUID(st_from["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
    )
    disabled_hook = WorkflowTransitionHook(
        id=disabled_hook_id,
        workspace_id=admin.workspace_id,
        project_id=uuid.UUID(proj_id),
        from_state_id=uuid.UUID(st_from["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
        sort_rank="0|hzzzzz:",
        name="Disabled Validator",
        hook_kind="sync_validator",
        is_enabled=False,
        wasm_module_sha256=b"\x00" * 32,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=dis_manifest_sha,
    )
    api_env.seed.add(disabled_hook)
    await api_env.seed.commit()

    # Create saved view referencing st_from and st_replacement
    v_resp = await client.post(
        f"/api/v1/projects/{pref}/views",
        json={
            "name": "Audit View",
            "layout": "board",
            "is_shared": True,
            "filters": {"state_ids": [st_from["id"], st_replacement["id"]]},
        },
    )
    assert v_resp.status_code == 201, v_resp.text
    view_id = v_resp.json()["id"]

    # 404 on audit-impact for non-existent state
    rnd_state = str(uuid.uuid4())
    assert (
        await client.get(f"/api/v1/projects/{pref}/states/{rnd_state}/audit-impact")
    ).status_code == 404

    # 1. Audit impact on default state and last state in group
    resp_def = await client.get(
        f"/api/v1/projects/{pref}/states/{default_state['id']}/audit-impact"
    )
    assert resp_def.status_code == 200
    impact_def = resp_def.json()
    assert impact_def["is_default"] is True
    assert any("Default State" in r for r in impact_def["blocking_reasons"])

    cancelled_st = next((s for s in states if s["group"] == "cancelled"), None)
    if cancelled_st:
        resp_canc = await client.get(
            f"/api/v1/projects/{pref}/states/{cancelled_st['id']}/audit-impact"
        )
        assert resp_canc.status_code == 200
        assert any("Last State in Group" in r for r in resp_canc.json()["blocking_reasons"])

    # 2. Audit impact on st_from: issues_count=2, hooks=2, saved_views=1
    resp_from = await client.get(f"/api/v1/projects/{pref}/states/{st_from['id']}/audit-impact")
    assert resp_from.status_code == 200
    impact_from = resp_from.json()
    assert impact_from["issues_count"] == 2
    assert len(impact_from["sample_issue_keys"]) == 2
    assert len(impact_from["workflow_hooks"]) == 2
    assert len(impact_from["saved_views"]) == 1
    assert impact_from["saved_views"][0]["id"] == view_id
    assert len(impact_from["valid_replacement_states"]) == len(states) - 1

    # 3. Capability check: VIEWER gets 403 on audit-impact
    as_principal(viewer)
    resp_forbidden = await client.get(
        f"/api/v1/projects/{pref}/states/{st_from['id']}/audit-impact"
    )
    assert resp_forbidden.status_code == 403
    as_principal(admin)

    # 4. Delete without replacement while active hook exists
    del_no_repl = await client.delete(f"/api/v1/projects/{pref}/states/{st_from['id']}")
    assert del_no_repl.status_code == 409
    assert del_no_repl.json()["code"] == "ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE"

    # 5. Delete with replacement but migrate_hooks=false while active hook exists
    del_no_hook_mig = await client.delete(
        f"/api/v1/projects/{pref}/states/{st_from['id']}"
        f"?replacement_state_id={st_replacement['id']}&migrate_hooks=false"
    )
    assert del_no_hook_mig.status_code == 409
    assert del_no_hook_mig.json()["code"] == "ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE"

    # 6. In-flight execution test -> 409 TRANSITION_IN_FLIGHT
    exec_id = uuid.uuid4()
    exec_row = WorkflowTransitionExecution(
        id=exec_id,
        workspace_id=admin.workspace_id,
        project_id=uuid.UUID(proj_id),
        issue_id=iss_1,
        invoking_principal_id=admin.id,
        from_state_id=uuid.UUID(st_from["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
        status="pending_async",
        hop_depth=0,
        issue_body_sha256_snapshot=b"\x00" * 32,
    )
    api_env.seed.add(exec_row)
    await api_env.seed.commit()

    # Verify In-Flight Gate in audit impact
    impact_inflight = (
        await client.get(f"/api/v1/projects/{pref}/states/{st_from['id']}/audit-impact")
    ).json()
    assert impact_inflight["pending_executions_count"] == 1
    assert any("In-Flight Gate" in r for r in impact_inflight["blocking_reasons"])

    del_inflight = await client.delete(
        f"/api/v1/projects/{pref}/states/{st_from['id']}?replacement_state_id={st_replacement['id']}"
    )
    assert del_inflight.status_code == 409
    assert del_inflight.json()["code"] == "TRANSITION_IN_FLIGHT"

    # Mark execution as approved (historical execution)
    await api_env.seed.execute(
        text("UPDATE workflow_transition_executions SET status = 'approved' WHERE id = :id"),
        {"id": exec_id},
    )
    await api_env.seed.commit()

    # Temporarily move issues and disable hook so only historical executions remain on st_from
    await api_env.seed.execute(text("SELECT set_config('app.transition_exec_id', 'bypass', true)"))
    await api_env.seed.execute(
        text("UPDATE issues SET state_id = :st WHERE state_id = :old"),
        {"st": uuid.UUID(st_replacement["id"]), "old": uuid.UUID(st_from["id"])},
    )
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET is_enabled = false WHERE id = :h"),
        {"h": hook_id},
    )
    await api_env.seed.commit()

    del_hist_block = await client.delete(f"/api/v1/projects/{pref}/states/{st_from['id']}")
    assert del_hist_block.status_code == 409
    assert del_hist_block.json()["code"] == "HISTORICAL_EXECUTIONS_REQUIRE_STATE"

    # Restore issues back to st_from for atomic migration test
    await api_env.seed.execute(text("SELECT set_config('app.transition_exec_id', 'bypass', true)"))
    await api_env.seed.execute(
        text("UPDATE issues SET state_id = :old WHERE id IN (:i1, :i2)"),
        {"old": uuid.UUID(st_from["id"]), "i1": iss_1, "i2": iss_2},
    )
    # Re-enable hook_id
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET is_enabled = true WHERE id = :h"),
        {"h": hook_id},
    )
    # Set disabled_hook to_state_id to st_replacement so migration cleanly prunes disabled self-loop
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET to_state_id = :st WHERE id = :h"),
        {"st": uuid.UUID(st_replacement["id"]), "h": disabled_hook_id},
    )
    await api_env.seed.commit()

    # 7. Self-loop prevention check -> 409 HOOK_MIGRATION_CREATES_SELF_LOOP
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET to_state_id = :st WHERE id = :h"),
        {"st": uuid.UUID(st_replacement["id"]), "h": hook_id},
    )
    await api_env.seed.commit()

    del_self_loop = await client.delete(
        f"/api/v1/projects/{pref}/states/{st_from['id']}?replacement_state_id={st_replacement['id']}"
    )
    assert del_self_loop.status_code == 409
    assert del_self_loop.json()["code"] == "HOOK_MIGRATION_CREATES_SELF_LOOP"

    # Reset hook to_state_id to st_to so it doesn't self-loop
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET to_state_id = :st WHERE id = :h"),
        {"st": uuid.UUID(st_to["id"]), "h": hook_id},
    )
    await api_env.seed.commit()

    # 8. Successful atomic delete with replacement_state_id and migrate_hooks=true
    del_ok = await client.delete(
        f"/api/v1/projects/{pref}/states/{st_from['id']}?replacement_state_id={st_replacement['id']}&migrate_hooks=true"
    )
    assert del_ok.status_code == 204

    # Verify Issue state updated
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issues WHERE id = :id AND state_id = :st",
            id=iss_1,
            st=uuid.UUID(st_replacement["id"]),
        )
        == 1
    )

    # Verify Hook from_state_id migrated and manifest recomputed
    await api_env.seed.rollback()
    hook_row = (
        await api_env.seed.execute(
            text(
                "SELECT from_state_id, to_state_id, manifest_sha256 "
                "FROM workflow_transition_hooks WHERE id = :id"
            ),
            {"id": hook_id},
        )
    ).one()
    assert hook_row[0] == uuid.UUID(st_replacement["id"])
    assert hook_row[1] == uuid.UUID(st_to["id"])
    expected_sha = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=b"\x00" * 32,
        from_state_id=uuid.UUID(st_replacement["id"]),
        to_state_id=uuid.UUID(st_to["id"]),
    )
    assert bytes(hook_row[2]) == expected_sha

    # Verify historical execution migrated
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM workflow_transition_executions "
            "WHERE id = :id AND from_state_id = :st",
            id=exec_id,
            st=uuid.UUID(st_replacement["id"]),
        )
        == 1
    )

    # Verify View filters_json deduplicated
    await api_env.seed.rollback()
    view_filters = (
        await api_env.seed.execute(
            text("SELECT filters_json FROM views WHERE id = :id"),
            {"id": uuid.UUID(view_id)},
        )
    ).scalar_one()
    assert view_filters["state_ids"] == [st_replacement["id"]]


async def test_label_reverse_audit_impact_and_safe_reassignment(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify label audit-impact and safe DELETE reassignment (KAN-29)."""
    proj_id, pref, admin, _editor, viewer, _outsider, client = await _setup_project_with_roles(
        api_env, make_user, as_principal, identifier="LBLREV"
    )
    as_principal(admin)

    states = (await client.get(f"/api/v1/projects/{pref}/states")).json()
    prios = (await client.get(f"/api/v1/projects/{pref}/priorities")).json()

    # Create 3 labels
    l_bug = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "type:bug", "color_hex": "#EF4444", "exclusive_group": "type"},
        )
    ).json()
    l_feat = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "type:feature", "color_hex": "#3B82F6", "exclusive_group": "type"},
        )
    ).json()
    l_urgent = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "urgent", "color_hex": "#F59E0B", "exclusive_group": None},
        )
    ).json()

    # Seed 3 issues
    iss_1 = await _seed_issue(
        api_env, proj_id, pref, admin.id, states[0]["id"], prios[0]["id"], "Issue 1"
    )
    iss_2 = await _seed_issue(
        api_env, proj_id, pref, admin.id, states[0]["id"], prios[0]["id"], "Issue 2"
    )
    iss_3 = await _seed_issue(
        api_env, proj_id, pref, admin.id, states[0]["id"], prios[0]["id"], "Issue 3"
    )

    # Tag Issue 1 with l_bug
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_1, "l": uuid.UUID(l_bug["id"])},
    )
    # Tag Issue 2 with l_bug and non-exclusive l_urgent
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_2, "l": uuid.UUID(l_bug["id"])},
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_2, "l": uuid.UUID(l_urgent["id"])},
    )
    # Tag Issue 3 with l_urgent AND l_feat
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_3, "l": uuid.UUID(l_urgent["id"])},
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_3, "l": uuid.UUID(l_feat["id"])},
    )
    await api_env.seed.commit()

    # Saved view referencing l_bug and l_feat
    v_resp = await client.post(
        f"/api/v1/projects/{pref}/views",
        json={
            "name": "Bugs View",
            "layout": "board",
            "is_shared": True,
            "filters": {"label_ids": [l_bug["id"], l_feat["id"]]},
        },
    )
    assert v_resp.status_code == 201, v_resp.text
    view_id = v_resp.json()["id"]

    # 1. Audit impact
    rnd_lbl = str(uuid.uuid4())
    assert (
        await client.get(f"/api/v1/projects/{pref}/labels/{rnd_lbl}/audit-impact")
    ).status_code == 404

    resp_impact = await client.get(f"/api/v1/projects/{pref}/labels/{l_bug['id']}/audit-impact")
    assert resp_impact.status_code == 200
    impact = resp_impact.json()
    assert impact["issues_count"] == 2
    assert len(impact["sample_issue_keys"]) == 2
    assert len(impact["saved_views"]) == 1
    assert impact["saved_views"][0]["id"] == view_id
    assert len(impact["valid_replacement_labels"]) == 2

    # 2. VIEWER gets 403 on audit-impact
    as_principal(viewer)
    res_403 = await client.get(f"/api/v1/projects/{pref}/labels/{l_bug['id']}/audit-impact")
    assert res_403.status_code == 403
    as_principal(admin)

    # 3. Invalid migration target -> 422
    assert (
        await client.delete(
            f"/api/v1/projects/{pref}/labels/{l_bug['id']}?replacement_label_id={l_bug['id']}"
        )
    ).status_code == 422
    assert (
        await client.delete(
            f"/api/v1/projects/{pref}/labels/{l_bug['id']}?replacement_label_id={rnd_lbl}"
        )
    ).status_code == 422

    # 4. Delete l_bug with replacement l_feat (reassignment)
    # iss_1 had l_bug -> now l_feat
    # iss_2 had l_bug and l_urgent -> now l_feat and l_urgent
    del_resp = await client.delete(
        f"/api/v1/projects/{pref}/labels/{l_bug['id']}?replacement_label_id={l_feat['id']}"
    )
    assert del_resp.status_code == 204

    # Verify iss_1 has l_feat
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_1,
            l=uuid.UUID(l_feat["id"]),
        )
        == 1
    )

    # Verify iss_2 has l_feat and l_urgent
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_2,
            l=uuid.UUID(l_feat["id"]),
        )
        == 1
    )
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_2,
            l=uuid.UUID(l_urgent["id"]),
        )
        == 1
    )

    # 5. Test PK collision avoidance: delete l_urgent with replacement l_feat
    # iss_3 already has l_feat, so l_urgent is cleanly detached without duplicate PK crash
    del_urg = await client.delete(
        f"/api/v1/projects/{pref}/labels/{l_urgent['id']}?replacement_label_id={l_feat['id']}"
    )
    assert del_urg.status_code == 204

    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_3,
            l=uuid.UUID(l_feat["id"]),
        )
        == 1
    )

    # 6. Test exclusive group conflict pruning on replacement
    l_type_extra = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "type:chore", "color_hex": "#64748B", "exclusive_group": "type"},
        )
    ).json()
    iss_4 = await _seed_issue(
        api_env, proj_id, pref, admin.id, states[0]["id"], prios[0]["id"], "Issue 4"
    )
    l_misc = (
        await client.post(
            f"/api/v1/projects/{pref}/labels",
            json={"name": "misc", "color_hex": "#64748B", "exclusive_group": None},
        )
    ).json()
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_4, "l": uuid.UUID(l_type_extra["id"])},
    )
    await api_env.seed.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:i, :l)"),
        {"i": iss_4, "l": uuid.UUID(l_misc["id"])},
    )
    await api_env.seed.commit()

    # Deleting l_misc with replacement l_feat deletes conflicting l_type_extra in group
    del_misc = await client.delete(
        f"/api/v1/projects/{pref}/labels/{l_misc['id']}?replacement_label_id={l_feat['id']}"
    )
    assert del_misc.status_code == 204
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_4,
            l=uuid.UUID(l_feat["id"]),
        )
        == 1
    )
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM issue_labels WHERE issue_id = :id AND label_id = :l",
            id=iss_4,
            l=uuid.UUID(l_type_extra["id"]),
        )
        == 0
    )

    # 7. Delete label without replacement_label_id (clean detach)
    del_detach = await client.delete(f"/api/v1/projects/{pref}/labels/{l_type_extra['id']}")
    assert del_detach.status_code == 204

    # Verify View deduplication
    await api_env.seed.rollback()
    view_filters = (
        await api_env.seed.execute(
            text("SELECT filters_json FROM views WHERE id = :id"),
            {"id": uuid.UUID(view_id)},
        )
    ).scalar_one()
    assert view_filters["label_ids"] == [l_feat["id"]]

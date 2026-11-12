# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Project configuration API tests: workflow states, priorities & labels (KB-P3-01b)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.tests.security.helpers import add_role_binding, rebuild_era

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
            "priority_id, created_by_id, original_created_by_id, board_rank) "
            "SELECT o.id, :ws, :p, (1000 + i), 'Bulk ' || i, :st, :pr, "
            ":creator, :creator, '0|hzzzzz:' "
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

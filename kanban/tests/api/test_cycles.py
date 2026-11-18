# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Cycles API unit and integration tests (S7.2 8g, S11.4).

Covers all mandatory feature test cases:
    1. Positive CRUD: create (201), Location, GET (200), PATCH (200), list with ?status= filter
    2. Status transitions: upcoming -> active (start/activate), 409 ACTIVE_CYCLE_EXISTS, 409 invalid
    3. Completed immutability: completed cannot be patched or deleted (409), upcoming deletion (204)
    4. Rollover: unfinished issues roll over to target cycle or null; activity events recorded
    5. Rollover error handling: self target, other project, completed target, 409 ROLLOVER_TOO_LARGE
    6. Issue membership: PUT to cycle, at-most-one active/upcoming rule (409), DELETE (204)
    7. Security & permissions: non-admin write (403), non-viewer read (404)
    8. Boundaries & feature toggle: end_date == start_date, end_date < start_date (422)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from database.models import WorkflowState
from kanban.services.cycles import set_project_cycles_enabled

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


async def test_case_1_positive_crud_and_status_filtering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive create (201), Location, GET (200), PATCH (200), and list filtering."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("CYC1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create upcoming cycle (201)
    create_payload = {
        "name": "Sprint 1",
        "start_date": "2026-11-15",
        "end_date": "2026-11-29",
    }
    resp = await client.post("/api/v1/projects/CYC1/cycles", json=create_payload)
    contract_recorder.record("create_cycle_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    cycle_id = body["id"]
    assert resp.headers["Location"] == f"/api/v1/cycles/{cycle_id}"
    assert body["name"] == "Sprint 1"
    assert body["status"] == "upcoming"
    assert body["start_date"] == "2026-11-15"
    assert body["end_date"] == "2026-11-29"
    assert body["issue_count"] == 0
    assert body["completed_count"] == 0

    # Verify CYCLE_CREATED activity record
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'CYCLE_CREATED'",
            obj=cycle_id,
        )
        == 1
    )

    # 2. GET cycle (200)
    get_resp = await client.get(f"/api/v1/cycles/{cycle_id}")
    contract_recorder.record("get_cycle_200", get_resp.request, get_resp)
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["id"] == cycle_id

    # 3. PATCH cycle (200)
    patch_payload = {
        "name": "Sprint 1 Hardened",
        "start_date": "2026-11-16",
        "end_date": "2026-11-30",
    }
    patch_resp = await client.patch(f"/api/v1/cycles/{cycle_id}", json=patch_payload)
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["name"] == "Sprint 1 Hardened"
    assert patched["start_date"] == "2026-11-16"
    assert patched["end_date"] == "2026-11-30"

    # Verify CYCLE_UPDATED activity record
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'CYCLE_UPDATED'",
            obj=cycle_id,
        )
        == 1
    )

    # 4. List cycles for project
    list_resp = await client.get("/api/v1/projects/CYC1/cycles")
    assert list_resp.status_code == 200, list_resp.text
    cycles = list_resp.json()
    assert len(cycles) == 1
    assert cycles[0]["id"] == cycle_id

    # 5. Filter by status
    up_resp = await client.get("/api/v1/projects/CYC1/cycles?status=upcoming")
    assert up_resp.status_code == 200
    assert len(up_resp.json()) == 1

    act_resp = await client.get("/api/v1/projects/CYC1/cycles?status=active")
    assert act_resp.status_code == 200
    assert len(act_resp.json()) == 0

    # 6. List by project UUID
    uuid_list_resp = await client.get(f"/api/v1/projects/{proj_id}/cycles")
    assert uuid_list_resp.status_code == 200
    assert len(uuid_list_resp.json()) == 1

    # 7. Invalid status filter -> 422
    inv_resp = await client.get("/api/v1/projects/CYC1/cycles?status=invalid_status")
    assert inv_resp.status_code == 422, inv_resp.text

    # 8. Burndown (200)
    bd_resp = await client.get(f"/api/v1/cycles/{cycle_id}/burndown")
    contract_recorder.record("burndown_200", bd_resp.request, bd_resp)
    assert bd_resp.status_code == 200, bd_resp.text
    assert bd_resp.json()["cycle_id"] == cycle_id


async def test_case_2_status_transitions_and_concurrency(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: upcoming -> active transitions, one-active constraint, invalid transitions."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("CYC2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create two upcoming cycles
    c1 = (await client.post("/api/v1/projects/CYC2/cycles", json={"name": "Cycle Alpha"})).json()
    c2 = (await client.post("/api/v1/projects/CYC2/cycles", json={"name": "Cycle Beta"})).json()

    # 1. Start C1: upcoming -> active (200)
    start_resp = await client.post(f"/api/v1/cycles/{c1['id']}/start")
    contract_recorder.record("start_cycle_200", start_resp.request, start_resp)
    assert start_resp.status_code == 200, start_resp.text
    assert start_resp.json()["status"] == "active"

    # Verify CYCLE_STATUS_CHANGED and CYCLE_ACTIVATED
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'CYCLE_STATUS_CHANGED'",
            obj=c1["id"],
        )
        == 1
    )
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'CYCLE_ACTIVATED'",
            obj=c1["id"],
        )
        == 1
    )

    # 2. Attempt starting C2 while C1 is active -> 409 ACTIVE_CYCLE_EXISTS
    c2_start = await client.post(f"/api/v1/cycles/{c2['id']}/start")
    contract_recorder.record("active_cycle_exists_409", c2_start.request, c2_start)
    assert c2_start.status_code == 409, c2_start.text
    assert c2_start.json()["code"] == "ACTIVE_CYCLE_EXISTS"

    # Test /activate alias also enforces the constraint
    c2_act = await client.post(f"/api/v1/cycles/{c2['id']}/activate")
    assert c2_act.status_code == 409, c2_act.text
    assert c2_act.json()["code"] == "ACTIVE_CYCLE_EXISTS"

    # 3. Invalid transition: start already active cycle -> 409 INVALID_CYCLE_TRANSITION
    c1_restart = await client.post(f"/api/v1/cycles/{c1['id']}/start")
    assert c1_restart.status_code == 409, c1_restart.text
    assert c1_restart.json()["code"] == "INVALID_CYCLE_TRANSITION"

    # 4. Invalid transition: complete upcoming cycle -> 409 INVALID_CYCLE_TRANSITION
    c2_complete = await client.post(f"/api/v1/cycles/{c2['id']}/complete", json={})
    assert c2_complete.status_code == 409, c2_complete.text
    assert c2_complete.json()["code"] == "INVALID_CYCLE_TRANSITION"


async def test_case_3_completed_immutability_and_delete(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 3: Completed cycles are immutable (PATCH/DELETE 409), non-completed delete (204)."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("CYC3", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    c1 = (await client.post("/api/v1/projects/CYC3/cycles", json={"name": "Sprint Finish"})).json()
    await client.post(f"/api/v1/cycles/{c1['id']}/start")

    # Complete C1
    comp_resp = await client.post(f"/api/v1/cycles/{c1['id']}/complete", json={})
    assert comp_resp.status_code == 200, comp_resp.text
    assert comp_resp.json()["cycle"]["status"] == "completed"

    # Completed cycle cannot be started or completed again
    re_start = await client.post(f"/api/v1/cycles/{c1['id']}/start")
    assert re_start.status_code == 409
    assert re_start.json()["code"] == "INVALID_CYCLE_TRANSITION"

    re_comp = await client.post(f"/api/v1/cycles/{c1['id']}/complete", json={})
    assert re_comp.status_code == 409
    assert re_comp.json()["code"] == "INVALID_CYCLE_TRANSITION"

    # Completed cycle cannot be patched -> 409 CYCLE_COMPLETED
    patch_resp = await client.patch(f"/api/v1/cycles/{c1['id']}", json={"name": "New Name"})
    assert patch_resp.status_code == 409, patch_resp.text
    assert patch_resp.json()["code"] == "CYCLE_COMPLETED"

    # Completed cycle cannot be deleted -> 409 CYCLE_COMPLETED
    del_resp = await client.delete(f"/api/v1/cycles/{c1['id']}")
    assert del_resp.status_code == 409, del_resp.text
    assert del_resp.json()["code"] == "CYCLE_COMPLETED"

    # Create upcoming cycle and delete it -> 204
    c2 = (await client.post("/api/v1/projects/CYC3/cycles", json={"name": "To Delete"})).json()
    del_ok = await client.delete(f"/api/v1/cycles/{c2['id']}")
    assert del_ok.status_code == 204, del_ok.text

    # Verify CYCLE_DELETED activity
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'CYCLE_DELETED'",
            obj=c2["id"],
        )
        == 1
    )

    # GET deleted cycle -> 404
    get_del = await client.get(f"/api/v1/cycles/{c2['id']}")
    assert get_del.status_code == 404


async def test_case_4_rollover_on_complete(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: Rollover moves unfinished issues to target cycle, leaving completed intact."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("ROLL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create C1 (active) and C2 (upcoming)
    c1 = (await client.post("/api/v1/projects/ROLL/cycles", json={"name": "Cycle 1"})).json()
    c2 = (await client.post("/api/v1/projects/ROLL/cycles", json={"name": "Cycle 2"})).json()
    await client.post(f"/api/v1/cycles/{c1['id']}/start")

    # Find the "Done" workflow state id
    states_stmt = select(WorkflowState).where(
        WorkflowState.project_id == proj_id,
        WorkflowState.state_group == "completed",
    )
    done_state = (await api_env.seed.execute(states_stmt)).scalars().first()
    assert done_state is not None

    # Create 5 issues
    issue_ids: list[str] = []
    for i in range(1, 6):
        resp = await client.post(
            "/api/v1/projects/ROLL/issues",
            json={"summary": f"Issue {i} in sprint"},
        )
        assert resp.status_code == 201
        issue_ids.append(resp.json()["id"])

    # Mark issues 4 and 5 as Done
    await api_env.seed.execute(text("SELECT set_config('app.transition_exec_id', 'bypass', true)"))
    await api_env.seed.execute(
        text("UPDATE issues SET state_id = :st WHERE id IN (:id4, :id5)"),
        {"st": done_state.id, "id4": issue_ids[3], "id5": issue_ids[4]},
    )
    await api_env.seed.commit()

    # Assign all 5 issues to C1
    for key in ["ROLL-1", "ROLL-2", "ROLL-3", "ROLL-4", "ROLL-5"]:
        put_resp = await client.put(f"/api/v1/cycles/{c1['id']}/issues/{key}")
        assert put_resp.status_code == 200, put_resp.text

    # Verify counts on C1: 5 total, 2 completed
    c1_check = (await client.get(f"/api/v1/cycles/{c1['id']}")).json()
    assert c1_check["issue_count"] == 5
    assert c1_check["completed_count"] == 2

    # Complete C1 with rollover to C2
    comp_resp = await client.post(
        f"/api/v1/cycles/{c1['id']}/complete",
        json={"rollover_to_cycle_id": c2["id"]},
    )
    contract_recorder.record("complete_cycle_rollover_200", comp_resp.request, comp_resp)
    assert comp_resp.status_code == 200, comp_resp.text
    comp_body = comp_resp.json()
    assert comp_body["cycle"]["status"] == "completed"
    assert comp_body["rolled_over"] == 3
    assert comp_body["rollover_to_cycle_id"] == c2["id"]

    # Verify DB: issues 1, 2, 3 now belong to C2; issues 4, 5 still belong to C1
    await api_env.seed.rollback()
    c2_issues = (
        (
            await api_env.seed.execute(
                text("SELECT id FROM issues WHERE cycle_id = :cid"),
                {"cid": c2["id"]},
            )
        )
        .scalars()
        .all()
    )
    assert len(c2_issues) == 3

    c1_issues = (
        (
            await api_env.seed.execute(
                text("SELECT id FROM issues WHERE cycle_id = :cid"),
                {"cid": c1["id"]},
            )
        )
        .scalars()
        .all()
    )
    assert len(c1_issues) == 2

    # Verify ISSUE_FIELD_CHANGED activity records with reason="rollover"
    rollover_events = (
        await api_env.seed.execute(
            text(
                "SELECT count(*) FROM activity_records "
                "WHERE event_type = 'ISSUE_FIELD_CHANGED' "
                "  AND payload->>'reason' = 'rollover'"
            )
        )
    ).scalar_one()
    assert rollover_events == 3

    # Null rollover: complete C2 without target -> clears cycle_id
    await client.post(f"/api/v1/cycles/{c2['id']}/start")
    null_comp = await client.post(
        f"/api/v1/cycles/{c2['id']}/complete",
        json={"rollover_to_cycle_id": None},
    )
    assert null_comp.status_code == 200, null_comp.text
    assert null_comp.json()["rolled_over"] == 3
    assert null_comp.json()["rollover_to_cycle_id"] is None

    # Verify cycle_id became NULL
    await api_env.seed.rollback()
    cleared_count = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE id = ANY(:ids) AND cycle_id IS NULL"),
            {"ids": [uuid.UUID(i) for i in issue_ids[:3]]},
        )
    ).scalar_one()
    assert cleared_count == 3


async def test_case_5_rollover_error_handling(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Rollover validations (self target, other project, completed, ROLLOVER_TOO_LARGE)."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("ROL1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    _ = await make_project("ROL2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    c1 = (await client.post("/api/v1/projects/ROL1/cycles", json={"name": "C1"})).json()
    c2 = (await client.post("/api/v1/projects/ROL1/cycles", json={"name": "C2"})).json()
    c_other = (await client.post("/api/v1/projects/ROL2/cycles", json={"name": "C Other"})).json()
    await client.post(f"/api/v1/cycles/{c1['id']}/start")

    # 1. Target is self -> 422
    self_resp = await client.post(
        f"/api/v1/cycles/{c1['id']}/complete",
        json={"rollover_to_cycle_id": c1["id"]},
    )
    assert self_resp.status_code == 422
    assert self_resp.json()["code"] == "ROLLOVER_TARGET_INVALID"

    # 2. Target not found -> 422
    rand_uuid = str(uuid.uuid4())
    nf_resp = await client.post(
        f"/api/v1/cycles/{c1['id']}/complete",
        json={"rollover_to_cycle_id": rand_uuid},
    )
    assert nf_resp.status_code == 422
    assert nf_resp.json()["code"] == "ROLLOVER_TARGET_INVALID"

    # 3. Target in different project -> 422
    diff_resp = await client.post(
        f"/api/v1/cycles/{c1['id']}/complete",
        json={"rollover_to_cycle_id": c_other["id"]},
    )
    assert diff_resp.status_code == 422
    assert diff_resp.json()["code"] == "ROLLOVER_TARGET_INVALID"

    # 4. Target is already completed -> 422
    # Complete C1 so it is completed
    await client.post(f"/api/v1/cycles/{c1['id']}/complete", json={})
    # Start C2 now that C1 is completed
    await client.post(f"/api/v1/cycles/{c2['id']}/start")
    comp_target = await client.post(
        f"/api/v1/cycles/{c2['id']}/complete",
        json={"rollover_to_cycle_id": c1["id"]},
    )
    assert comp_target.status_code == 422
    assert comp_target.json()["code"] == "ROLLOVER_TARGET_INVALID"

    # 5. Rollover too large (> 1000 issues) -> 409 ROLLOVER_TOO_LARGE
    # Use patch to set MAX_ROLLOVER_ISSUES to 0 for boundary verification
    with patch("kanban.services.cycles.MAX_ROLLOVER_ISSUES", 0):
        # Create 1 issue in C2
        iss = (
            await client.post("/api/v1/projects/ROL1/issues", json={"summary": "Large issue"})
        ).json()
        await client.put(f"/api/v1/cycles/{c2['id']}/issues/{iss['key']}")

        large_resp = await client.post(
            f"/api/v1/cycles/{c2['id']}/complete",
            json={"rollover_to_cycle_id": None},
        )
        assert large_resp.status_code == 409
        assert large_resp.json()["code"] == "ROLLOVER_TOO_LARGE"


async def test_case_6_issue_membership_put_and_delete(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: Issue cycle membership PUT and DELETE, at-most-one active/upcoming constraint."""
    admin = await make_user("admin6", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("MEMB", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    _ = await make_project("MEM2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    c1 = (await client.post("/api/v1/projects/MEMB/cycles", json={"name": "Sprint Alpha"})).json()
    c2 = (await client.post("/api/v1/projects/MEMB/cycles", json={"name": "Sprint Beta"})).json()
    c_other = (
        await client.post("/api/v1/projects/MEM2/cycles", json={"name": "Sprint Other"})
    ).json()

    # Create issue in MEMB
    issue = (
        await client.post("/api/v1/projects/MEMB/issues", json={"summary": "Cycle Issue"})
    ).json()

    # 1. Assign to C1 -> 200
    put_resp = await client.put(f"/api/v1/cycles/{c1['id']}/issues/{issue['key']}")
    assert put_resp.status_code == 200, put_resp.text

    # Verify ISSUE_CYCLE_CHANGED emitted
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :obj"
            " AND event_type = 'ISSUE_CYCLE_CHANGED'",
            obj=issue["id"],
        )
        == 1
    )

    # 2. Attempt assigning to C2 while already in C1 -> 409 ISSUE_IN_ANOTHER_CYCLE
    put_again = await client.put(f"/api/v1/cycles/{c2['id']}/issues/{issue['key']}")
    assert put_again.status_code == 409, put_again.text
    assert put_again.json()["code"] == "ISSUE_IN_ANOTHER_CYCLE"

    # 3. Project mismatch -> 422 PROJECT_MISMATCH
    put_mismatch = await client.put(f"/api/v1/cycles/{c_other['id']}/issues/{issue['key']}")
    assert put_mismatch.status_code == 422, put_mismatch.text
    assert put_mismatch.json()["code"] == "PROJECT_MISMATCH"

    # 4. Remove issue from C1 -> 204
    del_resp = await client.delete(f"/api/v1/cycles/{c1['id']}/issues/{issue['key']}")
    assert del_resp.status_code == 204, del_resp.text

    # 5. Remove issue not in cycle -> 404
    del_again = await client.delete(f"/api/v1/cycles/{c1['id']}/issues/{issue['key']}")
    assert del_again.status_code == 404, del_again.text


async def test_case_7_security_permissions(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 7: Project-level role enforcement: member write (403), non-viewer read (404)."""
    admin = await make_user("admin7", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member7")
    viewer = await make_user("viewer7")
    outsider = await make_user("outsider7")
    _ = await make_project(
        "SEC1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", viewer: "VIEWER"},
    )

    admin_client = as_principal(admin)
    c1 = (
        await admin_client.post("/api/v1/projects/SEC1/cycles", json={"name": "Sec Sprint"})
    ).json()

    # Viewer (VIEW only, lacks EDIT) attempts write operations -> 403 with descriptive detail
    viewer_client = as_principal(viewer)
    post_403 = await viewer_client.post(
        "/api/v1/projects/SEC1/cycles",
        json={"name": "Viewer Sprint"},
    )
    contract_recorder.record("forbidden_403", post_403.request, post_403)
    assert post_403.status_code == 403, post_403.text
    assert post_403.json()["code"] == "INSUFFICIENT_CAPABILITY"
    assert (
        "Missing required capability: EDIT (requires Project Member, Project Admin, "
        "Workspace Admin, or Server Admin role)." in post_403.json()["detail"]
    )

    patch_403 = await viewer_client.patch(
        f"/api/v1/cycles/{c1['id']}",
        json={"name": "Hacked"},
    )
    assert patch_403.status_code == 403
    assert patch_403.json()["code"] == "INSUFFICIENT_CAPABILITY"

    start_403 = await viewer_client.post(f"/api/v1/cycles/{c1['id']}/start")
    assert start_403.status_code == 403

    comp_403 = await viewer_client.post(f"/api/v1/cycles/{c1['id']}/complete", json={})
    assert comp_403.status_code == 403

    del_403 = await viewer_client.delete(f"/api/v1/cycles/{c1['id']}")
    assert del_403.status_code == 403

    # Member (EDIT capability) can create and update cycles
    member_client = as_principal(member)
    post_member = await member_client.post(
        "/api/v1/projects/SEC1/cycles",
        json={"name": "Member Sprint"},
    )
    assert post_member.status_code == 201, post_member.text

    patch_member = await member_client.patch(
        f"/api/v1/cycles/{c1['id']}",
        json={"name": "Sec Sprint Updated"},
    )
    assert patch_member.status_code == 200, patch_member.text

    # But member cannot delete (requires ADMIN) -> 403 with ADMIN detail
    del_member_403 = await member_client.delete(f"/api/v1/cycles/{c1['id']}")
    assert del_member_403.status_code == 403
    assert del_member_403.json()["code"] == "INSUFFICIENT_CAPABILITY"
    assert (
        "Missing required capability: ADMIN (requires Project Admin, "
        "Workspace Admin, or Server Admin role)." in del_member_403.json()["detail"]
    )

    # Outsider (no project access) attempts GET -> 404
    outsider_client = as_principal(outsider)
    get_404 = await outsider_client.get(f"/api/v1/cycles/{c1['id']}")
    contract_recorder.record("not_found_404", get_404.request, get_404)
    assert get_404.status_code == 404, get_404.text

    list_404 = await outsider_client.get("/api/v1/projects/SEC1/cycles")
    assert list_404.status_code == 404


async def test_case_8_boundaries_and_feature_toggle(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 8: Boundaries (end_date == start_date vs < start_date) and cycles_enabled toggle."""
    admin = await make_user("admin8", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BND1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. end_date == start_date is valid -> 201
    eq_resp = await client.post(
        "/api/v1/projects/BND1/cycles",
        json={"name": "Single Day", "start_date": "2026-11-20", "end_date": "2026-11-20"},
    )
    assert eq_resp.status_code == 201, eq_resp.text

    # 2. end_date < start_date on create -> 422 DATE_ORDER
    inv_post = await client.post(
        "/api/v1/projects/BND1/cycles",
        json={"name": "Backwards", "start_date": "2026-11-20", "end_date": "2026-11-19"},
    )
    assert inv_post.status_code == 422, inv_post.text
    assert inv_post.json()["code"] == "DATE_ORDER"

    # 3. end_date < start_date on patch -> 422 DATE_ORDER
    cid = eq_resp.json()["id"]
    inv_patch = await client.patch(
        f"/api/v1/cycles/{cid}",
        json={"end_date": "2026-11-10"},
    )
    assert inv_patch.status_code == 422, inv_patch.text
    assert inv_patch.json()["code"] == "DATE_ORDER"

    # 4. Feature toggle: set project cycles_enabled = False
    set_project_cycles_enabled(proj_id, enabled=False)
    try:
        # All cycle routes now return 404 FEATURE_DISABLED
        assert (await client.get("/api/v1/projects/BND1/cycles")).status_code == 404
        assert (
            await client.post("/api/v1/projects/BND1/cycles", json={"name": "New"})
        ).status_code == 404
        assert (await client.get(f"/api/v1/cycles/{cid}")).status_code == 404
        patch_dis = await client.patch(f"/api/v1/cycles/{cid}", json={"name": "Patch"})
        assert patch_dis.status_code == 404
        assert (await client.post(f"/api/v1/cycles/{cid}/start")).status_code == 404
        assert (await client.post(f"/api/v1/cycles/{cid}/complete", json={})).status_code == 404
        assert (await client.delete(f"/api/v1/cycles/{cid}")).status_code == 404
        assert (await client.get(f"/api/v1/cycles/{cid}/burndown")).status_code == 404
    finally:
        set_project_cycles_enabled(proj_id, enabled=True)


async def test_case_9_not_found_branches_and_conflicts(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 9: 404 on nonexistent objects, 409 CYCLE_CONFLICT on overlapping dates, no-op."""
    admin = await make_user("admin9", workspace_role="WORKSPACE_ADMIN")
    await make_project("CONF", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    rand_uuid = str(uuid.uuid4())

    # 1. Nonexistent project / cycle 404s
    assert (await client.get("/api/v1/projects/NO_SUCH_PROJ/cycles")).status_code == 404
    assert (
        await client.post("/api/v1/projects/NO_SUCH_PROJ/cycles", json={"name": "X"})
    ).status_code == 404
    assert (await client.get(f"/api/v1/cycles/{rand_uuid}")).status_code == 404
    patch_rand = await client.patch(f"/api/v1/cycles/{rand_uuid}", json={"name": "X"})
    assert patch_rand.status_code == 404
    assert (await client.post(f"/api/v1/cycles/{rand_uuid}/start")).status_code == 404
    assert (await client.post(f"/api/v1/cycles/{rand_uuid}/complete", json={})).status_code == 404
    assert (await client.delete(f"/api/v1/cycles/{rand_uuid}")).status_code == 404
    assert (await client.put(f"/api/v1/cycles/{rand_uuid}/issues/CONF-1")).status_code == 404
    assert (await client.delete(f"/api/v1/cycles/{rand_uuid}/issues/CONF-1")).status_code == 404

    # 2. GIST exclusion constraint: overlapping cycles in same project -> 409 CYCLE_CONFLICT
    c1 = (
        await client.post(
            "/api/v1/projects/CONF/cycles",
            json={"name": "C1", "start_date": "2026-11-01", "end_date": "2026-11-15"},
        )
    ).json()

    c_overlap = await client.post(
        "/api/v1/projects/CONF/cycles",
        json={"name": "C Overlap", "start_date": "2026-11-10", "end_date": "2026-11-20"},
    )
    assert c_overlap.status_code == 409, c_overlap.text
    assert c_overlap.json()["code"] == "CYCLE_CONFLICT"

    # Non-overlapping cycle
    c2 = (
        await client.post(
            "/api/v1/projects/CONF/cycles",
            json={"name": "C2", "start_date": "2026-11-16", "end_date": "2026-11-30"},
        )
    ).json()

    # Patch C2 to overlap with C1 -> 409 CYCLE_CONFLICT
    patch_overlap = await client.patch(
        f"/api/v1/cycles/{c2['id']}",
        json={"start_date": "2026-11-05"},
    )
    assert patch_overlap.status_code == 409, patch_overlap.text
    assert patch_overlap.json()["code"] == "CYCLE_CONFLICT"

    # 3. No-op patch (empty payload or identical values) -> 200, zero new activity
    act_before = await _count(
        api_env,
        "SELECT count(*) FROM activity_records "
        "WHERE object_id = :obj AND event_type = 'CYCLE_UPDATED'",
        obj=c1["id"],
    )
    noop_resp = await client.patch(f"/api/v1/cycles/{c1['id']}", json={})
    assert noop_resp.status_code == 200
    act_after = await _count(
        api_env,
        "SELECT count(*) FROM activity_records "
        "WHERE object_id = :obj AND event_type = 'CYCLE_UPDATED'",
        obj=c1["id"],
    )
    assert act_before == act_after

    # 4. Assign an issue previously in a completed cycle to an upcoming cycle -> 200
    # Complete C1
    await client.post(f"/api/v1/cycles/{c1['id']}/start")
    iss = (
        await client.post("/api/v1/projects/CONF/issues", json={"summary": "Reassign issue"})
    ).json()
    await client.put(f"/api/v1/cycles/{c1['id']}/issues/{iss['key']}")
    await client.post(f"/api/v1/cycles/{c1['id']}/complete", json={})

    # Now assign to C2 (upcoming) -> succeeds because C1 is completed
    reassign_resp = await client.put(f"/api/v1/cycles/{c2['id']}/issues/{iss['key']}")
    assert reassign_resp.status_code == 200, reassign_resp.text

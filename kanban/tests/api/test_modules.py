# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Module API test suite: CRUD, feature flag 404, issue assignments and limits (KB-P3-10b)."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.services import modules as svc

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count_activity(env: ApiEnv, obj_id: uuid.UUID, event_type: str) -> int:
    """Return count of activity records matching object_id and event_type."""
    await env.seed.rollback()
    res = await env.seed.execute(
        text("SELECT COUNT(*) FROM activity_records WHERE object_id = :obj AND event_type = :evt"),
        {"obj": obj_id, "evt": event_type},
    )
    return int(res.scalar_one())


async def _get_activity_payload(
    env: ApiEnv, obj_id: uuid.UUID, event_type: str
) -> dict[str, object] | None:
    """Return payload of latest activity record matching object_id and event_type."""
    await env.seed.rollback()
    row = (
        await env.seed.execute(
            text(
                "SELECT payload FROM activity_records "
                "WHERE object_id = :obj AND event_type = :evt "
                "ORDER BY recorded_at DESC LIMIT 1"
            ),
            {"obj": obj_id, "evt": event_type},
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if isinstance(row, str):
        return json.loads(row)  # type: ignore[no-any-return]
    return row  # type: ignore[no-any-return]


async def test_case_1_positive_module_lifecycle_and_assignment(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive create module 201, assign to issue 200, list shows issue_count: 1."""
    admin = await make_user("projadmin", workspace_role="WORKSPACE_ADMIN")
    lead_user = await make_user("leaduser")
    proj_id = await make_project(
        "MOD1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", lead_user: "VIEWER"},
        modules_enabled=True,
    )
    client = as_principal(admin)

    # 1. Create module (status 201)
    create_payload = {
        "name": "Auth Core",
        "description_markdown": "# Authentication\nCore identity and tokens.",
        "lead_principal_id": str(lead_user.id),
        "status": "in_progress",
        "start_date": "2026-11-01",
        "target_date": "2026-11-30",
    }
    r_create = await client.post("/api/v1/projects/MOD1/modules", json=create_payload)
    contract_recorder.record("module_create_201", r_create.request, r_create)
    assert r_create.status_code == 201, r_create.text
    mod_data = r_create.json()
    module_id = uuid.UUID(mod_data["id"])
    assert r_create.headers["Location"] == f"/api/v1/modules/{module_id}"
    assert mod_data["name"] == "Auth Core"
    assert mod_data["status"] == "in_progress"
    assert mod_data["lead"] is not None
    assert mod_data["lead"]["id"] == str(lead_user.id)
    assert mod_data["lead"]["handle"] in ("leaduser", "@leaduser")
    assert mod_data["issue_count"] == 0
    assert mod_data["completed_count"] == 0

    # Verify MODULE_CREATED activity written
    created_count = await _count_activity(api_env, module_id, "MODULE_CREATED")
    assert created_count >= 1

    # 2. Create an issue in this project
    r_issue = await client.post(
        "/api/v1/projects/MOD1/issues",
        json={"summary": "Implement OAuth endpoints"},
    )
    assert r_issue.status_code == 201, r_issue.text
    issue_data = r_issue.json()
    issue_key = issue_data["key"]
    issue_id = uuid.UUID(issue_data["id"])

    # 3. Assign module to issue (PUT status 200)
    assign_payload = {"module_ids": [str(module_id)]}
    r_assign = await client.put(f"/api/v1/issues/{issue_key}/modules", json=assign_payload)
    contract_recorder.record("issue_assign_200", r_assign.request, r_assign)
    assert r_assign.status_code == 200, r_assign.text
    assert r_assign.json()["module_ids"] == [str(module_id)]

    # Verify ISSUE_MODULES_CHANGED activity written against the issue
    chg_count = await _count_activity(api_env, issue_id, "ISSUE_MODULES_CHANGED")
    assert chg_count >= 1
    chg_payload = await _get_activity_payload(api_env, issue_id, "ISSUE_MODULES_CHANGED")
    assert chg_payload is not None
    added_items = chg_payload.get("added")
    assert isinstance(added_items, list)
    assert str(module_id) in added_items

    # 4. List modules: verify issue_count == 1
    r_list = await client.get("/api/v1/projects/MOD1/modules")
    assert r_list.status_code == 200, r_list.text
    items = r_list.json()
    assert len(items) == 1
    assert items[0]["id"] == str(module_id)
    assert items[0]["issue_count"] == 1
    assert items[0]["completed_count"] == 0

    # 5. Fetch single module: GET /api/v1/modules/{module_id}
    r_get = await client.get(f"/api/v1/modules/{module_id}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["issue_count"] == 1

    # 6. Verify completed_count increments when issue transitions to completed
    # Fetch completed workflow state
    completed_state_id = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :p AND state_group = 'completed' LIMIT 1"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    r_patch_issue = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"state_id": str(completed_state_id)},
    )
    assert r_patch_issue.status_code == 200, r_patch_issue.text

    # Re-check module: completed_count is now 1
    r_get_completed = await client.get(f"/api/v1/modules/{module_id}")
    assert r_get_completed.status_code == 200
    assert r_get_completed.json()["completed_count"] == 1


async def test_case_2_feature_flag_modules_disabled(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    make_module: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Feature flag modules_enabled=false returns 404 MODULES_DISABLED for viewer."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer2")
    proj_id = await make_project(
        "DIS1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", viewer: "VIEWER"},
        modules_enabled=False,
    )
    # Seed a module directly in DB for testing module-id routes
    mod_id = await make_module(proj_id, "Disabled Mod", created_by=admin)

    # Seed an issue directly
    client_admin = as_principal(admin)
    r_issue = await client_admin.post(
        "/api/v1/projects/DIS1/issues",
        json={"summary": "Issue in disabled project"},
    )
    assert r_issue.status_code == 201, r_issue.text
    issue_key = r_issue.json()["key"]

    client_viewer = as_principal(viewer)

    # Test all endpoints return 404 MODULES_DISABLED
    # 1. GET /api/v1/projects/{ref}/modules
    r1 = await client_viewer.get("/api/v1/projects/DIS1/modules")
    contract_recorder.record("modules_disabled_404", r1.request, r1)
    assert r1.status_code == 404, r1.text
    b1 = r1.json()
    assert b1["code"] == "MODULES_DISABLED"
    assert b1["status"] == 404
    assert b1["title"] == "Not Found"

    # 2. POST /api/v1/projects/{ref}/modules (as admin with ADMIN cap)
    r2 = await client_admin.post(
        "/api/v1/projects/DIS1/modules",
        json={"name": "Will Fail"},
    )
    assert r2.status_code == 404, r2.text
    assert r2.json()["code"] == "MODULES_DISABLED"

    # 3. GET /api/v1/modules/{module_id}
    r3 = await client_viewer.get(f"/api/v1/modules/{mod_id}")
    assert r3.status_code == 404, r3.text
    assert r3.json()["code"] == "MODULES_DISABLED"

    # 4. PATCH /api/v1/modules/{module_id}
    r4 = await client_admin.patch(
        f"/api/v1/modules/{mod_id}",
        json={"name": "Updated Name"},
    )
    assert r4.status_code == 404, r4.text
    assert r4.json()["code"] == "MODULES_DISABLED"

    # 5. DELETE /api/v1/modules/{module_id}
    r5 = await client_admin.delete(f"/api/v1/modules/{mod_id}")
    assert r5.status_code == 404, r5.text
    assert r5.json()["code"] == "MODULES_DISABLED"

    # 6. PUT /api/v1/issues/{ref}/modules
    r6 = await client_admin.put(
        f"/api/v1/issues/{issue_key}/modules",
        json={"module_ids": [str(mod_id)]},
    )
    assert r6.status_code == 404, r6.text
    assert r6.json()["code"] == "MODULES_DISABLED"

    # Granular issue-module endpoints
    r7 = await client_admin.put(f"/api/v1/modules/{mod_id}/issues/{issue_key}")
    assert r7.status_code == 404, r7.text
    assert r7.json()["code"] == "MODULES_DISABLED"

    r8 = await client_admin.delete(f"/api/v1/modules/{mod_id}/issues/{issue_key}")
    assert r8.status_code == 404, r8.text
    assert r8.json()["code"] == "MODULES_DISABLED"

    # Verify issue GET response completely omits the module_ids key
    r_get_issue = await client_viewer.get(f"/api/v1/issues/{issue_key}")
    assert r_get_issue.status_code == 200, r_get_issue.text
    assert "module_ids" not in r_get_issue.json()


async def test_case_3_security_anti_enumeration_and_rbac(  # noqa: PLR0913, PLR0917, PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    make_module: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Non-viewer receives plain 404 NOT_FOUND; member create 403; lead 422."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member3")
    outsider = await make_user("outsider3")
    inactive_user = await make_user("inactive3")

    proj_id = await make_project(
        "SEC1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
        modules_enabled=True,
    )
    mod_id = await make_module(proj_id, "Security Mod", created_by=admin)

    # Deactivate inactive_user
    await api_env.seed.execute(
        text("UPDATE principals SET status = 'DISABLED' WHERE id = :u"),
        {"u": inactive_user.id},
    )
    await api_env.seed.commit()

    # 1. Non-viewer receives plain 404 without code: MODULES_DISABLED
    client_outsider = as_principal(outsider)
    r_unreadable = await client_outsider.get("/api/v1/projects/SEC1/modules")
    contract_recorder.record("non_viewer_plain_404", r_unreadable.request, r_unreadable)
    assert r_unreadable.status_code == 404, r_unreadable.text

    # Compare against nonexistent project
    r_nonexistent = await client_outsider.get("/api/v1/projects/NONEXIST/modules")
    b_unreadable = r_unreadable.json()
    b_nonexistent = r_nonexistent.json()
    b_unreadable.pop("request_id", None)
    b_nonexistent.pop("request_id", None)
    assert b_unreadable == b_nonexistent
    assert "MODULES_DISABLED" not in json.dumps(b_unreadable)

    # Non-viewer module detail 404
    r_mod_unreadable = await client_outsider.get(f"/api/v1/modules/{mod_id}")
    r_mod_nonexistent = await client_outsider.get(f"/api/v1/modules/{uuid.uuid4()}")
    assert r_mod_unreadable.status_code == 404
    b_mod_unreadable = r_mod_unreadable.json()
    b_mod_nonexistent = r_mod_nonexistent.json()
    b_mod_unreadable.pop("request_id", None)
    b_mod_nonexistent.pop("request_id", None)
    assert b_mod_unreadable == b_mod_nonexistent

    # 2. Member with PROJECT_MEMBER (VIEW + EDIT on issues, but NOT ADMIN on project)
    client_member = as_principal(member)
    r_create_denied = await client_member.post(
        "/api/v1/projects/SEC1/modules",
        json={"name": "Unauthorized Module"},
    )
    assert r_create_denied.status_code == 403, r_create_denied.text
    assert r_create_denied.json()["code"] == "INSUFFICIENT_CAPABILITY"

    r_patch_denied = await client_member.patch(
        f"/api/v1/modules/{mod_id}",
        json={"name": "Hacked Module"},
    )
    assert r_patch_denied.status_code == 403
    assert r_patch_denied.json()["code"] == "INSUFFICIENT_CAPABILITY"

    r_del_denied = await client_member.delete(f"/api/v1/modules/{mod_id}")
    assert r_del_denied.status_code == 403
    assert r_del_denied.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. Lead principal eligibility
    client_admin = as_principal(admin)

    # Random nonexistent UUID
    r_lead_random = await client_admin.post(
        "/api/v1/projects/SEC1/modules",
        json={"name": "Mod Random", "lead_principal_id": str(uuid.uuid4())},
    )
    assert r_lead_random.status_code == 422, r_lead_random.text
    assert r_lead_random.json()["code"] == "LEAD_NOT_ELIGIBLE"

    # Outsider who lacks VIEW on project
    r_lead_outsider = await client_admin.post(
        "/api/v1/projects/SEC1/modules",
        json={"name": "Mod Outsider", "lead_principal_id": str(outsider.id)},
    )
    assert r_lead_outsider.status_code == 422, r_lead_outsider.text
    assert r_lead_outsider.json()["code"] == "LEAD_NOT_ELIGIBLE"
    # Anti-enumeration: identical body
    b_lead_outsider = r_lead_outsider.json()
    b_lead_random = r_lead_random.json()
    b_lead_outsider.pop("request_id", None)
    b_lead_random.pop("request_id", None)
    assert b_lead_outsider == b_lead_random

    # Inactive principal
    r_lead_inactive = await client_admin.post(
        "/api/v1/projects/SEC1/modules",
        json={"name": "Mod Inactive", "lead_principal_id": str(inactive_user.id)},
    )
    assert r_lead_inactive.status_code == 422
    assert r_lead_inactive.json()["code"] == "LEAD_NOT_ELIGIBLE"


async def test_case_4_boundary_validations_and_limits(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: 10 modules accepted, 11 returns 422; duplicate name 409; 65537-byte desc 422."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "BND1", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    _ = await make_project(
        "BND2", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    # 1. Duplicate module name in same project (case-insensitive)
    r_mod1 = await client.post("/api/v1/projects/BND1/modules", json={"name": "Alpha Service"})
    assert r_mod1.status_code == 201, r_mod1.text
    mod1_id = r_mod1.json()["id"]

    r_dup = await client.post("/api/v1/projects/BND1/modules", json={"name": "alpha service"})
    assert r_dup.status_code == 409, r_dup.text
    assert r_dup.json()["code"] == "MODULE_NAME_TAKEN"

    r_dup_trim = await client.post(
        "/api/v1/projects/BND1/modules", json={"name": "   ALPHA SERVICE   "}
    )
    assert r_dup_trim.status_code == 409
    assert r_dup_trim.json()["code"] == "MODULE_NAME_TAKEN"

    # Same name in DIFFERENT project is permitted
    r_mod_b = await client.post("/api/v1/projects/BND2/modules", json={"name": "Alpha Service"})
    assert r_mod_b.status_code == 201, r_mod_b.text
    mod_b_id = r_mod_b.json()["id"]

    # PATCH to duplicate name of another module in same project
    r_mod2 = await client.post("/api/v1/projects/BND1/modules", json={"name": "Beta Service"})
    assert r_mod2.status_code == 201
    mod2_id = r_mod2.json()["id"]

    r_patch_dup = await client.patch(f"/api/v1/modules/{mod2_id}", json={"name": "alpha service"})
    assert r_patch_dup.status_code == 409
    assert r_patch_dup.json()["code"] == "MODULE_NAME_TAKEN"

    # PATCH same module to its own name is permitted
    r_patch_self = await client.patch(f"/api/v1/modules/{mod2_id}", json={"name": "Beta Service"})
    assert r_patch_self.status_code == 200

    # 2. Description size limit
    # 65536 bytes accepted
    valid_desc = "a" * 65536
    r_desc_ok = await client.post(
        "/api/v1/projects/BND1/modules",
        json={"name": "Big Desc Mod", "description_markdown": valid_desc},
    )
    assert r_desc_ok.status_code == 201, r_desc_ok.text

    # 65537 bytes rejected with 422
    too_big_desc = "a" * 65537
    r_desc_bad = await client.post(
        "/api/v1/projects/BND1/modules",
        json={"name": "Oversized Mod", "description_markdown": too_big_desc},
    )
    assert r_desc_bad.status_code == 422, r_desc_bad.text
    assert r_desc_bad.json()["code"] == "DESCRIPTION_TOO_LARGE"

    # 3. Name length boundary
    r_empty_name = await client.post("/api/v1/projects/BND1/modules", json={"name": "   "})
    assert r_empty_name.status_code == 422

    r_long_name = await client.post("/api/v1/projects/BND1/modules", json={"name": "x" * 121})
    assert r_long_name.status_code == 422

    # 4. Date range validation
    r_date_bad = await client.post(
        "/api/v1/projects/BND1/modules",
        json={"name": "Date Mod", "start_date": "2026-11-20", "target_date": "2026-11-10"},
    )
    assert r_date_bad.status_code == 422
    assert r_date_bad.json()["code"] == "INVALID_DATE_RANGE"

    # 5. Issue module limit: 10 accepted, 11th rejected
    r_issue = await client.post(
        "/api/v1/projects/BND1/issues",
        json={"summary": "Issue for limit check"},
    )
    assert r_issue.status_code == 201
    issue_key = r_issue.json()["key"]

    module_ids: list[str] = [mod1_id, mod2_id, r_desc_ok.json()["id"]]
    for i in range(4, 12):
        r_extra = await client.post("/api/v1/projects/BND1/modules", json={"name": f"Module {i}"})
        assert r_extra.status_code == 201
        module_ids.append(r_extra.json()["id"])

    # 10 modules accepted
    r_10 = await client.put(
        f"/api/v1/issues/{issue_key}/modules", json={"module_ids": module_ids[:10]}
    )
    assert r_10.status_code == 200, r_10.text
    assert len(r_10.json()["module_ids"]) == 10

    # 11 modules rejected
    r_11 = await client.put(
        f"/api/v1/issues/{issue_key}/modules", json={"module_ids": module_ids[:11]}
    )
    contract_recorder.record("module_limit_422", r_11.request, r_11)
    assert r_11.status_code == 422, r_11.text
    assert r_11.json()["code"] == "MODULE_LIMIT"

    # Granular 11th module rejected
    r_add_11th = await client.put(f"/api/v1/modules/{module_ids[10]}/issues/{issue_key}")
    assert r_add_11th.status_code == 422
    assert r_add_11th.json()["code"] == "MODULE_LIMIT"

    # Direct service call limit validation
    with pytest.raises(ProblemException) as exc:
        await svc.update_issue_modules(
            api_env.seed,
            PrincipalContext(
                principal_id=admin.id, workspace_id=api_env.workspace_id, token_scopes=("session",)
            ),
            issue_key,
            [uuid.uuid4() for _ in range(11)],
        )
    assert exc.value.code == "MODULE_LIMIT"

    # 6. Cross-project module assignment rejected
    r_cross = await client.put(
        f"/api/v1/issues/{issue_key}/modules",
        json={"module_ids": [mod_b_id]},
    )
    assert r_cross.status_code == 422, r_cross.text
    assert r_cross.json()["code"] == "MODULE_NOT_IN_PROJECT"

    r_cross_granular = await client.put(f"/api/v1/modules/{mod_b_id}/issues/{issue_key}")
    assert r_cross_granular.status_code == 422, r_cross_granular.text
    assert r_cross_granular.json()["code"] == "CROSS_PROJECT_NOT_ALLOWED"


async def test_case_5_delete_cascade_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Deleting module removes issue links & project defaults, logs MODULE_DELETED."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "DEL1", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    # 1. Create module
    r_mod = await client.post("/api/v1/projects/DEL1/modules", json={"name": "Ephemeral Mod"})
    assert r_mod.status_code == 201
    mod_id = uuid.UUID(r_mod.json()["id"])

    # 2. Create 2 issues and assign module
    r_i1 = await client.post("/api/v1/projects/DEL1/issues", json={"summary": "Issue 1"})
    r_i2 = await client.post("/api/v1/projects/DEL1/issues", json={"summary": "Issue 2"})
    k1 = r_i1.json()["key"]
    k2 = r_i2.json()["key"]

    await client.put(f"/api/v1/issues/{k1}/modules", json={"module_ids": [str(mod_id)]})
    await client.put(f"/api/v1/issues/{k2}/modules", json={"module_ids": [str(mod_id)]})

    # Set as project module default
    await client.put("/api/v1/projects/DEL1/module-defaults", json={"module_ids": [str(mod_id)]})

    # Verify counts before delete
    defaults_before = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM project_module_defaults WHERE module_id = :m"),
            {"m": mod_id},
        )
    ).scalar_one()
    assert defaults_before == 1

    issue_links_before = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issue_modules WHERE module_id = :m"),
            {"m": mod_id},
        )
    ).scalar_one()
    assert issue_links_before == 2

    # 3. Delete module (204 No Content)
    r_del = await client.delete(f"/api/v1/modules/{mod_id}")
    assert r_del.status_code == 204

    # 4. Verify cascade clean-up
    defaults_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM project_module_defaults WHERE module_id = :m"),
            {"m": mod_id},
        )
    ).scalar_one()
    assert defaults_after == 0

    issue_links_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issue_modules WHERE module_id = :m"),
            {"m": mod_id},
        )
    ).scalar_one()
    assert issue_links_after == 0

    # Module get returns 404
    r_get_deleted = await client.get(f"/api/v1/modules/{mod_id}")
    assert r_get_deleted.status_code == 404

    # Object record soft-deleted
    deleted_at = (
        await api_env.seed.execute(
            text("SELECT deleted_at FROM objects WHERE id = :m"),
            {"m": mod_id},
        )
    ).scalar_one()
    assert deleted_at is not None

    # Verify MODULE_DELETED activity record with removed_issue_links == 2
    del_count = await _count_activity(api_env, mod_id, "MODULE_DELETED")
    assert del_count == 1
    del_payload = await _get_activity_payload(api_env, mod_id, "MODULE_DELETED")
    assert del_payload is not None
    assert del_payload.get("removed_issue_links") == 2


async def test_case_6_patch_and_granular_endpoints(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: PATCH module fields, granular issue add/remove, and activity logs."""
    admin = await make_user("admin6", workspace_role="WORKSPACE_ADMIN")
    lead_user = await make_user("lead6")
    _ = await make_project(
        "GRN1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", lead_user: "VIEWER"},
        modules_enabled=True,
    )
    client = as_principal(admin)

    # 1. Create module
    r_mod = await client.post("/api/v1/projects/GRN1/modules", json={"name": "Initial Name"})
    assert r_mod.status_code == 201
    mod_id = uuid.UUID(r_mod.json()["id"])

    # 2. Patch fields
    patch_body = {
        "name": "Updated Name",
        "description_markdown": "Updated description",
        "lead_principal_id": str(lead_user.id),
        "status": "completed",
        "start_date": "2026-11-05",
        "target_date": "2026-11-25",
    }
    r_patch = await client.patch(f"/api/v1/modules/{mod_id}", json=patch_body)
    assert r_patch.status_code == 200, r_patch.text
    data = r_patch.json()
    assert data["name"] == "Updated Name"
    assert data["description_markdown"] == "Updated description"
    assert data["status"] == "completed"
    assert data["lead"] is not None
    assert data["lead"]["id"] == str(lead_user.id)

    # Clear lead_principal_id
    r_clear_lead = await client.patch(f"/api/v1/modules/{mod_id}", json={"lead_principal_id": None})
    assert r_clear_lead.status_code == 200
    assert r_clear_lead.json()["lead"] is None

    # Invalid date range on patch
    r_bad_dates = await client.patch(
        f"/api/v1/modules/{mod_id}",
        json={"start_date": "2026-11-20", "target_date": "2026-11-10"},
    )
    assert r_bad_dates.status_code == 422
    assert r_bad_dates.json()["code"] == "INVALID_DATE_RANGE"

    # Verify MODULE_UPDATED activity record
    upd_count = await _count_activity(api_env, mod_id, "MODULE_UPDATED")
    assert upd_count >= 1
    upd_payload = await _get_activity_payload(api_env, mod_id, "MODULE_UPDATED")
    assert upd_payload is not None
    assert "changes" in upd_payload

    # 3. Create issue for granular assignment
    r_iss = await client.post("/api/v1/projects/GRN1/issues", json={"summary": "Granular Issue"})
    assert r_iss.status_code == 201
    iss_key = r_iss.json()["key"]
    iss_id = uuid.UUID(r_iss.json()["id"])

    # Granular PUT add
    r_add = await client.put(f"/api/v1/modules/{mod_id}/issues/{iss_key}")
    assert r_add.status_code == 204

    # Check activity ISSUE_MODULE_ADDED
    added_count = await _count_activity(api_env, iss_id, "ISSUE_MODULE_ADDED")
    assert added_count == 1

    # Idempotent PUT add
    r_add_dup = await client.put(f"/api/v1/modules/{mod_id}/issues/{iss_key}")
    assert r_add_dup.status_code == 204

    # Granular DELETE remove
    r_rem = await client.delete(f"/api/v1/modules/{mod_id}/issues/{iss_key}")
    assert r_rem.status_code == 204

    # Check activity ISSUE_MODULE_REMOVED
    rem_count = await _count_activity(api_env, iss_id, "ISSUE_MODULE_REMOVED")
    assert rem_count == 1

    # Bulk assign and then bulk clear
    r_bulk_set = await client.put(
        f"/api/v1/issues/{iss_key}/modules", json={"module_ids": [str(mod_id)]}
    )
    assert r_bulk_set.status_code == 200
    assert r_bulk_set.json()["module_ids"] == [str(mod_id)]

    # Idempotent bulk assign (added=[], removed=[])
    r_bulk_same = await client.put(
        f"/api/v1/issues/{iss_key}/modules", json={"module_ids": [str(mod_id)]}
    )
    assert r_bulk_same.status_code == 200
    assert r_bulk_same.json()["module_ids"] == [str(mod_id)]

    r_bulk_clear = await client.put(f"/api/v1/issues/{iss_key}/modules", json={"module_ids": []})
    assert r_bulk_clear.status_code == 200
    assert r_bulk_clear.json()["module_ids"] == []

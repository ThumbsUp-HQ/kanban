# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hybrid assignees API tests: permissions, boundaries, anti-enumeration (KB-P3-03)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.assignees import FREE_TEXT_HINT, AssigneeCreate
from kanban.services.assignees import add_assignee
from kanban.tests.security.helpers import add_acl_entry, add_role_binding, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def test_case_1_positive_assign_and_get_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 1: Positive assign by @handle, issue GET lists assignee, ASSIGNEE_ADDED."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer")
    await make_project(
        "PRJ1",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", viewer: "MEMBER"},
    )
    client = as_principal(admin)

    # 1. Create issue
    resp_create = await client.post(
        "/api/v1/projects/PRJ1/issues",
        json={"summary": "Positive Assignee Issue", "description_markdown": "Details"},
    )
    assert resp_create.status_code == 201, resp_create.text
    issue_data = resp_create.json()
    issue_key = issue_data["key"]

    # 2. Assign viewer by @handle
    resp_assign = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": f"@{viewer.handle}"},
    )
    contract_recorder.record("principal_assign_201", resp_assign.request, resp_assign)
    assert resp_assign.status_code == 201, resp_assign.text
    assign_data = resp_assign.json()
    assert assign_data["kind"] == "principal"
    assert assign_data["principal"]["id"] == str(viewer.id)
    assert assign_data["principal"]["handle"] == viewer.handle
    assert assign_data["principal"]["type"] == "USER"

    # 2b. Assign free text vendor
    resp_ft = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "Security Vendor Team"},
    )
    assert resp_ft.status_code == 201, resp_ft.text
    ft_data = resp_ft.json()
    assert ft_data["kind"] == "free_text"
    assert ft_data["free_text"] == "Security Vendor Team"

    # 3. GET issue and verify assignees list
    resp_get = await client.get(f"/api/v1/issues/{issue_key}")
    assert resp_get.status_code == 200, resp_get.text
    get_data = resp_get.json()
    assert "assignees" in get_data
    assert len(get_data["assignees"]) == 2
    assert get_data["assignees"][0]["id"] == assign_data["id"]
    assert get_data["assignees"][0]["principal"]["handle"] == viewer.handle
    assert get_data["assignees"][1]["id"] == ft_data["id"]
    assert get_data["assignees"][1]["free_text"] == "Security Vendor Team"

    # 4. Verify ASSIGNEE_ADDED rows exist in activity_records
    act_rows = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'ASSIGNEE_ADDED' "
                    "ORDER BY recorded_at ASC"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .all()
    )
    assert len(act_rows) == 2
    assert act_rows[0]["event_type"] == "ASSIGNEE_ADDED"
    assert act_rows[0]["payload"]["kind"] == "principal"
    assert act_rows[0]["payload"]["principal_id"] == str(viewer.id)
    assert act_rows[1]["event_type"] == "ASSIGNEE_ADDED"
    assert act_rows[1]["payload"]["kind"] == "free_text"
    assert act_rows[1]["payload"]["free_text"] == "Security Vendor Team"


async def test_case_2_security_anti_enumeration_and_deny(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 2: Ineligible principal returns byte-identical 422; DENY rejected."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    ws_user = await make_user("wsuser")  # Exists in workspace, but NO project VIEW
    proj_id = await make_project("PRJ2", created_by=admin)
    client = as_principal(admin)

    resp_create = await client.post(
        "/api/v1/projects/PRJ2/issues",
        json={"summary": "Security Test Issue"},
    )
    assert resp_create.status_code == 201, resp_create.text
    issue_key = resp_create.json()["key"]

    # 1. Assign user without project VIEW -> 422 ASSIGNEE_NOT_ELIGIBLE
    resp_ws = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(ws_user.id)},
    )
    contract_recorder.record("ineligible_assignee_422", resp_ws.request, resp_ws)
    assert resp_ws.status_code == 422, resp_ws.text
    assert resp_ws.json()["code"] == "ASSIGNEE_NOT_ELIGIBLE"

    # 2. Assign nonexistent random UUID -> 422 ASSIGNEE_NOT_ELIGIBLE
    random_id = uuid.uuid4()
    resp_rand = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(random_id)},
    )
    assert resp_rand.status_code == 422, resp_rand.text
    assert resp_rand.json()["code"] == "ASSIGNEE_NOT_ELIGIBLE"

    # 2b. Assign nonexistent handle -> 422 ASSIGNEE_NOT_ELIGIBLE
    resp_handle_missing = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": "@ghost_missing_user"},
    )
    assert resp_handle_missing.status_code == 422, resp_handle_missing.text
    assert resp_handle_missing.json()["code"] == "ASSIGNEE_NOT_ELIGIBLE"

    # 3. Verify byte-identical response body (ignoring request_id)
    ws_body = dict(resp_ws.json())
    rand_body = dict(resp_rand.json())
    handle_body = dict(resp_handle_missing.json())
    ws_body.pop("request_id", None)
    rand_body.pop("request_id", None)
    handle_body.pop("request_id", None)
    assert ws_body == rand_body
    assert ws_body == handle_body

    # 4. User with explicit DENY on project is also rejected
    denied_user = await make_user("denieduser")
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        denied_user.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_id,
    )
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        denied_user.id,
        effect="DENY",
        capability_mask=1,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    resp_denied = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(denied_user.id)},
    )
    assert resp_denied.status_code == 422, resp_denied.text
    assert resp_denied.json()["code"] == "ASSIGNEE_NOT_ELIGIBLE"
    denied_body = dict(resp_denied.json())
    denied_body.pop("request_id", None)
    assert denied_body == ws_body


async def test_case_3_enumeration_suggestions_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 3: Suggestions never leak user across projects; zero email; unreadable is 404."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    alice = await make_user("alice", workspace_role=None)  # Project A only
    bob = await make_user("bob", workspace_role=None)  # Project B only

    proj_a = await make_project("PRJA", created_by=admin, roles={alice: "MEMBER"})
    await make_project("PRJB", created_by=admin, roles={bob: "MEMBER"})

    client_admin = as_principal(admin)

    # 1. Query suggestions in Project A for q=a
    resp_sugg_a = await client_admin.get("/api/v1/projects/PRJA/assignee-suggestions?q=a")
    contract_recorder.record("suggestions_200", resp_sugg_a.request, resp_sugg_a)
    assert resp_sugg_a.status_code == 200, resp_sugg_a.text
    items_a = resp_sugg_a.json()["items"]
    handles_a = [item["handle"] for item in items_a]
    assert "alice" in handles_a
    assert "bob" not in handles_a

    # 2. Query suggestions in Project A for q=b (bob has access only to Project B)
    resp_sugg_b = await client_admin.get("/api/v1/projects/PRJA/assignee-suggestions?q=b")
    assert resp_sugg_b.status_code == 200, resp_sugg_b.text
    items_b = resp_sugg_b.json()["items"]
    handles_b = [item["handle"] for item in items_b]
    assert "bob" not in handles_b

    # 3. Verify zero email key or sensitive attribute in response items
    for item in items_a + items_b:
        assert "email" not in item
        assert "auth_provider" not in item
        assert "dn" not in item

    # 4. Caller without VIEW on project returns 404
    client_alice = as_principal(alice)
    resp_unreadable = await client_alice.get("/api/v1/projects/PRJB/assignee-suggestions?q=b")
    contract_recorder.record(
        "unreadable_project_suggestions_404",
        resp_unreadable.request,
        resp_unreadable,
    )
    assert resp_unreadable.status_code == 404, resp_unreadable.text

    # 5. Record EXPLAIN (ANALYZE, BUFFERS) for suggestions query
    explain_stmt = text(
        "EXPLAIN (ANALYZE, BUFFERS) "
        "SELECT "
        "  p.id AS id, "
        "  o.canonical_key AS handle, "
        "  p.display_name AS display_name, "
        "  p.principal_type AS type "
        "FROM principals p "
        "JOIN objects o ON o.id = p.id "
        "JOIN effective_resource_access era ON era.principal_id = p.id "
        "WHERE era.object_id = :project_id "
        "  AND era.workspace_id = :workspace_id "
        "  AND (era.allow_mask & 1) = 1 "
        "  AND (era.deny_mask & 1) = 0 "
        "  AND p.workspace_id = :workspace_id "
        "  AND p.status = 'ACTIVE' "
        "  AND p.principal_type IN ('USER', 'AGENT') "
        "  AND ( "
        "    o.canonical_key ILIKE 'a%' ESCAPE '\\' "
        "    OR p.display_name ILIKE 'a%' ESCAPE '\\' "
        "  ) "
        "ORDER BY p.display_name ASC, o.canonical_key ASC "
        "LIMIT 10"
    )
    explain_res = (
        await api_env.seed.execute(
            explain_stmt,
            {
                "project_id": proj_a,
                "workspace_id": api_env.workspace_id,
            },
        )
    ).fetchall()
    explain_lines = [r[0] for r in explain_res]
    out_path = Path("docs/qa/KANBA-83/suggestions-explain.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(explain_lines) + "\n", encoding="utf-8")  # noqa: ASYNC240


async def test_case_4_free_text_normalization_and_duplicates(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Test Case 4: Free text normalization, HTML stripping, boundaries, and duplicates."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("PRJ4", created_by=admin)
    client = as_principal(admin)

    resp_create = await client.post(
        "/api/v1/projects/PRJ4/issues",
        json={"summary": "Free Text Issue"},
    )
    assert resp_create.status_code == 201, resp_create.text
    issue_key = resp_create.json()["key"]

    # 1. Normal free text stored with notify: false and hint
    resp_ft = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "Vendor: NCC Group"},
    )
    contract_recorder.record("free_text_assign_201", resp_ft.request, resp_ft)
    assert resp_ft.status_code == 201, resp_ft.text
    ft_data = resp_ft.json()
    assert ft_data["kind"] == "free_text"
    assert ft_data["free_text"] == "Vendor: NCC Group"
    assert ft_data["notify"] is False
    assert ft_data["hint"] == FREE_TEXT_HINT

    # 2. HTML tags stripped: "<b>x</b>" -> "x"
    resp_html = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "<b>x</b>"},
    )
    assert resp_html.status_code == 201, resp_html.text
    assert resp_html.json()["free_text"] == "x"

    # 3. 121 chars returns 422 FREE_TEXT_INVALID
    resp_121 = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "a" * 121},
    )
    assert resp_121.status_code == 422, resp_121.text
    assert resp_121.json()["code"] == "FREE_TEXT_INVALID"

    # 4. Zero-width only string returns 422 FREE_TEXT_INVALID
    resp_zw = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "\u200b\u200c\u200d"},
    )
    assert resp_zw.status_code == 422, resp_zw.text
    assert resp_zw.json()["code"] == "FREE_TEXT_INVALID"

    # 5. Case-insensitive duplicate returns 409 ASSIGNEE_EXISTS
    resp_dup = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "vendor: ncc group"},
    )
    assert resp_dup.status_code == 409, resp_dup.text
    assert resp_dup.json()["code"] == "ASSIGNEE_EXISTS"


async def test_case_5_boundaries_and_literal_like_matching(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 5: 20 total limit, 10 free-text limit, query boundaries, literal LIKE escaping."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("PRJ5", created_by=admin)
    client = as_principal(admin)

    resp_create = await client.post(
        "/api/v1/projects/PRJ5/issues",
        json={"summary": "Boundary Issue"},
    )
    assert resp_create.status_code == 201, resp_create.text
    issue_key = resp_create.json()["key"]

    # 1. Add 10 free text assignees (succeeds)
    for i in range(10):
        resp_ft_i = await client.post(
            f"/api/v1/issues/{issue_key}/assignees",
            json={"free_text": f"FreeText-{i}"},
        )
        assert resp_ft_i.status_code == 201, resp_ft_i.text

    # 2. 11th free text rejected -> 422 ASSIGNEE_LIMIT
    resp_ft_11 = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"free_text": "FreeText-11"},
    )
    assert resp_ft_11.status_code == 422, resp_ft_11.text
    assert resp_ft_11.json()["code"] == "ASSIGNEE_LIMIT"

    # 3. Add 10 principal assignees (reaches 20 total)
    users: list[SeededUser] = []
    for i in range(10):
        u = await make_user(f"viewer{i}")
        await add_role_binding(
            api_env.seed,
            api_env.workspace_id,
            u.id,
            role="MEMBER",
            scope_type="project",
            project_id=proj_id,
        )
        users.append(u)
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    for u in users:
        resp_p_i = await client.post(
            f"/api/v1/issues/{issue_key}/assignees",
            json={"principal": str(u.id)},
        )
        assert resp_p_i.status_code == 201, resp_p_i.text

    # 4. 21st assignee rejected -> 422 ASSIGNEE_LIMIT
    extra_user = await make_user("viewer21")
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        extra_user.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    resp_21 = await client.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(extra_user.id)},
    )
    assert resp_21.status_code == 422, resp_21.text
    assert resp_21.json()["code"] == "ASSIGNEE_LIMIT"

    # 5. Query string boundaries: 65 chars rejected -> 422
    resp_q65 = await client.get(f"/api/v1/projects/PRJ5/assignee-suggestions?q={'x' * 65}")
    assert resp_q65.status_code == 422, resp_q65.text

    # 6. Literal LIKE matching for % and _
    # Create user with display name containing %_
    special_user = await make_user("specialuser")
    await api_env.seed.execute(
        text("UPDATE principals SET display_name = 'Special%_Name' WHERE id = :id"),
        {"id": special_user.id},
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        special_user.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_id,
    )
    # Create decoy user that would match if % was treated as wildcard
    decoy_user = await make_user("decoyuser")
    await api_env.seed.execute(
        text("UPDATE principals SET display_name = 'SpecialXYZName' WHERE id = :id"),
        {"id": decoy_user.id},
    )
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        decoy_user.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    resp_special = await client.get("/api/v1/projects/PRJ5/assignee-suggestions?q=Special%_")
    assert resp_special.status_code == 200, resp_special.text
    special_items = resp_special.json()["items"]
    special_names = [it["display_name"] for it in special_items]
    assert "Special%_Name" in special_names
    assert "SpecialXYZName" not in special_names


async def test_case_6_delete_assignee_and_cross_issue_404(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 6: Delete assignee returns 204 and logs ASSIGNEE_REMOVED; wrong issue is 404."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer")
    await make_project("PRJ6", created_by=admin, roles={viewer: "MEMBER"})
    client = as_principal(admin)

    # 1. Create two issues
    resp_iss1 = await client.post(
        "/api/v1/projects/PRJ6/issues",
        json={"summary": "Issue One"},
    )
    resp_iss2 = await client.post(
        "/api/v1/projects/PRJ6/issues",
        json={"summary": "Issue Two"},
    )
    key1 = resp_iss1.json()["key"]
    key2 = resp_iss2.json()["key"]

    # 2. Assign to issue 1
    resp_assign = await client.post(
        f"/api/v1/issues/{key1}/assignees",
        json={"principal": str(viewer.id)},
    )
    assert resp_assign.status_code == 201, resp_assign.text
    assignee_id = resp_assign.json()["id"]

    # 3. Deleting from issue 2 (wrong issue) -> 404
    resp_del_wrong = await client.delete(f"/api/v1/issues/{key2}/assignees/{assignee_id}")
    assert resp_del_wrong.status_code == 404, resp_del_wrong.text

    # 4. Deleting from issue 1 -> 204
    resp_del = await client.delete(f"/api/v1/issues/{key1}/assignees/{assignee_id}")
    assert resp_del.status_code == 204, resp_del.text

    # 5. Verify ASSIGNEE_REMOVED in activity_records
    act_row = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'ASSIGNEE_REMOVED' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .one()
    )
    assert act_row["event_type"] == "ASSIGNEE_REMOVED"
    assert act_row["payload"]["kind"] == "principal"
    assert act_row["payload"]["principal_id"] == str(viewer.id)

    # 6. Deleting already-deleted assignee -> 404
    resp_del_again = await client.delete(f"/api/v1/issues/{key1}/assignees/{assignee_id}")
    assert resp_del_again.status_code == 404, resp_del_again.text

    # 7. Add and delete free-text assignee -> 204 and ASSIGNEE_REMOVED with kind=free_text
    resp_ft = await client.post(
        f"/api/v1/issues/{key1}/assignees",
        json={"free_text": "Temporary Contractor"},
    )
    assert resp_ft.status_code == 201, resp_ft.text
    ft_id = resp_ft.json()["id"]

    resp_del_ft = await client.delete(f"/api/v1/issues/{key1}/assignees/{ft_id}")
    assert resp_del_ft.status_code == 204, resp_del_ft.text

    act_ft_row = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE workspace_id = :wid AND event_type = 'ASSIGNEE_REMOVED' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"wid": api_env.workspace_id},
            )
        )
        .mappings()
        .one()
    )
    assert act_ft_row["event_type"] == "ASSIGNEE_REMOVED"
    assert act_ft_row["payload"]["kind"] == "free_text"
    assert act_ft_row["payload"]["free_text"] == "Temporary Contractor"


async def test_extra_permissions_and_payload_validations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test permission gates (EDIT required), payload validation, and duplicate principal."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer")
    await make_project(
        "PRJX",
        created_by=admin,
        roles={viewer: "MEMBER"},
    )
    client_admin = as_principal(admin)

    resp_iss = await client_admin.post(
        "/api/v1/projects/PRJX/issues",
        json={"summary": "Permission Validation Issue"},
    )
    issue_key = resp_iss.json()["key"]

    # 1. Payload with both principal and free_text rejected -> 422
    resp_both = await client_admin.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(viewer.id), "free_text": "Vendor"},
    )
    assert resp_both.status_code == 422, resp_both.text

    # 2. Payload with neither rejected -> 422
    resp_neither = await client_admin.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={},
    )
    assert resp_neither.status_code == 422, resp_neither.text

    # 3. Duplicate principal rejected -> 409 ASSIGNEE_EXISTS
    resp_first = await client_admin.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(viewer.id)},
    )
    assert resp_first.status_code == 201, resp_first.text

    resp_second = await client_admin.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": str(viewer.id)},
    )
    assert resp_second.status_code == 409, resp_second.text
    assert resp_second.json()["code"] == "ASSIGNEE_EXISTS"

    # 4. Agent principal assignment succeeds
    agent_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, status, display_name) "
            "VALUES (:id, :ws_id, 'AGENT', 'ACTIVE', 'Review Bot')"
        ),
        {"id": agent_id, "ws_id": api_env.workspace_id},
    )
    await api_env.seed.execute(
        text(
            "SELECT register_object("
            "'user'::object_kind, :ws_id, NULL, 'review-bot', 'Review Bot', :id, :id"
            ")"
        ),
        {"ws_id": api_env.workspace_id, "id": agent_id},
    )
    # Grant VIEW on project to agent in ERA
    proj_row = (
        await api_env.seed.execute(text("SELECT id FROM projects WHERE identifier = 'PRJX'"))
    ).scalar_one()
    await api_env.seed.execute(
        text(
            "INSERT INTO effective_resource_access "
            "(object_id, principal_id, workspace_id, allow_mask, deny_mask) "
            "VALUES (:obj_id, :p_id, :ws_id, 1, 0)"
        ),
        {"obj_id": proj_row, "p_id": agent_id, "ws_id": api_env.workspace_id},
    )
    await api_env.seed.commit()

    resp_agent = await client_admin.post(
        f"/api/v1/issues/{issue_key}/assignees",
        json={"principal": "@review-bot"},
    )
    assert resp_agent.status_code == 201, resp_agent.text
    assert resp_agent.json()["principal"]["type"] == "AGENT"
    assert resp_agent.json()["principal"]["handle"] == "review-bot"

    # 5. Direct add_assignee call with uuid.UUID instance in body.principal
    agent_assignee_id = resp_agent.json()["id"]
    await client_admin.delete(f"/api/v1/issues/{issue_key}/assignees/{agent_assignee_id}")

    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )
    direct_res = await add_assignee(
        api_env.seed,
        caller,
        issue_key,
        AssigneeCreate(principal=agent_id),
    )
    assert direct_res.kind == "principal"
    assert direct_res.id is not None

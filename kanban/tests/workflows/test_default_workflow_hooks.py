# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: D400, D415, E501, TC002, ARG001
"""Feature unit and security tests for system-wide and workspace default workflow hook templates (KAN-438)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select, text

from database.models.agent_definition import AgentDefinition
from database.models.projects import Project
from database.models.spine import Workspace
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import DefaultWorkflowHook, WorkflowTransitionHook
from kanban.projects.blueprint_service import (
    BlueprintState,
    ProjectBlueprint,
)
from kanban.tests.api.conftest import SeededUser
from kanban.tests.security.helpers import add_role_binding, create_user, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv

pytestmark = pytest.mark.committed_db


async def _enroll_mfa(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Enroll and confirm TOTP factor so require_admin_aal2 evaluates AAL rather than MFA_ENROLLMENT_REQUIRED."""
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
    await session.commit()


async def _seed_agent(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    slug: str = "reality-checker",
) -> uuid.UUID:
    """Seed an AgentDefinition and return its ID."""
    agent_id = uuid.uuid4()
    agent = AgentDefinition(
        id=agent_id,
        workspace_id=workspace_id,
        principal_id=principal_id,
        slug=slug,
        display_name="Reality-Checker Gate",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
        timeout_ms=60000,
    )
    session.add(agent)
    await session.commit()
    return agent_id


@pytest.mark.asyncio
async def test_admin_crud_and_copy_on_create_inheritance(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 1:

    1. Admin creates system and workspace default hooks (* -> Done, In Progress -> Done).
    2. Creating new project NEWP automatically inherits both hooks with inherited_from_template_id set.
    """
    session = api_env.seed
    ws_id = api_env.workspace_id
    server_admin = await make_user("s_admin", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, server_admin.id)
    client_admin = as_principal(server_admin, aal_level=2)

    # Seed @reality-checker agent in workspace
    await _seed_agent(session, ws_id, server_admin.id, slug="reality-checker")

    # 1. Create system template: * Any -> Done with @reality-checker
    res_sys = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Reality-Checker Any Gate",
            "scope_kind": "system",
            "from_state_name": "*",
            "to_state_name": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "@reality-checker",
            "failure_policy": "fail_closed",
            "timeout_ms": 120000,
        },
    )
    assert res_sys.status_code == 201, res_sys.text
    sys_hook_data = res_sys.json()
    assert sys_hook_data["name"] == "Reality-Checker Any Gate"
    assert sys_hook_data["scope_kind"] == "system"
    assert sys_hook_data["from_state_name"] is None  # normalized wildcard
    assert sys_hook_data["to_state_name"] == "Done"
    sys_template_id = sys_hook_data["id"]

    # 2. Create workspace template: In Progress -> Done
    res_ws = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Workspace In Progress Gate",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "@reality-checker",
            "failure_policy": "fail_closed",
            "timeout_ms": 90000,
        },
    )
    assert res_ws.status_code == 201, res_ws.text
    ws_hook_data = res_ws.json()
    assert ws_hook_data["name"] == "Workspace In Progress Gate"
    assert ws_hook_data["scope_kind"] == "workspace"
    assert ws_hook_data["workspace_id"] == str(ws_id)
    ws_template_id = ws_hook_data["id"]

    # 3. Create new project NEWP via projects API
    res_proj = await client_admin.post(
        "/api/v1/projects",
        json={
            "name": "New Project",
            "identifier": "NEWP",
        },
    )
    assert res_proj.status_code == 201, res_proj.text
    newp_id = uuid.UUID(res_proj.json()["id"])

    # 4. Verify NEWP automatically has both inherited hooks
    hooks_stmt = (
        select(WorkflowTransitionHook)
        .where(WorkflowTransitionHook.project_id == newp_id)
        .order_by(WorkflowTransitionHook.sort_rank.asc())
    )
    newp_hooks = list((await session.execute(hooks_stmt)).scalars().all())
    assert len(newp_hooks) == 2

    hook_names = {h.name for h in newp_hooks}
    assert "Reality-Checker Any Gate" in hook_names
    assert "Workspace In Progress Gate" in hook_names

    template_ids = {str(h.inherited_from_template_id) for h in newp_hooks}
    assert sys_template_id in template_ids
    assert ws_template_id in template_ids

    # 5. Verify serialized response via API exposes inherited_from_template_id and inherited_from_scope
    res_list = await client_admin.get("/api/v1/projects/NEWP/workflow-hooks")
    assert res_list.status_code == 200, res_list.text
    rules = res_list.json()
    assert len(rules) >= 1
    all_hook_items = [h for r in rules for h in r["hooks"]]
    assert len(all_hook_items) == 2

    for item in all_hook_items:
        assert item["inherited_from_template_id"] is not None
        assert item["inherited_from_scope"] in ("system", "workspace")


@pytest.mark.asyncio
async def test_non_agentic_project_detach_and_sibling_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 2:

    1. NEWP and SIBP both inherit default hook.
    2. Project Admin deletes inherited hook on NEWP.
    3. NEWP hook is removed, while default template and SIBP hook remain completely intact.
    """
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("admin_user", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    await _seed_agent(session, ws_id, admin.id, slug="reality-checker")

    # Create default hook template
    res_tpl = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Standard Reality Gate",
            "scope_kind": "system",
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "@reality-checker",
            "failure_policy": "fail_closed",
        },
    )
    assert res_tpl.status_code == 201, res_tpl.text
    tpl_id = res_tpl.json()["id"]

    # Create NEWP and SIBP
    res_newp = await client_admin.post(
        "/api/v1/projects", json={"name": "New P", "identifier": "NEW1"}
    )
    assert res_newp.status_code == 201
    newp_id = uuid.UUID(res_newp.json()["id"])

    res_sibp = await client_admin.post(
        "/api/v1/projects", json={"name": "Sib P", "identifier": "SIB1"}
    )
    assert res_sibp.status_code == 201
    sibp_id = uuid.UUID(res_sibp.json()["id"])

    # Both projects have inherited hook
    hook_newp = (
        await session.execute(
            select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == newp_id)
        )
    ).scalar_one()
    assert str(hook_newp.inherited_from_template_id) == tpl_id

    hook_sibp = (
        await session.execute(
            select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == sibp_id)
        )
    ).scalar_one()
    assert str(hook_sibp.inherited_from_template_id) == tpl_id

    # Detach (delete) inherited hook from NEWP
    res_del = await client_admin.delete(f"/api/v1/workflow-hooks/{hook_newp.id}")
    assert res_del.status_code == 204

    # NEWP now has 0 hooks (non-agentic tracker)
    newp_hooks_remaining = (
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == newp_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(newp_hooks_remaining) == 0

    # SIBP hook remains intact
    sibp_hooks_remaining = (
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == sibp_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(sibp_hooks_remaining) == 1

    # Default template remains intact
    tpl_row = await session.get(DefaultWorkflowHook, uuid.UUID(tpl_id))
    assert tpl_row is not None


@pytest.mark.asyncio
async def test_security_auth_and_aal2_enforcement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test Case 3:

    1. Non-admin receives HTTP 403.
    2. Missing AAL2 returns HTTP 403 or 401.
    """
    session = api_env.seed
    admin = await make_user("super_adm", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    member = await make_user("norm_member")

    # 1. Non-admin with AAL2 -> 403
    client_member_aal2 = as_principal(member, aal_level=2)
    res_forbidden = await client_member_aal2.get("/api/v1/admin/default-workflow-hooks")
    assert res_forbidden.status_code == 403, res_forbidden.text

    # 2. Server admin with AAL1 (missing AAL2) -> 403 or 401
    client_admin_aal1 = as_principal(admin, aal_level=1)
    res_aal1 = await client_admin_aal1.get("/api/v1/admin/default-workflow-hooks")
    assert res_aal1.status_code in (401, 403), res_aal1.text

    # 3. Workspace admin creating system hook -> 403
    ws_admin = await make_user("ws_adm_only", workspace_role="WORKSPACE_ADMIN")
    await _enroll_mfa(session, ws_admin.id)
    client_ws_admin = as_principal(ws_admin, aal_level=2)
    res_sys_denied = await client_ws_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Unauthorized System Hook",
            "scope_kind": "system",
            "to_state_name": "Done",
        },
    )
    assert res_sys_denied.status_code == 403, res_sys_denied.text


@pytest.mark.asyncio
async def test_workspace_convenience_routes_and_sync_defaults(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test workspace routes (/workspaces/{workspace}/default-workflow-hooks) and sync-defaults endpoint."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("ws_mgr", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client = as_principal(admin, aal_level=2)

    await _seed_agent(session, ws_id, admin.id, slug="reality-checker")

    # Create workspace template via workspace convenience route
    res_create = await client.post(
        f"/api/v1/workspaces/{ws_id}/default-workflow-hooks",
        json={
            "name": "WS Sync Gate",
            "scope_kind": "workspace",
            "to_state_name": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "@reality-checker",
        },
    )
    assert res_create.status_code == 201, res_create.text
    tpl_id = res_create.json()["id"]

    # List workspace templates
    res_list = await client.get(f"/api/v1/workspaces/{ws_id}/default-workflow-hooks")
    assert res_list.status_code == 200
    assert any(t["id"] == tpl_id for t in res_list.json())

    # Create existing project without hooks initially
    proj_id = await make_project("SYNC1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    # Delete any auto-materialized hooks to simulate older project
    existing = (
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    for h in existing:
        await session.delete(h)
    await session.commit()

    # Call sync-defaults endpoint
    res_sync = await client.post("/api/v1/projects/SYNC1/workflow-hooks/sync-defaults")
    assert res_sync.status_code == 200, res_sync.text
    synced_hooks = res_sync.json()
    assert len(synced_hooks) >= 1
    assert any(h["name"] == "WS Sync Gate" for h in synced_hooks)


@pytest.mark.asyncio
async def test_system_template_cross_tenant_isolation_and_rejections(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify system templates forbid agent_definition_id/UUID and resolve agent_slug per workspace."""
    session = api_env.seed
    admin = await make_user("sys_cross_admin", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    fake_agent_id = uuid.uuid4()

    # 1. Reject agent_definition_id on system create
    res_err1 = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Invalid Agent ID System Hook",
            "scope_kind": "system",
            "to_state_name": "Done",
            "agent_definition_id": str(fake_agent_id),
        },
    )
    assert res_err1.status_code == 422, res_err1.text
    assert res_err1.json()["code"] == "SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG"

    # 2. Reject UUID string in agent on system create
    res_err2 = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Invalid UUID Agent System Hook",
            "scope_kind": "system",
            "to_state_name": "Done",
            "agent": str(fake_agent_id),
        },
    )
    assert res_err2.status_code == 422, res_err2.text
    assert res_err2.json()["code"] == "SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG"

    # 3. Create valid system template with slug
    res_sys = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Cross Tenant Reality Gate",
            "scope_kind": "system",
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "agent": "@reality-checker",
        },
    )
    assert res_sys.status_code == 201, res_sys.text
    sys_tpl_id = res_sys.json()["id"]

    # 4. Reject PATCH with agent_definition_id
    res_err3 = await client_admin.patch(
        f"/api/v1/admin/default-workflow-hooks/{sys_tpl_id}",
        json={"agent_definition_id": str(fake_agent_id)},
    )
    assert res_err3.status_code == 422, res_err3.text
    assert res_err3.json()["code"] == "SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG"

    # 5. Create Workspace B and seed an agent in Workspace B
    ws_b = Workspace(name="Workspace Beta", slug=f"ws-b-{uuid.uuid4().hex[:6]}")
    session.add(ws_b)
    await session.commit()

    agent_b_id = await _seed_agent(session, ws_b.id, admin.id, slug="reality-checker")

    # 6. Create admin in Workspace B and create project
    user_b_id = await create_user(
        session, ws_b.id, handle=f"@admin_b_{uuid.uuid4().hex[:4]}", display_name="Admin B"
    )
    await add_role_binding(session, ws_b.id, user_b_id, role="SERVER_ADMIN", scope_type="server")
    await rebuild_era(session, ws_b.id)
    await session.commit()
    user_b = SeededUser(id=user_b_id, workspace_id=ws_b.id, handle="admin_b")
    await _enroll_mfa(session, user_b.id)
    client_b = as_principal(user_b, aal_level=2)

    res_proj_b = await client_b.post(
        "/api/v1/projects",
        json={"name": "Workspace B Project", "identifier": "WSB1"},
    )
    assert res_proj_b.status_code == 201, res_proj_b.text
    wsb_proj_id = uuid.UUID(res_proj_b.json()["id"])

    # Verify materialized hook in Workspace B
    hook_b = (
        await session.execute(
            select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == wsb_proj_id)
        )
    ).scalar_one()
    assert hook_b.agent_definition_id == agent_b_id
    assert str(hook_b.inherited_from_template_id) == sys_tpl_id


@pytest.mark.asyncio
async def test_admin_validations_and_conflict_handling(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify cross-workspace 403, invalid WASM 422, bounds 422, and duplicate name 409."""
    session = api_env.seed
    admin = await make_user("val_admin", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    ws_admin = await make_user("ws_admin_only", workspace_role="WORKSPACE_ADMIN")
    await _enroll_mfa(session, ws_admin.id)
    client_ws_admin = as_principal(ws_admin, aal_level=2)

    # 1. Cross-workspace create attempt by non-server-admin -> 403
    foreign_ws_id = uuid.uuid4()
    res_cross = await client_ws_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Cross WS Attempt",
            "scope_kind": "workspace",
            "workspace_id": str(foreign_ws_id),
            "to_state_name": "Done",
        },
    )
    assert res_cross.status_code == 403, res_cross.text
    assert res_cross.json()["code"] == "CROSS_WORKSPACE_FORBIDDEN"

    # Switch principal back to server admin
    client_admin = as_principal(admin, aal_level=2)

    # 2. Invalid WASM hex -> 422
    res_wasm_err = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Invalid WASM Hex",
            "scope_kind": "system",
            "to_state_name": "Done",
            "wasm_module_sha256": "not-valid-hex!",
        },
    )
    assert res_wasm_err.status_code == 422, res_wasm_err.text

    # 3. max_rework_attempts = 0 (out of 1..20 bounds) -> 422
    res_rework_err = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Zero Rework Attempts",
            "scope_kind": "system",
            "to_state_name": "Done",
            "max_rework_attempts": 0,
        },
    )
    assert res_rework_err.status_code == 422, res_rework_err.text

    # 4. Whitespace name -> 422
    res_ws_name_err = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "    ",
            "scope_kind": "system",
            "to_state_name": "Done",
        },
    )
    assert res_ws_name_err.status_code == 422, res_ws_name_err.text

    # 5. Invalid hook_kind -> 422
    res_kind_err = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Unknown Kind Template",
            "scope_kind": "system",
            "to_state_name": "Done",
            "hook_kind": "arbitrary_custom_unknown_kind",
        },
    )
    assert res_kind_err.status_code == 422, res_kind_err.text

    # 6. Duplicate template name -> 409
    res_first = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Unique Name Test",
            "scope_kind": "system",
            "to_state_name": "Done",
            "agent": "@reality-checker",
        },
    )
    assert res_first.status_code == 201, res_first.text

    res_dup = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Unique Name Test",
            "scope_kind": "system",
            "to_state_name": "Done",
            "agent": "@reality-checker",
        },
    )
    assert res_dup.status_code == 409, res_dup.text
    assert res_dup.json()["code"] == "TEMPLATE_NAME_CONFLICT"


@pytest.mark.asyncio
async def test_disabled_workspace_template_suppresses_system_template(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify a disabled workspace template with the same name suppresses an enabled system template."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("suppress_admin", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    await _seed_agent(session, ws_id, admin.id, slug="reality-checker")

    # 1. Enabled system template
    res_sys = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Universal Security Check",
            "scope_kind": "system",
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "agent": "@reality-checker",
            "is_enabled": True,
        },
    )
    assert res_sys.status_code == 201, res_sys.text

    # 2. Disabled workspace template with same name
    res_ws = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Universal Security Check",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "agent": "@reality-checker",
            "is_enabled": False,
        },
    )
    assert res_ws.status_code == 201, res_ws.text

    # 3. Create project in this workspace
    res_proj = await client_admin.post(
        "/api/v1/projects",
        json={"name": "Suppression Test Project", "identifier": "SUP1"},
    )
    assert res_proj.status_code == 201, res_proj.text
    proj_id = uuid.UUID(res_proj.json()["id"])

    # 4. Verify hook was NOT created because the workspace template suppressed the system template
    hooks = (
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    hook_names = {h.name for h in hooks}
    assert "Universal Security Check" not in hook_names


@pytest.mark.asyncio
async def test_apply_blueprint_inherits_default_hooks(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify apply_blueprint with is_new_project=True inherits default hook templates."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("bp_adm", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    await _seed_agent(session, ws_id, admin.id, slug="reality-checker")

    # Create default hook template
    res_tpl = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Blueprint Hook Inheritance Gate",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "agent": "@reality-checker",
        },
    )
    assert res_tpl.status_code == 201, res_tpl.text
    tpl_id = res_tpl.json()["id"]

    # Apply blueprint for a new project via admin API
    bp = ProjectBlueprint(
        identifier="BP99",
        name="Blueprint Generated Project",
        states=[
            BlueprintState(name="In Progress", group="started", color="#3b82f6"),
            BlueprintState(name="Done", group="completed", color="#10b981"),
            BlueprintState(name="Canceled", group="cancelled", color="#ef4444"),
        ],
    )
    res_plan = await client_admin.post(
        "/api/v1/admin/projects/blueprint:plan",
        json={"blueprint": bp.model_dump()},
    )
    assert res_plan.status_code == 200, res_plan.text
    plan_sha = res_plan.json()["plan_sha256"]

    res_apply = await client_admin.post(
        "/api/v1/admin/projects/blueprint:apply",
        json={"blueprint": bp.model_dump(), "plan_sha256": plan_sha},
    )
    assert res_apply.status_code == 200, res_apply.text
    proj = (
        await session.execute(
            select(Project).where(
                Project.workspace_id == ws_id,
                Project.identifier == bp.identifier,
            )
        )
    ).scalar_one()
    proj_id = proj.id

    # Verify project has inherited hook
    hooks = list(
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(hooks) >= 1
    inherited = [h for h in hooks if str(h.inherited_from_template_id) == tpl_id]
    assert len(inherited) == 1
    assert inherited[0].name == "Blueprint Hook Inheritance Gate"


@pytest.mark.asyncio
async def test_wasm_and_builtin_default_hooks_inheritance(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify wasm_sync and builtin default hook templates materialize onto new projects."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("wasm_adm", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    qa_wasm_sha = "92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968"
    sec_wasm_sha = "7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874"

    # 1. Create builtin system template
    res_sys = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "System Builtin QA Guard",
            "scope_kind": "system",
            "from_state_name": "*",
            "to_state_name": "Done",
            "hook_kind": "builtin",
            "wasm_module_sha256": qa_wasm_sha,
            "failure_policy": "fail_closed",
        },
    )
    assert res_sys.status_code == 201, res_sys.text
    sys_tpl_id = res_sys.json()["id"]

    # 2. Create wasm_validator workspace template
    res_ws = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Workspace Sec Guard",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "wasm_validator",
            "wasm_module_sha256": sec_wasm_sha,
            "failure_policy": "fail_closed",
        },
    )
    assert res_ws.status_code == 201, res_ws.text
    ws_tpl_id = res_ws.json()["id"]

    # 3. Create project
    res_proj = await client_admin.post(
        "/api/v1/projects",
        json={"name": "WASM Project", "identifier": "WASM1"},
    )
    assert res_proj.status_code == 201, res_proj.text
    proj_id = uuid.UUID(res_proj.json()["id"])

    # 4. Verify hooks materialized onto project
    hooks = list(
        (
            await session.execute(
                select(WorkflowTransitionHook).where(WorkflowTransitionHook.project_id == proj_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(hooks) >= 2
    sys_hook = next((h for h in hooks if str(h.inherited_from_template_id) == sys_tpl_id), None)
    ws_hook = next((h for h in hooks if str(h.inherited_from_template_id) == ws_tpl_id), None)

    assert sys_hook is not None
    assert sys_hook.name == "System Builtin QA Guard"
    assert sys_hook.wasm_module_sha256 == bytes.fromhex(qa_wasm_sha)
    assert sys_hook.agent_definition_id is None

    assert ws_hook is not None
    assert ws_hook.name == "Workspace Sec Guard"
    assert ws_hook.wasm_module_sha256 == bytes.fromhex(sec_wasm_sha)
    assert ws_hook.agent_definition_id is None

    # 5. Verify ApprovedWasmModule was seeded in workspace for both shas
    modules = list(
        (
            await session.execute(
                select(ApprovedWasmModule).where(ApprovedWasmModule.workspace_id == ws_id)
            )
        )
        .scalars()
        .all()
    )
    mod_shas = {m.sha256.hex() for m in modules}
    assert qa_wasm_sha in mod_shas
    assert sec_wasm_sha in mod_shas


@pytest.mark.asyncio
async def test_hook_kind_cross_field_validations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify cross-field validation rules between hook_kind, wasm_module_sha256, and agent targets."""
    session = api_env.seed
    ws_id = api_env.workspace_id
    admin = await make_user("val_adm", workspace_role="SERVER_ADMIN")
    await _enroll_mfa(session, admin.id)
    client_admin = as_principal(admin, aal_level=2)

    qa_wasm_sha = "92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968"

    # 1. wasm_sync missing wasm_module_sha256 -> 422 MISSING_WASM_MODULE
    res = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "WASM No Sha",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "wasm_sync",
        },
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "MISSING_WASM_MODULE"

    # 2. agent_async missing agent target -> 422 MISSING_AGENT_TARGET
    res = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Agent No Target",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "agent_async",
        },
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "MISSING_AGENT_TARGET"

    # 3. agent_async with wasm_module_sha256 -> 422 INVALID_HOOK_TARGET
    res = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Agent With Wasm",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "agent_async",
            "agent": "@reality-checker",
            "wasm_module_sha256": qa_wasm_sha,
        },
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "INVALID_HOOK_TARGET"

    # 4. wasm_sync with agent -> 422 INVALID_HOOK_TARGET
    res = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Wasm With Agent",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "wasm_sync",
            "wasm_module_sha256": qa_wasm_sha,
            "agent": "@reality-checker",
        },
    )
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "INVALID_HOOK_TARGET"

    # 5. Create valid agent template, then PATCH with wasm_module_sha256 -> 422 INVALID_HOOK_TARGET
    res_agent = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Valid Agent Hook",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "agent_async",
            "agent": "@reality-checker",
        },
    )
    assert res_agent.status_code == 201, res_agent.text
    agent_tpl_id = res_agent.json()["id"]

    res_patch = await client_admin.patch(
        f"/api/v1/admin/default-workflow-hooks/{agent_tpl_id}",
        json={"wasm_module_sha256": qa_wasm_sha},
    )
    assert res_patch.status_code == 422, res_patch.text
    assert res_patch.json()["code"] == "INVALID_HOOK_TARGET"

    # 6. Create valid wasm template, then PATCH with agent -> 422 INVALID_HOOK_TARGET
    res_wasm = await client_admin.post(
        "/api/v1/admin/default-workflow-hooks",
        json={
            "name": "Valid Wasm Hook",
            "scope_kind": "workspace",
            "workspace_id": str(ws_id),
            "from_state_name": "In Progress",
            "to_state_name": "Done",
            "hook_kind": "wasm_sync",
            "wasm_module_sha256": qa_wasm_sha,
        },
    )
    assert res_wasm.status_code == 201, res_wasm.text
    wasm_tpl_id = res_wasm.json()["id"]

    res_patch_wasm = await client_admin.patch(
        f"/api/v1/admin/default-workflow-hooks/{wasm_tpl_id}",
        json={"agent": "@reality-checker"},
    )
    assert res_patch_wasm.status_code == 422, res_patch_wasm.text
    assert res_patch_wasm.json()["code"] == "INVALID_HOOK_TARGET"

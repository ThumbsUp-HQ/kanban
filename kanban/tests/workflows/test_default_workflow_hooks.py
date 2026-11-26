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
from database.models.workflow import DefaultWorkflowHook, WorkflowTransitionHook

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

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

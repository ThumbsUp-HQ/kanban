# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit test suite for Standard User vs Admin RBAC matrix (KANBA-202)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.admin.principal_service import bind_role
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.tests.security.helpers import create_workspace

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def test_auth_me_role_and_capabilities_matrix(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify GET /api/v1/auth/me returns role and capabilities across all principal tiers."""
    del api_env
    # 1. Standard user (WORKSPACE_MEMBER)
    member = await make_user("standard_user", workspace_role="WORKSPACE_MEMBER")
    client_member = as_principal(member)
    res_mem = await client_member.get("/api/v1/auth/me")
    assert res_mem.status_code == 200
    data_mem = res_mem.json()
    assert data_mem["is_server_admin"] is False
    assert data_mem["is_workspace_admin"] is False
    assert data_mem["workspace_role"] == "WORKSPACE_MEMBER"
    assert "CREATE_PROJECT" in data_mem["workspace_capabilities"]
    assert "MANAGE_WORKSPACE_SETTINGS" not in data_mem["workspace_capabilities"]
    assert "ADMIN_AUTH_STUDIO" not in data_mem["workspace_capabilities"]

    # 2. Workspace Admin
    ws_admin = await make_user("ws_admin_user", workspace_role="WORKSPACE_ADMIN")
    client_ws_admin = as_principal(ws_admin, aal_level=2)
    res_ws = await client_ws_admin.get("/api/v1/auth/me")
    assert res_ws.status_code == 200
    data_ws = res_ws.json()
    assert data_ws["is_server_admin"] is False
    assert data_ws["is_workspace_admin"] is True
    assert data_ws["workspace_role"] == "WORKSPACE_ADMIN"
    assert "CREATE_PROJECT" in data_ws["workspace_capabilities"]
    assert "MANAGE_WORKSPACE_SETTINGS" in data_ws["workspace_capabilities"]
    assert "MANAGE_WORKSPACE_MCP_KEYS" in data_ws["workspace_capabilities"]
    assert "ADMIN_AUTH_STUDIO" not in data_ws["workspace_capabilities"]

    # 3. Server Admin
    srv_admin = await make_user("srv_admin_user", workspace_role="SERVER_ADMIN")
    client_srv_admin = as_principal(srv_admin, aal_level=2)
    res_srv = await client_srv_admin.get("/api/v1/auth/me")
    assert res_srv.status_code == 200
    data_srv = res_srv.json()
    assert data_srv["is_server_admin"] is True
    assert data_srv["is_workspace_admin"] is True
    assert data_srv["workspace_role"] == "SERVER_ADMIN"
    assert "MANAGE_SERVER_ADMIN" in data_srv["workspace_capabilities"]
    assert "ADMIN_AUTH_STUDIO" in data_srv["workspace_capabilities"]
    assert "SYSTEM_STORAGE" in data_srv["workspace_capabilities"]


async def test_project_response_is_project_admin_and_role(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify ProjectResponse includes is_project_admin and project_role."""
    del api_env
    admin = await make_user("proj_owner", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("proj_member", workspace_role="WORKSPACE_MEMBER")

    client_admin = as_principal(admin)
    p_res = await client_admin.post(
        "/api/v1/projects",
        json={"identifier": "RBAC", "name": "RBAC Studio", "description_markdown": "Test"},
    )
    assert p_res.status_code == 201
    proj_body = p_res.json()
    assert proj_body["is_project_admin"] is True
    assert proj_body["project_role"] == "PROJECT_ADMIN"

    # Add member as VIEWER
    add_res = await client_admin.post(
        "/api/v1/projects/RBAC/members",
        json={"principal_id": str(member.id), "role": "VIEWER"},
    )
    assert add_res.status_code == 201

    # Member reads project
    client_mem = as_principal(member)
    get_res = await client_mem.get("/api/v1/projects/RBAC")
    assert get_res.status_code == 200
    mem_proj = get_res.json()
    assert mem_proj["is_project_admin"] is False
    assert mem_proj["project_role"] == "VIEWER"


async def test_project_members_crud_and_capability_gating(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify GET, POST, DELETE /api/v1/projects/{ref}/members capability enforcement."""
    del api_env
    admin = await make_user("admin_lead", workspace_role="WORKSPACE_ADMIN")
    p_res = await as_principal(admin).post(
        "/api/v1/projects",
        json={"identifier": "MEM", "name": "Member Project", "description_markdown": "Desc"},
    )
    assert p_res.status_code == 201
    member_a = await make_user("user_a", workspace_role="WORKSPACE_MEMBER")
    member_b = await make_user("user_b", workspace_role="WORKSPACE_MEMBER")

    # 1. Project Admin adds member_a
    add_a = await as_principal(admin).post(
        "/api/v1/projects/MEM/members",
        json={"principal_id": str(member_a.id), "role": "MEMBER"},
    )
    assert add_a.status_code == 201
    assert add_a.json()["role"] == "MEMBER"
    assert add_a.json()["principal_id"] == str(member_a.id)

    # 2. Member A cannot add member_b (403 INSUFFICIENT_CAPABILITY)
    denied_add = await as_principal(member_a).post(
        "/api/v1/projects/MEM/members",
        json={"principal_id": str(member_b.id), "role": "VIEWER"},
    )
    assert denied_add.status_code == 403
    assert denied_add.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. List members
    list_res = await as_principal(member_a).get("/api/v1/projects/MEM/members")
    assert list_res.status_code == 200
    members_data = list_res.json()
    assert any(m["principal_id"] == str(member_a.id) for m in members_data)

    # 4. Member A cannot delete member_a (403 INSUFFICIENT_CAPABILITY)
    denied_del = await as_principal(member_a).delete(f"/api/v1/projects/MEM/members/{member_a.id}")
    assert denied_del.status_code == 403
    assert denied_del.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 5. Project Admin deletes member_a (204)
    ok_del = await as_principal(admin).delete(f"/api/v1/projects/MEM/members/{member_a.id}")
    assert ok_del.status_code == 204


async def test_workspace_admin_cannot_grant_server_admin(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Verify WORKSPACE_ADMIN cannot bind SERVER_ADMIN role (403 INSUFFICIENT_CAPABILITY)."""
    ws_admin = await make_user("mid_admin", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("normal_user", workspace_role="WORKSPACE_MEMBER")

    with pytest.raises(ProblemException) as exc_info:
        await bind_role(
            api_env.seed,
            workspace_id=api_env.workspace_id,
            actor_id=ws_admin.id,
            principal_id=target_user.id,
            role_name="SERVER_ADMIN",
            scope_type="server",
        )
    assert exc_info.value.status == 403
    assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"


async def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b" " + b"0" * 28,
            "dek": b" " + b"0" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )


async def test_workspace_settings_update_name_slug_and_conflict(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify workspace name/slug updates and duplicate slug rejection."""
    admin = await make_user("ws_settings_admin", workspace_role="WORKSPACE_ADMIN")
    standard_user = await make_user("regular_user", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)
    client_admin = api_env.client

    # 1. Update name and slug via PATCH /api/v1/admin/workspace-settings
    patch_res = await client_admin.patch(
        "/api/v1/admin/workspace-settings",
        json={"name": "Engineering Alpha", "slug": "eng-alpha"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["name"] == "Engineering Alpha"
    assert data["slug"] == "eng-alpha"

    # 2. Duplicate slug conflict via PATCH /api/v1/workspaces/{id}
    # Create another workspace first via seed session
    ws_other_id = await create_workspace(api_env.seed, name="Other Team")
    await api_env.seed.execute(
        text("UPDATE workspaces SET slug = 'other-team' WHERE id = :id"),
        {"id": ws_other_id},
    )
    await api_env.seed.commit()

    # Attempt to change current workspace slug to 'other-team' -> 409 WORKSPACE_SLUG_CONFLICT
    conflict_res = await client_admin.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}",
        json={"slug": "other-team"},
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["code"] == "WORKSPACE_SLUG_CONFLICT"

    # 3. Standard user denied PATCH /api/v1/workspaces/{id} -> 403 INSUFFICIENT_CAPABILITY
    denied_patch = await as_principal(standard_user).patch(
        f"/api/v1/workspaces/{api_env.workspace_id}",
        json={"name": "Hacked Name"},
    )
    assert denied_patch.status_code == 403
    assert denied_patch.json()["code"] == "INSUFFICIENT_CAPABILITY"

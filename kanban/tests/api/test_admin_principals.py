# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Principals & Groups REST API (KB-P4-09b)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text

from database.models import Principal as DBPrincipal
from database.models.auth import UserSession
from database.models.mcp_api_key import McpApiKey
from kanban.admin.principal_service import (
    add_group_member,
    bind_role,
    get_principal_detail,
    list_principals,
    normalize_handle,
    provision_agent,
    provision_group,
    provision_user,
    remove_group_member,
    resolve_principal_id,
    unbind_role,
    update_principal,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.app import create_app
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.tests.security.helpers import (
    create_project,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
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


@pytest.mark.asyncio
async def test_admin_routes_protected() -> None:
    """Audit route table to verify all /api/v1/admin/* routes require AAL2."""
    app = create_app()
    assert_admin_routes_protected(app)


@pytest.mark.asyncio
async def test_principals_lifecycle_and_group_membership(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test provisioning user, group, agent, adding member, binding role, and querying detail."""
    admin = await make_user("admin_user", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Provision user maya
    resp_user = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "maya",
            "display_name": "Maya Lin",
            "email": "maya@example.com",
        },
    )
    assert resp_user.status_code == 201
    user_data = resp_user.json()
    assert user_data["principal"] == "@maya"
    maya_id = user_data["id"]

    # 2. Provision group Core Backend
    resp_group = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "GROUP",
            "display_name": "Core Backend",
        },
    )
    assert resp_group.status_code == 201
    group_data = resp_group.json()
    assert group_data["principal"] == "Core Backend"
    group_id = group_data["id"]

    # 3. Provision agent forensic-code-check
    resp_agent = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "AGENT",
            "handle": "forensic-code-check",
            "display_name": "Forensic Code Checker",
        },
    )
    assert resp_agent.status_code == 201
    agent_data = resp_agent.json()
    assert agent_data["principal"] == "@forensic-code-check"

    # 4. List principals
    resp_list = await api_env.client.get("/api/v1/admin/principals")
    assert resp_list.status_code == 200
    p_list = resp_list.json()
    handles = [p["principal"] for p in p_list]
    assert "@maya" in handles
    assert "Core Backend" in handles
    assert "@forensic-code-check" in handles

    # 5. Add maya to Core Backend
    resp_member = await api_env.client.post(f"/api/v1/admin/groups/{group_id}/members/{maya_id}")
    assert resp_member.status_code == 200
    assert resp_member.json()["status"] == "member_added"

    # 6. Verify maya detail shows group Core Backend
    resp_maya = await api_env.client.get(f"/api/v1/admin/principals/{maya_id}")
    assert resp_maya.status_code == 200
    maya_detail = resp_maya.json()
    assert "Core Backend" in maya_detail["groups"]

    # 7. Create project KAN and bind role MEMBER to maya on KAN
    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="KAN", name="Kanban Project"
    )
    await api_env.seed.commit()

    resp_bind = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": maya_id,
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(prj_id),
        },
    )
    assert resp_bind.status_code == 200

    # 8. Check maya roles in detail
    resp_maya2 = await api_env.client.get(f"/api/v1/admin/principals/{maya_id}")
    maya_roles = resp_maya2.json()["roles"]
    assert any(r["role"] == "MEMBER" and r["scope"] == "KAN" for r in maya_roles)


@pytest.mark.asyncio
async def test_principal_deactivation_sessions_and_mcp_keys_revoked(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Deactivating a user revokes user sessions and MCP keys in same transaction."""
    admin = await make_user("admin_deact", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("target_to_deact", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)

    # Seed an active session for target_user
    sess_id = uuid.uuid4()
    api_env.seed.add(
        UserSession(
            id=sess_id,
            token_sha256=b"x" * 32,
            principal_id=target_user.id,
            workspace_id=target_user.workspace_id,
            aal_level=1,
            idle_expires_at=func.clock_timestamp() + text("interval '1 hour'"),
            absolute_expires_at=func.clock_timestamp() + text("interval '12 hours'"),
        )
    )

    # Seed an active MCP API key for target_user
    key_id = uuid.uuid4()
    api_env.seed.add(
        McpApiKey(
            id=key_id,
            workspace_id=target_user.workspace_id,
            principal_id=target_user.id,
            surface="agent",
            key_prefix="kb_agt_",
            key_sha256=b"y" * 32,
            display_hint="1234",
            scopes=["agent:read"],
            created_by_id=admin.id,
            expires_at=func.clock_timestamp() + text("interval '90 days'"),
        )
    )
    await api_env.seed.commit()

    # Deactivate target user
    resp = await api_env.client.patch(
        f"/api/v1/admin/principals/{target_user.id}",
        json={"status": "deactivated"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"

    # Verify session is revoked
    sess_revoked = (
        await api_env.seed.execute(select(UserSession.revoked_at).where(UserSession.id == sess_id))
    ).scalar_one()
    assert sess_revoked is not None

    # Verify session does not resolve
    resolved = (
        await api_env.seed.execute(
            text("SELECT id FROM kb_auth.session_resolve(:sha)"),
            {"sha": b"x" * 32},
        )
    ).first()
    assert resolved is None

    # Verify MCP key is revoked
    key_revoked = (
        await api_env.seed.execute(select(McpApiKey.revoked_at).where(McpApiKey.id == key_id))
    ).scalar_one()
    assert key_revoked is not None


@pytest.mark.asyncio
async def test_lockout_prevented_on_last_server_admin(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Deactivating or unbinding the last SERVER_ADMIN returns 409 LOCKOUT_PREVENTED."""
    admin = await make_user("solo_admin", workspace_role="SERVER_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Attempt to deactivate last server admin
    resp = await api_env.client.patch(
        f"/api/v1/admin/principals/{admin.id}",
        json={"status": "deactivated"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "LOCKOUT_PREVENTED"
    assert "SERVER_ADMIN" in body["detail"]

    # 2. Attempt to unbind SERVER_ADMIN role
    resp_unbind = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(admin.id),
            "role": "SERVER_ADMIN",
            "scope_type": "server",
        },
    )
    assert resp_unbind.status_code == 409
    assert resp_unbind.json()["code"] == "LOCKOUT_PREVENTED"


@pytest.mark.asyncio
async def test_group_cycle_and_depth_limits(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Cycle detection returns GROUP_CYCLE_REJECTED and depth > 8 returns GROUP_DEPTH_EXCEEDED."""
    admin = await make_user("admin_closure", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Create group A and group B
    r_a = await api_env.client.post(
        "/api/v1/admin/principals", json={"type": "GROUP", "display_name": "Group A"}
    )
    r_b = await api_env.client.post(
        "/api/v1/admin/principals", json={"type": "GROUP", "display_name": "Group B"}
    )
    id_a = r_a.json()["id"]
    id_b = r_b.json()["id"]

    # Add B as member of A (A contains B)
    r_add1 = await api_env.client.post(f"/api/v1/admin/groups/{id_a}/members/{id_b}")
    assert r_add1.status_code == 200

    # Add A as member of B (B contains A -> cycle!)
    r_add2 = await api_env.client.post(f"/api/v1/admin/groups/{id_b}/members/{id_a}")
    assert r_add2.status_code == 409
    assert r_add2.json()["code"] == "GROUP_CYCLE_REJECTED"

    # Self-membership cycle
    r_self = await api_env.client.post(f"/api/v1/admin/groups/{id_a}/members/{id_a}")
    assert r_self.status_code == 409
    assert r_self.json()["code"] == "GROUP_CYCLE_REJECTED"


@pytest.mark.asyncio
async def test_principals_boundary_validations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Boundary checks: handle syntax, empty display_name, limit bounds."""
    admin = await make_user("admin_bound", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # Bad handle format
    resp_bad = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "-invalid_start",
            "display_name": "Bad Handle User",
            "email": "bad@example.com",
        },
    )
    assert resp_bad.status_code == 422

    # Limit > 100
    resp_lim = await api_env.client.get("/api/v1/admin/principals?limit=101")
    assert resp_lim.status_code == 422

    # Limit < 1
    resp_lim0 = await api_env.client.get("/api/v1/admin/principals?limit=0")
    assert resp_lim0.status_code == 422

    # Invalid filter
    resp_filt = await api_env.client.get("/api/v1/admin/principals?filter=INVALID_TYPE")
    assert resp_filt.status_code == 422

    # Missing handle for USER
    r_no_handle = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "USER", "display_name": "No Handle", "email": "nohandle@example.com"},
    )
    assert r_no_handle.status_code == 422

    # Missing email for USER
    r_no_email = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "USER", "handle": "nohandle", "display_name": "No Email"},
    )
    assert r_no_email.status_code == 422

    # Unsupported principal type
    r_bad_type = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "SUPER_HERO", "display_name": "Superman"},
    )
    assert r_bad_type.status_code == 422

    # Invalid email format
    r_bad_email = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "bademail",
            "display_name": "Bad Email",
            "email": "not-an-email",
        },
    )
    assert r_bad_email.status_code == 422

    # Display name length bounds (< 1 or > 120)
    r_empty_dn = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "emptydn",
            "display_name": "   ",
            "email": "empty@example.com",
        },
    )
    assert r_empty_dn.status_code == 422

    r_long_dn = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "longdn",
            "display_name": "x" * 121,
            "email": "long@example.com",
        },
    )
    assert r_long_dn.status_code == 422


@pytest.mark.asyncio
async def test_principals_conflict_identifiers(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Duplicate email, handle, group name, and agent slug raise 409 CONFLICT_IDENTIFIER."""
    admin = await make_user("admin_conflicts", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Provision user alice
    r1 = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "alice",
            "display_name": "Alice M",
            "email": "alice@example.com",
        },
    )
    assert r1.status_code == 201

    # Duplicate email
    r_dup_email = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "alice2",
            "display_name": "Alice 2",
            "email": "alice@example.com",
        },
    )
    assert r_dup_email.status_code == 409
    assert r_dup_email.json()["code"] == "CONFLICT_IDENTIFIER"

    # Duplicate handle
    r_dup_handle = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "alice",
            "display_name": "Alice 3",
            "email": "alice3@example.com",
        },
    )
    assert r_dup_handle.status_code == 409
    assert r_dup_handle.json()["code"] == "CONFLICT_IDENTIFIER"

    # 2. Provision group Devs
    r_grp1 = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "GROUP", "display_name": "Devs"},
    )
    assert r_grp1.status_code == 201

    # Duplicate group name
    r_grp2 = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "GROUP", "display_name": "Devs"},
    )
    assert r_grp2.status_code == 409
    assert r_grp2.json()["code"] == "CONFLICT_IDENTIFIER"

    # 3. Provision agent bot-a
    r_agt1 = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "AGENT", "handle": "bot-a", "display_name": "Bot A"},
    )
    assert r_agt1.status_code == 201

    # Duplicate agent slug
    r_agt2 = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "AGENT", "handle": "bot-a", "display_name": "Bot A Again"},
    )
    assert r_agt2.status_code == 409
    assert r_agt2.json()["code"] == "CONFLICT_IDENTIFIER"


@pytest.mark.asyncio
async def test_principals_patch_and_reactivation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test updating display_name, deactivation, and reactivation."""
    admin = await make_user("admin_patch", workspace_role="WORKSPACE_ADMIN")
    user = await make_user("user_patch", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)

    # 1. Update display name
    r_patch_name = await api_env.client.patch(
        f"/api/v1/admin/principals/{user.id}",
        json={"display_name": "Updated User Patch Name"},
    )
    assert r_patch_name.status_code == 200
    assert r_patch_name.json()["display_name"] == "Updated User Patch Name"

    # 2. Deactivate
    r_deact = await api_env.client.patch(
        f"/api/v1/admin/principals/{user.id}",
        json={"status": "deactivated"},
    )
    assert r_deact.status_code == 200
    assert r_deact.json()["status"] == "deactivated"

    # 3. Reactivate
    r_react = await api_env.client.patch(
        f"/api/v1/admin/principals/{user.id}",
        json={"status": "active"},
    )
    assert r_react.status_code == 200
    assert r_react.json()["status"] == "active"

    # 4. Invalid status
    r_bad_status = await api_env.client.patch(
        f"/api/v1/admin/principals/{user.id}",
        json={"status": "sleeping"},
    )
    assert r_bad_status.status_code == 422

    # 5. Invalid display name in patch
    r_bad_dn = await api_env.client.patch(
        f"/api/v1/admin/principals/{user.id}",
        json={"display_name": ""},
    )
    assert r_bad_dn.status_code == 422

    # 6. Non-existent principal patch
    r_non_exist = await api_env.client.patch(
        f"/api/v1/admin/principals/{uuid.uuid4()}",
        json={"display_name": "Ghost"},
    )
    assert r_non_exist.status_code == 404


@pytest.mark.asyncio
async def test_remove_group_member_and_role_bindings_matrix(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test group member removal, role binding validation errors, idempotent binds, and unbinds."""
    admin = await make_user("admin_rb_matrix", workspace_role="WORKSPACE_ADMIN")
    user = await make_user("user_rb_matrix", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="PRJ", name="Project PRJ"
    )
    await api_env.seed.commit()

    # 1. Provision group and add user
    r_grp = await api_env.client.post(
        "/api/v1/admin/principals", json={"type": "GROUP", "display_name": "Test Group"}
    )
    grp_id = r_grp.json()["id"]

    await api_env.client.post(f"/api/v1/admin/groups/{grp_id}/members/{user.id}")

    # Remove group member
    r_rm = await api_env.client.delete(f"/api/v1/admin/groups/{grp_id}/members/{user.id}")
    assert r_rm.status_code == 200
    assert r_rm.json()["status"] == "member_removed"

    # Remove again (rowcount 0, idempotent)
    r_rm2 = await api_env.client.delete(f"/api/v1/admin/groups/{grp_id}/members/{user.id}")
    assert r_rm2.status_code == 200

    # 2. Role binding validation errors
    # Invalid scope_type
    r_bad_st = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(user.id), "role": "MEMBER", "scope_type": "galactic"},
    )
    assert r_bad_st.status_code == 422

    # Invalid role name
    r_bad_role = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(user.id), "role": "OVERLORD", "scope_type": "workspace"},
    )
    assert r_bad_role.status_code == 422

    # Server scope with invalid role
    r_srv_bad = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(user.id), "role": "WORKSPACE_MEMBER", "scope_type": "server"},
    )
    assert r_srv_bad.status_code == 422

    # Workspace scope with project_id
    r_ws_proj = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "WORKSPACE_MEMBER",
            "scope_type": "workspace",
            "scope_id": str(prj_id),
        },
    )
    assert r_ws_proj.status_code == 422

    # Project scope without project_id
    r_prj_none = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(user.id), "role": "MEMBER", "scope_type": "project"},
    )
    assert r_prj_none.status_code == 422

    # Project scope with invalid project_id
    r_prj_ghost = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(uuid.uuid4()),
        },
    )
    assert r_prj_ghost.status_code == 404

    # Valid bind
    r_bind = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(prj_id),
        },
    )
    assert r_bind.status_code == 200
    assert r_bind.json()["status"] == "role_bound"

    # Bind again -> already_bound
    r_bind_dup = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(prj_id),
        },
    )
    assert r_bind_dup.status_code == 200
    assert r_bind_dup.json()["status"] == "already_bound"

    # Unbind role with invalid role name
    r_ub_bad = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(user.id), "role": "INVALID", "scope_type": "project"},
    )
    assert r_ub_bad.status_code == 422

    # Unbind role success
    r_ub = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(prj_id),
        },
    )
    assert r_ub.status_code == 200
    assert r_ub.json()["status"] == "role_unbound"

    # Unbind non-existent role binding
    r_ub_none = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/role-bindings",
        json={
            "principal_id": str(user.id),
            "role": "MEMBER",
            "scope_type": "project",
            "scope_id": str(prj_id),
        },
    )
    assert r_ub_none.status_code == 200


@pytest.mark.asyncio
async def test_resolve_principal_and_filters(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test resolving principal by various formats and filtering lists."""
    admin = await make_user("admin_res", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Provision group and agent
    r_g = await api_env.client.post(
        "/api/v1/admin/principals", json={"type": "GROUP", "display_name": "Infra Team"}
    )
    g_id = r_g.json()["id"]

    r_a = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "AGENT", "handle": "sec-bot", "display_name": "Security Bot"},
    )
    a_id = r_a.json()["id"]

    # Resolve group by name
    r_g_get = await api_env.client.get(f"/api/v1/admin/principals/{g_id}")
    assert r_g_get.status_code == 200
    assert r_g_get.json()["principal"] == "Infra Team"

    # Resolve agent by slug
    r_a_get = await api_env.client.get(f"/api/v1/admin/principals/{a_id}")
    assert r_a_get.status_code == 200
    assert r_a_get.json()["principal"] == "@sec-bot"

    # List with filters
    r_list_u = await api_env.client.get("/api/v1/admin/principals?filter=USER")
    assert r_list_u.status_code == 200
    assert all(p["type"] == "USER" for p in r_list_u.json())

    r_list_g = await api_env.client.get("/api/v1/admin/principals?filter=GROUP")
    assert r_list_g.status_code == 200
    assert all(p["type"] == "GROUP" for p in r_list_g.json())

    r_list_a = await api_env.client.get("/api/v1/admin/principals?filter=AGENT")
    assert r_list_a.status_code == 200
    assert all(p["type"] == "AGENT" for p in r_list_a.json())

    # Non-existent principal
    r_ghost = await api_env.client.get(f"/api/v1/admin/principals/{uuid.uuid4()}")
    assert r_ghost.status_code == 404


@pytest.mark.asyncio
async def test_principal_service_unit_edge_cases(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Direct unit testing of principal_service edge cases and validation branches."""
    admin = await make_user("admin_srv_edge", workspace_role="WORKSPACE_ADMIN")
    user = await make_user("user_srv_edge", workspace_role="WORKSPACE_MEMBER")

    # 1. normalize_handle
    assert normalize_handle("@valid_handle") == "valid_handle"
    assert normalize_handle("valid.name-123") == "valid.name-123"
    with pytest.raises(ProblemException) as exc:
        normalize_handle("-invalid")
    assert exc.value.code == "VALIDATION_FAILED"

    # 2. resolve_principal_id by display name
    resolved_by_dn = await resolve_principal_id(api_env.seed, admin.workspace_id, "User_srv_edge")
    assert resolved_by_dn == user.id

    with pytest.raises(ProblemException) as exc:
        await resolve_principal_id(api_env.seed, admin.workspace_id, "NonExistentGhost")
    assert exc.value.code == "NOT_FOUND"

    # 3. get_principal_detail for group and agent
    g_info = await provision_group(
        api_env.seed, admin.workspace_id, admin.id, name="Service Edge Group"
    )
    g_detail = await get_principal_detail(api_env.seed, admin.workspace_id, g_info["id"])
    assert g_detail["type"] == "GROUP"
    assert g_detail["principal"] == "Service Edge Group"

    a_info = await provision_agent(
        api_env.seed, admin.workspace_id, admin.id, handle="edge-agent", display_name="Edge Agent"
    )
    a_detail = await get_principal_detail(api_env.seed, admin.workspace_id, a_info["id"])
    assert a_detail["type"] == "AGENT"
    assert a_detail["principal"] == "@edge-agent"

    # 4. list_principals validation
    with pytest.raises(ProblemException) as exc:
        await list_principals(api_env.seed, admin.workspace_id, limit=0)
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await list_principals(api_env.seed, admin.workspace_id, limit=101)
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await list_principals(api_env.seed, admin.workspace_id, filter_type="INVALID")
    assert exc.value.code == "VALIDATION_FAILED"

    # 5. provision_group & provision_agent length validation
    with pytest.raises(ProblemException) as exc:
        await provision_group(api_env.seed, admin.workspace_id, admin.id, name="")
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await provision_group(api_env.seed, admin.workspace_id, admin.id, name="g" * 121)
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await provision_agent(
            api_env.seed, admin.workspace_id, admin.id, handle="bot", display_name=""
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await provision_agent(
            api_env.seed, admin.workspace_id, admin.id, handle="bot", display_name="b" * 121
        )
    assert exc.value.code == "VALIDATION_FAILED"

    # 6. update_principal validation
    with pytest.raises(ProblemException) as exc:
        await update_principal(api_env.seed, admin.workspace_id, admin.id, user.id, display_name="")
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await update_principal(
            api_env.seed, admin.workspace_id, admin.id, user.id, display_name="u" * 121
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await update_principal(
            api_env.seed, admin.workspace_id, admin.id, user.id, status="invalid_status"
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await update_principal(
            api_env.seed, admin.workspace_id, admin.id, uuid.uuid4(), display_name="Ghost"
        )
    assert exc.value.code == "NOT_FOUND"

    # 7. add_group_member not found branches
    with pytest.raises(ProblemException) as exc:
        await add_group_member(api_env.seed, admin.workspace_id, admin.id, uuid.uuid4(), user.id)
    assert exc.value.code == "NOT_FOUND"

    with pytest.raises(ProblemException) as exc:
        await add_group_member(
            api_env.seed, admin.workspace_id, admin.id, uuid.UUID(g_info["id"]), uuid.uuid4()
        )
    assert exc.value.code == "NOT_FOUND"

    # 8. bind_role validation branches
    with pytest.raises(ProblemException) as exc:
        await bind_role(
            api_env.seed, admin.workspace_id, admin.id, uuid.uuid4(), "MEMBER", "workspace"
        )
    assert exc.value.code == "NOT_FOUND"

    with pytest.raises(ProblemException) as exc:
        await bind_role(
            api_env.seed, admin.workspace_id, admin.id, user.id, "MEMBER", "invalid_scope"
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await bind_role(
            api_env.seed, admin.workspace_id, admin.id, user.id, "INVALID_ROLE", "workspace"
        )
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await bind_role(api_env.seed, admin.workspace_id, admin.id, user.id, "MEMBER", "server")
    assert exc.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc:
        await bind_role(
            api_env.seed, admin.workspace_id, admin.id, user.id, "SERVER_ADMIN", "workspace"
        )
    assert exc.value.code == "VALIDATION_FAILED"

    # 9. unbind_role invalid role and idempotent removal
    with pytest.raises(ProblemException) as exc:
        await unbind_role(
            api_env.seed, admin.workspace_id, admin.id, user.id, "INVALID_ROLE", "workspace"
        )
    assert exc.value.code == "VALIDATION_FAILED"

    unb_res = await unbind_role(
        api_env.seed, admin.workspace_id, admin.id, uuid.uuid4(), "MEMBER", "workspace"
    )
    assert unb_res["status"] == "role_unbound"

    # 10. resolve_principal_id branches: agent slug, display name, and not found
    agent_info = await provision_agent(
        api_env.seed,
        admin.workspace_id,
        admin.id,
        handle="res-agent",
        display_name="Resolved Agent",
    )
    p_by_slug = await resolve_principal_id(api_env.seed, admin.workspace_id, "res-agent")
    assert p_by_slug == uuid.UUID(agent_info["id"])

    p_by_dn = await resolve_principal_id(api_env.seed, admin.workspace_id, "resolved agent")
    assert p_by_dn == uuid.UUID(agent_info["id"])

    with pytest.raises(ProblemException) as exc:
        await resolve_principal_id(api_env.seed, admin.workspace_id, "nonexistent-principal-xyz")
    assert exc.value.code == "NOT_FOUND"

    # 11. add_group_member idempotent branch
    idemp = await add_group_member(
        api_env.seed, admin.workspace_id, admin.id, uuid.UUID(g_info["id"]), user.id
    )
    assert idemp["status"] == "member_added"

    # 12. remove_group_member idempotent removal
    rem_res = await remove_group_member(
        api_env.seed, admin.workspace_id, admin.id, uuid.uuid4(), user.id
    )
    assert rem_res["status"] == "member_removed"

    # 13. provision duplicate conflicts
    await provision_user(
        api_env.seed,
        admin.workspace_id,
        admin.id,
        handle="dupe_user",
        display_name="Dupe",
        email="dupe@example.com",
    )
    with pytest.raises(ProblemException) as exc:
        async with api_env.seed.begin_nested():
            await provision_user(
                api_env.seed,
                admin.workspace_id,
                admin.id,
                handle="dupe_user",
                display_name="Other",
                email="other@example.com",
            )
    assert exc.value.code == "CONFLICT_IDENTIFIER"

    with pytest.raises(ProblemException) as exc:
        async with api_env.seed.begin_nested():
            await provision_group(
                api_env.seed, admin.workspace_id, admin.id, name="Service Edge Group"
            )
    assert exc.value.code == "CONFLICT_IDENTIFIER"

    with pytest.raises(ProblemException) as exc:
        async with api_env.seed.begin_nested():
            await provision_agent(
                api_env.seed,
                admin.workspace_id,
                admin.id,
                handle="res-agent",
                display_name="Other Agent",
            )
    assert exc.value.code == "CONFLICT_IDENTIFIER"

    # 14. get_principal_detail SCRIPT_EPHEMERAL rejection
    eph_id = uuid.uuid4()
    p_eph = DBPrincipal(
        id=eph_id,
        workspace_id=admin.workspace_id,
        principal_type="SCRIPT_EPHEMERAL",
        status="ACTIVE",
        display_name="Ephemeral Script Principal",
    )
    api_env.seed.add(p_eph)
    await api_env.seed.commit()
    with pytest.raises(ProblemException) as exc:
        await get_principal_detail(api_env.seed, admin.workspace_id, str(eph_id))
    assert exc.value.code == "NOT_FOUND"

    # 15. Group nesting depth limit (8 levels)
    async def _exhaust_group_depth() -> None:
        curr_g = g_info["id"]
        for idx in range(10):
            next_g = await provision_group(
                api_env.seed, admin.workspace_id, admin.id, name=f"Depth Group {idx}"
            )
            await add_group_member(
                api_env.seed,
                admin.workspace_id,
                admin.id,
                uuid.UUID(next_g["id"]),
                uuid.UUID(curr_g),
            )
            curr_g = next_g["id"]

    with pytest.raises(ProblemException) as depth_exc:
        await _exhaust_group_depth()
    assert depth_exc.value.code in ("GROUP_DEPTH_EXCEEDED", "GROUP_CYCLE_REJECTED")

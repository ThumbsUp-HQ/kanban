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
    _format_principal_entry,
    _highest_role,
    _resolve_provider_label,
    _slugify_or_default,
    _validate_principal_filter,
    add_group_member,
    bind_role,
    get_principal_detail,
    list_group_members,
    list_principals,
    normalize_handle,
    provision_agent,
    provision_group,
    provision_user,
    remove_group_member,
    reset_password,
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
async def test_principals_lifecycle_and_group_membership(  # noqa: PLR0915
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

    maya_p = next(p for p in p_list if p["principal"] == "@maya")
    assert maya_p["handle"] == "@maya"
    assert maya_p["email"] == "maya@example.com"
    assert maya_p["role"] == "WORKSPACE_MEMBER"
    assert maya_p["provider"] == "LOCAL"

    backend_p = next(p for p in p_list if p["principal"] == "Core Backend")
    assert backend_p["handle"] == "@Core Backend"
    assert backend_p["email"] is None
    assert backend_p["role"] == "WORKSPACE_MEMBER"
    assert backend_p["provider"] == "LOCAL"

    agent_p = next(p for p in p_list if p["principal"] == "@forensic-code-check")
    assert agent_p["handle"] == "@forensic-code-check"
    assert agent_p["email"] is None
    assert agent_p["role"] == "WORKSPACE_MEMBER"
    assert agent_p["provider"] == "LOCAL"

    # 5. Add maya to Core Backend
    resp_member = await api_env.client.post(f"/api/v1/admin/groups/{group_id}/members/{maya_id}")
    assert resp_member.status_code == 200
    assert resp_member.json()["status"] == "member_added"

    # 5b. GET group members verifying handle, email, role, provider
    resp_members = await api_env.client.get(f"/api/v1/admin/groups/{group_id}/members")
    assert resp_members.status_code == 200
    m_list = resp_members.json()
    assert len(m_list) == 1
    assert m_list[0]["principal"] == "@maya"
    assert m_list[0]["handle"] == "@maya"
    assert m_list[0]["email"] == "maya@example.com"
    assert m_list[0]["role"] == "WORKSPACE_MEMBER"
    assert m_list[0]["provider"] == "LOCAL"

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


@pytest.mark.asyncio
async def test_provision_group_with_handle_slug(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test provisioning a GROUP with an explicit handle slug normalizes and persists handle."""
    admin = await make_user("admin_user_grp", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    resp = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "GROUP",
            "handle": "@infra-team",
            "display_name": "Infra Team",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["principal"] == "infra-team"
    assert data["handle"] == "@infra-team"
    assert data["display_name"] == "Infra Team"

    # Verify listing includes the normalized handle
    resp_list = await api_env.client.get("/api/v1/admin/principals")
    assert resp_list.status_code == 200
    p_list = resp_list.json()
    group_entry = next((p for p in p_list if p["id"] == data["id"]), None)
    assert group_entry is not None
    assert group_entry["principal"] == "infra-team"
    assert group_entry["handle"] == "@infra-team"
    assert group_entry["display_name"] == "Infra Team"

    # Verify detail endpoint returns the normalized handle
    resp_detail = await api_env.client.get(f"/api/v1/admin/principals/{data['id']}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["principal"] == "infra-team"
    assert detail["handle"] == "@infra-team"


@pytest.mark.asyncio
async def test_admin_principals_endpoints_additional_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test filter=ALL, password reset, patch with password, and group member endpoints."""
    admin = await make_user("admin_coverage", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("target_cov_user", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)

    # 1. Filter = ALL
    resp_all = await api_env.client.get("/api/v1/admin/principals?filter=ALL")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) >= 2

    # 2. Patch with password
    patch_resp = await api_env.client.patch(
        f"/api/v1/admin/principals/{target_user.id}",
        json={"display_name": "Updated Cov User", "password": "NewSecretPassword123!"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "Updated Cov User"

    # 3. Direct reset password endpoint
    pwd_resp = await api_env.client.post(
        f"/api/v1/admin/principals/{target_user.id}/password",
        json={"password": "AnotherSecretPassword456!"},
    )
    assert pwd_resp.status_code == 200

    # 4. Group members GET endpoint
    grp_resp = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "GROUP", "display_name": "Cov Test Group"},
    )
    assert grp_resp.status_code == 201
    grp_id = grp_resp.json()["id"]

    members_resp = await api_env.client.get(f"/api/v1/admin/groups/{grp_id}/members")
    assert members_resp.status_code == 200
    assert members_resp.json() == []

    # 5. RoleBindingRequest validation error when role is missing
    role_invalid = await api_env.client.post(
        "/api/v1/admin/role-bindings",
        json={"principal_id": str(target_user.id), "scope_type": "workspace"},
    )
    assert role_invalid.status_code == 422


@pytest.mark.asyncio
async def test_admin_principals_and_group_members_handle_contract(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Verify GET /api/v1/admin/principals and GET /api/v1/admin/groups/{id}/members return handle.

    Asserts handle (@alice, @infra-team), email, role, and provider are populated.
    """
    admin = await make_user("admin_handle_test", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    # 1. Provision user alice
    r_user = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "USER",
            "handle": "alice",
            "display_name": "Alice QA",
            "email": "alice@example.com",
        },
    )
    assert r_user.status_code == 201
    user_payload = r_user.json()
    assert user_payload["handle"] == "@alice"
    assert user_payload["principal"] == "@alice"
    assert user_payload["email"] == "alice@example.com"
    assert user_payload["role"] == "WORKSPACE_MEMBER"
    assert user_payload["provider"] == "LOCAL"
    alice_id = user_payload["id"]

    # 2. Provision group infra-team
    r_group = await api_env.client.post(
        "/api/v1/admin/principals",
        json={
            "type": "GROUP",
            "handle": "infra-team",
            "display_name": "Infra Team",
        },
    )
    assert r_group.status_code == 201
    grp_payload = r_group.json()
    assert grp_payload["handle"] == "@infra-team"
    assert grp_payload["principal"] == "infra-team"
    assert grp_payload["email"] is None
    assert grp_payload["role"] == "WORKSPACE_MEMBER"
    assert grp_payload["provider"] == "LOCAL"
    grp_id = grp_payload["id"]

    # 3. Add alice to infra-team
    r_add = await api_env.client.post(f"/api/v1/admin/groups/{grp_id}/members/{alice_id}")
    assert r_add.status_code == 200

    # 4. Verify GET /api/v1/admin/principals returns handle, email, role, provider
    r_list = await api_env.client.get("/api/v1/admin/principals")
    assert r_list.status_code == 200
    principals = r_list.json()

    alice_entry = next(p for p in principals if p["id"] == alice_id)
    assert alice_entry["handle"] == "@alice"
    assert alice_entry["principal"] == "@alice"
    assert alice_entry["email"] == "alice@example.com"
    assert alice_entry["role"] == "WORKSPACE_MEMBER"
    assert alice_entry["provider"] == "LOCAL"

    infra_entry = next(p for p in principals if p["id"] == grp_id)
    assert infra_entry["handle"] == "@infra-team"
    assert infra_entry["principal"] == "infra-team"
    assert infra_entry["email"] is None
    assert infra_entry["role"] == "WORKSPACE_MEMBER"
    assert infra_entry["provider"] == "LOCAL"

    # 5. Verify GET /api/v1/admin/groups/{grp_id}/members returns handle, email, role, provider
    r_members = await api_env.client.get(f"/api/v1/admin/groups/{grp_id}/members")
    assert r_members.status_code == 200
    members = r_members.json()
    assert len(members) == 1
    alice_member = members[0]
    assert alice_member["id"] == alice_id
    assert alice_member["handle"] == "@alice"
    assert alice_member["principal"] == "@alice"
    assert alice_member["email"] == "alice@example.com"
    assert alice_member["role"] == "WORKSPACE_MEMBER"
    assert alice_member["provider"] == "LOCAL"


@pytest.mark.asyncio
async def test_principal_service_unit_handle_contract(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Direct unit tests for principal_service ensuring handle, email, role, provider."""
    admin = await make_user("admin_unit_test", workspace_role="WORKSPACE_ADMIN")
    session = api_env.seed

    # 1. provision_group direct unit call
    grp = await provision_group(
        session,
        admin.workspace_id,
        admin.id,
        name="infra-team",
        display_name="Infra Team",
    )
    assert grp["handle"] == "@infra-team"
    assert grp["principal"] == "infra-team"
    assert grp["email"] is None
    assert grp["role"] == "WORKSPACE_MEMBER"
    assert grp["provider"] == "LOCAL"

    # 2. provision_agent direct unit call
    agent = await provision_agent(
        session,
        admin.workspace_id,
        admin.id,
        handle="code-checker",
        display_name="Code Checker",
    )
    assert agent["handle"] == "@code-checker"
    assert agent["principal"] == "@code-checker"
    assert agent["email"] is None
    assert agent["role"] == "WORKSPACE_MEMBER"
    assert agent["provider"] == "LOCAL"

    # 3. provision_user direct unit call
    user = await provision_user(
        session,
        admin.workspace_id,
        admin.id,
        handle="bob",
        display_name="Bob Test",
        email="bob@example.com",
    )
    assert user["handle"] == "@bob"
    assert user["principal"] == "@bob"
    assert user["email"] == "bob@example.com"
    assert user["role"] == "WORKSPACE_MEMBER"
    assert user["provider"] == "LOCAL"

    # Add bob to infra-team and call list_group_members
    await add_group_member(
        session,
        admin.workspace_id,
        admin.id,
        uuid.UUID(grp["id"]),
        uuid.UUID(user["id"]),
    )
    members = await list_group_members(session, admin.workspace_id, uuid.UUID(grp["id"]))
    assert len(members) == 1
    assert members[0]["handle"] == "@bob"
    assert members[0]["principal"] == "@bob"
    assert members[0]["email"] == "bob@example.com"
    assert members[0]["role"] == "WORKSPACE_MEMBER"
    assert members[0]["provider"] == "LOCAL"

    # 4. resolve_principal_id by group name, agent slug, and display name
    resolved_grp = await resolve_principal_id(session, admin.workspace_id, "infra-team")
    assert resolved_grp == uuid.UUID(grp["id"])

    resolved_agent = await resolve_principal_id(session, admin.workspace_id, "code-checker")
    assert resolved_agent == uuid.UUID(agent["id"])

    resolved_user = await resolve_principal_id(session, admin.workspace_id, "Bob Test")
    assert resolved_user == uuid.UUID(user["id"])

    # 5. get_principal_detail for GROUP and AGENT
    grp_det = await get_principal_detail(session, admin.workspace_id, "infra-team")
    assert grp_det["type"] == "GROUP"
    assert grp_det["handle"] == "@infra-team"

    agent_det = await get_principal_detail(session, admin.workspace_id, "code-checker")
    assert agent_det["type"] == "AGENT"
    assert agent_det["handle"] == "@code-checker"

    # 6. list_principals verifying all types formatted with handle, email, role, provider
    all_p = await list_principals(session, admin.workspace_id)
    assert any(p["handle"] == "@infra-team" and p["type"] == "GROUP" for p in all_p)
    assert any(p["handle"] == "@code-checker" and p["type"] == "AGENT" for p in all_p)
    assert any(p["handle"] == "@bob" and p["type"] == "USER" for p in all_p)

    # 7. update_principal invalid status
    with pytest.raises(ProblemException) as exc_st:
        await update_principal(
            session,
            admin.workspace_id,
            admin.id,
            uuid.UUID(grp["id"]),
            status="invalid_status",
        )
    assert exc_st.value.code == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_principal_service_edge_cases_and_helpers(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Exercise helpers and not_found error paths in principal_service."""
    admin = await make_user("admin_helpers", workspace_role="WORKSPACE_ADMIN")
    session = api_env.seed

    # 1. resolve_principal_id not found
    with pytest.raises(ProblemException) as exc_info1:
        await resolve_principal_id(session, admin.workspace_id, "nonexistent-entity-12345")
    assert exc_info1.value.code == "NOT_FOUND"

    # 2. get_principal_detail not found
    with pytest.raises(ProblemException) as exc_info2:
        await get_principal_detail(session, admin.workspace_id, "nonexistent-ref-12345")
    assert exc_info2.value.code == "NOT_FOUND"

    # 3. list_group_members not found
    with pytest.raises(ProblemException) as exc_info3:
        await list_group_members(session, admin.workspace_id, uuid.uuid4())
    assert exc_info3.value.code == "NOT_FOUND"

    # 4. reset_password not found
    with pytest.raises(ProblemException) as exc_info4:
        await reset_password(session, admin.workspace_id, admin.id, uuid.uuid4(), "Secret123!")
    assert exc_info4.value.code == "NOT_FOUND"

    # 5. _validate_principal_filter
    assert _validate_principal_filter(None) is None
    assert _validate_principal_filter("ALL") is None
    assert _validate_principal_filter("   ") is None
    assert _validate_principal_filter("USER") == "USER"
    assert _validate_principal_filter("GROUP") == "GROUP"
    with pytest.raises(ProblemException) as exc_info5:
        _validate_principal_filter("INVALID_TYPE")
    assert exc_info5.value.code == "VALIDATION_FAILED"

    # 6. _highest_role
    assert _highest_role([]) == "WORKSPACE_MEMBER"
    assert _highest_role(["CUSTOM_ROLE"]) == "CUSTOM_ROLE"
    assert _highest_role(["WORKSPACE_MEMBER", "SERVER_ADMIN"]) == "SERVER_ADMIN"

    # 7. _resolve_provider_label
    assert _resolve_provider_label("LOCAL_ADMIN", "local") == "LOCAL"
    assert _resolve_provider_label("OIDC", "google-workspace") == "GOOGLE"
    assert _resolve_provider_label("OAUTH2", "github-enterprise") == "GITHUB"
    assert _resolve_provider_label("LDAP", "ad-primary") == "ACTIVE_DIRECTORY"
    assert _resolve_provider_label("LDAP", "openldap") == "LDAP"
    assert _resolve_provider_label("OAUTH2", "custom-oauth") == "OAUTH2"
    assert _resolve_provider_label("SAML", "okta") == "SAML"

    # 8. provision_user with password and then reset_password
    user_pw = await provision_user(
        session,
        admin.workspace_id,
        admin.id,
        handle="userpw",
        display_name="User With Password",
        email="userpw@example.com",
        password="InitialPassword123!",  # noqa: S106
    )
    user_pw_id = uuid.UUID(user_pw["id"])
    reset_res = await reset_password(
        session,
        admin.workspace_id,
        admin.id,
        user_pw_id,
        "UpdatedPassword456!",
    )
    assert reset_res["status"] == "ok"

    # 9. bind_role validation errors
    with pytest.raises(ProblemException) as exc_b1:
        await bind_role(
            session, admin.workspace_id, admin.id, user_pw_id, "WORKSPACE_ADMIN", "server"
        )
    assert exc_b1.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc_b2:
        await bind_role(
            session, admin.workspace_id, admin.id, user_pw_id, "SERVER_ADMIN", "workspace"
        )
    assert exc_b2.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc_b3:
        await bind_role(
            session,
            admin.workspace_id,
            admin.id,
            user_pw_id,
            "PROJECT_ADMIN",
            "project",
            project_id=None,
        )
    assert exc_b3.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc_b4:
        await bind_role(
            session,
            admin.workspace_id,
            admin.id,
            user_pw_id,
            "PROJECT_ADMIN",
            "project",
            project_id=uuid.uuid4(),
        )
    assert exc_b4.value.code == "NOT_FOUND"

    # 10. bind_role with SERVER_ADMIN from non-server-admin triggers INSUFFICIENT_CAPABILITY
    with pytest.raises(ProblemException) as exc_sa:
        await bind_role(session, admin.workspace_id, admin.id, user_pw_id, "SERVER_ADMIN", "server")
    assert exc_sa.value.code == "INSUFFICIENT_CAPABILITY"

    # 11. bind_role with valid WORKSPACE_GUEST
    bg_res = await bind_role(
        session, admin.workspace_id, admin.id, user_pw_id, "WORKSPACE_GUEST", "workspace"
    )
    assert bg_res["role"] == "WORKSPACE_GUEST"

    # 12. unbind_role successful
    ub_res = await unbind_role(
        session, admin.workspace_id, admin.id, user_pw_id, "WORKSPACE_GUEST", "workspace"
    )
    assert ub_res["status"] == "role_unbound"

    # unbind again when already unbound
    ub_res2 = await unbind_role(
        session, admin.workspace_id, admin.id, user_pw_id, "WORKSPACE_GUEST", "workspace"
    )
    assert ub_res2["status"] == "role_unbound"

    # 13. _format_principal_entry with group slugification and UUID display name fallback
    p_group_custom = DBPrincipal(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        principal_type="GROUP",
        status="ACTIVE",
        display_name="DevOps Security Team",
    )
    formatted_grp = await _format_principal_entry(session, admin.workspace_id, p_group_custom)
    assert formatted_grp["handle"] == "@DevOps Security Team"

    p_group_uuid = DBPrincipal(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        principal_type="GROUP",
        status="ACTIVE",
        display_name=str(uuid.uuid4()),
    )
    formatted_uuid = await _format_principal_entry(session, admin.workspace_id, p_group_uuid)
    assert formatted_uuid["handle"] == "@group"

    # 14. _slugify_or_default unit tests
    assert _slugify_or_default("infra-team", "fallback") == "infra-team"
    assert _slugify_or_default("@infra-team", "fallback") == "infra-team"
    assert _slugify_or_default("Infra Team", "fallback") == "infra-team"
    assert _slugify_or_default(str(uuid.uuid4()), "fallback") == "fallback"
    assert _slugify_or_default(None, "fallback") == "fallback"
    assert _slugify_or_default("", "fallback") == "fallback"
    assert _slugify_or_default("   ", "fallback") == "fallback"

    # 15. get_principal_detail for group without Group row, with UUID name, and SCRIPT_EPHEMERAL
    session.add(p_group_custom)
    session.add(p_group_uuid)
    await session.flush()
    detail_grp = await get_principal_detail(session, admin.workspace_id, str(p_group_custom.id))
    assert detail_grp["handle"] == "@DevOps Security Team"

    detail_uuid = await get_principal_detail(session, admin.workspace_id, str(p_group_uuid.id))
    assert detail_uuid["handle"] == "@group"

    grp_uuid_name = await provision_group(
        session,
        admin.workspace_id,
        admin.id,
        name=str(uuid.uuid4()),
        display_name="Cloud Security",
    )
    detail_uuid_name = await get_principal_detail(
        session, admin.workspace_id, grp_uuid_name["id"]
    )
    assert detail_uuid_name["handle"] == "@cloud-security"

    p_group_row = (
        await session.execute(
            select(DBPrincipal).where(DBPrincipal.id == uuid.UUID(grp_uuid_name["id"]))
        )
    ).scalar_one()
    formatted_uuid_name = await _format_principal_entry(
        session, admin.workspace_id, p_group_row
    )
    assert formatted_uuid_name["handle"] == "@cloud-security"

    p_eph = DBPrincipal(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        principal_type="SCRIPT_EPHEMERAL",
        status="ACTIVE",
        display_name="Ephemeral",
    )
    session.add(p_eph)
    await session.flush()
    with pytest.raises(ProblemException) as exc_eph:
        await get_principal_detail(session, admin.workspace_id, str(p_eph.id))
    assert exc_eph.value.code == "NOT_FOUND"

    # 16. add_group_member idempotent branch
    g_mem_test = await provision_group(session, admin.workspace_id, admin.id, name="idem-group")
    gid = uuid.UUID(g_mem_test["id"])
    await add_group_member(session, admin.workspace_id, admin.id, gid, user_pw_id)
    dup_mem = await add_group_member(session, admin.workspace_id, admin.id, gid, user_pw_id)
    assert dup_mem["status"] == "ok"

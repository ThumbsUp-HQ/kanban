# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and RBAC security tests for unified /api/v1/mcp-keys router (KAN-31)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.mcp_keys import (
    _resolve_key_project_list,
    _resolve_project_id_to_key_map,
    revoke_unified_mcp_key,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
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


async def _enroll_and_confirm_totp(api_env: ApiEnv, user_id: uuid.UUID) -> None:
    """Enroll and confirm TOTP for user to satisfy AAL2 policy."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()


@pytest.mark.asyncio
async def test_unified_mcp_keys_self_service_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Standard user can mint, list (view=mine), and revoke personal/workspace keys."""
    user = await make_user("unified_member", workspace_role="WORKSPACE_MEMBER")
    await api_env.seed.commit()
    client = api_env.client

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        aal_level=1,
    )

    # 1. Mint personal key
    mint_resp = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "My Personal CLI",
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "scope_tier": "workspace",
            "expires_in_days": 30,
        },
    )
    assert mint_resp.status_code == 201
    mint_data = mint_resp.json()
    assert mint_data["label"] == "My Personal CLI"
    assert mint_data["surface"] == "agent"
    assert "token" in mint_data
    assert "raw_key" in mint_data
    assert "key_prefix" in mint_data
    assert mint_data["key_prefix"] == "kb_agt_"
    key_id = mint_data["id"]

    # 2. List caller keys via view=mine
    list_resp = await client.get("/api/v1/mcp-keys?view=mine")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    items = list_data if isinstance(list_data, list) else list_data.get("keys", [])
    found_keys = [k for k in items if k["id"] == key_id]
    assert len(found_keys) == 1
    assert "token" not in found_keys[0]
    assert "raw_key" not in found_keys[0]

    # 3. Revoke key
    del_resp = await client.delete(f"/api/v1/mcp-keys/{key_id}")
    assert del_resp.status_code == 204

    # 4. List again: key should be marked revoked
    list_after = await client.get("/api/v1/mcp-keys?view=mine")
    assert list_after.status_code == 200
    raw_after = list_after.json()
    items_after = raw_after if isinstance(raw_after, list) else raw_after.get("keys", [])
    revoked_key = next(k for k in items_after if k["id"] == key_id)
    assert revoked_key["revoked_at"] is not None


@pytest.mark.asyncio
async def test_global_scope_tier_privilege_escalation_guard(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Global/server scope tier strictly requires SERVER_ADMIN with AAL2."""
    regular_user = await make_user("non_admin_esc", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("ws_admin_esc", workspace_role="WORKSPACE_ADMIN")
    server_admin = await make_user("srv_admin_esc", workspace_role="SERVER_ADMIN")

    await _enroll_and_confirm_totp(api_env, ws_admin.id)
    await _enroll_and_confirm_totp(api_env, server_admin.id)

    client = api_env.client

    # 1. Regular user trying to mint global/server scope tier is rejected 403
    api_env.resolver.principal = PrincipalContext(
        principal_id=regular_user.id,
        workspace_id=regular_user.workspace_id,
        aal_level=1,
    )
    resp_reg = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Escalation Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_reg.status_code == 403

    # 2. Workspace admin trying to mint global/server tier is rejected 403
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    resp_ws = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Admin Escalation",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_ws.status_code == 403

    # 3. Server admin with AAL1 is rejected 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=1,
    )
    resp_srv_aal1 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Srv Admin AAL1",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_srv_aal1.status_code == 403
    assert resp_srv_aal1.json()["code"] == "AAL2_REQUIRED"

    # 4. Server admin with AAL2 succeeds
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_srv_aal2 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Legitimate Server Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_srv_aal2.status_code == 201
    assert resp_srv_aal2.json()["scope_tier"] == "global"


@pytest.mark.asyncio
async def test_admin_surface_and_destructive_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Admin surface requires tier-matched admin role; admin:destructive requires SERVER_ADMIN."""
    regular_user = await make_user("admin_surf_regular", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("admin_surf_ws", workspace_role="WORKSPACE_ADMIN")
    server_admin = await make_user("admin_surf_srv", workspace_role="SERVER_ADMIN")

    await _enroll_and_confirm_totp(api_env, ws_admin.id)
    await _enroll_and_confirm_totp(api_env, server_admin.id)

    client = api_env.client

    # 1. Regular user cannot mint admin surface key
    api_env.resolver.principal = PrincipalContext(
        principal_id=regular_user.id,
        workspace_id=regular_user.workspace_id,
        aal_level=1,
    )
    resp_reg = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Bypass Admin Key",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "workspace",
        },
    )
    assert resp_reg.status_code == 403

    # 1b. Regular user with AAL2 also cannot mint admin surface workspace or global key
    api_env.resolver.principal = PrincipalContext(
        principal_id=regular_user.id,
        workspace_id=regular_user.workspace_id,
        aal_level=2,
    )
    resp_reg_aal2 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Bypass Admin Key AAL2",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "workspace",
        },
    )
    assert resp_reg_aal2.status_code == 403
    assert resp_reg_aal2.json()["code"] == "INSUFFICIENT_CAPABILITY"

    resp_reg_glob_admin = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Bypass Admin Global Key AAL2",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "server",
        },
    )
    assert resp_reg_glob_admin.status_code == 403
    assert resp_reg_glob_admin.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 2. Workspace admin with AAL1 cannot mint admin surface key
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=1,
    )
    resp_ws_aal1 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Admin Key AAL1",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "workspace",
        },
    )
    assert resp_ws_aal1.status_code == 403
    assert resp_ws_aal1.json()["code"] == "AAL2_REQUIRED"

    # 3. Workspace admin with AAL2 can mint admin:read key
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    resp_ws_aal2 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Admin Key AAL2",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "workspace",
        },
    )
    assert resp_ws_aal2.status_code == 201

    # 4. Workspace admin cannot mint admin:destructive scope
    resp_ws_dest = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Destructive",
            "surface": "admin",
            "scopes": ["admin:read", "admin:destructive"],
            "scope_tier": "workspace",
        },
    )
    assert resp_ws_dest.status_code == 403

    # 5. Server admin with AAL2 can mint admin:destructive scope
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_srv_dest = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Server Destructive",
            "surface": "admin",
            "scopes": ["admin:read", "admin:destructive"],
            "scope_tier": "server",
        },
    )
    assert resp_srv_dest.status_code == 201


@pytest.mark.asyncio
async def test_capability_delete_bitmask_aal2_guard(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Capability.DELETE (128) in capability_mask strictly requires AAL2."""
    ws_admin = await make_user("bitmask_ws_admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_and_confirm_totp(api_env, ws_admin.id)
    client = api_env.client

    # AAL1 with capability_mask=128 fails with 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=1,
    )
    resp_aal1 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Delete Mask Key",
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 128,
        },
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # AAL2 with capability_mask=128 succeeds
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    resp_aal2 = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Delete Mask Key",
            "surface": "agent",
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 128,
        },
    )
    assert resp_aal2.status_code == 201


@pytest.mark.asyncio
async def test_project_admin_governance_leak_prevention(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """PROJECT_ADMIN governance listing and revocation is confined to own projects."""
    ws_admin = await make_user("proj_leak_ws_admin", workspace_role="WORKSPACE_ADMIN")
    proj_admin = await make_user("proj_leak_p_admin", workspace_role="WORKSPACE_MEMBER")

    await _enroll_and_confirm_totp(api_env, ws_admin.id)
    await _enroll_and_confirm_totp(api_env, proj_admin.id)

    client = api_env.client

    # Create two projects in the workspace: PJA and PJB using helper
    pja_id = await create_project(
        api_env.seed,
        ws_admin.workspace_id,
        identifier="PJA",
        name="Project Alpha",
        created_by_id=ws_admin.id,
    )
    await create_project(
        api_env.seed,
        ws_admin.workspace_id,
        identifier="PJB",
        name="Project Beta",
        created_by_id=ws_admin.id,
    )
    await api_env.seed.commit()

    # Grant proj_admin PROJECT_ADMIN role on PJA only
    await add_role_binding(
        api_env.seed,
        ws_admin.workspace_id,
        proj_admin.id,
        "PROJECT_ADMIN",
        scope_type="project",
        project_id=pja_id,
    )
    await api_env.seed.commit()

    # WS admin mints keys for:
    # 1. Workspace scope
    # 2. PJA project scope
    # 3. PJB project scope
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    k_ws_resp = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert k_ws_resp.status_code == 201
    k_ws_id = k_ws_resp.json()["id"]

    k_pja_resp = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "PJA Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJA"],
        },
    )
    assert k_pja_resp.status_code == 201
    k_pja_id = k_pja_resp.json()["id"]

    k_pjb_resp = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "PJB Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJB"],
        },
    )
    assert k_pjb_resp.status_code == 201
    k_pjb_id = k_pjb_resp.json()["id"]

    # Now proj_admin calls view=governance with AAL2
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin.id,
        workspace_id=proj_admin.workspace_id,
        aal_level=2,
    )

    # 1. Listing governance keys without project filter returns ONLY PJA keys
    gov_list_resp = await client.get("/api/v1/mcp-keys?view=governance")
    assert gov_list_resp.status_code == 200
    gov_items = (
        gov_list_resp.json()
        if isinstance(gov_list_resp.json(), list)
        else gov_list_resp.json().get("keys", [])
    )
    listed_ids = {k["id"] for k in gov_items}
    assert k_pja_id in listed_ids
    assert k_ws_id not in listed_ids
    assert k_pjb_id not in listed_ids

    # 2. Filtering governance for PJB (which proj_admin does not administer) returns empty
    gov_pjb_resp = await client.get("/api/v1/mcp-keys?view=governance&project_ref=PJB")
    assert gov_pjb_resp.status_code == 200
    pjb_items = (
        gov_pjb_resp.json()
        if isinstance(gov_pjb_resp.json(), list)
        else gov_pjb_resp.json().get("keys", [])
    )
    assert len(pjb_items) == 0

    # 2b. Legacy /api/v1/admin/mcp-keys endpoint parity for project admin
    # Filtering legacy admin endpoint for workspace scope as project admin returns empty list
    legacy_ws = await client.get("/api/v1/admin/mcp-keys?scope_tier=workspace")
    assert legacy_ws.status_code == 200
    assert legacy_ws.json() == []

    # Listing legacy admin endpoint as project admin returns only PJA keys
    legacy_list = await client.get("/api/v1/admin/mcp-keys")
    assert legacy_list.status_code == 200
    legacy_ids = {k["id"] for k in legacy_list.json()}
    assert k_pja_id in legacy_ids
    assert k_ws_id not in legacy_ids
    assert k_pjb_id not in legacy_ids

    # Legacy delete: proj_admin cannot revoke workspace key or PJB key via admin route
    del_legacy_ws = await client.delete(f"/api/v1/admin/mcp-keys/{k_ws_id}")
    assert del_legacy_ws.status_code == 404
    del_legacy_pjb = await client.delete(f"/api/v1/admin/mcp-keys/{k_pjb_id}")
    assert del_legacy_pjb.status_code == 404

    # 2c. proj_admin can mint admin surface project key for PJA, but not for PJB
    pja_admin_surf = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "PJA Admin Surf",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJA"],
        },
    )
    assert pja_admin_surf.status_code == 201

    pjb_admin_surf = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "PJB Admin Surf",
            "surface": "admin",
            "scopes": ["admin:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJB"],
        },
    )
    assert pjb_admin_surf.status_code == 403
    assert pjb_admin_surf.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. proj_admin cannot revoke workspace key
    del_ws = await client.delete(f"/api/v1/mcp-keys/{k_ws_id}")
    assert del_ws.status_code == 404

    # 4. proj_admin cannot revoke PJB key
    del_pjb = await client.delete(f"/api/v1/mcp-keys/{k_pjb_id}")
    assert del_pjb.status_code == 404

    # 5. proj_admin CAN revoke PJA key
    del_pja = await client.delete(f"/api/v1/mcp-keys/{k_pja_id}")
    assert del_pja.status_code == 204


@pytest.mark.asyncio
async def test_unified_mcp_keys_filters_and_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test project_ref, surface, and scope_tier filters, and 404 validation."""
    user = await make_user("filter_user", workspace_role="WORKSPACE_MEMBER")
    client = api_env.client

    pja_id = await create_project(
        api_env.seed,
        user.workspace_id,
        identifier="PJF",
        name="Filter Project",
        created_by_id=user.id,
    )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        aal_level=1,
    )

    # 1. Mint key with allowed_projects
    mint_pja = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Project Filter Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJF"],
        },
    )
    assert mint_pja.status_code == 201
    pja_key_id = mint_pja.json()["id"]

    # 2. Mint key with allowed_project_ids directly
    mint_pja_ids = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Project IDs Key",
            "surface": "docs",
            "scopes": ["docs:read"],
            "scope_tier": "project",
            "allowed_project_ids": [str(pja_id)],
        },
    )
    assert mint_pja_ids.status_code == 201

    # 3. Mint with invalid project ref -> 422 INVALID_TIER_SHAPE
    mint_bad_proj = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Bad Proj Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": ["DOES_NOT_EXIST"],
        },
    )
    assert mint_bad_proj.status_code == 422

    # 4. Filter view=mine by surface
    list_agent = await client.get("/api/v1/mcp-keys?view=mine&surface=agent")
    assert list_agent.status_code == 200
    agent_keys = list_agent.json()
    assert all(k["surface"] == "agent" for k in agent_keys)

    # 5. Filter view=mine by scope_tier
    list_project = await client.get("/api/v1/mcp-keys?view=mine&scope_tier=project")
    assert list_project.status_code == 200
    assert any(k["id"] == pja_key_id for k in list_project.json())

    # 6. Filter view=mine by non-existent project_ref -> returns empty list 200 OK
    list_bad_ref = await client.get("/api/v1/mcp-keys?view=mine&project_ref=NO_SUCH_PROJ")
    assert list_bad_ref.status_code == 200
    assert len(list_bad_ref.json()) == 0

    # 7. Filter view=mine by valid project_ref
    list_good_ref = await client.get("/api/v1/mcp-keys?view=mine&project_ref=PJF")
    assert list_good_ref.status_code == 200
    assert any(k["id"] == pja_key_id for k in list_good_ref.json())

    # 8. Revoke non-existent key -> 404
    del_nf = await client.delete("/api/v1/mcp-keys/00000000-0000-0000-0000-000000000000")
    assert del_nf.status_code == 404


@pytest.mark.asyncio
async def test_governance_rbac_and_aal2_filters(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test governance view AAL2 checks and non-admin role rejection."""
    reg_user = await make_user("gov_reg_user", workspace_role="WORKSPACE_MEMBER")
    ws_admin = await make_user("gov_ws_admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_and_confirm_totp(api_env, reg_user.id)
    await _enroll_and_confirm_totp(api_env, ws_admin.id)

    client = api_env.client

    # 1. Non-admin with AAL1 calling governance -> 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=reg_user.id,
        workspace_id=reg_user.workspace_id,
        aal_level=1,
    )
    resp_aal1 = await client.get("/api/v1/mcp-keys?view=governance")
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # 2. Non-admin with AAL2 calling governance -> 403 FORBIDDEN
    api_env.resolver.principal = PrincipalContext(
        principal_id=reg_user.id,
        workspace_id=reg_user.workspace_id,
        aal_level=2,
    )
    resp_reg_aal2 = await client.get("/api/v1/mcp-keys?view=governance")
    assert resp_reg_aal2.status_code == 403
    assert resp_reg_aal2.json()["code"] == "FORBIDDEN"

    # 3. WS Admin with AAL2 mints key, then revokes under governance
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    mint_resp = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Gov Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert mint_resp.status_code == 201

    # 4. Mint key owned by reg_user
    api_env.resolver.principal = PrincipalContext(
        principal_id=reg_user.id,
        workspace_id=reg_user.workspace_id,
        aal_level=1,
    )
    mint_reg = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Reg Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert mint_reg.status_code == 201
    reg_k_id = mint_reg.json()["id"]

    # 5. WS Admin with AAL1 attempting to revoke reg_user's key -> 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=1,
    )
    resp_rev_aal1 = await client.delete(f"/api/v1/mcp-keys/{reg_k_id}")
    assert resp_rev_aal1.status_code == 403
    assert resp_rev_aal1.json()["code"] == "AAL2_REQUIRED"

    # 6. WS Admin with AAL2 can revoke the key (204)
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    resp_rev_ws = await client.delete(f"/api/v1/mcp-keys/{reg_k_id}")
    assert resp_rev_ws.status_code == 204


@pytest.mark.asyncio
async def test_unified_mcp_keys_edge_cases_and_governance_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test governance scope queries, server/workspace/project admin edge revocation cases."""
    ws_admin = await make_user("edge_ws_admin", workspace_role="WORKSPACE_ADMIN")
    proj_admin = await make_user("edge_p_admin", workspace_role="WORKSPACE_MEMBER")
    server_admin = await make_user("edge_s_admin", workspace_role="SERVER_ADMIN")

    await _enroll_and_confirm_totp(api_env, ws_admin.id)
    await _enroll_and_confirm_totp(api_env, proj_admin.id)
    await _enroll_and_confirm_totp(api_env, server_admin.id)

    client = api_env.client

    # Create project PJE
    pje_id = await create_project(
        api_env.seed,
        ws_admin.workspace_id,
        identifier="PJE",
        name="Project Echo",
        created_by_id=ws_admin.id,
    )
    # Create project PJZ (proj_admin has no role on PJZ)
    await create_project(
        api_env.seed,
        ws_admin.workspace_id,
        identifier="PJZ",
        name="Project Zulu",
        created_by_id=ws_admin.id,
    )
    # Grant proj_admin PROJECT_ADMIN on PJE only
    await add_role_binding(
        api_env.seed,
        ws_admin.workspace_id,
        proj_admin.id,
        "PROJECT_ADMIN",
        scope_type="project",
        project_id=pje_id,
    )
    await api_env.seed.commit()

    # 1. Project Admin calls view=governance with scope_tier=workspace -> returns [] (line 216)
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin.id,
        workspace_id=proj_admin.workspace_id,
        aal_level=2,
    )
    resp_p_ws = await client.get("/api/v1/mcp-keys?view=governance&scope_tier=workspace")
    assert resp_p_ws.status_code == 200
    assert len(resp_p_ws.json()) == 0

    # 2. Workspace Admin calls view=governance with scope_tier=project (lines 211, 244)
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    resp_w_proj = await client.get("/api/v1/mcp-keys?view=governance&scope_tier=project")
    assert resp_w_proj.status_code == 200

    # 3. Server Admin calls view=governance with scope_tier=server (line 204)
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_s_server = await client.get("/api/v1/mcp-keys?view=governance&scope_tier=server")
    assert resp_s_server.status_code == 200

    # 4. Mint key on PJZ (where proj_admin has no role)
    mint_pjz = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "PJZ Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": ["PJZ"],
        },
    )
    assert mint_pjz.status_code == 201
    pjz_key_id = mint_pjz.json()["id"]

    # Mint workspace key
    mint_ws_key = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "WS Edge Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert mint_ws_key.status_code == 201
    ws_key_id = mint_ws_key.json()["id"]

    # 5. Project Admin attempts to revoke workspace key -> 404 (line 469)
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin.id,
        workspace_id=proj_admin.workspace_id,
        aal_level=2,
    )
    del_ws_fail = await client.delete(f"/api/v1/mcp-keys/{ws_key_id}")
    assert del_ws_fail.status_code == 404

    # 6. Project Admin attempts to revoke PJZ key (no can_admin) -> 404 (line 480)
    del_pjz_fail = await client.delete(f"/api/v1/mcp-keys/{pjz_key_id}")
    assert del_pjz_fail.status_code == 404

    # 7. Create foreign workspace key directly in seed to test cross-workspace revocation guards
    foreign_ws_id = await create_workspace(api_env.seed, name="Foreign Workspace")
    foreign_p_id = await create_user(
        api_env.seed, foreign_ws_id, handle="@foreign", display_name="Foreign"
    )
    await add_role_binding(
        api_env.seed,
        foreign_ws_id,
        foreign_p_id,
        "WORKSPACE_MEMBER",
        scope_type="workspace",
    )
    await api_env.seed.commit()

    # Workspace Admin attempts to revoke foreign workspace key -> 404 (line 460)
    # Server Admin attempts to revoke foreign workspace key -> 404 (line 456-457)
    api_env.resolver.principal = PrincipalContext(
        principal_id=foreign_p_id,
        workspace_id=foreign_ws_id,
        aal_level=1,
    )
    mint_foreign = await client.post(
        "/api/v1/mcp-keys",
        json={
            "label": "Foreign Key",
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert mint_foreign.status_code == 201
    foreign_key_id = mint_foreign.json()["id"]

    # WS Admin in primary workspace tries to revoke foreign key -> 404
    api_env.resolver.principal = PrincipalContext(
        principal_id=ws_admin.id,
        workspace_id=ws_admin.workspace_id,
        aal_level=2,
    )
    del_foreign_ws = await client.delete(f"/api/v1/mcp-keys/{foreign_key_id}")
    assert del_foreign_ws.status_code == 404

    # Server Admin with primary workspace tries to revoke foreign key -> 404
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    del_foreign_srv = await client.delete(f"/api/v1/mcp-keys/{foreign_key_id}")
    assert del_foreign_srv.status_code == 404


@pytest.mark.asyncio
async def test_unified_mcp_keys_unit_branch_coverage() -> None:  # noqa: PLR0915
    """Test helper functions and branch edges in unified router."""
    # 1. _resolve_project_id_to_key_map exception handling
    failing_session = AsyncMock()
    failing_session.execute.side_effect = RuntimeError("DB error")
    res_empty = await _resolve_project_id_to_key_map(failing_session, {uuid.uuid4()})
    assert res_empty == {}

    # 2. _resolve_key_project_list with key having project_id but no allowed_project_ids
    p_id = uuid.uuid4()
    mock_key = MagicMock()
    mock_key.allowed_project_ids = None
    mock_key.project_id = p_id
    assert _resolve_key_project_list(mock_key, {p_id: "PROJ"}) == ["PROJ"]

    # 3. Direct branch tests for revoke_unified_mcp_key
    mock_session = AsyncMock()
    key_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    foreign_ws = uuid.uuid4()
    caller_ws = uuid.uuid4()

    mock_db_key = MagicMock()
    mock_db_key.principal_id = owner_id
    mock_db_key.workspace_id = foreign_ws
    mock_db_key.scope_tier = "workspace"
    mock_session.get.return_value = mock_db_key

    # 3a. Server Admin trying to revoke key from different workspace -> 404
    caller_sa = MagicMock()
    caller_sa.principal_id = uuid.uuid4()
    caller_sa.workspace_id = caller_ws
    caller_sa.aal_level = 2
    mock_scalar_sa = MagicMock()
    mock_scalar_sa.scalar_one.return_value = True
    mock_session.execute.return_value = mock_scalar_sa

    with pytest.raises(ProblemException) as exc_info:
        await revoke_unified_mcp_key(key_id, caller_sa, mock_session)
    assert exc_info.value.status == 404

    # 3b. Workspace Admin trying to revoke key from different workspace -> 404
    caller_wa = MagicMock()
    caller_wa.principal_id = uuid.uuid4()
    caller_wa.workspace_id = caller_ws
    caller_wa.aal_level = 2

    async def mock_exec_wa(*_args: object, **_kwargs: object) -> MagicMock:
        scalar = MagicMock()
        # First call: server_admin check -> False; Second call: workspace_admin check -> True
        call_count = getattr(mock_exec_wa, "calls", 0)
        mock_exec_wa.calls = call_count + 1  # type: ignore[attr-defined]
        scalar.scalar_one.return_value = call_count > 0
        return scalar

    mock_session.execute = mock_exec_wa
    with pytest.raises(ProblemException) as exc_info_wa:
        await revoke_unified_mcp_key(key_id, caller_wa, mock_session)
    assert exc_info_wa.value.status == 404

    # 3c. Project Admin trying to revoke workspace-tier key -> 404
    caller_pa = MagicMock()
    caller_pa.principal_id = uuid.uuid4()
    caller_pa.workspace_id = foreign_ws
    caller_pa.aal_level = 2

    async def mock_exec_pa_non_admin(*_args: object, **_kwargs: object) -> MagicMock:
        scalar = MagicMock()
        scalar.scalar_one.return_value = False
        return scalar

    mock_session.execute = mock_exec_pa_non_admin
    with pytest.raises(ProblemException) as exc_info_pa:
        await revoke_unified_mcp_key(key_id, caller_pa, mock_session)
    assert exc_info_pa.value.status == 404

    # 3d. Project Admin trying to revoke project-tier key without can_admin -> 404
    mock_db_key.scope_tier = "project"
    mock_db_key.project_id = uuid.uuid4()
    with pytest.raises(ProblemException) as exc_info_pa2:
        await revoke_unified_mcp_key(key_id, caller_pa, mock_session)
    assert exc_info_pa2.value.status == 404

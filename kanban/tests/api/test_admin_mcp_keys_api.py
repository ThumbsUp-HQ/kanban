# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLR0915
"""API integration tests for admin MCP keys endpoints and introspection (KB-P4-02a)."""

from __future__ import annotations

import base64
import json
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text
from starlette.requests import Request

from database.models.mcp_api_key import McpApiKey
from kanban.api.deps import PrincipalContext
from kanban.api.internal.mcp_introspect import get_internal_session
from kanban.api.v1.admin.mcp_keys import (
    McpApiKeyMintRequest,
    _resolve_admin_key_project_list,
    _resolve_admin_project_id_to_key_map,
)
from kanban.app import create_internal_app
from kanban.security.service_auth import create_internal_service_auth_header
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

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


@pytest.mark.asyncio
async def test_admin_mcp_keys_endpoints_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test admin REST endpoints (AAL2 enforcement, mint, list, revoke) & internal introspection."""
    admin_user = await make_user("mcp_admin", workspace_role="WORKSPACE_ADMIN")
    member_user = await make_user("mcp_member", workspace_role="WORKSPACE_MEMBER")

    # Seed confirmed TOTP factor for admin_user so AAL2 policy permits evaluation
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": admin_user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": admin_user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    client = api_env.client

    # 1. AAL1 caller is rejected with 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=1,
    )
    resp_aal1 = await client.post(
        "/api/v1/admin/mcp-keys",
        json={"surface": "agent", "scopes": ["agent:read"]},
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    resp_aal1_get = await client.get("/api/v1/admin/mcp-keys")
    assert resp_aal1_get.status_code == 403
    assert resp_aal1_get.json()["code"] == "AAL2_REQUIRED"

    # 1b. MFA-unenrolled admin is rejected with 403 MFA_ENROLLMENT_REQUIRED
    unenrolled_admin = await make_user("mcp_unenrolled_admin", workspace_role="WORKSPACE_ADMIN")
    api_env.resolver.principal = PrincipalContext(
        principal_id=unenrolled_admin.id,
        workspace_id=unenrolled_admin.workspace_id,
        aal_level=1,
    )
    resp_unenrolled = await client.post(
        "/api/v1/admin/mcp-keys",
        json={"surface": "agent", "scopes": ["agent:read"]},
    )
    assert resp_unenrolled.status_code == 403
    assert resp_unenrolled.json()["code"] == "MFA_ENROLLMENT_REQUIRED"

    resp_unenrolled_get = await client.get("/api/v1/admin/mcp-keys")
    assert resp_unenrolled_get.status_code == 403
    assert resp_unenrolled_get.json()["code"] == "MFA_ENROLLMENT_REQUIRED"

    # 2. Non-admin caller with AAL2 rejected with 403 FORBIDDEN
    api_env.resolver.principal = PrincipalContext(
        principal_id=member_user.id,
        workspace_id=member_user.workspace_id,
        aal_level=2,
    )
    resp_non_admin = await client.post(
        "/api/v1/admin/mcp-keys",
        json={"surface": "agent", "scopes": ["agent:read"]},
    )
    assert resp_non_admin.status_code == 403
    assert resp_non_admin.json()["code"] == "FORBIDDEN"

    # 3. Workspace admin with AAL2 mints successfully (201)
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    resp_mint = await client.post(
        "/api/v1/admin/mcp-keys",
        json={"surface": "agent", "scopes": ["agent:read", "agent:write"]},
    )
    assert resp_mint.status_code == 201
    contract_recorder.record("mint_mcp_api_key_201", resp_mint.request, resp_mint)
    mint_data = resp_mint.json()
    assert mint_data["surface"] == "agent"
    assert mint_data["scopes"] == ["agent:read", "agent:write"]
    assert "token" in mint_data
    token = mint_data["token"]
    assert token.startswith("kb_agt_")
    assert "Location" in resp_mint.headers
    key_id = mint_data["id"]

    # 4. List keys: returns metadata without plaintext token
    resp_list = await client.get("/api/v1/admin/mcp-keys")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert any(k["id"] == key_id for k in list_data)
    for k in list_data:
        assert "token" not in k
        assert "key_sha256" not in k
        assert len(k["display_hint"]) == 4

    # 4b. List keys with surface filter
    resp_list_agent = await client.get("/api/v1/admin/mcp-keys?surface=agent")
    assert resp_list_agent.status_code == 200
    assert any(k["id"] == key_id for k in resp_list_agent.json())

    resp_list_docs = await client.get("/api/v1/admin/mcp-keys?surface=docs")
    assert resp_list_docs.status_code == 200
    assert not any(k["id"] == key_id for k in resp_list_docs.json())

    # 5. Internal introspection via POST /internal/v1/mcp/introspect on internal_app
    raw_app = getattr(client._transport, "app", None)  # noqa: SLF001
    assert raw_app is not None
    internal_app = create_internal_app(raw_app)
    int_transport = httpx.ASGITransport(app=internal_app)
    async with httpx.AsyncClient(
        transport=int_transport, base_url="http://internal.test"
    ) as int_client:
        intro_path = "/internal/v1/mcp/introspect"
        # 5a. Missing internal auth header returns 401
        resp_intro_noauth = await int_client.post(
            intro_path,
            json={"token": token, "surface": "agent"},
        )
        assert resp_intro_noauth.status_code == 401

        # 5a2. Spoofed X-Ssl-Client-Cert HTTP header is rejected (401)
        resp_intro_cert = await int_client.post(
            intro_path,
            headers={"X-Ssl-Client-Cert": "test-client-cert-content"},
            json={"token": token, "surface": "agent"},
        )
        assert resp_intro_cert.status_code == 401

        # 5b. Valid role-bound internal auth header returns active: true
        body_agent = json.dumps({"token": token, "surface": "agent"}).encode("utf-8")
        internal_auth = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=intro_path,
            body_bytes=body_agent,
        )
        resp_intro = await int_client.post(
            intro_path,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": internal_auth},
            content=body_agent,
        )
        assert resp_intro.status_code == 200
        contract_recorder.record("mcp_introspect_active_200", resp_intro.request, resp_intro)
        intro_data = resp_intro.json()
        assert intro_data["active"] is True
        assert intro_data["surface"] == "agent"
        assert intro_data["scopes"] == ["agent:read", "agent:write"]

        # 5c. Surface mismatch via introspection returns active: false, reason: SURFACE_KEY_MISMATCH
        body_admin = json.dumps({"token": token, "surface": "admin"}).encode("utf-8")
        internal_auth_admin = create_internal_service_auth_header(
            principal="mcp-gateway",
            method="POST",
            path=intro_path,
            body_bytes=body_admin,
        )
        resp_intro_mismatch = await int_client.post(
            intro_path,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": internal_auth_admin},
            content=body_admin,
        )
        assert resp_intro_mismatch.status_code == 200
        contract_recorder.record(
            "mcp_introspect_surface_mismatch_200",
            resp_intro_mismatch.request,
            resp_intro_mismatch,
        )
        assert resp_intro_mismatch.json()["active"] is False
        assert resp_intro_mismatch.json()["reason"] == "SURFACE_KEY_MISMATCH"

    # 6. Revoke key via DELETE /api/v1/admin/mcp-keys/{key_id} -> 204
    resp_del = await client.delete(f"/api/v1/admin/mcp-keys/{key_id}")
    assert resp_del.status_code == 204

    # 6b. Deleting unknown key returns 404 NOT_FOUND
    unknown_id = "00000000-0000-0000-0000-000000000000"
    resp_del_unknown = await client.delete(f"/api/v1/admin/mcp-keys/{unknown_id}")
    assert resp_del_unknown.status_code == 404
    assert resp_del_unknown.json()["code"] == "NOT_FOUND"

    # 7. Introspection of revoked key returns active: false
    async with httpx.AsyncClient(
        transport=int_transport, base_url="http://internal.test"
    ) as int_client:
        resp_intro_revoked = await int_client.post(
            intro_path,
            headers={"Content-Type": "application/json", "X-KB-Internal-Auth": internal_auth},
            content=body_agent,
        )
        assert resp_intro_revoked.status_code == 200
        contract_recorder.record(
            "mcp_introspect_revoked_200",
            resp_intro_revoked.request,
            resp_intro_revoked,
        )
        assert resp_intro_revoked.json()["active"] is False


@pytest.mark.asyncio
async def test_internal_mcp_introspect_missing_session_factory() -> None:
    """Introspection session dependency raises RuntimeError when app has no session factory."""

    class DummyApp:
        class DummyState:
            pass

        def __init__(self) -> None:
            self.state = self.DummyState()

    req = Request({"type": "http", "app": DummyApp()})
    with pytest.raises(RuntimeError, match="Session factory not configured"):
        async for _ in get_internal_session(req):
            pass


@pytest.mark.asyncio
async def test_admin_mcp_keys_hierarchical_and_unlimited_minting(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test admin endpoints with unlimited keys, disabled tools, and CIDRs."""
    admin_user = await make_user("hier_admin", workspace_role="WORKSPACE_ADMIN")
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": admin_user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": admin_user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    client = api_env.client
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )

    # 1. Mint key with unlimited=True and confirm_unlimited=True
    resp = await client.post(
        "/api/v1/admin/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
            "unlimited": True,
            "confirm_unlimited": True,
            "disabled_tools": ["complete_work"],
            "allowed_cidrs": ["10.0.0.0/8"],
        },
    )
    assert resp.status_code == 201
    contract_recorder.record("mint_admin_mcp_key_hierarchical_201", resp.request, resp)
    data = resp.json()
    assert data["scope_tier"] == "workspace"
    assert data["expires_at"] is None
    assert data["disabled_tools"] == ["complete_work"]
    assert data["allowed_cidrs"] == ["10.0.0.0/8"]
    key_id = data["id"]

    # 2. List with surface filter
    resp_list = await client.get("/api/v1/admin/mcp-keys?surface=agent&include_revoked=false")
    assert resp_list.status_code == 200
    assert any(k["id"] == key_id for k in resp_list.json())

    # 3. Revoke via DELETE /api/v1/admin/mcp-keys/{id}
    resp_del = await client.delete(f"/api/v1/admin/mcp-keys/{key_id}")
    assert resp_del.status_code == 204

    # 4. Revoke non-existent key returns 404
    resp_del_nf = await client.delete("/api/v1/admin/mcp-keys/00000000-0000-0000-0000-000000000000")
    assert resp_del_nf.status_code == 404

    # 5. SERVER_ADMIN listing with scope_tier filter and revoking global key
    server_admin = await make_user("global_sa", workspace_role="WORKSPACE_ADMIN")
    await api_env.seed.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :pid, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"ws_id": server_admin.workspace_id, "pid": server_admin.id},
    )
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {"p_id": server_admin.id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x01" + b"\x00" * 44},
    )
    res_totp = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": server_admin.id},
    )
    p_row = res_totp.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_global = await client.post(
        "/api/v1/admin/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "global",
            "owner_kind": "service_bot",
        },
    )
    assert resp_global.status_code == 201
    global_key_id = resp_global.json()["id"]

    resp_list_global = await client.get("/api/v1/admin/mcp-keys?scope_tier=global")
    assert resp_list_global.status_code == 200
    assert any(k["id"] == global_key_id for k in resp_list_global.json())

    # Regular admin cannot delete global key (404)
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    resp_del_denied = await client.delete(f"/api/v1/admin/mcp-keys/{global_key_id}")
    assert resp_del_denied.status_code == 404

    # Server admin can delete global key (204)
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_del_allowed = await client.delete(f"/api/v1/admin/mcp-keys/{global_key_id}")
    assert resp_del_allowed.status_code == 204


@pytest.mark.asyncio
async def test_personal_mcp_keys_api_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test personal self-service MCP key endpoints (mint, list, revoke, and authorization)."""
    user_a = await make_user("user_a", workspace_role="WORKSPACE_MEMBER")
    user_b = await make_user("user_b", workspace_role="WORKSPACE_MEMBER")

    client = api_env.client

    # 1. User A mints a personal MCP key
    api_env.resolver.principal = PrincipalContext(
        principal_id=user_a.id,
        workspace_id=user_a.workspace_id,
        aal_level=1,
    )
    resp_mint = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
            "disabled_tools": ["complete_work"],
        },
    )
    assert resp_mint.status_code == 201
    contract_recorder.record("mint_personal_mcp_key_201", resp_mint.request, resp_mint)
    mint_data = resp_mint.json()
    key_id = mint_data["id"]
    assert mint_data["owner_kind"] == "personal_user"
    assert mint_data["disabled_tools"] == ["complete_work"]

    # 2. User A lists their personal keys
    resp_list = await client.get("/api/v1/auth/mcp-keys")
    assert resp_list.status_code == 200
    contract_recorder.record("list_personal_mcp_keys_200", resp_list.request, resp_list)
    keys = resp_list.json()["keys"]
    assert any(k["id"] == key_id for k in keys)

    # 3. User B cannot see or revoke User A's key (404)
    api_env.resolver.principal = PrincipalContext(
        principal_id=user_b.id,
        workspace_id=user_b.workspace_id,
        aal_level=1,
    )
    resp_b_list = await client.get("/api/v1/auth/mcp-keys")
    assert not any(k["id"] == key_id for k in resp_b_list.json()["keys"])

    resp_b_del = await client.delete(f"/api/v1/auth/mcp-keys/{key_id}")
    assert resp_b_del.status_code == 404

    # 4. User A revokes their key (204)
    api_env.resolver.principal = PrincipalContext(
        principal_id=user_a.id,
        workspace_id=user_a.workspace_id,
        aal_level=1,
    )
    resp_del = await client.delete(f"/api/v1/auth/mcp-keys/{key_id}")
    assert resp_del.status_code == 204
    contract_recorder.record("revoke_personal_mcp_key_204", resp_del.request, resp_del)

    # 5. Revoking non-existent key returns 404
    resp_del_nf = await client.delete("/api/v1/auth/mcp-keys/00000000-0000-0000-0000-000000000000")
    assert resp_del_nf.status_code == 404

    # 6. Verify scope_tier='server' on /api/v1/auth/mcp-keys returns 403 (not 422 VALIDATION_FAILED)
    # AAL1 user attempting scope_tier='server' gets 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=user_a.id,
        workspace_id=user_a.workspace_id,
        aal_level=1,
    )
    resp_server_aal1 = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_server_aal1.status_code == 403
    assert resp_server_aal1.json()["code"] == "AAL2_REQUIRED"

    # AAL2 non-server-admin user attempting scope_tier='server' gets 403 INSUFFICIENT_CAPABILITY
    api_env.resolver.principal = PrincipalContext(
        principal_id=user_a.id,
        workspace_id=user_a.workspace_id,
        aal_level=2,
    )
    resp_server_aal2_non_admin = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
        },
    )
    assert resp_server_aal2_non_admin.status_code == 403
    assert resp_server_aal2_non_admin.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # Server admin with AAL2 succeeds minting scope_tier='server'
    server_admin = await make_user("srv_admin_personal", workspace_role="SERVER_ADMIN")
    api_env.resolver.principal = PrincipalContext(
        principal_id=server_admin.id,
        workspace_id=server_admin.workspace_id,
        aal_level=2,
    )
    resp_server_admin_ok = await client.post(
        "/api/v1/auth/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "server",
            "label": "Personal Server Bot",
        },
    )
    assert resp_server_admin_ok.status_code == 201
    assert resp_server_admin_ok.json()["scope_tier"] == "global"


@pytest.mark.asyncio
async def test_admin_mcp_keys_allowed_projects_and_project_admin_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test admin MCP keys allowed_projects resolution, project admin list & revoke (KAN-417)."""
    admin_user = await make_user("proj_admin_cov", workspace_role="WORKSPACE_ADMIN")
    proj_admin_user = await make_user("proj_admin_user", workspace_role="WORKSPACE_MEMBER")
    server_admin = await make_user("srv_admin_cov", workspace_role="SERVER_ADMIN")

    for u in (admin_user, proj_admin_user, server_admin):
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
            {
                "p_id": u.id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        res = await api_env.seed.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": u.id},
        )
        p_row = res.mappings().first()
        if p_row:
            await api_env.seed.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

    # Create real project in workspace and bind PROJECT_ADMIN to proj_admin_user
    real_proj_id = await create_project(
        api_env.seed,
        admin_user.workspace_id,
        identifier="PROJCOV",
        name="Coverage Project",
        created_by_id=admin_user.id,
    )
    await add_role_binding(
        api_env.seed,
        admin_user.workspace_id,
        proj_admin_user.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=real_proj_id,
    )
    await api_env.seed.commit()

    client = api_env.client
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )

    # 1. Mint key without explicit project_id so allowed_projects[0] becomes project_id
    fake_allowed_uuid = str(uuid.uuid4())
    resp_mint = await client.post(
        "/api/v1/admin/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "project",
            "allowed_projects": [
                "NON_EXISTENT_KEY",
                "PROJCOV",
                fake_allowed_uuid,
                "not-a-valid-uuid",
            ],
        },
    )
    assert resp_mint.status_code == 201
    mint_data = resp_mint.json()
    assert mint_data["scope_tier"] == "project"
    assert "PROJCOV" in mint_data.get("allowed_projects", [])
    key_id = mint_data["id"]

    # 2. List keys as project admin for that project
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin_user.id,
        workspace_id=proj_admin_user.workspace_id,
        aal_level=2,
    )
    resp_list_member = await client.get("/api/v1/admin/mcp-keys")
    assert resp_list_member.status_code == 200
    assert len(resp_list_member.json()) == 1
    assert resp_list_member.json()[0]["id"] == key_id

    # Filtering by scope_tier != project gets [] (hits line 304)
    resp_list_member_ws = await client.get("/api/v1/admin/mcp-keys?scope_tier=workspace")
    assert resp_list_member_ws.status_code == 200
    assert resp_list_member_ws.json() == []

    # 3. Mint a workspace-scoped key as workspace admin
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    resp_ws_mint = await client.post(
        "/api/v1/admin/mcp-keys",
        json={
            "surface": "agent",
            "scopes": ["agent:read"],
            "scope_tier": "workspace",
        },
    )
    assert resp_ws_mint.status_code == 201
    ws_key_id = resp_ws_mint.json()["id"]

    # 4. As project admin, attempting to revoke a workspace-tier key returns 404 (hits line 408)
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin_user.id,
        workspace_id=proj_admin_user.workspace_id,
        aal_level=2,
    )
    resp_del_ws_fail = await client.delete(f"/api/v1/admin/mcp-keys/{ws_key_id}")
    assert resp_del_ws_fail.status_code == 404

    # 5. Project admin revoking project-tier key for administered project succeeds (line 421)
    resp_del_proj_ok = await client.delete(f"/api/v1/admin/mcp-keys/{key_id}")
    assert resp_del_proj_ok.status_code == 204

    # 6. Revoke key as server admin with mismatched workspace_id (hits line 396 -> 404)
    ws2_id = await create_workspace(api_env.seed, name="WS-2-Coverage")
    ws2_user_id = await create_user(
        api_env.seed, ws2_id, handle="@ws2user", display_name="WS2 User"
    )
    await add_role_binding(
        api_env.seed, ws2_id, ws2_user_id, role="SERVER_ADMIN", scope_type="server"
    )
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": ws2_user_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": ws2_user_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=ws2_user_id,
        workspace_id=ws2_id,
        aal_level=2,
    )
    resp_del_server_mismatch = await client.delete(f"/api/v1/admin/mcp-keys/{ws_key_id}")
    assert resp_del_server_mismatch.status_code == 404

    # 7. Revoke key as workspace admin from different workspace (hits line 399 -> 404)
    other_ws_id = await create_workspace(api_env.seed, name="Other-WS")
    other_admin_id = await create_user(
        api_env.seed, other_ws_id, handle="@other_admin", display_name="Other Admin"
    )
    await add_role_binding(
        api_env.seed, other_ws_id, other_admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {"p_id": other_admin_id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x01" + b"\x00" * 44},
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": other_admin_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=other_admin_id,
        workspace_id=other_ws_id,
        aal_level=2,
    )
    resp_del_other_ws = await client.delete(f"/api/v1/admin/mcp-keys/{ws_key_id}")
    assert resp_del_other_ws.status_code == 404

    # 8. Revoke workspace key as proper admin succeeds
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    resp_del_ok = await client.delete(f"/api/v1/admin/mcp-keys/{ws_key_id}")
    assert resp_del_ok.status_code == 204


@pytest.mark.asyncio
async def test_admin_mcp_keys_helper_units(api_env: ApiEnv) -> None:
    """Direct unit tests for helper edge cases in admin/mcp_keys.py."""
    # 1. CIDR validator
    assert McpApiKeyMintRequest.validate_allowed_cidrs(None) is None
    assert McpApiKeyMintRequest.validate_allowed_cidrs([]) == []
    assert McpApiKeyMintRequest.validate_allowed_cidrs(["192.168.1.0/24"]) == ["192.168.1.0/24"]
    with pytest.raises(ValueError, match="Invalid CIDR block"):
        McpApiKeyMintRequest.validate_allowed_cidrs(["invalid-cidr"])

    # 2. Key project list resolver
    p_id = uuid.uuid4()
    dummy_key = McpApiKey(
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        surface="agent",
        key_prefix="kb_agt_",
        key_sha256=b"x" * 32,
        display_hint="test",
        scopes=["agent:read"],
        project_id=p_id,
        allowed_project_ids=None,
    )
    assert _resolve_admin_key_project_list(dummy_key, {p_id: "PROJ-KEY"}) == ["PROJ-KEY"]
    assert _resolve_admin_key_project_list(dummy_key, {}) == [str(p_id)]

    dummy_key_allowed = McpApiKey(
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        surface="agent",
        key_prefix="kb_agt_",
        key_sha256=b"x" * 32,
        display_hint="test",
        scopes=["agent:read"],
        project_id=None,
        allowed_project_ids=[p_id],
    )
    assert _resolve_admin_key_project_list(
        dummy_key_allowed, {p_id: "ALLOWED-KEY"}
    ) == ["ALLOWED-KEY"]

    dummy_key_none = McpApiKey(
        workspace_id=uuid.uuid4(),
        principal_id=uuid.uuid4(),
        surface="agent",
        key_prefix="kb_agt_",
        key_sha256=b"x" * 32,
        display_hint="test",
        scopes=["agent:read"],
        project_id=None,
        allowed_project_ids=None,
    )
    assert _resolve_admin_key_project_list(dummy_key_none, {}) is None

    # 3. Project key map resolver
    assert await _resolve_admin_project_id_to_key_map(api_env.seed, set()) == {}
    res_map = await _resolve_admin_project_id_to_key_map(api_env.seed, {p_id})
    assert isinstance(res_map, dict)

    class BadSession:
        async def execute(self, *_args: object, **_kwargs: object) -> None:
            msg = "DB fail"
            raise RuntimeError(msg)

    assert await _resolve_admin_project_id_to_key_map(BadSession(), {p_id}) == {}  # type: ignore[arg-type]


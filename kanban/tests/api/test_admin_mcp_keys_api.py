# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""API integration tests for admin MCP keys endpoints and introspection (KB-P4-02a)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

from kanban.api.deps import PrincipalContext
from kanban.api.internal.mcp_introspect import get_internal_session
from kanban.security.mcp_keys import create_internal_mcp_auth_header

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
async def test_admin_mcp_keys_endpoints_lifecycle(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test admin REST endpoints (AAL2 enforcement, mint, list, revoke) & internal introspection."""
    admin_user = await make_user("mcp_admin", workspace_role="WORKSPACE_ADMIN")
    member_user = await make_user("mcp_member", workspace_role="WORKSPACE_MEMBER")

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

    # 5. Internal introspection via POST /internal/v1/mcp/introspect
    # 5a. Missing internal auth header returns 401
    resp_intro_noauth = await client.post(
        "/internal/v1/mcp/introspect",
        json={"token": token, "surface": "agent"},
    )
    assert resp_intro_noauth.status_code == 401

    # 5a2. Client certificate authentication bypasses HMAC header requirement
    resp_intro_cert = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-Ssl-Client-Cert": "test-client-cert-content"},
        json={"token": token, "surface": "agent"},
    )
    assert resp_intro_cert.status_code == 200
    assert resp_intro_cert.json()["active"] is True

    # 5b. Valid internal auth header returns active: true
    internal_auth = create_internal_mcp_auth_header()
    resp_intro = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": internal_auth},
        json={"token": token, "surface": "agent"},
    )
    assert resp_intro.status_code == 200
    contract_recorder.record("mcp_introspect_active_200", resp_intro.request, resp_intro)
    intro_data = resp_intro.json()
    assert intro_data["active"] is True
    assert intro_data["surface"] == "agent"
    assert intro_data["scopes"] == ["agent:read", "agent:write"]

    # 5c. Surface mismatch via introspection returns active: false, reason: SURFACE_KEY_MISMATCH
    resp_intro_mismatch = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": internal_auth},
        json={"token": token, "surface": "admin"},
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
    resp_intro_revoked = await client.post(
        "/internal/v1/mcp/introspect",
        headers={"X-KB-Internal-Auth": internal_auth},
        json={"token": token, "surface": "agent"},
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

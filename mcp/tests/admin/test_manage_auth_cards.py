# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_auth_cards (KB-P4-09a)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
import yaml
from sqlalchemy import text

from kanban.auth.cards.lockout import record_external_admin_handshake
from kanban.auth.cards.repository import admin_upsert
from mcp.app import create_mcp_app
from mcp.auth import McpAuthMiddleware
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.settings import McpSettings
from mcp.surfaces.admin.manage_auth_cards import (
    _derive_slug,
    _extract_secret_string,
    create_manage_auth_cards_tool,
    manage_auth_cards,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_manage_auth_cards(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_auth_cards via JSON-RPC 2.0 tools/call on /mcp/admin."""
    active_session_id = session_id
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/admin",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-admin", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token
    if scopes is not None:
        headers["X-KB-Scopes"] = scopes
    if aal_level is not None:
        headers["X-KB-AAL-Level"] = str(aal_level)

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "manage_auth_cards",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data)


@pytest.mark.asyncio
async def test_manage_auth_cards_lifecycle_and_secret_redaction(
    admin_env: AdminTestEnv,
) -> None:
    """Create OIDC card with secret canary, list without secret.

    Get, update, reorder first, toggle.
    """
    # 1. Create LOCAL_ADMIN card first in database so system has primary local admin
    await admin_env.seed_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(admin_env.server_admin.id), "w_id": str(admin_env.workspace_id)},
    )
    c_local_id = uuid.uuid4()
    await admin_upsert(
        admin_env.seed_session,
        card_id=c_local_id,
        workspace_id=admin_env.workspace_id,
        provider_kind="LOCAL_ADMIN",
        slug="local-admin",
        display_name="Local Admin",
        button_subtext="Built-in Emergency Admin",
        is_enabled=True,
        sort_rank="1001",
        dek_kid="test-kid-1",
    )
    await admin_env.seed_session.commit()

    # 2. Action: 'create' with test secret canary 's3cr3t-canary-91'
    d_create = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "create",
            "provider_kind": "OIDC",
            "slug": "okta-sso",
            "display_name": "Okta Enterprise SSO",
            "button_subtext": "Sign in with Okta",
            "icon_preset": "okta",
            "public_config": {
                "kind": "OIDC",
                "issuer": "https://auth.example.com",
                "client_id": "okta-client-123",
            },
            "secret": {
                "client_secret": "s3cr3t-canary-91",
            },
            "allowed_email_domains": ["example.com"],
            "auto_provision_users": True,
        },
        scopes="admin:write",
    )
    res_create = d_create["result"]
    assert not res_create.get("isError")
    created_yaml = yaml.safe_load(res_create["content"][0]["text"])
    assert created_yaml["slug"] == "okta-sso"
    assert created_yaml["provider_kind"] == "OIDC"
    # Ensure secrets never returned
    assert "client_secret" not in created_yaml
    assert "encrypted_secret_blob" not in created_yaml
    assert "wrapped_dek" not in created_yaml

    # 3. Action: 'list' returns summary projection and no secrets
    d_list = await _call_manage_auth_cards(
        admin_env,
        {"action": "list"},
        scopes="admin:read",
    )
    assert not d_list["result"].get("isError")
    list_yaml = yaml.safe_load(d_list["result"]["content"][0]["text"])
    assert "cards" in list_yaml
    slugs = [c["slug"] for c in list_yaml["cards"]]
    assert "local-admin" in slugs
    assert "okta-sso" in slugs
    for card in list_yaml["cards"]:
        assert "client_secret" not in card
        assert "encrypted_secret_blob" not in card
        assert "wrapped_dek" not in card

    # 4. Action: 'get' by slug
    d_get = await _call_manage_auth_cards(
        admin_env,
        {"action": "get", "card": "okta-sso"},
        scopes="admin:read",
    )
    assert not d_get["result"].get("isError")
    get_yaml = yaml.safe_load(d_get["result"]["content"][0]["text"])
    assert get_yaml["slug"] == "okta-sso"
    assert "client_secret" not in get_yaml
    assert "encrypted_secret_blob" not in get_yaml

    # 5. Action: 'update' card metadata
    d_up = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "update",
            "card": "okta-sso",
            "display_name": "Corporate Okta Identity",
            "button_subtext": "Single Sign-On",
            "allowed_email_domains": ["corp.example.com"],
            "secret": {"client_secret": "updated-secret"},
        },
        scopes="admin:write",
    )
    assert not d_up["result"].get("isError")
    up_yaml = yaml.safe_load(d_up["result"]["content"][0]["text"])
    assert up_yaml["display_name"] == "Corporate Okta Identity"

    # 6. Action: 'reorder' to first position (after="")
    d_reorder = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "reorder",
            "card": "okta-sso",
            "after": "",
        },
        scopes="admin:write",
    )
    assert not d_reorder["result"].get("isError")
    reorder_yaml = yaml.safe_load(d_reorder["result"]["content"][0]["text"])
    assert reorder_yaml["slug"] == "okta-sso"

    # 7. Action: 'test_handshake' probe
    d_probe = await _call_manage_auth_cards(
        admin_env,
        {"action": "test_handshake", "card": "local-admin"},
        scopes="admin:read",
    )
    assert not d_probe["result"].get("isError")
    probe_yaml = yaml.safe_load(d_probe["result"]["content"][0]["text"])
    assert probe_yaml["status"] in ("OK", "UNVERIFIED")

    # 8. Action: 'enable' card
    d_enable = await _call_manage_auth_cards(
        admin_env,
        {"action": "enable", "card": "okta-sso"},
        scopes="admin:write",
    )
    assert not d_enable["result"].get("isError")
    enable_yaml = yaml.safe_load(d_enable["result"]["content"][0]["text"])
    assert enable_yaml["is_enabled"] is True


@pytest.mark.asyncio
async def test_manage_auth_cards_lockout_layers_db_trigger_and_probe(
    admin_env: AdminTestEnv,
) -> None:
    """Verify both LOCKOUT_PREVENTED variants: handshake_probe_15m and db_trigger."""
    # Seed LOCAL_ADMIN card and OIDC card in database
    await admin_env.seed_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(admin_env.server_admin.id), "w_id": str(admin_env.workspace_id)},
    )
    c_local_id = uuid.uuid4()
    await admin_upsert(
        admin_env.seed_session,
        card_id=c_local_id,
        workspace_id=admin_env.workspace_id,
        provider_kind="LOCAL_ADMIN",
        slug="lockout-local-admin",
        display_name="Local Admin",
        button_subtext="Emergency Root",
        is_enabled=True,
        sort_rank="1001",
        dek_kid="test-kid-1",
    )

    c_oidc_id = uuid.uuid4()
    await admin_upsert(
        admin_env.seed_session,
        card_id=c_oidc_id,
        workspace_id=admin_env.workspace_id,
        provider_kind="OIDC",
        slug="lockout-ext-oidc",
        display_name="External OIDC Card",
        is_enabled=True,
        sort_rank="2001",
        dek_kid="test-kid-1",
    )
    await admin_env.seed_session.execute(
        text(
            "INSERT INTO user_identities ("
            "  workspace_id, auth_card_id, principal_id, "
            "  immutable_subject_id, subject_email_at_link"
            ") VALUES (:ws_id, :cid, :pid, 'oidc-admin-sub', 'server-admin@example.com')"
        ),
        {"ws_id": admin_env.workspace_id, "cid": c_oidc_id, "pid": admin_env.server_admin.id},
    )
    await admin_env.seed_session.commit()

    # 1. Layer 2: Disabling LOCAL_ADMIN without recent external admin handshake
    # -> handshake_probe_15m
    d_probe_lockout = await _call_manage_auth_cards(
        admin_env,
        {"action": "disable", "card": "lockout-local-admin"},
        scopes="admin:write",
    )
    assert d_probe_lockout["result"]["isError"] is True
    err_probe = yaml.safe_load(d_probe_lockout["result"]["content"][0]["text"])["error"]
    assert err_probe["code"] == "LOCKOUT_PREVENTED"
    assert "handshake_probe_15m" in (err_probe.get("hint") or "")

    # Record verified external admin login handshake for the OIDC card
    await record_external_admin_handshake(admin_env.seed_session, c_oidc_id)
    await admin_env.seed_session.commit()

    # Now disabling LOCAL_ADMIN succeeds
    d_local_disable = await _call_manage_auth_cards(
        admin_env,
        {"action": "disable", "card": "lockout-local-admin"},
        scopes="admin:write",
    )
    assert not d_local_disable["result"].get("isError")

    # 2. Layer 1: Attempting to disable sole remaining admin-capable card -> db_trigger
    d_sole_lockout = await _call_manage_auth_cards(
        admin_env,
        {"action": "disable", "card": "lockout-ext-oidc"},
        scopes="admin:write",
    )
    assert d_sole_lockout["result"]["isError"] is True
    err_db = yaml.safe_load(d_sole_lockout["result"]["content"][0]["text"])["error"]
    assert err_db["code"] == "LOCKOUT_PREVENTED"
    assert "db_trigger" in (err_db.get("hint") or "")


@pytest.mark.asyncio
async def test_manage_auth_cards_delete_and_confirmation_phrase(
    admin_env: AdminTestEnv,
) -> None:
    """Delete requires admin:destructive and confirm_slug matching card slug."""
    await admin_env.seed_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(admin_env.server_admin.id), "w_id": str(admin_env.workspace_id)},
    )
    c_del_id = uuid.uuid4()
    await admin_upsert(
        admin_env.seed_session,
        card_id=c_del_id,
        workspace_id=admin_env.workspace_id,
        provider_kind="OIDC",
        slug="unused-card-to-delete",
        display_name="Unused Card",
        is_enabled=False,
        sort_rank="1001",
        dek_kid="test-kid-1",
    )
    await admin_env.seed_session.commit()

    # 1. Delete with admin:write scope only -> INSUFFICIENT_SCOPE
    d_scope = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "delete",
            "card": "unused-card-to-delete",
            "confirm_slug": "unused-card-to-delete",
        },
        scopes="admin:write",
    )
    assert d_scope["result"]["isError"] is True
    err_scope = yaml.safe_load(d_scope["result"]["content"][0]["text"])["error"]
    assert err_scope["code"] == "INSUFFICIENT_SCOPE"

    # 2. Delete with wrong confirm_slug -> CONFIRM_PHRASE_MISMATCH
    d_mismatch = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "delete",
            "card": "unused-card-to-delete",
            "confirm_slug": "wrong-slug-phrase",
        },
        scopes="admin:destructive",
    )
    assert d_mismatch["result"]["isError"] is True
    err_mismatch = yaml.safe_load(d_mismatch["result"]["content"][0]["text"])["error"]
    assert err_mismatch["code"] == "CONFIRM_PHRASE_MISMATCH"

    # 3. Delete with matching confirm_slug -> succeeds
    d_del_ok = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "delete",
            "card": "unused-card-to-delete",
            "confirm_slug": "unused-card-to-delete",
        },
        scopes="admin:destructive",
    )
    assert not d_del_ok["result"].get("isError")
    del_yaml = yaml.safe_load(d_del_ok["result"]["content"][0]["text"])
    assert del_yaml["deleted"] is True


@pytest.mark.asyncio
async def test_manage_auth_cards_boundary_validations(admin_env: AdminTestEnv) -> None:
    """Boundary validations: max 50 email domains, missing fields, unknown action."""
    # 1. 51 email domains -> VALIDATION_FAILED
    d_domains = await _call_manage_auth_cards(
        admin_env,
        {
            "action": "create",
            "provider_kind": "OIDC",
            "display_name": "Test Card",
            "allowed_email_domains": [f"domain{i}.com" for i in range(51)],
        },
        scopes="admin:write",
    )
    assert d_domains["result"]["isError"] is True
    err_dom = yaml.safe_load(d_domains["result"]["content"][0]["text"])["error"]
    assert err_dom["code"] == "VALIDATION_FAILED"

    # 2. Missing card reference for get
    d_no_card = await _call_manage_auth_cards(
        admin_env,
        {"action": "get"},
        scopes="admin:read",
    )
    assert d_no_card["result"]["isError"] is True
    assert (
        yaml.safe_load(d_no_card["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 3. Missing display_name on create
    d_no_name = await _call_manage_auth_cards(
        admin_env,
        {"action": "create", "provider_kind": "OIDC"},
        scopes="admin:write",
    )
    assert d_no_name["result"]["isError"] is True
    assert (
        yaml.safe_load(d_no_name["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 4. Unknown action
    d_unknown = await _call_manage_auth_cards(
        admin_env,
        {"action": "unknown_action"},
    )
    assert d_unknown["result"]["isError"] is True
    assert (
        yaml.safe_load(d_unknown["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 5. Unknown parameter
    d_bad_param = await _call_manage_auth_cards(
        admin_env,
        {"action": "list", "unexpected_param": "foo"},
    )
    assert d_bad_param["result"]["isError"] is True
    assert (
        yaml.safe_load(d_bad_param["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 6. Invalid provider_kind for create
    d_bad_kind = await _call_manage_auth_cards(
        admin_env,
        {"action": "create", "provider_kind": "INVALID_KIND", "display_name": "Test"},
        scopes="admin:write",
    )
    assert d_bad_kind["result"]["isError"] is True
    assert (
        yaml.safe_load(d_bad_kind["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 7. Delete without confirm_slug parameter
    d_no_confirm = await _call_manage_auth_cards(
        admin_env,
        {"action": "delete", "card": "some-card"},
        scopes="admin:destructive",
    )
    assert d_no_confirm["result"]["isError"] is True
    assert (
        yaml.safe_load(d_no_confirm["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 8. List with lod="full"
    d_list_full = await _call_manage_auth_cards(
        admin_env,
        {"action": "list", "lod": "full"},
        scopes="admin:read",
    )
    assert not d_list_full["result"].get("isError")
    full_yaml = yaml.safe_load(d_list_full["result"]["content"][0]["text"])
    assert full_yaml == {} or "cards" in full_yaml

    # 9. Insufficient scope: list with no scopes
    d_no_scope_list = await _call_manage_auth_cards(
        admin_env,
        {"action": "list"},
        scopes="",
    )
    assert d_no_scope_list["result"]["isError"] is True
    assert (
        yaml.safe_load(d_no_scope_list["result"]["content"][0]["text"])["error"]["code"]
        == "INSUFFICIENT_SCOPE"
    )

    # 10. Insufficient scope: create with admin:read only
    d_read_create = await _call_manage_auth_cards(
        admin_env,
        {"action": "create", "provider_kind": "OIDC", "display_name": "Test"},
        scopes="admin:read",
    )
    assert d_read_create["result"]["isError"] is True
    assert (
        yaml.safe_load(d_read_create["result"]["content"][0]["text"])["error"]["code"]
        == "INSUFFICIENT_SCOPE"
    )


@pytest.mark.asyncio
async def test_manage_auth_cards_surface_key_mismatch_and_middleware(
    admin_env: AdminTestEnv,
) -> None:
    """Calling /mcp/admin with kb_agt_ key returns 403 SURFACE_KEY_MISMATCH."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mcp_app_auth = create_mcp_app(settings, kanban_app=admin_env.fastapi_app)

    mw = McpAuthMiddleware(
        mcp_app_auth,
        surface=Surface.ADMIN,
        internal_client=admin_env.internal_client,
        settings=settings,
    )
    transport = httpx.ASGITransport(app=mw)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. kb_agt_ key on /mcp/admin -> 403 SURFACE_KEY_MISMATCH
        agent_key = "kb_agt_" + "9" * 32
        resp = await client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {agent_key}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "SURFACE_KEY_MISMATCH"


@pytest.mark.asyncio
async def test_manage_auth_cards_tool_spec_and_direct_invocation() -> None:
    """Directly test ToolSpec metadata, help branch, and context errors."""
    tool = create_manage_auth_cards_tool()
    assert tool.name == "manage_auth_cards"
    assert tool.surface == Surface.ADMIN

    # Direct call for action="help"
    help_out = await manage_auth_cards({"action": "help"})
    help_yaml = yaml.safe_load(help_out)
    assert help_yaml["tool"] == "manage_auth_cards"

    # Direct call without MCP context raises UPSTREAM_UNAVAILABLE
    with pytest.raises(KbMcpError) as exc_info:
        await manage_auth_cards({"action": "list"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    assert _extract_secret_string("raw-secret") == "raw-secret"
    assert _extract_secret_string({"secret": "key-secret"}) == "key-secret"
    assert _extract_secret_string({"bind_dn_password": "ldap-pw"}) == "ldap-pw"
    assert _extract_secret_string(None) is None

    assert _derive_slug(None, None, "Google Enterprise SSO") == "google-enterprise-sso"
    assert _derive_slug(None, None, "OK") == "ok-auth"
    assert _derive_slug(None, None, None) == "auth-card"
    assert _derive_slug("my-card", None, None) == "my-card"

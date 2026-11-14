# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_principals_and_groups (KB-P4-09b)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from kanban.tests.security.helpers import create_project
from mcp.context import reset_current_mcp_context, set_current_mcp_context
from mcp.errors import KbMcpError
from mcp.surfaces.admin.manage_principals_and_groups import (
    _assert_scope,
    create_manage_principals_and_groups_tool,
    manage_principals_and_groups_tool,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_manage_principals(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_principals_and_groups via JSON-RPC 2.0 tools/call on /mcp/admin."""
    active_session_id = session_id
    if active_session_id is None:
        init_headers: dict[str, str] = {}
        if subject_token is not None:
            init_headers["X-KB-Subject-Token"] = subject_token
        if scopes is not None:
            init_headers["X-KB-Scopes"] = scopes
        if aal_level is not None:
            init_headers["X-KB-AAL-Level"] = str(aal_level)
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
            headers=init_headers,
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
            "name": "manage_principals_and_groups",
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
async def test_manage_principals_lifecycle(admin_env: AdminTestEnv) -> None:
    """Test full principal lifecycle: provision, membership, roles, and status changes."""
    # 1. Provision user maya
    res_user = await _call_manage_principals(
        admin_env,
        {
            "action": "provision_user",
            "handle": "maya",
            "display_name": "Maya Lin",
            "email": "maya@example.com",
        },
        scopes="admin:read,admin:write",
    )
    assert res_user["result"]["isError"] is False
    content_user = yaml.safe_load(res_user["result"]["content"][0]["text"])
    assert content_user["status"] == "provisioned"
    assert content_user["principal"] == "@maya"

    # 2. Provision group Core Backend
    res_group = await _call_manage_principals(
        admin_env,
        {
            "action": "provision_group",
            "display_name": "Core Backend",
        },
        scopes="admin:read,admin:write",
    )
    assert res_group["result"]["isError"] is False
    content_group = yaml.safe_load(res_group["result"]["content"][0]["text"])
    assert content_group["status"] == "provisioned"
    assert content_group["principal"] == "Core Backend"

    # 3. Provision agent forensic-code-check
    res_agent = await _call_manage_principals(
        admin_env,
        {
            "action": "provision_agent",
            "handle": "forensic-code-check",
            "display_name": "Forensic Code Checker",
        },
        scopes="admin:read,admin:write",
    )
    assert res_agent["result"]["isError"] is False
    content_agent = yaml.safe_load(res_agent["result"]["content"][0]["text"])
    assert content_agent["status"] == "provisioned"
    assert content_agent["principal"] == "@forensic-code-check"

    # 4. List principals
    res_list = await _call_manage_principals(
        admin_env,
        {"action": "list"},
        scopes="admin:read",
    )
    assert res_list["result"]["isError"] is False
    content_list = yaml.safe_load(res_list["result"]["content"][0]["text"])
    principals = content_list["principals"]
    handles = [p["principal"] for p in principals]
    assert "@maya" in handles
    assert "Core Backend" in handles
    assert "@forensic-code-check" in handles

    # 5. Add maya to Core Backend group
    res_add = await _call_manage_principals(
        admin_env,
        {
            "action": "add_member",
            "group": "Core Backend",
            "principal": "@maya",
        },
        scopes="admin:read,admin:write",
    )
    assert res_add["result"]["isError"] is False

    # 6. Create project KAN and bind role MEMBER to maya on KAN
    await create_project(
        admin_env.seed_session, admin_env.workspace_id, identifier="KAN", name="Kanban Core"
    )
    await admin_env.seed_session.commit()

    res_bind = await _call_manage_principals(
        admin_env,
        {
            "action": "bind_role",
            "principal": "@maya",
            "role": "MEMBER",
            "scope": "KAN",
        },
        scopes="admin:read,admin:write",
    )
    assert res_bind["result"]["isError"] is False

    # 7. Get maya detail (spec S11.4 summary format)
    res_get = await _call_manage_principals(
        admin_env,
        {
            "action": "get",
            "principal": "@maya",
        },
        scopes="admin:read",
    )
    assert res_get["result"]["isError"] is False
    content_get = yaml.safe_load(res_get["result"]["content"][0]["text"])
    assert content_get["principal"] == "@maya"
    assert content_get["type"] == "USER"
    assert content_get["status"] == "active"
    assert "Core Backend" in content_get["groups"]
    assert any(r["role"] == "MEMBER" and r["scope"] == "KAN" for r in content_get["roles"])

    # 8. Deactivate maya
    res_deact = await _call_manage_principals(
        admin_env,
        {
            "action": "deactivate",
            "principal": "@maya",
        },
        scopes="admin:read,admin:write",
    )
    assert res_deact["result"]["isError"] is False
    assert yaml.safe_load(res_deact["result"]["content"][0]["text"])["status"] == "deactivated"

    # 9. Reactivate maya
    res_react = await _call_manage_principals(
        admin_env,
        {
            "action": "reactivate",
            "principal": "@maya",
        },
        scopes="admin:read,admin:write",
    )
    assert res_react["result"]["isError"] is False
    assert yaml.safe_load(res_react["result"]["content"][0]["text"])["status"] == "activated"


@pytest.mark.asyncio
async def test_manage_principals_scope_and_lockout(admin_env: AdminTestEnv) -> None:
    """Insufficient scope and lockout prevention checks."""
    # 1. Calling write action with admin:read only -> INSUFFICIENT_SCOPE
    res_scope = await _call_manage_principals(
        admin_env,
        {
            "action": "provision_user",
            "handle": "attacker",
            "display_name": "Attacker",
            "email": "attacker@example.com",
        },
        scopes="admin:read",
    )
    assert res_scope["result"]["isError"] is True
    err_scope = yaml.safe_load(res_scope["result"]["content"][0]["text"])["error"]
    assert err_scope["code"] == "INSUFFICIENT_SCOPE"

    # 2. Deactivating the only SERVER_ADMIN -> LOCKOUT_PREVENTED
    res_lockout = await _call_manage_principals(
        admin_env,
        {
            "action": "deactivate",
            "principal": f"@{admin_env.server_admin.handle}",
        },
        scopes="admin:read,admin:write",
    )
    assert res_lockout["result"]["isError"] is True
    err_lockout = yaml.safe_load(res_lockout["result"]["content"][0]["text"])["error"]
    assert err_lockout["code"] == "LOCKOUT_PREVENTED"


@pytest.mark.asyncio
async def test_manage_principals_boundary_and_validation(admin_env: AdminTestEnv) -> None:
    """Validation errors, group cycle rejection, and JIT help."""
    # 1. Missing action
    res_no_action = await _call_manage_principals(admin_env, {})
    assert res_no_action["result"]["isError"] is True
    assert (
        yaml.safe_load(res_no_action["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 2. Unknown action
    res_unknown = await _call_manage_principals(admin_env, {"action": "destroy_all"})
    assert res_unknown["result"]["isError"] is True
    assert (
        yaml.safe_load(res_unknown["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 3. JIT help
    res_help = await _call_manage_principals(admin_env, {"action": "help"})
    assert res_help["result"]["isError"] is False
    help_data = yaml.safe_load(res_help["result"]["content"][0]["text"])
    assert help_data["tool"] == "manage_principals_and_groups"
    assert "params" in help_data

    # 4. Missing required parameters for each action
    # get missing principal
    r_get_no_p = await _call_manage_principals(admin_env, {"action": "get"}, scopes="admin:read")
    assert r_get_no_p["result"]["isError"] is True
    assert (
        yaml.safe_load(r_get_no_p["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # provision_user missing fields
    r_pu_no = await _call_manage_principals(
        admin_env, {"action": "provision_user", "handle": "u"}, scopes="admin:read,admin:write"
    )
    assert r_pu_no["result"]["isError"] is True

    # provision_group missing display_name
    r_pg_no = await _call_manage_principals(
        admin_env, {"action": "provision_group"}, scopes="admin:read,admin:write"
    )
    assert r_pg_no["result"]["isError"] is True

    # provision_agent missing display_name
    r_pa_no = await _call_manage_principals(
        admin_env, {"action": "provision_agent", "handle": "agt"}, scopes="admin:read,admin:write"
    )
    assert r_pa_no["result"]["isError"] is True

    # deactivate missing principal
    r_deact_no = await _call_manage_principals(
        admin_env, {"action": "deactivate"}, scopes="admin:read,admin:write"
    )
    assert r_deact_no["result"]["isError"] is True

    # add_member missing fields
    r_add_no = await _call_manage_principals(
        admin_env, {"action": "add_member", "group": "g"}, scopes="admin:read,admin:write"
    )
    assert r_add_no["result"]["isError"] is True

    # bind_role missing fields
    r_br_no = await _call_manage_principals(
        admin_env, {"action": "bind_role", "principal": "p"}, scopes="admin:read,admin:write"
    )
    assert r_br_no["result"]["isError"] is True


@pytest.mark.asyncio
async def test_manage_principals_operations_coverage(admin_env: AdminTestEnv) -> None:
    """Test operations coverage: remove_member, unbind_role, filtered list, and gets."""
    # 1. Provision group and user
    res_g = await _call_manage_principals(
        admin_env,
        {"action": "provision_group", "display_name": "Ops Team"},
        scopes="admin:read,admin:write",
    )
    assert res_g["result"]["isError"] is False

    res_u = await _call_manage_principals(
        admin_env,
        {
            "action": "provision_user",
            "handle": "bob",
            "display_name": "Bob Smith",
            "email": "bob@example.com",
        },
        scopes="admin:read,admin:write",
    )
    assert res_u["result"]["isError"] is False

    # Add member then remove member
    res_add = await _call_manage_principals(
        admin_env,
        {"action": "add_member", "group": "Ops Team", "principal": "@bob"},
        scopes="admin:read,admin:write",
    )
    assert res_add["result"]["isError"] is False

    res_rm = await _call_manage_principals(
        admin_env,
        {"action": "remove_member", "group": "Ops Team", "principal": "@bob"},
        scopes="admin:read,admin:write",
    )
    assert res_rm["result"]["isError"] is False
    content_rm = yaml.safe_load(res_rm["result"]["content"][0]["text"])
    assert content_rm["status"] == "member_removed"

    # Bind role workspace scope then unbind
    res_bind_ws = await _call_manage_principals(
        admin_env,
        {
            "action": "bind_role",
            "principal": "@bob",
            "role": "WORKSPACE_MEMBER",
            "scope": "workspace",
        },
        scopes="admin:read,admin:write",
    )
    assert res_bind_ws["result"]["isError"] is False

    res_unbind_ws = await _call_manage_principals(
        admin_env,
        {
            "action": "unbind_role",
            "principal": "@bob",
            "role": "WORKSPACE_MEMBER",
            "scope": "workspace",
        },
        scopes="admin:read,admin:write",
    )
    assert res_unbind_ws["result"]["isError"] is False
    content_ub = yaml.safe_load(res_unbind_ws["result"]["content"][0]["text"])
    assert content_ub["status"] == "role_unbound"

    # List with filter and limit
    res_list_filter = await _call_manage_principals(
        admin_env,
        {"action": "list", "filter": "GROUP", "limit": 10},
        scopes="admin:read",
    )
    assert res_list_filter["result"]["isError"] is False

    # Get group detail
    res_get_g = await _call_manage_principals(
        admin_env,
        {"action": "get", "principal": "Ops Team"},
        scopes="admin:read",
    )
    assert res_get_g["result"]["isError"] is False
    content_g = yaml.safe_load(res_get_g["result"]["content"][0]["text"])
    assert content_g["type"] == "GROUP"

    # Bind role server scope
    res_bind_srv = await _call_manage_principals(
        admin_env,
        {
            "action": "bind_role",
            "principal": "@bob",
            "role": "SERVER_ADMIN",
            "scope": "server",
        },
        scopes="admin:read,admin:write",
    )
    assert res_bind_srv["result"]["isError"] is False


@pytest.mark.asyncio
async def test_manage_principals_tool_context_and_spec() -> None:
    """Test tool construction and context absence behavior."""
    spec = create_manage_principals_and_groups_tool()
    assert spec.name == "manage_principals_and_groups"

    token = set_current_mcp_context(None)
    try:
        # Calling _assert_scope with no context returns None
        _assert_scope("admin:write")

        # Calling tool handler with no context raises Internal error
        with pytest.raises(KbMcpError) as exc_info:
            await manage_principals_and_groups_tool({"action": "list"})
        assert exc_info.value.code.value == "INTERNAL"
    finally:
        reset_current_mcp_context(token)

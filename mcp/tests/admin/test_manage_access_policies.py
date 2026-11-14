# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_access_policies (KB-P4-09b)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml

from kanban.tests.security.helpers import (
    create_group,
    create_project,
    create_registered_object,
    create_user,
)
from mcp.context import reset_current_mcp_context, set_current_mcp_context
from mcp.errors import KbMcpError
from mcp.surfaces.admin.manage_access_policies import (
    _assert_scope,
    _format_caps_summary,
    _format_inspect_summary,
    create_manage_access_policies_tool,
    manage_access_policies_tool,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_manage_access_policies(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_access_policies via JSON-RPC 2.0 tools/call on /mcp/admin."""
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
            "name": "manage_access_policies",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data)


class _TestObject:
    def __init__(self, obj_id: uuid.UUID, key: str) -> None:
        self.id = obj_id
        self.key = key


async def _setup_issue_with_object(env: AdminTestEnv, key: str = "KAN-142") -> _TestObject:
    """Register project KAN and issue KAN-142 with object spine."""
    prj_id = await create_project(
        env.seed_session, env.workspace_id, identifier="KAN", name="Kanban Core"
    )

    issue_id = await create_registered_object(
        env.seed_session,
        env.workspace_id,
        kind="issue",
        key=key,
        title=f"Issue {key}",
        project_id=prj_id,
        created_by_id=env.server_admin.id,
    )
    await env.seed_session.commit()
    return _TestObject(issue_id, key)


@pytest.mark.asyncio
async def test_manage_access_policies_grant_and_inspect(admin_env: AdminTestEnv) -> None:
    """Grant ALLOW to group, inspect manifest with Spec S11.4 summary YAML, and revoke."""
    await _setup_issue_with_object(admin_env, "KAN-142")

    # 1. Provision group SecOps Reviewers
    await create_group(admin_env.seed_session, admin_env.workspace_id, "SecOps Reviewers")
    await admin_env.seed_session.commit()

    # 2. Grant ALLOW [VIEW, COMMENT] to group
    res_grant = await _call_manage_access_policies(
        admin_env,
        {
            "action": "grant",
            "object": "KAN-142",
            "principal": "SecOps Reviewers",
            "effect": "ALLOW",
            "capabilities": ["VIEW", "COMMENT"],
        },
        scopes="admin:read,admin:write",
    )
    assert res_grant["result"]["isError"] is False
    content_grant = yaml.safe_load(res_grant["result"]["content"][0]["text"])
    assert content_grant["status"] == "granted"
    assert content_grant["object"] == "KAN-142"
    assert content_grant["principal"] == "SecOps Reviewers"

    # 3. Inspect access manifest (spec S11.4 summary format)
    res_inspect = await _call_manage_access_policies(
        admin_env,
        {
            "action": "inspect",
            "object": "KAN-142",
        },
        scopes="admin:read",
    )
    assert res_inspect["result"]["isError"] is False
    content_inspect = yaml.safe_load(res_inspect["result"]["content"][0]["text"])
    assert content_inspect["object"] == "KAN-142"
    assert "inherited_scope" in content_inspect
    group_entries = content_inspect.get("groups", [])
    assert any(g["who"] == "SecOps Reviewers" for g in group_entries)

    # 4. Revoke grant
    res_revoke = await _call_manage_access_policies(
        admin_env,
        {
            "action": "revoke",
            "object": "KAN-142",
            "principal": "SecOps Reviewers",
            "effect": "ALLOW",
        },
        scopes="admin:read,admin:write",
    )
    assert res_revoke["result"]["isError"] is False
    content_revoke = yaml.safe_load(res_revoke["result"]["content"][0]["text"])
    assert content_revoke["status"] == "revoked"


@pytest.mark.asyncio
async def test_manage_access_policies_deny_and_redaction(admin_env: AdminTestEnv) -> None:
    """Grant DENY restriction and verify it appears in restricted summary."""
    await _setup_issue_with_object(admin_env, "KAN-143")

    # Provision user maya
    await create_user(
        admin_env.seed_session,
        admin_env.workspace_id,
        handle="@maya_restricted",
        display_name="Maya Restricted",
    )
    await admin_env.seed_session.commit()

    # Grant DENY [VIEW] to maya
    res_deny = await _call_manage_access_policies(
        admin_env,
        {
            "action": "grant",
            "object": "KAN-143",
            "principal": "@maya_restricted",
            "effect": "DENY",
            "capabilities": ["VIEW"],
        },
        scopes="admin:read,admin:write",
    )
    assert res_deny["result"]["isError"] is False

    # Inspect manifest
    res_inspect = await _call_manage_access_policies(
        admin_env,
        {
            "action": "inspect",
            "object": "KAN-143",
        },
        scopes="admin:read",
    )
    assert res_inspect["result"]["isError"] is False
    content = yaml.safe_load(res_inspect["result"]["content"][0]["text"])
    restricted = content.get("restricted", [])
    assert any(r["who"] == "Maya Restricted" and r["effect"] == "DENY" for r in restricted)


@pytest.mark.asyncio
async def test_manage_access_policies_scope_and_validation(admin_env: AdminTestEnv) -> None:
    """Scope enforcement and validation errors."""
    await _setup_issue_with_object(admin_env, "KAN-144")

    # 1. Grant with admin:read only -> INSUFFICIENT_SCOPE
    res_scope = await _call_manage_access_policies(
        admin_env,
        {
            "action": "grant",
            "object": "KAN-144",
            "principal": f"@{admin_env.server_admin.handle}",
            "effect": "ALLOW",
            "capabilities": ["VIEW"],
        },
        scopes="admin:read",
    )
    assert res_scope["result"]["isError"] is True
    err = yaml.safe_load(res_scope["result"]["content"][0]["text"])["error"]
    assert err["code"] == "INSUFFICIENT_SCOPE"

    # 2. Missing object argument
    res_no_obj = await _call_manage_access_policies(
        admin_env,
        {"action": "inspect"},
        scopes="admin:read",
    )
    assert res_no_obj["result"]["isError"] is True
    assert (
        yaml.safe_load(res_no_obj["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 3. JIT help
    res_help = await _call_manage_access_policies(
        admin_env,
        {"action": "help", "object": "KAN-144"},
        scopes="admin:read",
    )
    assert res_help["result"]["isError"] is False
    help_doc = yaml.safe_load(res_help["result"]["content"][0]["text"])
    assert help_doc["tool"] == "manage_access_policies"
    assert "params" in help_doc

    # 4. Missing action
    res_no_act = await _call_manage_access_policies(admin_env, {"object": "KAN-144"})
    assert res_no_act["result"]["isError"] is True
    assert (
        yaml.safe_load(res_no_act["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 5. Unknown action
    res_un_act = await _call_manage_access_policies(
        admin_env, {"action": "super_grant", "object": "KAN-144"}
    )
    assert res_un_act["result"]["isError"] is True
    assert (
        yaml.safe_load(res_un_act["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 6. Grant missing principal
    res_no_p = await _call_manage_access_policies(
        admin_env,
        {"action": "grant", "object": "KAN-144", "capabilities": ["VIEW"]},
        scopes="admin:read,admin:write",
    )
    assert res_no_p["result"]["isError"] is True
    assert (
        yaml.safe_load(res_no_p["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 7. Grant missing capabilities
    res_no_caps = await _call_manage_access_policies(
        admin_env,
        {"action": "grant", "object": "KAN-144", "principal": "@maya"},
        scopes="admin:read,admin:write",
    )
    assert res_no_caps["result"]["isError"] is True
    assert (
        yaml.safe_load(res_no_caps["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 8. Revoke missing principal
    res_rev_no_p = await _call_manage_access_policies(
        admin_env,
        {"action": "revoke", "object": "KAN-144"},
        scopes="admin:read,admin:write",
    )
    assert res_rev_no_p["result"]["isError"] is True
    assert (
        yaml.safe_load(res_rev_no_p["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )


@pytest.mark.asyncio
async def test_access_policies_formatting_helpers() -> None:
    """Direct unit testing of _format_caps_summary and _format_inspect_summary."""
    assert _format_caps_summary(["ADMIN", "VIEW"]) == "ADMIN"
    assert _format_caps_summary(["EDIT", "VIEW"]) == "EDIT"
    assert _format_caps_summary(["COMMENT", "VIEW"]) == "COMMENT"
    assert _format_caps_summary(["VIEW"]) == "VIEW"
    assert _format_caps_summary([]) == "NONE"
    assert _format_caps_summary(["LINK", "SHARE"]) == "LINK, SHARE"

    # Format inspect summary with all 6 groupings including external collaborators
    manifest_payload = {
        "inherited_scope": {"scope_label": "Project: KAN"},
        "users": [{"handle": "@alice", "capabilities": ["ADMIN"]}],
        "groups": [{"name": "Core Devs", "member_count": 5, "capabilities": ["EDIT"]}],
        "agents": [{"display_name": "Review Bot", "capabilities": ["COMMENT"]}],
        "deny_overrides": [{"display_name": "Restricted User"}],
        "redacted_entries": [
            {"label": "1 External Collaborator - outside your visibility boundary"}
        ],
    }
    summary = _format_inspect_summary("KAN-100", manifest_payload)
    assert summary["object"] == "KAN-100"
    assert summary["inherited_scope"] == "Project: KAN"
    assert len(summary["users"]) == 1
    assert len(summary["groups"]) == 1
    assert len(summary["agents"]) == 1
    assert len(summary["restricted"]) == 1
    assert summary["external"] == "1 External Collaborator - outside your visibility boundary"


@pytest.mark.asyncio
async def test_manage_access_policies_tool_context_and_spec() -> None:
    """Test tool construction and context absence behavior."""
    spec = create_manage_access_policies_tool()
    assert spec.name == "manage_access_policies"

    token = set_current_mcp_context(None)
    try:
        # Calling _assert_scope with no context returns None
        _assert_scope("admin:write")

        # Calling tool handler with no context raises Internal error
        with pytest.raises(KbMcpError) as exc_info:
            await manage_access_policies_tool({"action": "inspect", "object": "KAN-1"})
        assert exc_info.value.code.value == "INTERNAL"
    finally:
        reset_current_mcp_context(token)

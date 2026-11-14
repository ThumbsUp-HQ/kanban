# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: configure_workspace (KB-P4-09a)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest
import yaml
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.services.activity import ActivityEventType
from kanban.tests.security.helpers import (
    add_role_binding,
    create_user,
    create_workspace,
    rebuild_era,
)
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.surfaces.admin.configure_workspace import (
    configure_workspace,
    create_configure_workspace_tool,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_configure_workspace(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke configure_workspace via JSON-RPC 2.0 tools/call on /mcp/admin."""
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
            "name": "configure_workspace",
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
async def test_configure_workspace_get_defaults(admin_env: AdminTestEnv) -> None:
    """Action 'get' returns defaults conforming to S11.4 summary projection."""
    data = await _call_configure_workspace(
        admin_env,
        {"action": "get"},
        scopes="admin:read",
    )
    result = data["result"]
    assert not result.get("isError")

    text_out = result["content"][0]["text"]
    parsed = yaml.safe_load(text_out)

    assert parsed["workspace"] == "Engineering"
    assert parsed["air_gap_mode"] is False
    assert parsed["trash_retention_days"] == 30
    assert parsed["session"]["idle_min"] == 60
    assert parsed["session"]["absolute_min"] == 720
    assert parsed["mcp_key_max_ttl_days"] == 90


@pytest.mark.asyncio
async def test_configure_workspace_update_persists_and_emits_activity(
    admin_env: AdminTestEnv,
) -> None:
    """Action 'update' modifies settings and records WORKSPACE_SETTINGS_CHANGED."""
    data = await _call_configure_workspace(
        admin_env,
        {
            "action": "update",
            "settings": {
                "trash_retention_days": 45,
                "session_idle_timeout_min": 120,
            },
        },
        scopes="admin:write",
    )
    result = data["result"]
    assert not result.get("isError")

    text_out = result["content"][0]["text"]
    parsed = yaml.safe_load(text_out)
    assert parsed["trash_retention_days"] == 45
    assert parsed["session"]["idle_min"] == 120

    # Verify WORKSPACE_SETTINGS_CHANGED activity recorded in database
    res = await admin_env.seed_session.execute(
        text(
            "SELECT event_type, payload FROM activity_records "
            "WHERE workspace_id = :ws_id AND event_type = :etype "
            "ORDER BY recorded_at DESC LIMIT 1"
        ),
        {
            "ws_id": admin_env.workspace_id,
            "etype": ActivityEventType.WORKSPACE_SETTINGS_CHANGED.value,
        },
    )
    row = res.mappings().first()
    assert row is not None
    payload = row["payload"]
    assert payload["diff"]["trash_retention_days"] == 45
    assert payload["before"]["trash_retention_days"] == 30
    assert payload["after"]["trash_retention_days"] == 45


@pytest.mark.asyncio
async def test_configure_workspace_validation_boundaries(  # noqa: PLR0915
    admin_env: AdminTestEnv,
) -> None:
    """Invalid actions, boundary violations, and unknown setting keys return VALIDATION_FAILED."""
    # 1. Unknown action
    d1 = await _call_configure_workspace(
        admin_env,
        {"action": "destroy_all"},
        scopes="admin:write",
    )
    assert d1["result"]["isError"] is True
    err1 = yaml.safe_load(d1["result"]["content"][0]["text"])["error"]
    assert err1["code"] == "VALIDATION_FAILED"

    # 2. Unknown setting key
    d2 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"unsupported_key": 123}},
        scopes="admin:write",
    )
    assert d2["result"]["isError"] is True
    err2 = yaml.safe_load(d2["result"]["content"][0]["text"])["error"]
    assert err2["code"] == "VALIDATION_FAILED"

    # 3. trash_retention_days = 0 (min 1)
    d3 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"trash_retention_days": 0}},
        scopes="admin:write",
    )
    assert d3["result"]["isError"] is True
    err3 = yaml.safe_load(d3["result"]["content"][0]["text"])["error"]
    assert err3["code"] == "VALIDATION_FAILED"

    # 4. trash_retention_days = 366 (max 365)
    d4 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"trash_retention_days": 366}},
        scopes="admin:write",
    )
    assert d4["result"]["isError"] is True
    err4 = yaml.safe_load(d4["result"]["content"][0]["text"])["error"]
    assert err4["code"] == "VALIDATION_FAILED"

    # 5. session_idle_timeout_min = 721 (max 720)
    d5 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"session_idle_timeout_min": 721}},
        scopes="admin:write",
    )
    assert d5["result"]["isError"] is True
    err5 = yaml.safe_load(d5["result"]["content"][0]["text"])["error"]
    assert err5["code"] == "VALIDATION_FAILED"

    # 6. absolute < idle
    d6 = await _call_configure_workspace(
        admin_env,
        {
            "action": "update",
            "settings": {
                "session_idle_timeout_min": 120,
                "session_absolute_timeout_min": 60,
            },
        },
        scopes="admin:write",
    )
    assert d6["result"]["isError"] is True
    err6 = yaml.safe_load(d6["result"]["content"][0]["text"])["error"]
    assert err6["code"] == "VALIDATION_FAILED"

    # 6b. session_absolute_timeout_min out of bounds (< 60 or > 10080)
    d6b = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"session_absolute_timeout_min": 59}},
        scopes="admin:write",
    )
    assert d6b["result"]["isError"] is True
    assert (
        yaml.safe_load(d6b["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 6c. air_gap_mode not boolean
    d6c = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"air_gap_mode": "not-bool"}},
        scopes="admin:write",
    )
    assert d6c["result"]["isError"] is True
    assert (
        yaml.safe_load(d6c["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 6d. Unknown top-level argument
    d6d = await _call_configure_workspace(
        admin_env,
        {"action": "get", "unknown_top_arg": True},
        scopes="admin:read",
    )
    assert d6d["result"]["isError"] is True
    assert (
        yaml.safe_load(d6d["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 7. display_name empty or > 80 chars
    d7 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"display_name": ""}},
        scopes="admin:write",
    )
    assert d7["result"]["isError"] is True
    assert (
        yaml.safe_load(d7["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 8. default_project_visibility invalid
    d8 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"default_project_visibility": "global"}},
        scopes="admin:write",
    )
    assert d8["result"]["isError"] is True
    assert (
        yaml.safe_load(d8["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 9. mcp_key_max_ttl_days out of bounds
    d9 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"mcp_key_max_ttl_days": 0}},
        scopes="admin:write",
    )
    assert d9["result"]["isError"] is True
    assert (
        yaml.safe_load(d9["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 10. settings empty dict
    d10 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {}},
        scopes="admin:write",
    )
    assert d10["result"]["isError"] is True
    assert (
        yaml.safe_load(d10["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 11. ip_allowlist invalid CIDR / string
    d11 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"ip_allowlist": ["not-a-cidr"]}},
        scopes="admin:write",
    )
    assert d11["result"]["isError"] is True
    assert (
        yaml.safe_load(d11["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 12. email_domain_allowlist invalid
    d12 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"email_domain_allowlist": ["@invalid!domain"]}},
        scopes="admin:write",
    )
    assert d12["result"]["isError"] is True
    assert (
        yaml.safe_load(d12["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )

    # 13. cors_allowed_origins invalid (not http/https)
    d13 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"cors_allowed_origins": ["ftp://example.com"]}},
        scopes="admin:write",
    )
    assert d13["result"]["isError"] is True
    assert (
        yaml.safe_load(d13["result"]["content"][0]["text"])["error"]["code"] == "VALIDATION_FAILED"
    )


@pytest.mark.asyncio
async def test_configure_workspace_air_gap_toggle_and_aal2(admin_env: AdminTestEnv) -> None:
    """Toggling air_gap_mode requires AAL2 and emits AIR_GAP_MODE_CHANGED activity."""
    # 1. AAL1 token caller attempting to toggle air_gap_mode -> AAL2_REQUIRED
    d_aal1 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"air_gap_mode": True}},
        scopes="admin:write",
        aal_level=1,
    )
    assert d_aal1["result"]["isError"] is True
    err = yaml.safe_load(d_aal1["result"]["content"][0]["text"])["error"]
    assert err["code"] == "AAL2_REQUIRED"

    # 2. AAL2 caller succeeds
    d_aal2 = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"air_gap_mode": True}},
        scopes="admin:write",
        aal_level=2,
    )
    assert not d_aal2["result"].get("isError")
    parsed = yaml.safe_load(d_aal2["result"]["content"][0]["text"])
    assert parsed["air_gap_mode"] is True

    # Verify AIR_GAP_MODE_CHANGED activity record in database
    res = await admin_env.seed_session.execute(
        text(
            "SELECT event_type FROM activity_records "
            "WHERE workspace_id = :ws_id AND event_type = :etype"
        ),
        {
            "ws_id": admin_env.workspace_id,
            "etype": ActivityEventType.AIR_GAP_MODE_CHANGED.value,
        },
    )
    assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_configure_workspace_scope_enforcement(admin_env: AdminTestEnv) -> None:
    """Tool checks caller scopes (admin:read for get, admin:write for update)."""
    # 1. action='get' without admin:read -> INSUFFICIENT_SCOPE
    d_no_read = await _call_configure_workspace(
        admin_env,
        {"action": "get"},
        scopes="",
    )
    assert d_no_read["result"]["isError"] is True
    err1 = yaml.safe_load(d_no_read["result"]["content"][0]["text"])["error"]
    assert err1["code"] == "INSUFFICIENT_SCOPE"

    # 2. action='update' with only admin:read -> INSUFFICIENT_SCOPE
    d_no_write = await _call_configure_workspace(
        admin_env,
        {"action": "update", "settings": {"trash_retention_days": 40}},
        scopes="admin:read",
    )
    assert d_no_write["result"]["isError"] is True
    err2 = yaml.safe_load(d_no_write["result"]["content"][0]["text"])["error"]
    assert err2["code"] == "INSUFFICIENT_SCOPE"


@pytest.mark.asyncio
async def test_configure_workspace_help_and_full_lod(admin_env: AdminTestEnv) -> None:
    """Action 'help' and LOD 'full' return expected structured YAML schemas."""
    # 1. action='help'
    d_help = await _call_configure_workspace(
        admin_env,
        {"action": "help"},
    )
    assert not d_help["result"].get("isError")
    help_yaml = yaml.safe_load(d_help["result"]["content"][0]["text"])
    assert help_yaml["tool"] == "configure_workspace"

    # 2. lod='full' on get
    d_full = await _call_configure_workspace(
        admin_env,
        {"action": "get", "lod": "full"},
        scopes="admin:read",
    )
    assert not d_full["result"].get("isError")
    full_yaml = yaml.safe_load(d_full["result"]["content"][0]["text"])
    assert "workspace_id" in full_yaml
    assert "default_project_visibility" in full_yaml


@pytest.mark.asyncio
async def test_configure_workspace_rls_isolation(admin_env: AdminTestEnv) -> None:
    """Workspace B admin sees only Workspace B settings."""
    ws_b_id = await create_workspace(admin_env.seed_session, name="Workspace Beta")
    admin_b_id = await create_user(
        admin_env.seed_session, ws_b_id, handle="@admin_b", display_name="Admin Beta"
    )
    await add_role_binding(
        admin_env.seed_session,
        ws_b_id,
        admin_b_id,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    # Enroll and confirm TOTP for admin_b
    await admin_env.seed_session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": admin_b_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await admin_env.seed_session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": admin_b_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await admin_env.seed_session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )

    await rebuild_era(admin_env.seed_session, ws_b_id)
    await admin_env.seed_session.commit()

    token_b = "kb_adm_wsb_" + "8" * 32
    admin_env.fastapi_app.state.principal_resolver.token_map[token_b] = PrincipalContext(
        principal_id=admin_b_id,
        workspace_id=ws_b_id,
        token_scopes=("admin:read", "admin:write"),
        aal_level=2,
    )

    data_b = await _call_configure_workspace(
        admin_env,
        {"action": "get"},
        subject_token=token_b,
        scopes="admin:read",
    )
    assert not data_b["result"].get("isError")
    parsed_b = yaml.safe_load(data_b["result"]["content"][0]["text"])
    assert parsed_b["workspace"] == "Workspace Beta"


@pytest.mark.asyncio
async def test_configure_workspace_tool_spec_and_direct_invocation() -> None:
    """Directly test ToolSpec metadata, help branch, and context errors."""
    tool = create_configure_workspace_tool()
    assert tool.name == "configure_workspace"
    assert tool.surface == Surface.ADMIN

    # Direct call for action="help"
    help_out = await configure_workspace({"action": "help"})
    help_yaml = yaml.safe_load(help_out)
    assert help_yaml["tool"] == "configure_workspace"

    # Direct call without MCP context raises UPSTREAM_UNAVAILABLE
    with pytest.raises(KbMcpError) as exc_info:
        await configure_workspace({"action": "get"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # Direct call with mock returning non-dict
    mock_client = AsyncMock()
    mock_client.request.return_value = "not-a-dict"
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:read"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        with pytest.raises(KbMcpError) as exc_info2:
            await configure_workspace({"action": "get"})
        assert exc_info2.value.code == McpErrorCode.UPSTREAM_ERROR
    finally:
        reset_current_mcp_context(tok)

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: manage_custom_fields_and_scripts.

KB-P5-13, S11.4 Tool 7, S13.3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import yaml

from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.surfaces.admin.manage_custom_fields_and_scripts import (
    create_manage_custom_fields_and_scripts_tool,
    manage_custom_fields_and_scripts,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


def test_tool_creation_and_registration() -> None:
    """Tool factory returns valid ToolSpec on Surface.ADMIN."""
    tool = create_manage_custom_fields_and_scripts_tool()
    assert tool.name == "manage_custom_fields_and_scripts"
    assert tool.surface == Surface.ADMIN
    assert tool.handler is manage_custom_fields_and_scripts
    assert "action" in tool.input_schema["properties"]


@pytest.mark.asyncio
async def test_help_action() -> None:
    """Action 'help' works without MCP context and returns YAML help."""
    help_out = await manage_custom_fields_and_scripts({"action": "help"})
    data = yaml.safe_load(help_out)
    assert data["tool"] == "manage_custom_fields_and_scripts"
    assert "params" in data


@pytest.mark.asyncio
async def test_parameter_validation_and_unknown_action() -> None:
    """Reject unknown parameters, missing action, and unknown actions."""
    with pytest.raises(KbMcpError) as exc_info:
        await manage_custom_fields_and_scripts({"action": "help", "invalid_param": 123})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info2:
        await manage_custom_fields_and_scripts({})
    assert exc_info2.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info3:
        await manage_custom_fields_and_scripts({"action": "invalid_action"})
    # Raised at UPSTREAM_UNAVAILABLE because context checked first or validation
    assert exc_info3.value.code in (
        McpErrorCode.VALIDATION_FAILED,
        McpErrorCode.UPSTREAM_UNAVAILABLE,
    )


@pytest.mark.asyncio
async def test_context_and_surface_checks() -> None:
    """Enforce upstream context, Surface.ADMIN, and kb_adm_* key requirement."""
    # 1. No context
    with pytest.raises(KbMcpError) as exc_info:
        await manage_custom_fields_and_scripts({"action": "list_fields", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 2. Surface mismatch (e.g. Surface.AGENT)
    mock_client = AsyncMock()
    ctx_agent = McpRequestContext(
        client=mock_client,
        surface=Surface.AGENT,
        caller_scopes=frozenset({"admin:read"}),
    )
    tok = set_current_mcp_context(ctx_agent)
    try:
        with pytest.raises(KbMcpError) as exc_surface:
            await manage_custom_fields_and_scripts({"action": "list_fields", "project": "KAN"})
        assert exc_surface.value.code == McpErrorCode.SURFACE_KEY_MISMATCH
    finally:
        reset_current_mcp_context(tok)

    # 3. Agent token rejection (kb_agt_*)
    ctx_bad_token = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        subject_token="kb_agt_some_agent_key",  # noqa: S106
        caller_scopes=frozenset({"admin:read"}),
    )
    tok2 = set_current_mcp_context(ctx_bad_token)
    try:
        with pytest.raises(KbMcpError) as exc_token:
            await manage_custom_fields_and_scripts({"action": "list_fields", "project": "KAN"})
        assert exc_token.value.code == McpErrorCode.SURFACE_KEY_MISMATCH
    finally:
        reset_current_mcp_context(tok2)


@pytest.mark.asyncio
async def test_scope_checks() -> None:
    """Verify admin:read, admin:write, and admin:destructive enforcement."""
    mock_client = AsyncMock()

    # Scope empty
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset(),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # list_fields requires admin:read
        with pytest.raises(KbMcpError) as exc_read:
            await manage_custom_fields_and_scripts({"action": "list_fields", "project": "KAN"})
        assert exc_read.value.code == McpErrorCode.INSUFFICIENT_SCOPE

        # upsert_field requires admin:write
        with pytest.raises(KbMcpError) as exc_write:
            await manage_custom_fields_and_scripts(
                {"action": "upsert_field", "project": "KAN", "name": "F"}
            )
        assert exc_write.value.code == McpErrorCode.INSUFFICIENT_SCOPE

        # delete_field requires admin:destructive
        with pytest.raises(KbMcpError) as exc_dest:
            await manage_custom_fields_and_scripts(
                {"action": "delete_field", "project": "KAN", "field": "F"}
            )
        assert exc_dest.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_list_fields_all_lods() -> None:
    """Test action 'list_fields' across summary, standard, and full LODs."""
    mock_client = AsyncMock()
    mock_fields = [
        {
            "id": "01a1d000-0000-0000-0000-000000000001",
            "slug": "field-1",
            "name": "Field 1",
            "tier": "wasm",
            "output_format": "text",
            "target_scope": "PROJECT",
            "credential_mode": "INVOKING_USER",
            "is_enabled": True,
            "manifest_sha256": "abcdef1234567890",
            "approval_status": "APPROVED",
            "extra_private_field": "hidden_in_summary",
        }
    ]
    mock_client.request.return_value = mock_fields

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:read"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # 1. Missing project raises VALIDATION_FAILED
        with pytest.raises(KbMcpError) as exc_noproj:
            await manage_custom_fields_and_scripts({"action": "list_fields"})
        assert exc_noproj.value.code == McpErrorCode.VALIDATION_FAILED

        # 2. lod=summary
        out_summary = await manage_custom_fields_and_scripts(
            {"action": "list_fields", "project": "KAN", "lod": "summary"}
        )
        parsed_summary = yaml.safe_load(out_summary)
        assert parsed_summary["count"] == 1
        item_sum = parsed_summary["fields"][0]
        assert item_sum["slug"] == "field-1"
        assert "manifest_sha256" not in item_sum
        assert "extra_private_field" not in item_sum

        # 3. lod=standard
        out_standard = await manage_custom_fields_and_scripts(
            {"action": "list_fields", "project": "KAN", "lod": "standard"}
        )
        parsed_standard = yaml.safe_load(out_standard)
        item_std = parsed_standard["fields"][0]
        assert item_std["manifest_sha256"] == "abcdef1234567890"
        assert item_std["approval_status"] == "APPROVED"
        assert "extra_private_field" not in item_std

        # 4. lod=full
        out_full = await manage_custom_fields_and_scripts(
            {"action": "list_fields", "project": "KAN", "lod": "full"}
        )
        parsed_full = yaml.safe_load(out_full)
        assert parsed_full["fields"][0]["extra_private_field"] == "hidden_in_summary"

        # 5. Non-list response raises UPSTREAM_ERROR
        mock_client.request.return_value = {"error": "bad"}
        with pytest.raises(KbMcpError) as exc_up:
            await manage_custom_fields_and_scripts({"action": "list_fields", "project": "KAN"})
        assert exc_up.value.code == McpErrorCode.UPSTREAM_ERROR
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_upsert_and_delete_actions() -> None:
    """Test create, update, confirmation preview, and confirmed delete."""
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write", "admin:destructive"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # 1. Upsert without project
        with pytest.raises(KbMcpError) as exc_noproj:
            await manage_custom_fields_and_scripts({"action": "upsert_field", "name": "Test"})
        assert exc_noproj.value.code == McpErrorCode.VALIDATION_FAILED

        # 2. Create new field (POST)
        mock_client.request.return_value = {"id": "f1", "slug": "test-f"}
        out_create = await manage_custom_fields_and_scripts(
            {
                "action": "upsert_field",
                "project": "KAN",
                "name": "Test Field",
                "slug": "test-f",
                "tier": "wasm",
                "output_format": "text",
            }
        )
        parsed_create = yaml.safe_load(out_create)
        assert parsed_create["status"] == "created"
        assert parsed_create["field"]["slug"] == "test-f"
        mock_client.request.assert_called_with(
            "POST",
            "/api/v1/projects/KAN/custom-fields",
            json_data={
                "name": "Test Field",
                "slug": "test-f",
                "tier": "wasm",
                "output_format": "text",
            },
            subject_token=None,
            mcp_session_id=None,
        )

        # 3. Update existing field (PATCH)
        mock_client.request.return_value = {"id": "f1", "name": "Updated Name"}
        out_patch = await manage_custom_fields_and_scripts(
            {"action": "upsert_field", "project": "KAN", "field": "f1", "name": "Updated Name"}
        )
        parsed_patch = yaml.safe_load(out_patch)
        assert parsed_patch["status"] == "updated"
        mock_client.request.assert_called_with(
            "PATCH",
            "/api/v1/projects/KAN/custom-fields/f1",
            json_data={"name": "Updated Name"},
            subject_token=None,
            mcp_session_id=None,
        )

        # 4. Delete without project or field
        with pytest.raises(KbMcpError) as exc_del_noproj:
            await manage_custom_fields_and_scripts({"action": "delete_field"})
        assert exc_del_noproj.value.code == McpErrorCode.VALIDATION_FAILED

        # 5. Delete without confirm: true (two-stage preview)
        out_preview = await manage_custom_fields_and_scripts(
            {"action": "delete_field", "project": "KAN", "field": "f1"}
        )
        parsed_preview = yaml.safe_load(out_preview)
        assert parsed_preview["status"] == "confirmation_required"
        assert "confirm=true" in parsed_preview["message"]

        # 6. Delete with confirm: true
        mock_client.request.return_value = None
        out_deleted = await manage_custom_fields_and_scripts(
            {"action": "delete_field", "project": "KAN", "field": "f1", "confirm": True}
        )
        parsed_deleted = yaml.safe_load(out_deleted)
        assert parsed_deleted["status"] == "deleted"
        mock_client.request.assert_called_with(
            "DELETE",
            "/api/v1/projects/KAN/custom-fields/f1",
            subject_token=None,
            mcp_session_id=None,
        )
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_upload_wasm_module_action() -> None:
    """Test action 'upload_wasm_module'."""
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing project
        with pytest.raises(KbMcpError) as exc1:
            await manage_custom_fields_and_scripts(
                {"action": "upload_wasm_module", "wasm_base64": "abc"}
            )
        assert exc1.value.code == McpErrorCode.VALIDATION_FAILED

        # Missing wasm_base64
        with pytest.raises(KbMcpError) as exc2:
            await manage_custom_fields_and_scripts(
                {"action": "upload_wasm_module", "project": "KAN"}
            )
        assert exc2.value.code == McpErrorCode.VALIDATION_FAILED

        # Success
        mock_client.request.return_value = {
            "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "name": "echo_cvss",
            "size_bytes": 213,
        }
        out = await manage_custom_fields_and_scripts(
            {
                "action": "upload_wasm_module",
                "project": "KAN",
                "name": "echo_cvss",
                "wasm_base64": "AGFzbQE...",
            }
        )
        parsed = yaml.safe_load(out)
        assert parsed["status"] == "uploaded"
        assert parsed["module"]["name"] == "echo_cvss"
        mock_client.request.assert_called_with(
            "POST",
            "/api/v1/projects/KAN/wasm-modules",
            json_data={"name": "echo_cvss", "wasm_base64": "AGFzbQE..."},
            subject_token=None,
            mcp_session_id=None,
        )
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_escalation_request_and_approve_actions() -> None:
    """Test actions 'request_escalation' and 'approve_escalation'."""
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # 1. request_escalation validation
        with pytest.raises(KbMcpError) as exc1:
            await manage_custom_fields_and_scripts(
                {"action": "request_escalation", "project": "KAN"}
            )
        assert exc1.value.code == McpErrorCode.VALIDATION_FAILED

        with pytest.raises(KbMcpError) as exc2:
            await manage_custom_fields_and_scripts(
                {"action": "request_escalation", "project": "KAN", "field": "f1"}
            )
        assert exc2.value.code == McpErrorCode.VALIDATION_FAILED

        # Success request_escalation
        mock_client.request.return_value = {"id": "appr-1", "status": "PENDING"}
        out_req = await manage_custom_fields_and_scripts(
            {
                "action": "request_escalation",
                "project": "KAN",
                "field": "f1",
                "manifest_sha256": "man123",
                "justification": "Need server admin privileges",
            }
        )
        assert yaml.safe_load(out_req)["status"] == "escalation_requested"

        # 2. approve_escalation validation
        with pytest.raises(KbMcpError) as exc_appr_noproj:
            await manage_custom_fields_and_scripts({"action": "approve_escalation"})
        assert exc_appr_noproj.value.code == McpErrorCode.VALIDATION_FAILED

        with pytest.raises(KbMcpError) as exc3:
            await manage_custom_fields_and_scripts(
                {"action": "approve_escalation", "project": "KAN", "field": "f1"}
            )
        assert exc3.value.code == McpErrorCode.VALIDATION_FAILED

        # Success approve_escalation
        mock_client.request.return_value = {"id": "appr-1", "status": "APPROVED"}
        out_appr = await manage_custom_fields_and_scripts(
            {
                "action": "approve_escalation",
                "project": "KAN",
                "field": "f1",
                "manifest_sha256": "man123",
                "sp_warning_acknowledged": True,
            }
        )
        assert yaml.safe_load(out_appr)["status"] == "approved"
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_execute_field_action() -> None:
    """Test action 'execute_field' with cached read and force_refresh=True."""
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Validation
        with pytest.raises(KbMcpError) as exc1:
            await manage_custom_fields_and_scripts({"action": "execute_field", "issue": "KAN-142"})
        assert exc1.value.code == McpErrorCode.VALIDATION_FAILED

        # Cached read (GET /api/v1/issues/{issue}/custom-fields)
        mock_client.request.return_value = [
            {"field_id": "f1", "slug": "cvss-pill", "value": 9.8, "status": "computed"}
        ]
        out_cached = await manage_custom_fields_and_scripts(
            {"action": "execute_field", "field": "f1", "issue": "KAN-142"}
        )
        parsed_cached = yaml.safe_load(out_cached)
        assert parsed_cached["result"]["value"] == 9.8
        mock_client.request.assert_called_with(
            "GET",
            "/api/v1/issues/KAN-142/custom-fields",
            subject_token=None,
            mcp_session_id=None,
        )

        # Force refresh (POST /api/v1/issues/{issue}/custom-fields/{field}/execute)
        mock_client.request.return_value = {
            "field_id": "f1",
            "slug": "cvss-pill",
            "value": 9.8,
            "status": "computed",
        }
        out_fresh = await manage_custom_fields_and_scripts(
            {"action": "execute_field", "field": "f1", "issue": "KAN-142", "force_refresh": True}
        )
        parsed_fresh = yaml.safe_load(out_fresh)
        assert parsed_fresh["result"]["value"] == 9.8
        mock_client.request.assert_called_with(
            "POST",
            "/api/v1/issues/KAN-142/custom-fields/f1/execute",
            subject_token=None,
            mcp_session_id=None,
        )

        # Execute field not found in list returns full list
        mock_client.request.return_value = [{"field_id": "other_f"}]
        out_notfound = await manage_custom_fields_and_scripts(
            {"action": "execute_field", "field": "f1", "issue": "KAN-142"}
        )
        assert "other_f" in out_notfound

        # Unhandled action when context is valid
        with pytest.raises(KbMcpError) as exc_unhandled:
            await manage_custom_fields_and_scripts({"action": "unknown_action"})
        assert exc_unhandled.value.code == McpErrorCode.VALIDATION_FAILED

        # Null caller_scopes bypasses scope check
        ctx_no_scopes = McpRequestContext(
            client=mock_client,
            surface=Surface.ADMIN,
            caller_scopes=None,
        )
        tok_ns = set_current_mcp_context(ctx_no_scopes)
        try:
            mock_client.request.return_value = [{"id": "1", "slug": "s"}]
            out_ns = await manage_custom_fields_and_scripts(
                {"action": "list_fields", "project": "KAN"}
            )
            assert "fields" in out_ns
        finally:
            reset_current_mcp_context(tok_ns)
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_call_via_jsonrpc_admin_surface(admin_env: AdminTestEnv) -> None:
    """Full roundtrip invocation of Tool 7 over JSON-RPC 2.0 on /mcp/admin."""
    # Initialize session
    init_resp = await admin_env.mcp_client.post(
        "/mcp/admin",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-admin", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": admin_env.token_server_admin_full},
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers["mcp-session-id"]

    # Call tools/list to verify tool 7 is advertised
    list_resp = await admin_env.mcp_client.post(
        "/mcp/admin",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={
            "mcp-session-id": session_id,
            "X-KB-Subject-Token": admin_env.token_server_admin_full,
        },
    )
    assert list_resp.status_code == 200
    tools = list_resp.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "manage_custom_fields_and_scripts" in tool_names

    # Call manage_custom_fields_and_scripts with action="help"
    call_resp = await admin_env.mcp_client.post(
        "/mcp/admin",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "manage_custom_fields_and_scripts",
                "arguments": {"action": "help"},
            },
        },
        headers={
            "mcp-session-id": session_id,
            "X-KB-Subject-Token": admin_env.token_server_admin_full,
        },
    )
    assert call_resp.status_code == 200
    result = call_resp.json()["result"]
    assert not result.get("isError")
    content = result["content"][0]["text"]
    parsed = yaml.safe_load(content)
    assert parsed["tool"] == "manage_custom_fields_and_scripts"

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, D401, ERA001
"""Feature unit tests for /mcp/admin tool 8: manage_workflow_interceptors.

KB-P5-17b, S11.4 Tool 8.
"""

from __future__ import annotations

import uuid
from typing import Any
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
from mcp.surfaces.admin.manage_workflow_interceptors import (
    create_manage_workflow_interceptors_tool,
    manage_workflow_interceptors,
)


def _resolved(
    entity_id: str, kind: str = "project", key: str = "KAN", title: str = "Kanban"
) -> dict[str, Any]:
    """Helper to mock /api/v1/resolve responses for EntityResolver."""
    return {"id": entity_id, "kind": kind, "key": key, "title": title}


def test_tool_creation_and_registration() -> None:
    """Tool factory returns valid ToolSpec on Surface.ADMIN."""
    tool = create_manage_workflow_interceptors_tool()
    assert tool.name == "manage_workflow_interceptors"
    assert tool.surface == Surface.ADMIN
    assert tool.handler is manage_workflow_interceptors
    assert "action" in tool.input_schema["properties"]
    assert "hook_kind" in tool.input_schema["properties"]
    assert "dry_run" in tool.input_schema["properties"]["action"]["enum"]


@pytest.mark.asyncio
async def test_help_action_without_context() -> None:
    """Action 'help' works without MCP context and returns YAML help."""
    help_out = await manage_workflow_interceptors({"action": "help"})
    data = yaml.safe_load(help_out)
    assert data["tool"] == "manage_workflow_interceptors"
    assert "actions" in data
    assert "mutable_field_universe" in data
    assert "immutable_fields_notice" in data
    assert "dry_run_semantics" in data
    assert "params" in data


@pytest.mark.asyncio
async def test_help_action_with_context() -> None:
    """Action 'help' enriches live states and agents when context is available."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    mock_client.request.side_effect = [
        # EntityResolver resolve project
        _resolved(proj_uuid, kind="project", key="KAN"),
        # GET /api/v1/projects/{proj_id}/states
        [{"name": "Backlog"}, {"name": "In Progress"}, {"name": "Done"}],
        # GET /api/v1/agent-definitions
        [{"slug": "reality-checker"}, {"slug": "qa-agent"}],
    ]

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:read"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        help_out = await manage_workflow_interceptors({"action": "help", "project": "KAN"})
        data = yaml.safe_load(help_out)
        assert data["tool"] == "manage_workflow_interceptors"
        assert "Backlog" in data["live_states"]
        assert "reality-checker" in data["registered_agents"]
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_parameter_validation_and_unknown_action() -> None:
    """Reject unknown parameters, missing action, and unknown actions."""
    with pytest.raises(KbMcpError) as exc_info:
        await manage_workflow_interceptors({"action": "help", "invalid_param": 123})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info2:
        await manage_workflow_interceptors({})
    assert exc_info2.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info3:
        await manage_workflow_interceptors({"action": "invalid_action"})
    assert exc_info3.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_context_and_surface_checks() -> None:
    """Enforce upstream context, Surface.ADMIN, and kb_adm_* key requirement."""
    # 1. No context
    with pytest.raises(KbMcpError) as exc_info:
        await manage_workflow_interceptors({"action": "list", "project": "KAN"})
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
            await manage_workflow_interceptors({"action": "list", "project": "KAN"})
        assert exc_surface.value.code == McpErrorCode.SURFACE_KEY_MISMATCH
    finally:
        reset_current_mcp_context(tok)

    # 3. Agent token rejection (kb_agt_*)
    ctx_bad_token = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        subject_token="kb_agt_agent_key_xyz",  # noqa: S106
        caller_scopes=frozenset({"admin:read"}),
    )
    tok2 = set_current_mcp_context(ctx_bad_token)
    try:
        with pytest.raises(KbMcpError) as exc_token:
            await manage_workflow_interceptors({"action": "list", "project": "KAN"})
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
        # list requires admin:read
        with pytest.raises(KbMcpError) as exc_read:
            await manage_workflow_interceptors({"action": "list", "project": "KAN"})
        assert exc_read.value.code == McpErrorCode.INSUFFICIENT_SCOPE

        # attach requires admin:write
        with pytest.raises(KbMcpError) as exc_write:
            await manage_workflow_interceptors(
                {
                    "action": "attach",
                    "project": "KAN",
                    "name": "hook-1",
                    "to_state": "Done",
                    "hook_kind": "sync_validator",
                }
            )
        assert exc_write.value.code == McpErrorCode.INSUFFICIENT_SCOPE

        # detach requires admin:destructive
        with pytest.raises(KbMcpError) as exc_dest:
            await manage_workflow_interceptors(
                {"action": "detach", "project": "KAN", "hook": "hook-1"}
            )
        assert exc_dest.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_list_hooks_all_lods() -> None:
    """Test action 'list' across summary, standard, and full LODs."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    hook_uuid = str(uuid.uuid4())
    to_state_uuid = str(uuid.uuid4())
    mock_hooks_response = [
        {
            "from_state": None,
            "to_state": "Done",
            "active_hook_count": 1,
            "hooks": [
                {
                    "id": hook_uuid,
                    "project_id": proj_uuid,
                    "name": "qa-validator",
                    "from_state_id": None,
                    "to_state_id": to_state_uuid,
                    "hook_kind": "sync_validator",
                    "failure_policy": "fail_closed",
                    "is_enabled": True,
                    "sort_rank": 10,
                    "wasm_module_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
                    "extra_private_field": "hidden_in_summary",
                }
            ],
        }
    ]

    mock_client.request.side_effect = [
        # 1. Summary: resolve project
        _resolved(proj_uuid, kind="project", key="KAN"),
        # GET /api/v1/projects/{proj_id}/workflow-hooks
        mock_hooks_response,
        # 2. Standard: resolve project (cached or new)
        _resolved(proj_uuid, kind="project", key="KAN"),
        mock_hooks_response,
        # 3. Full: resolve project
        _resolved(proj_uuid, kind="project", key="KAN"),
        mock_hooks_response,
    ]

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:read"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing project raises VALIDATION_FAILED
        with pytest.raises(KbMcpError) as exc_noproj:
            await manage_workflow_interceptors({"action": "list"})
        assert exc_noproj.value.code == McpErrorCode.VALIDATION_FAILED

        # lod=summary
        out_summary = await manage_workflow_interceptors(
            {"action": "list", "project": "KAN", "lod": "summary"}
        )
        parsed_summary = yaml.safe_load(out_summary)
        assert len(parsed_summary["transition_rules"]) == 1
        hook_sum = parsed_summary["transition_rules"][0]["hooks"][0]
        assert hook_sum["name"] == "qa-validator"
        assert "wasm_module_sha256" not in hook_sum
        assert "extra_private_field" not in hook_sum

        # lod=standard
        out_standard = await manage_workflow_interceptors(
            {"action": "list", "project": "KAN", "lod": "standard"}
        )
        parsed_standard = yaml.safe_load(out_standard)
        hook_std = parsed_standard["transition_rules"][0]["hooks"][0]
        assert hook_std["name"] == "qa-validator"
        assert "wasm_module_sha256" in hook_std
        assert "extra_private_field" not in hook_std

        # lod=full
        out_full = await manage_workflow_interceptors(
            {"action": "list", "project": "KAN", "lod": "full"}
        )
        parsed_full = yaml.safe_load(out_full)
        assert (
            parsed_full["transition_rules"][0]["hooks"][0]["extra_private_field"]
            == "hidden_in_summary"
        )

        # Non-list response from upstream raises UPSTREAM_ERROR
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            {"error": "corrupted"},
        ]
        with pytest.raises(KbMcpError) as exc_up:
            await manage_workflow_interceptors({"action": "list", "project": "KAN"})
        assert exc_up.value.code == McpErrorCode.UPSTREAM_ERROR
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_attach_action_all_kinds() -> None:
    """Test action 'attach' for sync_validator, sync_mutator, and agent_interceptor."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    to_state_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing required fields
        with pytest.raises(KbMcpError) as exc_miss:
            await manage_workflow_interceptors({"action": "attach", "project": "KAN"})
        assert exc_miss.value.code == McpErrorCode.VALIDATION_FAILED

        # 1. sync_validator missing wasm_module_sha256
        with pytest.raises(KbMcpError) as exc_wasm:
            await manage_workflow_interceptors(
                {
                    "action": "attach",
                    "project": "KAN",
                    "name": "val-1",
                    "to_state": to_state_uuid,
                    "hook_kind": "sync_validator",
                }
            )
        assert exc_wasm.value.code == McpErrorCode.VALIDATION_FAILED

        # 2. sync_validator successful attach
        val_hook_id = str(uuid.uuid4())
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            {
                "id": val_hook_id,
                "project_id": proj_uuid,
                "name": "val-1",
                "to_state_id": to_state_uuid,
                "hook_kind": "sync_validator",
                "wasm_module_sha256": "11" * 32,
            },
        ]
        out_val = await manage_workflow_interceptors(
            {
                "action": "attach",
                "project": "KAN",
                "name": "val-1",
                "to_state": to_state_uuid,
                "hook_kind": "sync_validator",
                "wasm_module_sha256": "11" * 32,
            }
        )
        res_val = yaml.safe_load(out_val)
        assert res_val["status"] == "attached"
        assert res_val["hook"]["name"] == "val-1"

        # 3. sync_mutator missing allowed_mutable_fields
        with pytest.raises(KbMcpError) as exc_mut_none:
            await manage_workflow_interceptors(
                {
                    "action": "attach",
                    "project": "KAN",
                    "name": "mut-1",
                    "to_state": to_state_uuid,
                    "hook_kind": "sync_mutator",
                    "wasm_module_sha256": "22" * 32,
                }
            )
        assert exc_mut_none.value.code == McpErrorCode.VALIDATION_FAILED

        # 4. sync_mutator invalid immutable field (e.g. description)
        with pytest.raises(KbMcpError) as exc_mut_bad:
            await manage_workflow_interceptors(
                {
                    "action": "attach",
                    "project": "KAN",
                    "name": "mut-1",
                    "to_state": to_state_uuid,
                    "hook_kind": "sync_mutator",
                    "wasm_module_sha256": "22" * 32,
                    "allowed_mutable_fields": ["description"],
                }
            )
        assert exc_mut_bad.value.code == McpErrorCode.VALIDATION_FAILED

        # 5. sync_mutator successful attach
        mut_hook_id = str(uuid.uuid4())
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            {
                "id": mut_hook_id,
                "name": "mut-1",
                "hook_kind": "sync_mutator",
                "allowed_mutable_fields": ["labels", "priority"],
            },
        ]
        out_mut = await manage_workflow_interceptors(
            {
                "action": "attach",
                "project": "KAN",
                "name": "mut-1",
                "to_state": to_state_uuid,
                "hook_kind": "sync_mutator",
                "wasm_module_sha256": "22" * 32,
                "allowed_mutable_fields": ["labels", "priority"],
            }
        )
        res_mut = yaml.safe_load(out_mut)
        assert res_mut["status"] == "attached"

        # 6. agent_interceptor missing agent
        with pytest.raises(KbMcpError) as exc_agt_none:
            await manage_workflow_interceptors(
                {
                    "action": "attach",
                    "project": "KAN",
                    "name": "agt-1",
                    "to_state": to_state_uuid,
                    "hook_kind": "agent_interceptor",
                }
            )
        assert exc_agt_none.value.code == McpErrorCode.VALIDATION_FAILED

        # 7. agent_interceptor successful attach
        agt_hook_id = str(uuid.uuid4())
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            {
                "id": agt_hook_id,
                "name": "agt-1",
                "hook_kind": "agent_interceptor",
                "agent": "reality-checker",
            },
        ]
        out_agt = await manage_workflow_interceptors(
            {
                "action": "attach",
                "project": "KAN",
                "name": "agt-1",
                "to_state": to_state_uuid,
                "hook_kind": "agent_interceptor",
                "agent": "reality-checker",
            }
        )
        res_agt = yaml.safe_load(out_agt)
        assert res_agt["status"] == "attached"
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_update_action() -> None:
    """Test action 'update' modifies hook configuration."""
    mock_client = AsyncMock()
    hook_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing hook
        with pytest.raises(KbMcpError) as exc_miss:
            await manage_workflow_interceptors({"action": "update", "name": "hook-new"})
        assert exc_miss.value.code == McpErrorCode.VALIDATION_FAILED

        # Update hook by UUID
        mock_client.request.side_effect = [
            {"id": hook_uuid, "name": "hook-updated", "failure_policy": "fail_open_warn"},
        ]
        out = await manage_workflow_interceptors(
            {
                "action": "update",
                "hook": hook_uuid,
                "name": "hook-updated",
                "failure_policy": "fail_open_warn",
            }
        )
        data = yaml.safe_load(out)
        assert data["status"] == "updated"
        assert data["hook"]["name"] == "hook-updated"
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_reorder_action() -> None:
    """Test action 'reorder' updates hook sort orders."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    to_state_uuid = str(uuid.uuid4())
    hook1 = str(uuid.uuid4())
    hook2 = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing ordered_hook_ids
        with pytest.raises(KbMcpError) as exc_miss:
            await manage_workflow_interceptors(
                {"action": "reorder", "project": "KAN", "to_state": to_state_uuid}
            )
        assert exc_miss.value.code == McpErrorCode.VALIDATION_FAILED

        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            [{"id": hook2, "sort_rank": 10}, {"id": hook1, "sort_rank": 20}],
        ]
        out = await manage_workflow_interceptors(
            {
                "action": "reorder",
                "project": "KAN",
                "to_state": to_state_uuid,
                "ordered_hook_ids": [hook2, hook1],
            }
        )
        data = yaml.safe_load(out)
        assert data["status"] == "reordered"
        assert len(data["hooks"]) == 2
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_enable_and_disable_actions() -> None:
    """Test actions 'enable' and 'disable' toggle hook state."""
    mock_client = AsyncMock()
    hook_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Enable
        mock_client.request.side_effect = [
            {"id": hook_uuid, "name": "hook-1", "is_enabled": True},
        ]
        out_en = await manage_workflow_interceptors({"action": "enable", "hook": hook_uuid})
        data_en = yaml.safe_load(out_en)
        assert data_en["status"] == "enabled"
        assert data_en["hook"]["is_enabled"] is True

        # Disable
        mock_client.request.side_effect = [
            {"id": hook_uuid, "name": "hook-1", "is_enabled": False},
        ]
        out_dis = await manage_workflow_interceptors({"action": "disable", "hook": hook_uuid})
        data_dis = yaml.safe_load(out_dis)
        assert data_dis["status"] == "disabled"
        assert data_dis["hook"]["is_enabled"] is False
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_detach_action_two_stage_confirmation() -> None:
    """Test action 'detach' enforces 2-stage destructive confirmation."""
    mock_client = AsyncMock()
    hook_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:destructive"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # 1. Without confirm: returns confirmation required preview
        out_preview = await manage_workflow_interceptors({"action": "detach", "hook": hook_uuid})
        data_prev = yaml.safe_load(out_preview)
        assert data_prev["requires_confirmation"] is True
        assert data_prev["status"] == "confirmation_required"
        assert "confirm: true" in data_prev["copyable_confirmation"]
        # Ensure client.request was NEVER called
        assert mock_client.request.call_count == 0

        # 2. With confirm: true: performs delete
        mock_client.request.side_effect = [
            None,  # 204 No Content
        ]
        out_detach = await manage_workflow_interceptors(
            {"action": "detach", "hook": hook_uuid, "confirm": True}
        )
        data_det = yaml.safe_load(out_detach)
        assert data_det["status"] == "detached"
        assert data_det["hook"] == hook_uuid
        assert mock_client.request.call_count == 1
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_dry_run_action() -> None:
    """Test action 'dry_run' with sample ticket and existing issue."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    to_state_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # Missing project or to_state
        with pytest.raises(KbMcpError) as exc_miss:
            await manage_workflow_interceptors({"action": "dry_run", "project": "KAN"})
        assert exc_miss.value.code == McpErrorCode.VALIDATION_FAILED

        # Missing both sample_ticket and issue
        with pytest.raises(KbMcpError) as exc_target:
            await manage_workflow_interceptors(
                {"action": "dry_run", "project": "KAN", "to_state": to_state_uuid}
            )
        assert exc_target.value.code == McpErrorCode.VALIDATION_FAILED

        # Dry run with sample ticket
        dry_run_resp = {
            "would_commit": True,
            "simulated_outcome": "approved",
            "pipeline_stages_evaluated": 2,
            "cumulative_sync_latency_us": 1420,
            "applied_mutations": {"labels": ["qa-passed"]},
            "interceptors": [
                {
                    "hook_name": "check-proof",
                    "hook_kind": "sync_validator",
                    "decision": "approved",
                    "latency_us": 850,
                },
                {
                    "hook_name": "auto-label",
                    "hook_kind": "sync_mutator",
                    "decision": "mutated",
                    "latency_us": 570,
                },
            ],
            "database_changes_persisted": 0,
        }
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            dry_run_resp,
        ]
        out_ticket = await manage_workflow_interceptors(
            {
                "action": "dry_run",
                "project": "KAN",
                "to_state": to_state_uuid,
                "sample_ticket": {
                    "summary": "Fix login crash",
                    "description_markdown": "Details here",
                },
            }
        )
        data_ticket = yaml.safe_load(out_ticket)
        assert data_ticket["would_commit"] is True
        assert data_ticket["database_changes_persisted"] == 0

        # Dry run with existing issue key
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            dry_run_resp,
        ]
        out_issue = await manage_workflow_interceptors(
            {
                "action": "dry_run",
                "project": "KAN",
                "to_state": to_state_uuid,
                "issue": "KAN-142",
            }
        )
        data_issue = yaml.safe_load(out_issue)
        assert data_issue["would_commit"] is True
    finally:
        reset_current_mcp_context(tok)


@pytest.mark.asyncio
async def test_manage_workflow_interceptors_resolvers_and_missing_params() -> None:
    """Test state name resolution via EntityResolver and missing parameter validations."""
    mock_client = AsyncMock()
    proj_uuid = str(uuid.uuid4())
    state_uuid = str(uuid.uuid4())
    hook_uuid = str(uuid.uuid4())

    ctx = McpRequestContext(
        client=mock_client,
        surface=Surface.ADMIN,
        caller_scopes=frozenset({"admin:write", "admin:destructive"}),
    )
    tok = set_current_mcp_context(ctx)
    try:
        # 1. State resolution by name in attach
        mock_client.request.side_effect = [
            _resolved(proj_uuid, kind="project", key="KAN"),
            _resolved(state_uuid, kind="state", key="In QA", title="In QA"),
            {"id": hook_uuid, "name": "Hook 1"},
        ]
        out_attach = await manage_workflow_interceptors(
            {
                "action": "attach",
                "project": "KAN",
                "name": "Hook 1",
                "to_state": "In QA",
                "hook_kind": "sync_validator",
                "wasm_module_sha256": "33" * 32,
            }
        )
        data_att = yaml.safe_load(out_attach)
        assert data_att["status"] == "attached"

        # 2. Missing hook in enable
        with pytest.raises(KbMcpError) as exc_en:
            await manage_workflow_interceptors({"action": "enable"})
        assert exc_en.value.code == McpErrorCode.VALIDATION_FAILED

        # 3. Missing hook in disable
        with pytest.raises(KbMcpError) as exc_dis:
            await manage_workflow_interceptors({"action": "disable"})
        assert exc_dis.value.code == McpErrorCode.VALIDATION_FAILED

        # 4. Missing hook in detach
        with pytest.raises(KbMcpError) as exc_det:
            await manage_workflow_interceptors({"action": "detach"})
        assert exc_det.value.code == McpErrorCode.VALIDATION_FAILED

        # 5. Missing project in reorder
        with pytest.raises(KbMcpError) as exc_reord:
            await manage_workflow_interceptors(
                {"action": "reorder", "to_state": state_uuid, "ordered_hook_ids": [hook_uuid]}
            )
        assert exc_reord.value.code == McpErrorCode.VALIDATION_FAILED

        # 6. Missing project in dry_run
        with pytest.raises(KbMcpError) as exc_dry:
            await manage_workflow_interceptors(
                {"action": "dry_run", "to_state": state_uuid, "issue": "KAN-1"}
            )
        assert exc_dry.value.code == McpErrorCode.VALIDATION_FAILED
    finally:
        reset_current_mcp_context(tok)

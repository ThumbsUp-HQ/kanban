# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool: architect_project (KB-P4-10 / S11.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest
import yaml
from sqlalchemy import text

from mcp.context import (
    McpRequestContext,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.surfaces.admin.architect_project import (
    _map_api_error_to_mcp_error,
    architect_project,
    create_architect_project_tool,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_architect_project(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke architect_project via JSON-RPC 2.0 tools/call on /mcp/admin."""
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
            "name": "architect_project",
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
async def test_architect_project_help(admin_env: AdminTestEnv) -> None:
    """Action 'help' returns usage documentation without requiring credentials."""
    data = await _call_architect_project(admin_env, {"action": "help"})
    result = data["result"]
    assert not result.get("isError")
    parsed = yaml.safe_load(result["content"][0]["text"])
    assert parsed["tool"] == "architect_project"
    assert "params" in parsed


@pytest.mark.asyncio
async def test_architect_project_unknown_param(admin_env: AdminTestEnv) -> None:
    """Unknown parameter causes VALIDATION_FAILED error."""
    data = await _call_architect_project(
        admin_env,
        {"action": "get", "project": "KAN", "extra_bad_arg": 123},
        scopes="admin:read",
    )
    result = data["result"]
    assert result.get("isError")
    content = result["content"][0]["text"]
    assert "Unknown parameter" in content


@pytest.mark.asyncio
async def test_architect_project_scope_enforcement(admin_env: AdminTestEnv) -> None:
    """Scopes admin:read vs admin:write enforcement."""
    bp = {
        "identifier": "SCP",
        "name": "Scope Test",
        "states": [
            {"name": "Todo", "group": "started", "color": "#3B82F6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
    }
    # 1. Plan requires admin:write (fails with admin:read only)
    plan_read = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert plan_read["result"].get("isError")
    assert "admin:write" in plan_read["result"]["content"][0]["text"]

    # 2. Plan with admin:write succeeds
    plan_write = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not plan_write["result"].get("isError")
    parsed_plan = yaml.safe_load(plan_write["result"]["content"][0]["text"])
    assert parsed_plan["project"] == "SCP"
    assert "plan_sha256" in parsed_plan


@pytest.mark.asyncio
async def test_architect_project_plan_apply_and_roundtrip(admin_env: AdminTestEnv) -> None:
    """Plan + apply creates project, get returns blueprint, and get->plan yields empty diff."""
    bp = {
        "identifier": "ARC",
        "name": "Architect Project",
        "description_markdown": "Engineered via architect_project",
        "states": [
            {"name": "Backlog", "group": "backlog", "color": "#94A3B8"},
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {"name": "In Progress", "group": "started", "color": "#3B82F6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [
            {"name": "Urgent", "emoji": "🔥", "color": "#DC2626"},
            {"name": "High", "emoji": "⚡", "color": "#F97316"},
            {"name": "Medium", "emoji": "🔹", "color": "#EAB308"},
            {"name": "Low", "emoji": "💤", "color": "#22C55E"},
        ],
        "labels": [
            {"name": "api", "color": "#3B82F6", "exclusive_group": "layer"},
            {"name": "ui", "color": "#10B981", "exclusive_group": "layer"},
        ],
        "modules_enabled": True,
        "modules": [{"name": "Core"}, {"name": "Auth"}],
        "default_modules": ["Core"],
        "auto_archive_days": 14,
        "wip_limits": {"In Progress": {"soft": 3, "hard": 6}},
    }

    # 1. Plan summary LOD
    plan_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp, "lod": "summary"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not plan_res["result"].get("isError")
    plan_out = yaml.safe_load(plan_res["result"]["content"][0]["text"])
    plan_sha = plan_out["plan_sha256"]
    assert plan_out["project"] == "ARC"
    assert "create" in plan_out["changes"]["project"]

    # 2. Plan full LOD
    plan_full_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp, "lod": "full"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not plan_full_res["result"].get("isError")
    plan_full_out = yaml.safe_load(plan_full_res["result"]["content"][0]["text"])
    assert plan_full_out["plan_sha256"] == plan_sha

    # 3. Apply
    apply_res = await _call_architect_project(
        admin_env,
        {"action": "apply", "blueprint": bp, "plan_sha256": plan_sha},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not apply_res["result"].get("isError")
    apply_out = yaml.safe_load(apply_res["result"]["content"][0]["text"])
    assert apply_out["status"] == "applied"
    assert apply_out["project"] == "ARC"

    # 4. Get blueprint
    get_res = await _call_architect_project(
        admin_env,
        {"action": "get", "project": "ARC"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert not get_res["result"].get("isError")
    retrieved_bp = yaml.safe_load(get_res["result"]["content"][0]["text"])
    assert retrieved_bp["identifier"] == "ARC"
    assert retrieved_bp["name"] == "Architect Project"
    assert retrieved_bp["modules_enabled"] is True

    # 5. Roundtrip: plan with retrieved blueprint yields empty diff
    rt_plan = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": retrieved_bp},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not rt_plan["result"].get("isError")
    rt_out = yaml.safe_load(rt_plan["result"]["content"][0]["text"])
    assert rt_out.get("changes") is None or rt_out.get("changes") == {}


@pytest.mark.asyncio
async def test_architect_project_stale_plan(admin_env: AdminTestEnv) -> None:
    """Stale plan_sha256 rejected with PLAN_STALE."""
    bp = {
        "identifier": "STL",
        "name": "Stale Project",
        "states": [
            {"name": "Started", "group": "started", "color": "#3B82F6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
    }
    plan_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    plan_sha = yaml.safe_load(plan_res["result"]["content"][0]["text"])["plan_sha256"]

    # Mutate blueprint
    modified_bp = {**bp, "name": "Modified Stale Project"}
    apply_res = await _call_architect_project(
        admin_env,
        {"action": "apply", "blueprint": modified_bp, "plan_sha256": plan_sha},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert apply_res["result"].get("isError")
    assert "PLAN_STALE" in apply_res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_architect_project_state_and_priority_in_use(admin_env: AdminTestEnv) -> None:
    """Removing state or priority in use produces STATE_IN_USE and PRIORITY_IN_USE."""
    bp = {
        "identifier": "USE",
        "name": "In Use Tool Test",
        "states": [
            {"name": "Todo", "group": "unstarted", "color": "#64748B"},
            {"name": "In Progress", "group": "started", "color": "#3B82F6"},
            {"name": "StageA", "group": "started", "color": "#8B5CF6"},
            {"name": "Done", "group": "completed", "color": "#10B981"},
            {"name": "Cancelled", "group": "cancelled", "color": "#EF4444"},
        ],
        "priorities": [
            {"name": "P1", "color": "#EF4444"},
            {"name": "P2", "color": "#3B82F6"},
        ],
    }
    # Plan and apply
    p_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    sha = yaml.safe_load(p_res["result"]["content"][0]["text"])["plan_sha256"]
    await _call_architect_project(
        admin_env,
        {"action": "apply", "blueprint": bp, "plan_sha256": sha},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )

    await admin_env.seed_session.rollback()

    # Seed an issue using StageA and P1
    proj_row = (
        await admin_env.seed_session.execute(
            text("SELECT id FROM projects WHERE identifier = 'USE'")
        )
    ).first()
    assert proj_row is not None
    proj_id = proj_row.id

    st_row = (
        await admin_env.seed_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p AND name = 'StageA'"),
            {"p": proj_id},
        )
    ).first()
    assert st_row is not None
    st_id = st_row.id

    pri_row = (
        await admin_env.seed_session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p AND label = 'P1'"),
            {"p": proj_id},
        )
    ).first()
    assert pri_row is not None
    pri_id = pri_row.id

    issue_id = uuid.uuid4()
    seq_val = (
        await admin_env.seed_session.execute(
            text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id}
        )
    ).scalar_one()

    await admin_env.seed_session.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, :ckey, 'Test In Use', :creator, :id)"
        ),
        {
            "ws": admin_env.workspace_id,
            "proj": proj_id,
            "ckey": f"USE-{seq_val}",
            "creator": admin_env.server_admin.id,
            "id": issue_id,
        },
    )
    await admin_env.seed_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, :st, :pr, 'Test', :creator, :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": admin_env.workspace_id,
            "proj": proj_id,
            "seq": seq_val,
            "st": st_id,
            "pr": pri_id,
            "creator": admin_env.server_admin.id,
        },
    )
    await admin_env.seed_session.commit()

    # 1. Plan removing StageA without migration -> STATE_IN_USE
    bp_no_stage = {
        **bp,
        "states": [s for s in bp["states"] if s["name"] != "StageA"],
    }
    st_in_use_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp_no_stage},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert st_in_use_res["result"].get("isError")
    assert "STATE_IN_USE" in st_in_use_res["result"]["content"][0]["text"]

    # 2. Plan removing P1 -> PRIORITY_IN_USE
    bp_no_p1 = {
        **bp,
        "priorities": [p for p in bp["priorities"] if p["name"] != "P1"],
    }
    pri_in_use_res = await _call_architect_project(
        admin_env,
        {"action": "plan", "blueprint": bp_no_p1},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert pri_in_use_res["result"].get("isError")
    assert "PRIORITY_IN_USE" in pri_in_use_res["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_architect_project_direct_unit_branches() -> None:  # noqa: PLR0915
    """Direct unit tests covering parameter checks, errors, and upstream failures."""
    # 1. No context
    set_current_mcp_context(None)
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "get", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 2. Invalid action
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        session_id="test",
        surface=create_architect_project_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"admin:write"}),
    )
    set_current_mcp_context(ctx)

    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "invalid"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. Action get missing project
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "get"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. Action get insufficient scope
    ctx_noscope = McpRequestContext(
        session_id="test",
        surface=create_architect_project_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"unknown:scope"}),
    )
    set_current_mcp_context(ctx_noscope)
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "get", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.INSUFFICIENT_SCOPE

    # 5. Action get upstream error / non-dict
    set_current_mcp_context(ctx)
    mock_client.request.return_value = "not-a-dict"
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "get", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    # 6. Action get error mapping (NOT_FOUND)
    mock_client.request.side_effect = KbMcpError(McpErrorCode.NOT_FOUND, "Project not found")
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "get", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.NOT_FOUND

    # 7. Action plan missing blueprint
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "plan"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 8. Action plan non-dict
    mock_client.request.side_effect = None
    mock_client.request.return_value = "not-a-dict"
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "plan", "blueprint": {"identifier": "X"}})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    # 9. Action apply missing blueprint / missing plan_sha256
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "apply", "plan_sha256": "abc"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info:
        await architect_project({"action": "apply", "blueprint": {"identifier": "X"}})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 10. Action apply non-dict
    mock_client.request.return_value = "not-a-dict"
    with pytest.raises(KbMcpError) as exc_info:
        await architect_project(
            {"action": "apply", "blueprint": {"identifier": "X"}, "plan_sha256": "abc"}
        )
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    # 11. Error mapper checks
    e1 = _map_api_error_to_mcp_error(KbMcpError(McpErrorCode.STATE_IN_USE, "state in use"))
    assert e1.code == McpErrorCode.STATE_IN_USE
    assert e1.hint is not None

    e2 = _map_api_error_to_mcp_error(KbMcpError(McpErrorCode.PRIORITY_IN_USE, "pri in use"))
    assert e2.code == McpErrorCode.PRIORITY_IN_USE

    e3 = _map_api_error_to_mcp_error(KbMcpError(McpErrorCode.VALIDATION_FAILED, "invalid wip"))
    assert e3.code == McpErrorCode.VALIDATION_FAILED

    set_current_mcp_context(None)

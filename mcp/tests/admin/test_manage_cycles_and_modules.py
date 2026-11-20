# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, ANN401, ARG001
"""Feature unit tests for /mcp/admin tool: manage_cycles_and_modules (KB-P4-10 / S11.4)."""

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
from mcp.surfaces.admin.manage_cycles_and_modules import (
    MANAGE_CYCLES_AND_MODULES_SCHEMA,
    _is_uuid,
    _map_cycle_error,
    _resolve_cycle_id,
    _resolve_module_id,
    _resolve_view_id,
    create_manage_cycles_and_modules_tool,
    manage_cycles_and_modules,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_manage_cycles_and_modules(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_cycles_and_modules via JSON-RPC 2.0 tools/call on /mcp/admin."""
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
            "name": "manage_cycles_and_modules",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data)


async def _create_test_project(
    env: AdminTestEnv,
    identifier: str,
    name: str,
    *,
    modules_enabled: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a test project returning (project_id, started_state_id, completed_state_id)."""
    proj_id = (
        await env.seed_session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, :ident, :name, :creator)"
            ),
            {
                "ws": env.workspace_id,
                "ident": identifier,
                "name": name,
                "creator": env.server_admin.id,
            },
        )
    ).scalar_one()

    await env.seed_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, :ident, :name, :me)"
        ),
        {
            "id": proj_id,
            "ws": env.workspace_id,
            "ident": identifier,
            "name": name,
            "me": modules_enabled,
        },
    )
    await env.seed_session.commit()

    started_st = (
        await env.seed_session.execute(
            text(
                "SELECT id FROM workflow_states WHERE project_id = :p AND state_group = 'started'"
            ),
            {"p": proj_id},
        )
    ).scalar_one()

    completed_st = (
        await env.seed_session.execute(
            text(
                "SELECT id FROM workflow_states WHERE project_id = :p AND state_group = 'completed'"
            ),
            {"p": proj_id},
        )
    ).scalar_one()

    return proj_id, started_st, completed_st


@pytest.mark.asyncio
async def test_manage_cycles_and_modules_help(admin_env: AdminTestEnv) -> None:
    """Action 'help' returns usage documentation without requiring credentials."""
    data = await _call_manage_cycles_and_modules(admin_env, {"action": "help"})
    result = data["result"]
    assert not result.get("isError")
    parsed = yaml.safe_load(result["content"][0]["text"])
    assert parsed["tool"] == "manage_cycles_and_modules"
    assert "params" in parsed


@pytest.mark.asyncio
async def test_manage_cycles_and_modules_unknown_param(admin_env: AdminTestEnv) -> None:
    """Unknown parameter causes VALIDATION_FAILED error."""
    data = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "list_cycles", "project": "KAN", "bad_unknown_key": "val"},
        scopes="admin:read",
    )
    result = data["result"]
    assert result.get("isError")
    assert "Unknown parameter" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_manage_cycles_and_modules_scope_enforcement(admin_env: AdminTestEnv) -> None:
    """Read actions succeed with admin:read; mutating actions require admin:write."""
    _proj_id, _, _ = await _create_test_project(admin_env, "SCP2", "Scope Project")

    # 1. list_cycles with admin:read succeeds
    read_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "list_cycles", "project": "SCP2"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert not read_res["result"].get("isError")

    # 2. create_cycle with admin:read only fails with INSUFFICIENT_SCOPE
    write_fail = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_cycle", "project": "SCP2", "name": "Sprint 1"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert write_fail["result"].get("isError")
    assert "admin:write" in write_fail["result"]["content"][0]["text"]

    # 3. create_cycle with admin:write succeeds
    write_ok = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_cycle", "project": "SCP2", "name": "Sprint 1"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not write_ok["result"].get("isError")


@pytest.mark.asyncio
async def test_manage_cycles_lifecycle_and_monotonicity(admin_env: AdminTestEnv) -> None:
    """Cycle lifecycle: create, list, complete on upcoming fails (monotonicity), start, complete."""
    await _create_test_project(admin_env, "CYM", "Cycle Monotonicity Project")

    # 1. Create cycle
    create_res = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "create_cycle",
            "project": "CYM",
            "name": "Sprint Alpha",
            "start_date": "2026-12-01",
            "end_date": "2026-12-14",
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not create_res["result"].get("isError")
    cycle_data = yaml.safe_load(create_res["result"]["content"][0]["text"])
    assert cycle_data["name"] == "Sprint Alpha"
    assert cycle_data["status"] == "upcoming"

    # 2. List cycles
    list_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "list_cycles", "project": "CYM"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert not list_res["result"].get("isError")
    cycles = yaml.safe_load(list_res["result"]["content"][0]["text"])["cycles"]
    assert any(c["name"] == "Sprint Alpha" for c in cycles)

    # 3. Monotonicity violation: complete_cycle on upcoming cycle -> INVALID_TRANSITION
    bad_complete = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "complete_cycle", "project": "CYM", "cycle": "Sprint Alpha"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert bad_complete["result"].get("isError")
    assert "INVALID_TRANSITION" in bad_complete["result"]["content"][0]["text"]

    # 4. Start cycle -> active
    start_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "start_cycle", "project": "CYM", "cycle": "Sprint Alpha"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not start_res["result"].get("isError")
    assert yaml.safe_load(start_res["result"]["content"][0]["text"])["status"] == "active"

    # 5. Update cycle
    update_res = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "update_cycle",
            "project": "CYM",
            "cycle": "Sprint Alpha",
            "name": "Sprint Alpha Renamed",
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not update_res["result"].get("isError")
    assert (
        yaml.safe_load(update_res["result"]["content"][0]["text"])["name"] == "Sprint Alpha Renamed"
    )

    # 6. Complete cycle -> completed
    comp_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "complete_cycle", "project": "CYM", "cycle": "Sprint Alpha Renamed"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not comp_res["result"].get("isError")
    comp_data = yaml.safe_load(comp_res["result"]["content"][0]["text"])
    status = comp_data.get("status") or (
        comp_data.get("cycle", {}).get("status")
        if isinstance(comp_data.get("cycle"), dict)
        else None
    )
    assert status == "completed"


@pytest.mark.asyncio
async def test_manage_cycles_rollover(admin_env: AdminTestEnv) -> None:
    """Rollover unfinished issues from source cycle to target cycle."""
    proj_id, st_started, st_completed = await _create_test_project(
        admin_env, "ROL", "Rollover Test Project"
    )

    # Create Cycle 1 and Cycle 2
    c1_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_cycle", "project": "ROL", "name": "Cycle 1"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    c1_id = yaml.safe_load(c1_res["result"]["content"][0]["text"])["id"]

    c2_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_cycle", "project": "ROL", "name": "Cycle 2"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    yaml.safe_load(c2_res["result"]["content"][0]["text"])["id"]

    # Start Cycle 1
    await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "start_cycle", "project": "ROL", "cycle": "Cycle 1"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )

    # Priority row
    pri_row = (
        await admin_env.seed_session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_id},
        )
    ).first()
    assert pri_row is not None
    pri_id = pri_row.id

    # Seed 4 unfinished issues in Cycle 1
    for _ in range(4):
        iid = uuid.uuid4()
        seq = (
            await admin_env.seed_session.execute(
                text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id}
            )
        ).scalar_one()
        await admin_env.seed_session.execute(
            text(
                "SELECT register_object("
                "'issue'::object_kind, :ws, :proj, :ckey, 'Unfinished', :creator, :id)"
            ),
            {
                "ws": admin_env.workspace_id,
                "proj": proj_id,
                "ckey": f"ROL-{seq}",
                "creator": admin_env.server_admin.id,
                "id": iid,
            },
        )
        await admin_env.seed_session.execute(
            text(
                "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
                "state_id, priority_id, cycle_id, summary, created_by_id, "
                "original_created_by_id, board_rank) "
                "VALUES (:id, :ws, :proj, :seq, :st, :pr, :cyc, 'Unfinished', "
                ":creator, :creator, '0|hzzzzz:')"
            ),
            {
                "id": iid,
                "ws": admin_env.workspace_id,
                "proj": proj_id,
                "seq": seq,
                "st": st_started,
                "pr": pri_id,
                "cyc": uuid.UUID(c1_id),
                "creator": admin_env.server_admin.id,
            },
        )

    # Seed 2 completed issues in Cycle 1
    for _ in range(2):
        iid = uuid.uuid4()
        seq = (
            await admin_env.seed_session.execute(
                text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id}
            )
        ).scalar_one()
        await admin_env.seed_session.execute(
            text(
                "SELECT register_object("
                "'issue'::object_kind, :ws, :proj, :ckey, 'Done', :creator, :id)"
            ),
            {
                "ws": admin_env.workspace_id,
                "proj": proj_id,
                "ckey": f"ROL-{seq}",
                "creator": admin_env.server_admin.id,
                "id": iid,
            },
        )
        await admin_env.seed_session.execute(
            text(
                "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
                "state_id, priority_id, cycle_id, summary, created_by_id, "
                "original_created_by_id, board_rank) "
                "VALUES (:id, :ws, :proj, :seq, :st, :pr, :cyc, 'Done', "
                ":creator, :creator, '0|hzzzzz:')"
            ),
            {
                "id": iid,
                "ws": admin_env.workspace_id,
                "proj": proj_id,
                "seq": seq,
                "st": st_completed,
                "pr": pri_id,
                "cyc": uuid.UUID(c1_id),
                "creator": admin_env.server_admin.id,
            },
        )
    await admin_env.seed_session.commit()

    # Rollover
    rollover_res = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "rollover",
            "project": "ROL",
            "cycle": "Cycle 1",
            "target_cycle": "Cycle 2",
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not rollover_res["result"].get("isError")
    roll_data = yaml.safe_load(rollover_res["result"]["content"][0]["text"])
    assert roll_data["moved"] == 4
    assert roll_data["from"] == "Cycle 1"
    assert roll_data["to"] == "Cycle 2"


@pytest.mark.asyncio
async def test_manage_modules_lifecycle_and_disabled_guard(admin_env: AdminTestEnv) -> None:
    """Modules: disabled project -> MODULES_DISABLED; enabled -> create, list, update."""
    # 1. Project with modules disabled
    await _create_test_project(admin_env, "MDIS", "Disabled Modules", modules_enabled=False)

    dis_res = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_module", "project": "MDIS", "name": "Payment Engine"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert dis_res["result"].get("isError")
    assert "MODULES_DISABLED" in dis_res["result"]["content"][0]["text"]

    # 2. Project with modules enabled
    await _create_test_project(admin_env, "MENA", "Enabled Modules", modules_enabled=True)

    create_mod = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "create_module", "project": "MENA", "name": "Auth Module"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not create_mod["result"].get("isError")
    mod_data = yaml.safe_load(create_mod["result"]["content"][0]["text"])
    assert mod_data["name"] == "Auth Module"

    # List modules
    list_mods = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "list_modules", "project": "MENA"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert not list_mods["result"].get("isError")
    mods = yaml.safe_load(list_mods["result"]["content"][0]["text"])["modules"]
    assert any(m["name"] == "Auth Module" for m in mods)

    # Update module
    up_mod = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "update_module",
            "project": "MENA",
            "module": "Auth Module",
            "name": "Auth Core",
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not up_mod["result"].get("isError")
    assert yaml.safe_load(up_mod["result"]["content"][0]["text"])["name"] == "Auth Core"


@pytest.mark.asyncio
async def test_manage_views_lifecycle(admin_env: AdminTestEnv) -> None:
    """Views: create, list, update saved views."""
    await _create_test_project(admin_env, "VIW", "Views Project")

    # Create view
    v_spec = {"layout": "board", "group_by": "state"}
    c_view = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "create_view",
            "project": "VIW",
            "name": "Sprint Board",
            "view_spec": v_spec,
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not c_view["result"].get("isError")
    view_data = yaml.safe_load(c_view["result"]["content"][0]["text"])
    assert view_data["name"] == "Sprint Board"

    # List views
    l_views = await _call_manage_cycles_and_modules(
        admin_env,
        {"action": "list_views", "project": "VIW"},
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:read",
        aal_level=2,
    )
    assert not l_views["result"].get("isError")
    views = yaml.safe_load(l_views["result"]["content"][0]["text"])["views"]
    assert any(v["name"] == "Sprint Board" for v in views)

    # Update view
    u_view = await _call_manage_cycles_and_modules(
        admin_env,
        {
            "action": "update_view",
            "project": "VIW",
            "view": "Sprint Board",
            "name": "Active Sprint Board",
        },
        subject_token=admin_env.token_server_admin_full,
        scopes="admin:write",
        aal_level=2,
    )
    assert not u_view["result"].get("isError")
    assert yaml.safe_load(u_view["result"]["content"][0]["text"])["name"] == "Active Sprint Board"


def test_contract_no_bind_or_delete_actions() -> None:
    """Invariant: tool exposes repo binding actions and zero delete actions."""
    action_enum = MANAGE_CYCLES_AND_MODULES_SCHEMA["properties"]["action"]["enum"]
    assert "bind_project_repo" in action_enum
    for action in action_enum:
        assert "delete" not in action.lower(), f"Unexpected delete action found: {action}"
    assert len(action_enum) == 17


@pytest.mark.asyncio
async def test_manage_cycles_and_modules_direct_unit_branches() -> None:  # noqa: PLR0915
    """Direct unit tests covering parameter checks, resolvers, errors, and fallbacks."""
    # 1. UUID validator helper
    valid_uuid_str = str(uuid.uuid4())
    assert _is_uuid(valid_uuid_str) is True
    assert _is_uuid("not-a-uuid") is False

    # 2. Error mapper
    e1 = _map_cycle_error(KbMcpError(McpErrorCode.MODULES_DISABLED, "modules disabled"))
    assert e1.code == McpErrorCode.MODULES_DISABLED
    e2 = _map_cycle_error(KbMcpError(McpErrorCode.NOT_FOUND, "not found"))
    assert e2.code == McpErrorCode.NOT_FOUND
    e3 = _map_cycle_error(KbMcpError(McpErrorCode.VALIDATION_FAILED, "other"))
    assert e3.code == McpErrorCode.VALIDATION_FAILED

    # 3. Missing action / missing project
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_cycles"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. Context client is None
    mock_client = AsyncMock()
    ctx = McpRequestContext(
        session_id="test",
        surface=create_manage_cycles_and_modules_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"admin:write"}),
    )
    set_current_mcp_context(ctx)

    # 5. Resolvers with raw UUIDs
    assert await _resolve_cycle_id(ctx, "KAN", valid_uuid_str) == valid_uuid_str
    assert await _resolve_module_id(ctx, "KAN", valid_uuid_str) == valid_uuid_str
    assert await _resolve_view_id(ctx, "KAN", valid_uuid_str) == valid_uuid_str

    # 6. Resolvers not found
    mock_client.request.return_value = []
    with pytest.raises(KbMcpError) as exc_info:
        await _resolve_cycle_id(ctx, "KAN", "MissingCycle")
    assert exc_info.value.code == McpErrorCode.NOT_FOUND

    with pytest.raises(KbMcpError) as exc_info:
        await _resolve_module_id(ctx, "KAN", "MissingMod")
    assert exc_info.value.code == McpErrorCode.NOT_FOUND

    with pytest.raises(KbMcpError) as exc_info:
        await _resolve_view_id(ctx, "KAN", "MissingView")
    assert exc_info.value.code == McpErrorCode.NOT_FOUND

    # 7. Resolvers client is None
    ctx_no_client = McpRequestContext(
        session_id="test",
        surface=create_manage_cycles_and_modules_tool().surface,
        client=None,
    )
    with pytest.raises(KbMcpError):
        await _resolve_cycle_id(ctx_no_client, "KAN", "C1")
    with pytest.raises(KbMcpError):
        await _resolve_module_id(ctx_no_client, "KAN", "M1")
    with pytest.raises(KbMcpError):
        await _resolve_view_id(ctx_no_client, "KAN", "V1")

    # 8. Missing mandatory parameters for actions
    # create_cycle missing name
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "create_cycle", "project": "KAN"})
    # update_cycle missing cycle
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "update_cycle", "project": "KAN"})
    # start_cycle missing cycle
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "start_cycle", "project": "KAN"})
    # complete_cycle missing cycle
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "complete_cycle", "project": "KAN"})
    # rollover missing cycle / target_cycle
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "rollover", "project": "KAN"})
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "rollover", "project": "KAN", "cycle": "C1"})
    # create_module missing name
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "create_module", "project": "KAN"})
    # update_module missing module
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "update_module", "project": "KAN"})
    # create_view missing name
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "create_view", "project": "KAN"})
    # update_view missing view
    with pytest.raises(KbMcpError):
        await manage_cycles_and_modules({"action": "update_view", "project": "KAN"})

    # 9. List actions with lod='full'
    mock_client.request.return_value = [{"id": valid_uuid_str, "name": "Item"}]
    res_full_c = await manage_cycles_and_modules(
        {"action": "list_cycles", "project": "KAN", "lod": "full"}
    )
    assert "cycles" in res_full_c
    res_full_m = await manage_cycles_and_modules(
        {"action": "list_modules", "project": "KAN", "lod": "full"}
    )
    assert "modules" in res_full_m
    mock_client.request.return_value = {"items": [{"id": valid_uuid_str, "name": "Item"}]}
    res_full_v = await manage_cycles_and_modules(
        {"action": "list_views", "project": "KAN", "lod": "full"}
    )
    assert "views" in res_full_v

    # 10. List actions non-list error
    mock_client.request.return_value = "invalid-not-list"
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_cycles", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_modules", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    # 11. Rollover non-dict error
    mock_client.request.return_value = "invalid-not-dict"
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {
                "action": "rollover",
                "project": "KAN",
                "cycle": valid_uuid_str,
                "target_cycle": valid_uuid_str,
            }
        )
    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR

    # 12. Create view with filters_json
    mock_client.request.return_value = {"id": valid_uuid_str, "name": "Filtered"}
    v_res = await manage_cycles_and_modules(
        {
            "action": "create_view",
            "project": "KAN",
            "name": "Filtered",
            "view_spec": {"filters_json": {"state_id": ["open"]}},
        }
    )
    assert "Filtered" in v_res

    # 13. Help with project resolution
    mock_client.request.return_value = {
        "key": "KAN",
        "name": "Kanban",
        "states": [],
        "priorities": [],
    }
    help_out = await manage_cycles_and_modules({"action": "help", "project": "KAN"})
    assert "manage_cycles_and_modules" in help_out

    # 14. Context client unavailable
    set_current_mcp_context(None)
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_cycles", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 15. Scope checks
    ctx_read = McpRequestContext(
        session_id="test",
        surface=create_manage_cycles_and_modules_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"agent:read"}),
    )
    set_current_mcp_context(ctx_read)
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_cycles", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.INSUFFICIENT_SCOPE

    ctx_admin_read = McpRequestContext(
        session_id="test",
        surface=create_manage_cycles_and_modules_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"admin:read"}),
    )
    set_current_mcp_context(ctx_admin_read)
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "create_cycle", "project": "KAN", "name": "C1"})
    assert exc_info.value.code == McpErrorCode.INSUFFICIENT_SCOPE

    # 16. Upstream exceptions mapped with _map_cycle_error
    set_current_mcp_context(ctx)
    mock_client.request.side_effect = KbMcpError(McpErrorCode.MODULES_DISABLED, "modules disabled")

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_cycles", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "create_cycle", "project": "KAN", "name": "C1"})
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {
                "action": "update_cycle",
                "project": "KAN",
                "cycle": valid_uuid_str,
                "name": "New",
                "start_date": "2026-01-01",
                "end_date": "2026-01-14",
            }
        )
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {"action": "start_cycle", "project": "KAN", "cycle": valid_uuid_str}
        )
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {
                "action": "complete_cycle",
                "project": "KAN",
                "cycle": valid_uuid_str,
                "target_cycle": valid_uuid_str,
            }
        )
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "create_module", "project": "KAN", "name": "M1"})
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {
                "action": "update_module",
                "project": "KAN",
                "module": valid_uuid_str,
                "name": "M1-Updated",
            }
        )
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "list_views", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "create_view", "project": "KAN", "name": "V1"})
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules(
            {
                "action": "update_view",
                "project": "KAN",
                "view": valid_uuid_str,
                "name": "V1-Updated",
                "view_spec": {
                    "layout": "kanban",
                    "group_by": "state",
                    "sub_group_by": None,
                    "filters_json": {"state_id": ["open"]},
                },
            }
        )
    assert exc_info.value.code == McpErrorCode.MODULES_DISABLED

    # 17. Unsupported action
    mock_client.request.side_effect = None
    with pytest.raises(KbMcpError) as exc_info:
        await manage_cycles_and_modules({"action": "unsupported_action", "project": "KAN"})
    assert exc_info.value.code == McpErrorCode.VALIDATION_FAILED

    set_current_mcp_context(None)


@pytest.mark.asyncio
async def test_manage_cycles_and_modules_additional_branch_coverage() -> None:  # noqa: PLR0915
    """Additional branch coverage targeting manage_cycles_and_modules to reach >=95%."""
    valid_uuid_str = str(uuid.uuid4())
    mock_client = AsyncMock()

    # 1. Unknown parameter
    with pytest.raises(KbMcpError) as exc_unk:
        await manage_cycles_and_modules(
            {"action": "list_cycles", "project": "KAN", "bad_param": 123}
        )
    assert exc_unk.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. repo binding actions without project, but with valid uuid binding (line 316)
    ctx = McpRequestContext(
        session_id="test",
        surface=create_manage_cycles_and_modules_tool().surface,
        client=mock_client,
        caller_scopes=frozenset({"admin:write"}),
    )
    set_current_mcp_context(ctx)

    try:
        mock_client.request.return_value = {"id": valid_uuid_str, "status": "refreshed"}
        res_ref = await manage_cycles_and_modules(
            {
                "action": "refresh_repo_binding",
                "binding": valid_uuid_str,
            }
        )
        assert "refreshed" in res_ref

        # 3. admin:destructive scope authorization check (lines 327-338)
        ctx_destr = McpRequestContext(
            session_id="test",
            surface=create_manage_cycles_and_modules_tool().surface,
            client=mock_client,
            caller_scopes=frozenset({"admin:destructive"}),
        )
        set_current_mcp_context(ctx_destr)
        mock_client.request.return_value = {"id": valid_uuid_str, "name": "Cycle Destr"}
        res_d = await manage_cycles_and_modules(
            {
                "action": "create_cycle",
                "project": "KAN",
                "name": "Cycle Destr",
            }
        )
        assert "Cycle Destr" in res_d

        # 4. update_cycle with name, start_date, end_date (lines 408-410)
        set_current_mcp_context(ctx)
        mock_client.request.return_value = {"id": valid_uuid_str, "name": "Cycle Named"}
        res_up_c = await manage_cycles_and_modules(
            {
                "action": "update_cycle",
                "project": "KAN",
                "cycle": valid_uuid_str,
                "name": "Cycle Named",
                "start_date": "2026-01-01",
                "end_date": "2026-01-14",
            }
        )
        assert "Cycle Named" in res_up_c

        # 5. rollover KbMcpError (lines 495-496)
        mock_client.request.side_effect = KbMcpError(McpErrorCode.INTERNAL, "rollover error")
        with pytest.raises(KbMcpError):
            await manage_cycles_and_modules(
                {
                    "action": "rollover",
                    "project": "KAN",
                    "cycle": valid_uuid_str,
                    "target_cycle": valid_uuid_str,
                }
            )

        # 6. list_modules KbMcpError (lines 521-522)
        mock_client.request.side_effect = KbMcpError(McpErrorCode.INTERNAL, "list_modules error")
        with pytest.raises(KbMcpError):
            await manage_cycles_and_modules({"action": "list_modules", "project": "KAN"})

        # 7. update_module with and without name (lines 569-572)
        mock_client.request.side_effect = None
        mock_client.request.return_value = {"id": valid_uuid_str, "name": "M1-Updated"}
        res_up_m = await manage_cycles_and_modules(
            {
                "action": "update_module",
                "project": "KAN",
                "module": valid_uuid_str,
                "name": "M1-Updated",
            }
        )
        assert "M1-Updated" in res_up_m

        # 8. update_view with name (lines 657-659)
        mock_client.request.return_value = {"id": valid_uuid_str, "name": "V-New"}
        res_up_v = await manage_cycles_and_modules(
            {
                "action": "update_view",
                "project": "KAN",
                "view": valid_uuid_str,
                "name": "V-New",
            }
        )
        assert "V-New" in res_up_v

        # 9. bind_project_repo validation and credentials (lines 689-705)
        with pytest.raises(KbMcpError) as exc_bind:
            await manage_cycles_and_modules(
                {
                    "action": "bind_project_repo",
                    "project": "KAN",
                }
            )
        assert exc_bind.value.code == McpErrorCode.VALIDATION_FAILED

        async def _mock_repo_req(method: str, path: str, **kwargs: Any) -> Any:
            if method == "GET" and "/api/v1/resolve" in path:
                return {
                    "id": valid_uuid_str,
                    "kind": "project",
                    "key": "KAN",
                    "title": "Kanban",
                }
            if method == "POST" and "/repo-bindings" in path:
                return {"id": valid_uuid_str, "slug": "my-repo", "credential": "***"}
            if method == "POST" and f"/repo-bindings/{valid_uuid_str}/refresh" in path:
                return {"id": valid_uuid_str, "status": "refreshed"}
            if method == "DELETE" and f"/repo-bindings/{valid_uuid_str}" in path:
                return {"status": "ok"}
            return {}

        mock_client.request = AsyncMock(side_effect=_mock_repo_req)
        res_bind = await manage_cycles_and_modules(
            {
                "action": "bind_project_repo",
                "project": "KAN",
                "slug": "my-repo",
                "remote_url": "https://git.example.com/repo.git",
                "access_mode": "read_only",
                "credential": "secret-token",
            }
        )
        assert "my-repo" in res_bind

        # 10. list_repo_bindings invalid response (lines 730-731)
        async def _mock_list_bad(method: str, path: str, **kwargs: Any) -> Any:
            if method == "GET" and "/api/v1/resolve" in path:
                return {
                    "id": valid_uuid_str,
                    "kind": "project",
                    "key": "KAN",
                    "title": "Kanban",
                }
            return "not-a-list"

        mock_client.request = AsyncMock(side_effect=_mock_list_bad)
        with pytest.raises(KbMcpError) as exc_lr:
            await manage_cycles_and_modules({"action": "list_repo_bindings", "project": "KAN"})
        assert exc_lr.value.code == McpErrorCode.UPSTREAM_ERROR

        # 11. refresh_repo_binding parameter validations and slug resolution (lines 753-766)
        with pytest.raises(KbMcpError) as exc_ref_miss:
            await manage_cycles_and_modules({"action": "refresh_repo_binding", "project": "KAN"})
        assert exc_ref_miss.value.code == McpErrorCode.VALIDATION_FAILED

        with pytest.raises(KbMcpError) as exc_slug_no_proj:
            await manage_cycles_and_modules(
                {
                    "action": "refresh_repo_binding",
                    "binding": "slug-name",
                }
            )
        assert exc_slug_no_proj.value.code == McpErrorCode.VALIDATION_FAILED

        mock_client.request = AsyncMock(side_effect=_mock_repo_req)
        res_ref_slug = await manage_cycles_and_modules(
            {
                "action": "refresh_repo_binding",
                "binding": "slug-name",
                "project": "KAN",
            }
        )
        assert "refreshed" in res_ref_slug

        # 12. unbind_project_repo parameter validations, slug resolution, confirmation (lines 779-811)
        with pytest.raises(KbMcpError) as exc_unb_miss:
            await manage_cycles_and_modules({"action": "unbind_project_repo", "project": "KAN"})
        assert exc_unb_miss.value.code == McpErrorCode.VALIDATION_FAILED

        with pytest.raises(KbMcpError) as exc_unb_no_proj:
            await manage_cycles_and_modules(
                {
                    "action": "unbind_project_repo",
                    "binding": "slug-name",
                }
            )
        assert exc_unb_no_proj.value.code == McpErrorCode.VALIDATION_FAILED

        res_unb_warn = await manage_cycles_and_modules(
            {
                "action": "unbind_project_repo",
                "binding": "slug-name",
                "project": "KAN",
            }
        )
        assert "confirmation_required" in res_unb_warn

        res_unb_del = await manage_cycles_and_modules(
            {
                "action": "unbind_project_repo",
                "binding": "slug-name",
                "project": "KAN",
                "confirm": True,
            }
        )
        assert "deleted" in res_unb_del

    finally:
        set_current_mcp_context(None)

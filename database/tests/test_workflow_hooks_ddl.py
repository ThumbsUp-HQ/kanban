# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""DDL constraints, guard triggers, and RLS policies for workflow transition hooks (KB-P5-17a)."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_test_env(
    session: AsyncSession,
) -> dict[str, Any]:
    """Provision workspace, project, states, issues, wasm module, agent def, and principals."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Workflow DDL WS"},
    )

    admin_id = uuid.uuid4()
    member_id = uuid.uuid4()

    for pid, dname in (
        (admin_id, "Admin User"),
        (member_id, "Member User"),
    ):
        await session.execute(
            text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, :name, :uid, :id)"),
            {"ws": ws_id, "ckey": f"usr-{pid.hex[:8]}", "name": dname, "uid": pid, "id": pid},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name)"
            ),
            {"id": pid, "ws_id": ws_id, "name": dname},
        )
        await session.execute(
            text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
            {"id": pid, "ws_id": ws_id, "email": f"{pid.hex[:8]}@example.com"},
        )

    ident = f"P{uuid.uuid4().hex[:4].upper()}"
    proj_id = await session.scalar(
        text(
            "SELECT register_object("
            "'project'::object_kind, :ws, NULL, :ident, 'Workflow Project', :uid)"
        ),
        {"ws": ws_id, "ident": ident, "uid": admin_id},
    )
    assert isinstance(proj_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, 'Workflow Project')"
        ),
        {"id": proj_id, "ws": ws_id, "ident": ident},
    )

    # Project roles: admin has PROJECT_ADMIN, member has MEMBER
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p_id, 'PROJECT_ADMIN', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "p_id": admin_id, "proj_id": proj_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p_id, 'MEMBER', 'project', :proj_id)"
        ),
        {"ws_id": ws_id, "p_id": member_id, "proj_id": proj_id},
    )
    await session.execute(text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws_id})

    # Project triggers automatically seed default workflow states and priorities
    state_todo = await session.scalar(
        text("SELECT id FROM workflow_states WHERE project_id = :proj AND name = 'Todo' LIMIT 1"),
        {"proj": proj_id},
    )
    if state_todo is None:
        state_todo = await session.scalar(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :proj AND state_group = 'unstarted' LIMIT 1"
            ),
            {"proj": proj_id},
        )
    assert isinstance(state_todo, uuid.UUID)

    state_done = await session.scalar(
        text("SELECT id FROM workflow_states WHERE project_id = :proj AND name = 'Done' LIMIT 1"),
        {"proj": proj_id},
    )
    if state_done is None:
        state_done = await session.scalar(
            text(
                "SELECT id FROM workflow_states "
                "WHERE project_id = :proj AND state_group = 'completed' LIMIT 1"
            ),
            {"proj": proj_id},
        )
    assert isinstance(state_done, uuid.UUID)

    prio_id = await session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :proj AND is_default = true LIMIT 1"
        ),
        {"proj": proj_id},
    )
    if prio_id is None:
        prio_id = await session.scalar(
            text("SELECT id FROM project_priorities WHERE project_id = :proj LIMIT 1"),
            {"proj": proj_id},
        )
    assert isinstance(prio_id, uuid.UUID)

    # Issue
    seq = await session.scalar(text("SELECT allocate_issue_sequence(:proj)"), {"proj": proj_id})
    issue_ckey = f"{ident}-{seq}"
    issue_id = await session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, 'Test Issue', :uid)"),
        {"ws": ws_id, "proj": proj_id, "ckey": issue_ckey, "uid": admin_id},
    )
    assert isinstance(issue_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "  board_rank"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :seq, 'Test Issue', "
            "  'Issue body content', :state_id, :prio_id, :cb_id, :cb_id, "
            "  '0|i00000:'"
            ")"
        ),
        {
            "id": issue_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "seq": seq,
            "state_id": state_todo,
            "prio_id": prio_id,
            "cb_id": admin_id,
        },
    )

    # Wasm module
    wasm_sha256 = hashlib.sha256(b"\x00asm\x01\x00\x00\x00dummy").digest()
    wasm_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO approved_wasm_modules ("
            "  id, workspace_id, project_id, sha256, name, wasm_bytes, approved_by_id"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :sha, 'test-wasm', :bytes, :app_by"
            ")"
        ),
        {
            "id": wasm_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "sha": wasm_sha256,
            "bytes": b"\x00asm\x01\x00\x00\x00dummy",
            "app_by": admin_id,
        },
    )

    # Agent definition
    agent_def_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO agent_definitions ("
            "  id, workspace_id, project_id, principal_id, slug, display_name,"
            "  harness_kind, cli_binary_allowlist_id, cli_args_json"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :p_id, 'test-interceptor', 'Test Interceptor',"
            "  'cli_pipe', 'agy', '[\"-p\"]'::jsonb"
            ")"
        ),
        {
            "id": agent_def_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "p_id": admin_id,
        },
    )

    return {
        "workspace_id": ws_id,
        "admin_user_id": admin_id,
        "admin_principal_id": admin_id,
        "member_user_id": member_id,
        "member_principal_id": member_id,
        "project_id": proj_id,
        "state_todo": state_todo,
        "state_done": state_done,
        "issue_id": issue_id,
        "wasm_sha256": wasm_sha256,
        "agent_def_id": agent_def_id,
    }


@pytest.mark.asyncio
async def test_workflow_hooks_ddl_constraints(db_session: AsyncSession) -> None:
    """Verify check constraints on workflow_transition_hooks, executions, and invocations."""
    env = await _create_test_env(db_session)
    ws_id = env["workspace_id"]
    proj_id = env["project_id"]
    state_todo = env["state_todo"]
    state_done = env["state_done"]
    wasm_sha = env["wasm_sha256"]
    agent_def_id = env["agent_def_id"]
    issue_id = env["issue_id"]
    admin_p_id = env["admin_principal_id"]

    dummy_manifest = hashlib.sha256(b"dummy_manifest").digest()

    # 1. Positive insert sync_validator
    hook_val_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO workflow_transition_hooks ("
            "  id, workspace_id, project_id, name, from_state_id, to_state_id,"
            "  hook_kind, sort_rank, is_enabled, wasm_module_sha256,"
            "  failure_policy, manifest_sha256"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, 'val-1', :from_st, :to_st,"
            "  'sync_validator', '0|i00001:', true, :wasm_sha, 'fail_closed', :manifest"
            ")"
        ),
        {
            "id": hook_val_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "from_st": state_todo,
            "to_st": state_done,
            "wasm_sha": wasm_sha,
            "manifest": dummy_manifest,
        },
    )

    # 2. CHECK constraint: sync_validator with agent_definition_id set -> rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_hooks ("
                    "  workspace_id, project_id, name, from_state_id, to_state_id,"
                    "  hook_kind, sort_rank, wasm_module_sha256,"
                    "  agent_definition_id, manifest_sha256"
                    ") VALUES ("
                    "  :ws_id, :proj_id, 'invalid-hook', :from_st, :to_st,"
                    "  'sync_validator', '0|i00002:', :wasm_sha, :agent_def, :manifest"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "from_st": state_todo,
                    "to_st": state_done,
                    "wasm_sha": wasm_sha,
                    "agent_def": agent_def_id,
                    "manifest": dummy_manifest,
                },
            )
    assert "ck_workflow_transition_hooks_kind" in str(exc_info.value).lower()

    # 3. CHECK constraint: agent_interceptor with wasm_module_sha256 set -> rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_hooks ("
                    "  workspace_id, project_id, name, from_state_id, to_state_id,"
                    "  hook_kind, sort_rank, wasm_module_sha256,"
                    "  agent_definition_id, manifest_sha256"
                    ") VALUES ("
                    "  :ws_id, :proj_id, 'invalid-agent-hook', :from_st, :to_st,"
                    "  'agent_interceptor', '0|i00003:', :wasm_sha, :agent_def, :manifest"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "from_st": state_todo,
                    "to_st": state_done,
                    "wasm_sha": wasm_sha,
                    "agent_def": agent_def_id,
                    "manifest": dummy_manifest,
                },
            )
    assert "ck_workflow_transition_hooks_kind" in str(exc_info.value).lower()

    # 4. CHECK constraint: manifest_sha256 not 32 bytes -> rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_hooks ("
                    "  workspace_id, project_id, name, from_state_id, to_state_id,"
                    "  hook_kind, sort_rank, wasm_module_sha256, manifest_sha256"
                    ") VALUES ("
                    "  :ws_id, :proj_id, 'bad-manifest-hook', :from_st, :to_st,"
                    "  'sync_validator', '0|i00004:', :wasm_sha, :manifest"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "from_st": state_todo,
                    "to_st": state_done,
                    "wasm_sha": wasm_sha,
                    "manifest": b"short",
                },
            )
    assert "ck_workflow_transition_hooks_manifest_sha256" in str(exc_info.value).lower()

    # 5. Execution: hop_depth > 3 check constraint (KB-P5-17a test case 7)
    snapshot = hashlib.sha256(b"body").digest()
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_executions ("
                    "  workspace_id, project_id, issue_id, invoking_principal_id,"
                    "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
                    ") VALUES ("
                    "  :ws_id, :proj_id, :issue_id, :p_id,"
                    "  :from_st, :to_st, 'running_sync', 4, :snap"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "issue_id": issue_id,
                    "p_id": admin_p_id,
                    "from_st": state_todo,
                    "to_st": state_done,
                    "snap": snapshot,
                },
            )
    assert (
        "ck_workflow_transition_executions_hop_depth" in str(exc_info.value).lower()
        or "hop_depth" in str(exc_info.value).lower()
    )

    # 6. Execution: unique partial index wte_one_pending
    exec1_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO workflow_transition_executions ("
            "  id, workspace_id, project_id, issue_id, invoking_principal_id,"
            "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :issue_id, :p_id,"
            "  :from_st, :to_st, 'running_sync', 0, :snap"
            ")"
        ),
        {
            "id": exec1_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "issue_id": issue_id,
            "p_id": admin_p_id,
            "from_st": state_todo,
            "to_st": state_done,
            "snap": snapshot,
        },
    )

    # Second concurrent transition while status is 'running_sync' fails unique index wte_one_pending
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_executions ("
                    "  workspace_id, project_id, issue_id, invoking_principal_id,"
                    "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
                    ") VALUES ("
                    "  :ws_id, :proj_id, :issue_id, :p_id,"
                    "  :from_st, :to_st, 'running_sync', 0, :snap"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "issue_id": issue_id,
                    "p_id": admin_p_id,
                    "from_st": state_todo,
                    "to_st": state_done,
                    "snap": snapshot,
                },
            )
    assert "wte_one_pending" in str(exc_info.value).lower()

    # 7. Invocations positive insert + unique constraint (execution_id, hook_id)
    inv_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO workflow_hook_invocations ("
            "  id, workspace_id, execution_id, hook_id, hook_kind, status, duration_us"
            ") VALUES ("
            "  :id, :ws_id, :exec_id, :hook_id, 'sync_validator', 'allowed', 120"
            ")"
        ),
        {"id": inv_id, "ws_id": ws_id, "exec_id": exec1_id, "hook_id": hook_val_id},
    )

    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_hook_invocations ("
                    "  workspace_id, execution_id, hook_id, hook_kind, status, duration_us"
                    ") VALUES ("
                    "  :ws_id, :exec_id, :hook_id, 'sync_validator', 'allowed', 150"
                    ")"
                ),
                {"ws_id": ws_id, "exec_id": exec1_id, "hook_id": hook_val_id},
            )
    assert (
        "uq_workflow_hook_invocations_exec_hook" in str(exc_info.value).lower()
        or "unique constraint" in str(exc_info.value).lower()
    )


@pytest.mark.asyncio
async def test_issues_state_guard_trigger(db_session: AsyncSession) -> None:
    """Verify issues_state_guard trigger raises required guard error (test case 4)."""
    env = await _create_test_env(db_session)
    ws_id = env["workspace_id"]
    proj_id = env["project_id"]
    state_todo = env["state_todo"]
    state_done = env["state_done"]
    issue_id = env["issue_id"]
    admin_p_id = env["admin_principal_id"]

    # Switch session authorization to kanban_app and bind context
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(admin_p_id), "w_id": str(ws_id)},
    )

    # 1. Update summary without changing state_id -> succeeds
    await db_session.execute(
        text("UPDATE issues SET summary = 'Updated summary' WHERE id = :id"),
        {"id": issue_id},
    )

    # 2. Direct UPDATE issues SET state_id=... without app.transition_exec_id
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET state_id = :st WHERE id = :id"),
                {"st": state_done, "id": issue_id},
            )
    assert "STATE_CHANGE_REQUIRES_TRANSITION_ENGINE" in str(exc_info.value)

    # 3. Direct UPDATE with random UUID in app.transition_exec_id
    bogus_exec = uuid.uuid4()
    await db_session.execute(
        text("SELECT set_config('app.transition_exec_id', :val, true)"),
        {"val": str(bogus_exec)},
    )
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET state_id = :st WHERE id = :id"),
                {"st": state_done, "id": issue_id},
            )
    assert "STATE_CHANGE_REQUIRES_TRANSITION_ENGINE" in str(exc_info.value)

    # 4. Legitimate transition with active execution row -> succeeds!
    snapshot = hashlib.sha256(b"body").digest()
    valid_exec_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO workflow_transition_executions ("
            "  id, workspace_id, project_id, issue_id, invoking_principal_id,"
            "  from_state_id, to_state_id, status, hop_depth, issue_body_sha256_snapshot"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :issue_id, :p_id,"
            "  :from_st, :to_st, 'running_sync', 0, :snap"
            ")"
        ),
        {
            "id": valid_exec_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "issue_id": issue_id,
            "p_id": admin_p_id,
            "from_st": state_todo,
            "to_st": state_done,
            "snap": snapshot,
        },
    )

    await db_session.execute(
        text("SELECT set_config('app.transition_exec_id', :val, true)"),
        {"val": str(valid_exec_id)},
    )
    await db_session.execute(
        text("UPDATE issues SET state_id = :st WHERE id = :id"),
        {"st": state_done, "id": issue_id},
    )


@pytest.mark.asyncio
async def test_workflow_hooks_rls_security(db_session: AsyncSession) -> None:
    """Verify RLS policies on hooks, executions, and invocations (test case 9)."""
    env = await _create_test_env(db_session)
    ws_id = env["workspace_id"]
    proj_id = env["project_id"]
    state_todo = env["state_todo"]
    state_done = env["state_done"]
    wasm_sha = env["wasm_sha256"]
    member_p_id = env["member_principal_id"]

    dummy_manifest = hashlib.sha256(b"dummy_manifest").digest()

    # 1. Assert FORCE ROW LEVEL SECURITY on all 3 tables
    for tbl in [
        "workflow_transition_hooks",
        "workflow_transition_executions",
        "workflow_hook_invocations",
    ]:
        res = (
            (
                await db_session.execute(
                    text(
                        "SELECT c.relrowsecurity, c.relforcerowsecurity "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = :tbl"
                    ),
                    {"tbl": tbl},
                )
            )
            .mappings()
            .one()
        )
        assert res["relrowsecurity"] is True, f"{tbl} must have relrowsecurity=true"
        assert res["relforcerowsecurity"] is True, f"{tbl} must have relforcerowsecurity=true"

    # Insert hook under superuser
    hook_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO workflow_transition_hooks ("
            "  id, workspace_id, project_id, name, from_state_id, to_state_id,"
            "  hook_kind, sort_rank, is_enabled, wasm_module_sha256, manifest_sha256"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, 'hook-rls', :from_st, :to_st,"
            "  'sync_validator', '0|i00001:', true, :wasm_sha, :manifest"
            ")"
        ),
        {
            "id": hook_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "from_st": state_todo,
            "to_st": state_done,
            "wasm_sha": wasm_sha,
            "manifest": dummy_manifest,
        },
    )

    # Switch session to kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # Member principal context
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(member_p_id), "w_id": str(ws_id)},
    )

    # Hook is visible because member has VIEW on project
    rows = (
        (await db_session.execute(text("SELECT id FROM workflow_transition_hooks"))).scalars().all()
    )
    assert hook_id in rows

    # Hooks invisible across workspaces
    other_ws = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(member_p_id), "w_id": str(other_ws)},
    )
    rows_other = (
        (await db_session.execute(text("SELECT id FROM workflow_transition_hooks"))).scalars().all()
    )
    assert len(rows_other) == 0

    # Back to valid workspace, MEMBER insert into hooks rejected by WITH CHECK
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(member_p_id), "w_id": str(ws_id)},
    )
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO workflow_transition_hooks ("
                    "  workspace_id, project_id, name, to_state_id,"
                    "  hook_kind, sort_rank, wasm_module_sha256, manifest_sha256"
                    ") VALUES ("
                    "  :ws_id, :proj_id, 'member-hook', :to_st,"
                    "  'sync_validator', '0|i00002:', :wasm_sha, :manifest"
                    ")"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "to_st": state_done,
                    "wasm_sha": wasm_sha,
                    "manifest": dummy_manifest,
                },
            )
    assert (
        "row-level security" in str(exc_info.value).lower()
        or "check" in str(exc_info.value).lower()
    )

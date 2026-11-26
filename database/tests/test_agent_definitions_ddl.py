"""DDL constraints, RLS policies, and runtime validation tests for agent_definitions (KB-P5-16)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_test_spine(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, user, and agent principal for DDL tests."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "DDL WS"},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Test User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    agent_principal_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'AGENT', :ws_id, 'Test Agent Principal', 'ACTIVE')"
        ),
        {"id": agent_principal_id, "ws_id": ws_id},
    )

    return ws_id, u_id, agent_principal_id


@pytest.mark.asyncio
async def test_ddl_constraints_and_boundaries(db_session: AsyncSession) -> None:
    """Test Case 7: Boundary checks on slug, timeout_ms, mcp_allowed_tools, and harness fields."""
    ws_id, _, principal_id = await _create_test_spine(db_session)

    # 1. Positive insert
    agent_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO agent_definitions ("
            "  id, workspace_id, project_id, principal_id, slug, display_name,"
            "  harness_kind, cli_binary_allowlist_id, cli_args_json, timeout_ms"
            ") VALUES ("
            "  :id, :ws_id, NULL, :p_id, 'valid-agent', 'Valid Agent',"
            "  'cli_pipe', 'agy', '[\"-p\"]'::jsonb, 60000"
            ")"
        ),
        {"id": agent_id, "ws_id": ws_id, "p_id": principal_id},
    )

    # 2. Slug too short "a" rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id"
                    ") VALUES (:ws_id, :p_id, 'a', 'Too Short', 'cli_pipe', 'agy')"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    assert "check constraint" in str(exc_info.value).lower()

    # 3. Slug starting with hyphen "-abc" rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id"
                    ") VALUES (:ws_id, :p_id, '-abc', 'Hyphen Start', 'cli_pipe', 'agy')"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    assert "check constraint" in str(exc_info.value).lower()

    # 4. Timeout 999 rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id, timeout_ms"
                    ") VALUES (:ws_id, :p_id, 'timeout-999', 'T999', 'cli_pipe', 'agy', 999)"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    assert "check constraint" in str(exc_info.value).lower()

    # 5. Timeout 600001 rejected (max allowed is 600000 ms = 10 minutes)
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id, timeout_ms"
                    ") VALUES (:ws_id, :p_id, 't-600001', 'T600001', 'cli_pipe', 'agy', 600001)"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    assert "check constraint" in str(exc_info.value).lower()

    # 6. mcp_allowed_tools containing update_ticket rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id, mcp_allowed_tools"
                    ") VALUES ("
                    "  :ws_id, :p_id, 'bad-tool', 'Bad Tool', 'cli_pipe', 'agy', "
                    "  ARRAY['update_ticket']"
                    ")"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    err_str = str(exc_info.value).lower()
    assert "agent_def_mcp_tools_subset" in err_str or "check constraint" in err_str

    # 7. Harness consistency CHECK: in_app_sdk without provider_kind rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, model_id"
                    ") VALUES (:ws_id, :p_id, 'sdk-no-prov', 'SDK No Prov', 'in_app_sdk', 'gpt-4o')"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    err_harness = str(exc_info.value).lower()
    assert "agent_def_harness_fields" in err_harness or "check constraint" in err_harness

    # 8. cli_args_json is array CHECK: non-array object rejected
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id, cli_args_json"
                    ") VALUES ("
                    "  :ws_id, :p_id, 'bad-json', 'Bad JSON', 'cli_pipe', 'agy',"
                    '  \'{"not": "array"}\'::jsonb'
                    ")"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    err_args = str(exc_info.value).lower()
    assert "agent_def_args_is_array" in err_args or "check constraint" in err_args

    # 9. cli_binary_allowlist_id: non-allowlisted binary rejected by DDL CHECK
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id"
                    ") VALUES (:ws_id, :p_id, 'bash-bin', 'Bash Bin', 'cli_pipe', 'bash')"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    assert "check constraint" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_case_6_rls_security_and_non_enumeration(db_session: AsyncSession) -> None:
    """Test Case 6: RLS gate, zero rows without workspace, and WITH CHECK denial."""
    ws_id, user_id, principal_id = await _create_test_spine(db_session)

    # Insert an agent under superuser
    agent_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO agent_definitions ("
            "  id, workspace_id, principal_id, slug, display_name,"
            "  harness_kind, cli_binary_allowlist_id, cli_args_json"
            ") VALUES ("
            "  :id, :ws_id, :p_id, 'secret-agent', 'Secret Agent',"
            "  'cli_pipe', 'agy', '[\"-p\"]'::jsonb"
            ")"
        ),
        {"id": agent_id, "ws_id": ws_id, "p_id": principal_id},
    )

    # Assert FORCE RLS is active on agent_definitions
    table_info = (
        (
            await db_session.execute(
                text(
                    "SELECT c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = 'agent_definitions'"
                )
            )
        )
        .mappings()
        .one()
    )
    assert table_info["relrowsecurity"] is True
    assert table_info["relforcerowsecurity"] is True

    # Switch session to kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Query without app.workspace_id returns 0 rows
    rows_empty = (
        (await db_session.execute(text("SELECT id FROM agent_definitions"))).scalars().all()
    )
    assert len(rows_empty) == 0

    # 2. Query with another workspace returns 0 rows
    other_ws = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(user_id), "w_id": str(other_ws)},
    )
    rows_other = (
        (await db_session.execute(text("SELECT id FROM agent_definitions"))).scalars().all()
    )
    assert len(rows_other) == 0

    # 3. Direct insert as kanban_app with member role (no admin role) -> RLS WITH CHECK 42501
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": str(user_id), "w_id": str(ws_id)},
    )
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO agent_definitions ("
                    "  workspace_id, principal_id, slug, display_name,"
                    "  harness_kind, cli_binary_allowlist_id, cli_args_json"
                    ") VALUES ("
                    "  :ws_id, :p_id, 'direct-insert', 'Direct Insert',"
                    "  'cli_pipe', 'agy', '[\"-p\"]'::jsonb"
                    ")"
                ),
                {"ws_id": ws_id, "p_id": principal_id},
            )
    sqlstate = getattr(exc_info.value.orig, "sqlstate", None)
    assert sqlstate == "42501" or "row-level security" in str(exc_info.value).lower()

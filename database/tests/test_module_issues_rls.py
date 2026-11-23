# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for security_invoker enforcement on module_issues view (KAN-334 / GSF-023)."""
# ruff: noqa: E501, PLR0915, TC002

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSContext, RLSSessionFactory


@pytest.mark.asyncio
async def test_module_issues_view_has_security_invoker(db_session: AsyncSession) -> None:
    """Verify that module_issues view has security_invoker = true option enabled."""
    res = await db_session.execute(
        text(
            """
            SELECT c.relname, c.reloptions
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'module_issues'
            """
        )
    )
    row = res.mappings().first()
    assert row is not None, "module_issues view must exist in public schema"
    reloptions = row["reloptions"] or []
    assert any(
        "security_invoker=true" in opt or "security_invoker=on" in opt for opt in reloptions
    ), f"module_issues must have security_invoker option enabled, got: {reloptions}"


@pytest.mark.asyncio
async def test_module_issues_enforces_rls_isolation(db_session: AsyncSession) -> None:
    """Verify that module_issues view filters rows by tenant workspace under RLS."""
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]

    ws1_id = uuid.uuid4()
    ws2_id = uuid.uuid4()
    p1_id = uuid.uuid4()
    p2_id = uuid.uuid4()

    # 1. Setup two workspaces, projects, modules, issues, and issue_modules
    async with db_session.begin_nested():
        await db_session.execute(text("RESET SESSION AUTHORIZATION"))
        # Workspaces
        await db_session.execute(
            text(
                "INSERT INTO workspaces (id, slug, name) VALUES (:w1, :s1, 'WS1'), (:w2, :s2, 'WS2')"
            ),
            {
                "w1": ws1_id,
                "s1": f"ws-{ws1_id.hex[:10]}",
                "w2": ws2_id,
                "s2": f"ws-{ws2_id.hex[:10]}",
            },
        )
        # Principals & Users
        for ws_id, p_id, name in [(ws1_id, p1_id, "User 1"), (ws2_id, p2_id, "User 2")]:
            await db_session.execute(
                text(
                    "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :name, :p_id, :p_id)"
                ),
                {"ws_id": ws_id, "ckey": f"usr-{p_id.hex[:10]}", "name": name, "p_id": p_id},
            )
            await db_session.execute(
                text(
                    "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:p_id, 'USER', :ws_id, :name, 'ACTIVE')"
                ),
                {"p_id": p_id, "ws_id": ws_id, "name": name},
            )
            await db_session.execute(
                text(
                    "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:p_id, 'user', 'USER', :ws_id, :email)"
                ),
                {"p_id": p_id, "ws_id": ws_id, "email": f"{p_id.hex[:8]}@example.com"},
            )
            await db_session.execute(
                text(
                    "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) VALUES (uuidv7(), :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace')"
                ),
                {"ws_id": ws_id, "p_id": p_id},
            )

        # Projects
        proj_ids: dict[uuid.UUID, uuid.UUID] = {}
        for ws_id, p_id, key in [(ws1_id, p1_id, "PRJ1"), (ws2_id, p2_id, "PRJ2")]:
            p_obj_id = await db_session.scalar(
                text(
                    "SELECT register_object('project'::object_kind, :ws_id, NULL, :ident, :name, :uid)"
                ),
                {"ws_id": ws_id, "ident": key, "name": key, "uid": p_id},
            )
            assert isinstance(p_obj_id, uuid.UUID)
            proj_ids[ws_id] = p_obj_id
            await db_session.execute(
                text(
                    "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) VALUES (:id, :ws_id, :ident, :name, true)"
                ),
                {"id": p_obj_id, "ws_id": ws_id, "ident": key, "name": key},
            )

        # Modules
        mod_ids: dict[uuid.UUID, uuid.UUID] = {}
        for ws_id, p_id in [(ws1_id, p1_id), (ws2_id, p2_id)]:
            proj_id = proj_ids[ws_id]
            m_obj_id = await db_session.scalar(
                text(
                    "SELECT register_object('module'::object_kind, :ws_id, :proj_id, :ckey, 'Mod', :uid)"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "ckey": f"mod-{uuid.uuid4().hex[:10]}",
                    "uid": p_id,
                },
            )
            assert isinstance(m_obj_id, uuid.UUID)
            mod_ids[ws_id] = m_obj_id
            await db_session.execute(
                text(
                    "INSERT INTO modules (id, workspace_id, project_id, name) VALUES (:id, :ws_id, :proj_id, 'Mod')"
                ),
                {"id": m_obj_id, "ws_id": ws_id, "proj_id": proj_id},
            )

        # Issues
        iss_ids: dict[uuid.UUID, uuid.UUID] = {}
        for ws_id, p_id, key in [(ws1_id, p1_id, "PRJ1"), (ws2_id, p2_id, "PRJ2")]:
            proj_id = proj_ids[ws_id]
            seq = await db_session.scalar(
                text("SELECT allocate_issue_sequence(:pid)"),
                {"pid": proj_id},
            )
            state_id = await db_session.scalar(
                text(
                    "SELECT id FROM workflow_states WHERE project_id = :pid AND is_default = true LIMIT 1"
                ),
                {"pid": proj_id},
            )
            prio_id = await db_session.scalar(
                text(
                    "SELECT id FROM project_priorities WHERE project_id = :pid AND is_default = true LIMIT 1"
                ),
                {"pid": proj_id},
            )
            i_id = uuid.uuid4()
            await db_session.execute(
                text(
                    "SELECT register_object('issue'::object_kind, :ws_id, :proj_id, :ckey, 'Iss', :uid, :id)"
                ),
                {
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "ckey": f"{key}-{seq}",
                    "uid": p_id,
                    "id": i_id,
                },
            )
            iss_ids[ws_id] = i_id
            await db_session.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, "
                    "  description_markdown, state_id, priority_id, created_by_id, "
                    "  original_created_by_id, board_rank"
                    ") VALUES ("
                    "  :id, :ws_id, :proj_id, :seq, 'Iss', "
                    "  'Issue body', :sid, :prid, :cb, :cb, '0|hzzzzz:'"
                    ")"
                ),
                {
                    "id": i_id,
                    "ws_id": ws_id,
                    "proj_id": proj_id,
                    "seq": seq,
                    "cb": p_id,
                    "sid": state_id,
                    "prid": prio_id,
                },
            )

        # Issue modules join
        iss1_id = iss_ids[ws1_id]
        iss2_id = iss_ids[ws2_id]
        mod1_id = mod_ids[ws1_id]
        mod2_id = mod_ids[ws2_id]
        await db_session.execute(
            text(
                "INSERT INTO issue_modules (issue_id, module_id, workspace_id) VALUES (:i1, :m1, :w1), (:i2, :m2, :w2)"
            ),
            {
                "i1": iss1_id,
                "m1": mod1_id,
                "w1": ws1_id,
                "i2": iss2_id,
                "m2": mod2_id,
                "w2": ws2_id,
            },
        )
        await db_session.execute(text("SET SESSION AUTHORIZATION kanban_app"))

    # 2. Query module_issues under Workspace 1 context
    ctx1 = RLSContext(principal_id=p1_id, workspace_id=ws1_id)
    async with factory.session(ctx1) as sess1:
        res1 = await sess1.execute(
            text("SELECT module_id, issue_id, workspace_id FROM module_issues")
        )
        rows1 = res1.mappings().fetchall()
        assert len(rows1) == 1
        assert rows1[0]["workspace_id"] == ws1_id
        assert rows1[0]["issue_id"] == iss1_id
        assert rows1[0]["module_id"] == mod1_id

    # 3. Query module_issues under Workspace 2 context
    ctx2 = RLSContext(principal_id=p2_id, workspace_id=ws2_id)
    async with factory.session(ctx2) as sess2:
        res2 = await sess2.execute(
            text("SELECT module_id, issue_id, workspace_id FROM module_issues")
        )
        rows2 = res2.mappings().fetchall()
        assert len(rows2) == 1
        assert rows2[0]["workspace_id"] == ws2_id
        assert rows2[0]["issue_id"] == iss2_id
        assert rows2[0]["module_id"] == mod2_id

    # 4. Fail-closed: Unrelated workspace sees 0 rows
    ctx_unrelated = RLSContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    async with factory.session(ctx_unrelated) as sess_unrelated:
        res_null = await sess_unrelated.execute(text("SELECT count(*) FROM module_issues"))
        assert res_null.scalar_one() == 0

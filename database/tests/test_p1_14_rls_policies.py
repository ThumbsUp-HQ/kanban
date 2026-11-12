"""Comprehensive feature unit tests for Phase 1 FORCE ROW LEVEL SECURITY policies.

Covers:
1. Zero-context fail-closed (0 rows across every tenant table)
2. Cross-workspace & cross-project isolation
3. Write WITH CHECK enforcement (VIEWER comments, updates/inserts fail)
4. Explicit-deny & link boundary (DENY VIEW hides; far link endpoint masked)
5. Direct partition query blocked & read-only enforcement
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALL_TENANT_TABLES = [
    "workspaces",
    "principals",
    "users",
    "groups",
    "principal_group_edges",
    "principal_group_closure",
    "objects",
    "projects",
    "workflow_states",
    "project_priorities",
    "project_labels",
    "project_module_defaults",
    "issues",
    "cycles",
    "modules",
    "issue_modules",
    "issue_assignees",
    "issue_labels",
    "issue_subscriptions",
    "issue_comments",
    "docs",
    "pages",
    "page_versions",
    "stickies",
    "views",
    "object_links",
    "role_bindings",
    "resource_acl_entries",
    "effective_resource_access",
    "activity_records",
    "activity_chain_heads",
]


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Register and insert a workspace."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_user(
    session: AsyncSession,
    ws_id: uuid.UUID,
    display_name: str = "Test User",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Register and insert a user and principal."""
    u_id = uuid.uuid4()
    p_id = await session.scalar(
        text(
            "SELECT register_object(  'user'::object_kind, :ws_id, NULL, :ckey, :name, :uid, :id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex[:8]}",
            "name": display_name,
            "uid": u_id,
            "id": u_id,
        },
    )
    assert p_id == u_id

    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', :name)"
        ),
        {"id": u_id, "ws_id": ws_id, "name": display_name},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": u_id, "ws_id": ws_id, "email": f"{u_id.hex[:8]}@example.com"},
    )
    return u_id, u_id


async def _create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    user_id: uuid.UUID,
    identifier: str = "PRJ",
    name: str = "Test Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register and insert a project with default state and priority."""
    proj_id = await session.scalar(
        text("SELECT register_object('project'::object_kind, :ws_id, NULL, :ident, :name, :uid)"),
        {"ws_id": ws_id, "ident": identifier, "name": name, "uid": user_id},
    )
    assert isinstance(proj_id, uuid.UUID)

    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, :name)"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": identifier, "name": name},
    )

    state_id = await session.scalar(
        text(
            "SELECT id FROM workflow_states WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )
    assert isinstance(state_id, uuid.UUID)

    prio_id = await session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": proj_id},
    )
    assert isinstance(prio_id, uuid.UUID)

    return proj_id, state_id, prio_id


async def _create_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    user_id: uuid.UUID,
    state_id: uuid.UUID,
    prio_id: uuid.UUID,
    summary: str = "Test Issue",
) -> uuid.UUID:
    """Register and create an issue under a project."""
    seq = await session.scalar(
        text("SELECT allocate_issue_sequence(:pid)"),
        {"pid": proj_id},
    )
    assert isinstance(seq, int)

    p_ident = await session.scalar(
        text("SELECT identifier FROM projects WHERE id = :id"),
        {"id": proj_id},
    )
    ckey = f"{p_ident}-{seq}"

    iss_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws_id, :pid, :ckey, :summary, :uid, :id)"
        ),
        {
            "ws_id": ws_id,
            "pid": proj_id,
            "ckey": ckey,
            "summary": summary,
            "uid": user_id,
            "id": iss_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, created_by_id, "
            "  original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws_id, :pid, :seq, :summary, "
            "  'Issue body', :state_id, :prio_id, :uid, :uid, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": iss_id,
            "ws_id": ws_id,
            "pid": proj_id,
            "seq": seq,
            "summary": summary,
            "state_id": state_id,
            "prio_id": prio_id,
            "uid": user_id,
        },
    )
    return iss_id


async def _seed_two_workspaces(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed two full workspaces with projects, issues, comments, docs, pages, views, stickies."""
    # 1. WS1
    ws1 = await _create_workspace(db_session, name="Workspace 1")
    u_ws1, _ = await _create_user(db_session, ws1, display_name="User WS1")
    p_kan, st_kan, pr_kan = await _create_project(
        db_session, ws1, u_ws1, identifier="KAN", name="Kanban Core"
    )
    p_sec, st_sec, pr_sec = await _create_project(
        db_session, ws1, u_ws1, identifier="SEC", name="Security Ops"
    )

    kan_1 = await _create_issue(
        db_session, ws1, p_kan, u_ws1, st_kan, pr_kan, summary="KAN Core Issue 1"
    )
    kan_2 = await _create_issue(
        db_session, ws1, p_kan, u_ws1, st_kan, pr_kan, summary="KAN Core Issue 2"
    )
    sec_1 = await _create_issue(
        db_session, ws1, p_sec, u_ws1, st_sec, pr_sec, summary="SEC Secret Issue 1"
    )

    # Comment on KAN-1 and KAN-2
    comm_1 = await db_session.scalar(
        text(
            "INSERT INTO issue_comments (issue_id, author_id, workspace_id, body_markdown) "
            "VALUES (:iid, :uid, :ws, 'Comment on KAN-1') RETURNING id"
        ),
        {"iid": kan_1, "uid": u_ws1, "ws": ws1},
    )
    assert isinstance(comm_1, uuid.UUID)

    comm_2 = await db_session.scalar(
        text(
            "INSERT INTO issue_comments (issue_id, author_id, workspace_id, body_markdown) "
            "VALUES (:iid, :uid, :ws, 'Comment on KAN-2') RETURNING id"
        ),
        {"iid": kan_2, "uid": u_ws1, "ws": ws1},
    )
    assert isinstance(comm_2, uuid.UUID)

    # Doc and Page in WS1
    doc_1 = uuid.uuid4()
    doc_title = "KAN Architecture"
    await db_session.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :pid, :ckey, :title, :uid, :id)"),
        {
            "ws": ws1,
            "pid": p_kan,
            "ckey": f"doc-{doc_1.hex[:8]}",
            "title": doc_title,
            "uid": u_ws1,
            "id": doc_1,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
            "VALUES (:id, :ws, :pid, :title, 'Markdown documentation')"
        ),
        {"id": doc_1, "ws": ws1, "pid": p_kan, "title": doc_title},
    )

    page_1 = uuid.uuid4()
    page_title = "Overview Page"
    await db_session.execute(
        text("SELECT register_object('page'::object_kind, :ws, :pid, :ckey, :title, :uid, :id)"),
        {
            "ws": ws1,
            "pid": p_kan,
            "ckey": f"page-{page_1.hex[:8]}",
            "title": page_title,
            "uid": u_ws1,
            "id": page_1,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO pages (id, workspace_id, doc_id, parent_page_id, title, body_markdown) "
            "VALUES (:id, :ws, :doc, NULL, :title, 'Page body')"
        ),
        {"id": page_1, "ws": ws1, "doc": doc_1, "title": page_title},
    )

    # Sticky in WS1
    stk_1 = uuid.uuid4()
    await db_session.execute(
        text("SELECT register_object('sticky'::object_kind, :ws, :pid, :ckey, 'Idea', :uid, :id)"),
        {"ws": ws1, "pid": p_kan, "ckey": f"stk-{stk_1.hex[:8]}", "uid": u_ws1, "id": stk_1},
    )
    await db_session.execute(
        text(
            "INSERT INTO stickies (id, workspace_id, project_id, body_markdown, color_token) "
            "VALUES (:id, :ws, :pid, 'Scratch idea', 'amber')"
        ),
        {"id": stk_1, "ws": ws1, "pid": p_kan},
    )

    # View in WS1
    view_1 = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object(  'view'::object_kind, :ws, :pid, :k, 'Sprint View', :uid, :id)"
        ),
        {"ws": ws1, "pid": p_kan, "k": f"view-{view_1.hex[:8]}", "uid": u_ws1, "id": view_1},
    )
    await db_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, visibility, "
            "  name, layout, filters_json, wip_limits_json"
            ") VALUES ("
            "  :id, :ws, :pid, :uid, 'workspace', 'Sprint View', 'board', "
            "  '{}'::jsonb, '{}'::jsonb"
            ")"
        ),
        {"id": view_1, "ws": ws1, "pid": p_kan, "uid": u_ws1},
    )

    # Object Link in WS1: KAN-1 -> BLOCKS -> SEC-1
    link_1 = await db_session.scalar(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws, :src, 'issue', :tgt, 'issue', 'BLOCKS', 'KAN-1', 'SEC-1', :uid"
            ") RETURNING id"
        ),
        {"ws": ws1, "src": kan_1, "tgt": sec_1, "uid": u_ws1},
    )
    assert isinstance(link_1, uuid.UUID)

    # Activity Record in WS1
    act_1 = await db_session.scalar(
        text(
            "SELECT append_activity("
            "  :ws, :obj_id, 'issue'::object_kind, :actor, 'ISSUE_CREATED', '{\"k\": 1}'::jsonb"
            ")"
        ),
        {"ws": ws1, "obj_id": kan_1, "actor": u_ws1},
    )
    assert isinstance(act_1, uuid.UUID)

    # 2. WS2
    ws2 = await _create_workspace(db_session, name="Workspace 2")
    u_ws2, _ = await _create_user(db_session, ws2, display_name="User WS2")
    p_oth, st_oth, pr_oth = await _create_project(
        db_session, ws2, u_ws2, identifier="OTH", name="Other Project"
    )
    oth_1 = await _create_issue(
        db_session, ws2, p_oth, u_ws2, st_oth, pr_oth, summary="Other Issue 1"
    )

    # Refresh effective access for both workspaces
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws1}
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws2}
    )

    return {
        "ws1": ws1,
        "ws2": ws2,
        "u_ws1": u_ws1,
        "u_ws2": u_ws2,
        "p_kan": p_kan,
        "p_sec": p_sec,
        "p_oth": p_oth,
        "kan_1": kan_1,
        "kan_2": kan_2,
        "sec_1": sec_1,
        "oth_1": oth_1,
        "doc_1": doc_1,
        "page_1": page_1,
        "stk_1": stk_1,
        "view_1": view_1,
        "link_1": link_1,
        "act_1": act_1,
    }


# ==============================================================================
# TEST CASE 1: Zero-Context Fail-Closed (kanban_app & app_rls_reader)
# ==============================================================================
@pytest.mark.asyncio
async def test_01_zero_context_fail_closed(db_session: AsyncSession) -> None:
    """Test Case 1: kanban_app & app_rls_reader return 0 rows across EVERY table without context."""
    await _seed_two_workspaces(db_session)

    # Query all public tables except exempt catalog tables
    tbl_rows = await db_session.execute(
        text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
            "  AND c.relname NOT IN ("
            "    'alembic_version', 'link_type_matrix', 'auth_provider_cards', "
            "    'rate_limit_buckets', 'local_admin_credentials', 'sessions'"
            "  ) "
            "ORDER BY c.relname"
        )
    )
    tables_to_check = [r[0] for r in tbl_rows.all()]
    assert len(tables_to_check) >= len(ALL_TENANT_TABLES)

    # 1. Test as kanban_app with UNSET context
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # Unset context check
    for tbl in tables_to_check:
        cnt = await db_session.scalar(text(f"SELECT count(*) FROM {tbl}"))  # noqa: S608
        assert cnt == 0, f"Expected 0 rows for kanban_app on {tbl} with unset context, got {cnt}"

    # 2. Test as kanban_app with explicitly empty context
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', '', true), "
            "set_config('app.workspace_id', '', true)"
        )
    )
    for tbl in tables_to_check:
        cnt = await db_session.scalar(text(f"SELECT count(*) FROM {tbl}"))  # noqa: S608
        assert cnt == 0, f"Expected 0 rows for kanban_app on {tbl} with empty context, got {cnt}"

    # 3. Test as app_rls_reader with UNSET context
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION app_rls_reader"))
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', '', true), "
            "set_config('app.workspace_id', '', true)"
        )
    )
    for tbl in tables_to_check:
        cnt = await db_session.scalar(text(f"SELECT count(*) FROM {tbl}"))  # noqa: S608
        assert cnt == 0, (
            f"Expected 0 rows for app_rls_reader on {tbl} with unset context, got {cnt}"
        )

    # Reset authorization back to superuser
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))


# ==============================================================================
# TEST CASE 2: Cross-Workspace & Cross-Project Isolation
# ==============================================================================
@pytest.mark.asyncio
async def test_02_cross_workspace_and_project_isolation(db_session: AsyncSession) -> None:
    """Test Case 2: U_ws1 bound to KAN sees only KAN/WS1 rows and 0 rows from SEC or WS2."""
    seed = await _seed_two_workspaces(db_session)
    ws1 = seed["ws1"]
    u_ws1 = seed["u_ws1"]
    p_kan = seed["p_kan"]
    p_sec = seed["p_sec"]
    p_oth = seed["p_oth"]

    # Bind U_ws1 as MEMBER on project KAN
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws1, "p": u_ws1, "proj": p_kan},
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws1}
    )

    # Switch to kanban_app and bind context to (U_ws1, WS1)
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    # 1. Projects: KAN is visible, SEC and OTH return 0 rows
    kan_p = await db_session.scalar(
        text("SELECT count(*) FROM projects WHERE id = :id"), {"id": p_kan}
    )
    assert kan_p == 1
    sec_p = await db_session.scalar(
        text("SELECT count(*) FROM projects WHERE id = :id"), {"id": p_sec}
    )
    assert sec_p == 0
    oth_p = await db_session.scalar(
        text("SELECT count(*) FROM projects WHERE id = :id"), {"id": p_oth}
    )
    assert oth_p == 0

    # 2. Issues: KAN-1 and KAN-2 visible; SEC-1 and OTH-1 return 0 rows
    vis_issues = (await db_session.execute(text("SELECT id FROM issues"))).scalars().all()
    assert set(vis_issues) == {seed["kan_1"], seed["kan_2"]}

    # 3. Objects: KAN entities visible, SEC and OTH entities not in objects
    kan_obj = await db_session.scalar(
        text("SELECT count(*) FROM objects WHERE id = :id"), {"id": seed["kan_1"]}
    )
    assert kan_obj == 1
    sec_obj = await db_session.scalar(
        text("SELECT count(*) FROM objects WHERE id = :id"), {"id": seed["sec_1"]}
    )
    assert sec_obj == 0
    oth_obj = await db_session.scalar(
        text("SELECT count(*) FROM objects WHERE id = :id"), {"id": seed["oth_1"]}
    )
    assert oth_obj == 0

    # 4. Docs, Stickies, Views, Issue Comments, Activity Records
    vis_docs = (await db_session.execute(text("SELECT id FROM docs"))).scalars().all()
    assert set(vis_docs) == {seed["doc_1"]}

    vis_stickies = (await db_session.execute(text("SELECT id FROM stickies"))).scalars().all()
    assert set(vis_stickies) == {seed["stk_1"]}

    vis_views = (await db_session.execute(text("SELECT id FROM views"))).scalars().all()
    assert set(vis_views) == {seed["view_1"]}

    vis_comments = (await db_session.execute(text("SELECT id FROM issue_comments"))).scalars().all()
    # Both comments are on KAN issues
    assert len(vis_comments) == 2

    vis_acts = (await db_session.execute(text("SELECT id FROM activity_records"))).scalars().all()
    assert set(vis_acts) == {seed["act_1"]}

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))


# ==============================================================================
# TEST CASE 3: Write WITH CHECK Enforcement
# ==============================================================================
@pytest.mark.asyncio
async def test_03_write_with_check_enforcement(db_session: AsyncSession) -> None:
    """Test Case 3: As VIEWER (mask=3), comments succeed, updates/inserts fail with 42501."""
    seed = await _seed_two_workspaces(db_session)
    ws1 = seed["ws1"]
    ws2 = seed["ws2"]
    u_ws1 = seed["u_ws1"]
    p_kan = seed["p_kan"]
    p_oth = seed["p_oth"]
    kan_1 = seed["kan_1"]

    # Bind U_ws1 with role VIEWER (mask = 3 => VIEW=1 | COMMENT=2) on project KAN
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'VIEWER', 'project', :proj)"
        ),
        {"ws": ws1, "p": u_ws1, "proj": p_kan},
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws1}
    )

    # Switch to kanban_app and bind context
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    # 1. INSERT comment succeeds (COMMENT capability bit 2)
    comm_res = await db_session.execute(
        text(
            "INSERT INTO issue_comments (issue_id, author_id, workspace_id, body_markdown) "
            "VALUES (:iid, :uid, :ws, 'Viewer comment') RETURNING id"
        ),
        {"iid": kan_1, "uid": u_ws1, "ws": ws1},
    )
    comm_id = comm_res.scalar_one()
    assert isinstance(comm_id, uuid.UUID)

    # 2. UPDATE issues SET summary fails with 42501 (requires EDIT=4 or TRANSITION=8)
    sp1 = await db_session.begin_nested()
    with pytest.raises(DBAPIError) as exc1:
        await db_session.execute(
            text("UPDATE issues SET summary = 'Malicious update' WHERE id = :id"),
            {"id": kan_1},
        )
    assert exc1.value.orig is not None
    assert getattr(exc1.value.orig, "sqlstate", None) == "42501"
    await sp1.rollback()

    # 3. INSERT INTO issues fails with 42501 (requires EDIT=4 on project)
    # Pre-allocate valid sequence and spine object in maintenance mode
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    seq3 = await db_session.scalar(text("SELECT allocate_issue_sequence(:pid)"), {"pid": p_kan})
    iss3_id = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws, :pid, :ckey, 'Unauthorized Issue', :uid, :id"
            ")"
        ),
        {"ws": ws1, "pid": p_kan, "ckey": f"KAN-{seq3}", "uid": u_ws1, "id": iss3_id},
    )

    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    sp2 = await db_session.begin_nested()
    with pytest.raises(DBAPIError) as exc2:
        await db_session.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, "
                "  description_markdown, state_id, priority_id, created_by_id, "
                "  original_created_by_id, board_rank"
                ") VALUES ("
                "  :id, :ws, :pid, :seq, 'Unauthorized Issue', 'desc', "
                "  (SELECT id FROM workflow_states "
                "   WHERE project_id = :pid AND is_default = true LIMIT 1), "
                "  (SELECT id FROM project_priorities "
                "   WHERE project_id = :pid AND is_default = true LIMIT 1), "
                "  :uid, :uid, '0|hzzzzz:'"
                ")"
            ),
            {"id": iss3_id, "ws": ws1, "pid": p_kan, "seq": seq3, "uid": u_ws1},
        )
    assert exc2.value.orig is not None
    assert getattr(exc2.value.orig, "sqlstate", None) == "42501"
    await sp2.rollback()

    # 4. Attempting to INSERT an issue with workspace_id = WS2 while bound to WS1 raises 42501
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    seq4 = await db_session.scalar(text("SELECT allocate_issue_sequence(:pid)"), {"pid": p_oth})
    state_oth = await db_session.scalar(
        text(
            "SELECT id FROM workflow_states WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": p_oth},
    )
    prio_oth = await db_session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :pid AND is_default = true LIMIT 1"
        ),
        {"pid": p_oth},
    )
    iss4_id = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws, :pid, :ckey, 'Cross-Workspace Issue', :uid, :id"
            ")"
        ),
        {"ws": ws2, "pid": p_oth, "ckey": f"OTH-{seq4}", "uid": u_ws1, "id": iss4_id},
    )

    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    sp3 = await db_session.begin_nested()
    with pytest.raises(DBAPIError) as exc3:
        await db_session.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, "
                "  description_markdown, state_id, priority_id, created_by_id, "
                "  original_created_by_id, board_rank"
                ") VALUES ("
                "  :id, :ws2, :pid, :seq, 'Cross-Workspace Issue', "
                "  'desc', :state_id, :prio_id, "
                "  :uid, :uid, '0|hzzzzz:'"
                ")"
            ),
            {
                "id": iss4_id,
                "ws2": ws2,
                "pid": p_oth,
                "seq": seq4,
                "state_id": state_oth,
                "prio_id": prio_oth,
                "uid": u_ws1,
            },
        )
    assert exc3.value.orig is not None
    assert getattr(exc3.value.orig, "sqlstate", None) == "42501"
    await sp3.rollback()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))


# ==============================================================================
# TEST CASE 4: Explicit-Deny & Link Boundary
# ==============================================================================
@pytest.mark.asyncio
async def test_04_explicit_deny_and_link_boundary(db_session: AsyncSession) -> None:
    """Test Case 4: DENY VIEW hides issue; object_links visible but far endpoint masked."""
    seed = await _seed_two_workspaces(db_session)
    ws1 = seed["ws1"]
    u_ws1 = seed["u_ws1"]
    p_kan = seed["p_kan"]
    kan_1 = seed["kan_1"]
    kan_2 = seed["kan_2"]
    sec_1 = seed["sec_1"]

    # 1. Grant MEMBER on project KAN
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws1, "p": u_ws1, "proj": p_kan},
    )

    # 2. Add explicit DENY VIEW on KAN-2
    await db_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws, :obj, :p, 'DENY', 1)"
        ),
        {"ws": ws1, "obj": kan_2, "p": u_ws1},
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws1}
    )

    # Switch to kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    # KAN-1 is visible, KAN-2 is hidden by explicit DENY
    vis_issues = (await db_session.execute(text("SELECT id FROM issues"))).scalars().all()
    assert kan_1 in vis_issues
    assert kan_2 not in vis_issues

    # Comments on KAN-2 are also hidden
    vis_comments = (
        (
            await db_session.execute(
                text("SELECT id FROM issue_comments WHERE issue_id = :id"),
                {"id": kan_2},
            )
        )
        .scalars()
        .all()
    )
    assert len(vis_comments) == 0

    # 3. Link boundary test: object_links row KAN-1 -> BLOCKS -> SEC-1
    # Visible in object_links because user has VIEW on KAN-1 (source_id)
    links = (
        (
            await db_session.execute(
                text("SELECT id, source_id, target_id FROM object_links WHERE source_id = :src"),
                {"src": kan_1},
            )
        )
        .mappings()
        .all()
    )
    assert len(links) == 1
    assert links[0]["target_id"] == sec_1

    # But querying objects for sec_1 returns 0 rows (far endpoint masked)
    sec_obj_cnt = await db_session.scalar(
        text("SELECT count(*) FROM objects WHERE id = :id"),
        {"id": sec_1},
    )
    assert sec_obj_cnt == 0

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))


# ==============================================================================
# TEST CASE 5: Direct Partition Query Blocked & Read-Only Enforcement
# ==============================================================================
@pytest.mark.asyncio
async def test_05_partition_blocked_and_readonly_reader(db_session: AsyncSession) -> None:
    """Test Case 5: Direct child partition blocked on kanban_app; app_rls_reader read-only."""
    seed = await _seed_two_workspaces(db_session)
    ws1 = seed["ws1"]
    u_ws1 = seed["u_ws1"]
    p_kan = seed["p_kan"]

    # Bind U_ws1 on KAN
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws1, "p": u_ws1, "proj": p_kan},
    )
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws1}
    )

    # Identify a partition table name
    part_row = await db_session.scalar(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE 'activity_records_y%' LIMIT 1"
        )
    )
    assert part_row is not None
    part_name = str(part_row)

    # 1. As kanban_app bound to U_ws1:
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, u_ws1, ws1)

    # Querying parent activity_records returns KAN activity rows
    parent_cnt = await db_session.scalar(text("SELECT count(*) FROM activity_records"))
    assert parent_cnt >= 1

    # Direct query to child partition returns 0 rows (default-deny due to zero policies)
    child_cnt = await db_session.scalar(text(f"SELECT count(*) FROM {part_name}"))  # noqa: S608
    assert child_cnt == 0

    # 2. Switch to app_rls_reader: verify read-only enforcement
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION app_rls_reader"))
    await bind_ctx(db_session, u_ws1, ws1)

    # SELECT on activity_records works
    reader_parent_cnt = await db_session.scalar(text("SELECT count(*) FROM activity_records"))
    assert reader_parent_cnt >= 1

    # INSERT on any table raises 42501 or 25006
    sp = await db_session.begin_nested()
    with pytest.raises((DBAPIError, ProgrammingError)) as exc_w:
        await db_session.execute(
            text(
                "INSERT INTO issue_comments (issue_id, author_id, workspace_id, body_markdown) "
                "VALUES (:iid, :uid, :ws, 'Read only test')"
            ),
            {"iid": seed["kan_1"], "uid": u_ws1, "ws": ws1},
        )
    sqlstate = getattr(exc_w.value.orig, "sqlstate", None) if exc_w.value.orig else None
    assert sqlstate in ("42501", "25006")
    await sp.rollback()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))

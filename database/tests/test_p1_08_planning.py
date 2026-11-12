"""Unit tests for Phase 1 cycles, modules, and planning join tables (KB-P1-08)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _get_sqlstate(exc: BaseException) -> str:
    """Extract PostgreSQL SQLSTATE code from SQLAlchemy DBAPIError/IntegrityError."""
    orig = getattr(exc, "orig", None)
    return str(getattr(orig, "sqlstate", None) or "")


@dataclass
class PlanContext:
    """Workspace, user, and project context for planning tests."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    identifier: str
    state_id: uuid.UUID
    priority_id: uuid.UUID


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Planning Workspace",
) -> uuid.UUID:
    """Create a workspace and return its UUID."""
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
    workspace_id: uuid.UUID,
    email: str,
    display_name: str = "Test User",
) -> uuid.UUID:
    """Create a user in principals, objects, and users tables."""
    u_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws_id, :name)"
        ),
        {"id": u_id, "ws_id": workspace_id, "name": display_name},
    )
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL::uuid, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws_id": workspace_id,
            "ckey": f"usr-{u_id.hex[:8]}",
            "title": display_name,
            "creator": u_id,
            "id": u_id,
        },
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": u_id, "ws_id": workspace_id, "email": email},
    )
    return u_id


async def _create_agent(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    display_name: str = "Test Agent",
) -> uuid.UUID:
    """Create an AGENT principal in principals table."""
    a_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'AGENT', :ws_id, :name)"
        ),
        {"id": a_id, "ws_id": workspace_id, "name": display_name},
    )
    return a_id


async def _create_group(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    name: str = "Test Group",
) -> uuid.UUID:
    """Create a GROUP principal in principals and groups tables."""
    g_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'GROUP', :ws_id, :name)"
        ),
        {"id": g_id, "ws_id": workspace_id, "name": name},
    )
    await session.execute(
        text("INSERT INTO groups (id, workspace_id, name) VALUES (:id, :ws_id, :name)"),
        {"id": g_id, "ws_id": workspace_id, "name": name},
    )
    return g_id


async def _create_project(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    *,
    identifier: str = "PLAN",
    name: str = "Planning Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a project and return (project_id, default_state_id, default_priority_id)."""
    p_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, :ident, :name, :creator, :id"
            ")"
        ),
        {
            "ws": workspace_id,
            "ident": identifier,
            "name": name,
            "creator": creator_id,
            "id": p_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, :name)"
        ),
        {
            "id": p_id,
            "ws": workspace_id,
            "ident": identifier,
            "name": name,
        },
    )

    state_row = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    state_id = state_row.scalar_one()

    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    prio_id = prio_row.scalar_one()

    return p_id, state_id, prio_id


async def _setup_context(
    session: AsyncSession,
    *,
    identifier: str = "PLAN",
    modules_enabled: bool = False,
) -> PlanContext:
    """Set up workspace, user, and project context."""
    ws_id = await _create_workspace(session)
    u_id = await _create_user(session, ws_id, f"lead-{uuid.uuid4().hex[:6]}@example.com")
    p_id, s_id, prio_id = await _create_project(session, ws_id, u_id, identifier=identifier)
    if modules_enabled:
        await session.execute(
            text("UPDATE projects SET modules_enabled = true WHERE id = :id"),
            {"id": p_id},
        )
    return PlanContext(
        workspace_id=ws_id,
        project_id=p_id,
        user_id=u_id,
        identifier=identifier,
        state_id=s_id,
        priority_id=prio_id,
    )


async def _create_cycle(
    session: AsyncSession,
    ctx: PlanContext,
    *,
    name: str = "Sprint 1",
    status: str = "upcoming",
    dates: tuple[date | None, date | None] | None = None,
) -> uuid.UUID:
    """Register cycle object and insert cycle row."""
    c_id = uuid.uuid4()
    sdate = dates[0] if dates else None
    edate = dates[1] if dates else None
    await session.execute(
        text(
            "SELECT register_object("
            "  'cycle'::object_kind, :ws, :proj, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "ckey": f"cycle-{c_id.hex[:12]}",
            "title": name,
            "creator": ctx.user_id,
            "id": c_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO cycles (id, workspace_id, project_id, name, status, start_date, end_date) "
            "VALUES (:id, :ws, :proj, :name, :status, :sdate, :edate)"
        ),
        {
            "id": c_id,
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "name": name,
            "status": status,
            "sdate": sdate,
            "edate": edate,
        },
    )
    return c_id


async def _create_module(
    session: AsyncSession,
    ctx: PlanContext,
    *,
    name: str = "Auth Module",
    dates: tuple[date | None, date | None] | None = None,
) -> uuid.UUID:
    """Register module object and insert module row."""
    m_id = uuid.uuid4()
    sdate = dates[0] if dates else None
    tdate = dates[1] if dates else None
    await session.execute(
        text(
            "SELECT register_object("
            "  'module'::object_kind, :ws, :proj, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "ckey": f"mod-{m_id.hex[:12]}",
            "title": name,
            "creator": ctx.user_id,
            "id": m_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO modules (id, workspace_id, project_id, name, start_date, target_date) "
            "VALUES (:id, :ws, :proj, :name, :sdate, :tdate)"
        ),
        {
            "id": m_id,
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "name": name,
            "sdate": sdate,
            "tdate": tdate,
        },
    )
    return m_id


async def _create_issue(
    session: AsyncSession,
    ctx: PlanContext,
    summary: str = "Test Issue",
    cycle_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create an issue within ctx."""
    seq_row = await session.execute(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": ctx.project_id},
    )
    seq = seq_row.scalar_one()
    i_id = uuid.uuid4()
    canonical_key = f"{ctx.identifier}-{seq}"

    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :p, :ckey, :summary, :user, :id)"),
        {
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "ckey": canonical_key,
            "summary": summary,
            "user": ctx.user_id,
            "id": i_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, state_id, priority_id,"
            "  created_by_id, original_created_by_id, cycle_id, board_rank"
            ") VALUES ("
            "  :id, :ws, :proj, :seq, :summary, :state, :prio, :user, :user, :cycle, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": i_id,
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "seq": seq,
            "summary": summary,
            "state": ctx.state_id,
            "prio": ctx.priority_id,
            "user": ctx.user_id,
            "cycle": cycle_id,
        },
    )
    return i_id


# -----------------------------------------------------------------------------
# Case 1: Positive: Issue assigned to cycle; deleting cycle sets cycle_id to NULL
# -----------------------------------------------------------------------------
async def test_case_1_cycle_delete_sets_null(db_session: AsyncSession) -> None:
    """Deleting a cycle sets issues.cycle_id to NULL via ON DELETE SET NULL."""
    ctx = await _setup_context(db_session)
    c_id = await _create_cycle(db_session, ctx, name="Sprint Alpha")
    i_id = await _create_issue(db_session, ctx, summary="Issue in Alpha", cycle_id=c_id)

    # Verify assigned
    row = await db_session.execute(text("SELECT cycle_id FROM issues WHERE id = :id"), {"id": i_id})
    assert row.scalar_one() == c_id

    # Delete cycle
    await db_session.execute(text("DELETE FROM cycles WHERE id = :id"), {"id": c_id})

    # Verify cycle_id became NULL
    row_after = await db_session.execute(
        text("SELECT cycle_id FROM issues WHERE id = :id"), {"id": i_id}
    )
    assert row_after.scalar_one() is None


# -----------------------------------------------------------------------------
# Case 2: Positive: Module defaults auto-applied; creator & assignee autosubscribed
# -----------------------------------------------------------------------------
async def test_case_2_module_defaults_and_autosubscribe(db_session: AsyncSession) -> None:
    """When modules_enabled=TRUE and defaults exist, new issues get modules and subscriptions."""
    ctx = await _setup_context(db_session, modules_enabled=True)

    # Create 2 modules
    mod1 = await _create_module(db_session, ctx, name="Core Module")
    mod2 = await _create_module(db_session, ctx, name="Billing Module")

    # Add both as project defaults
    await db_session.execute(
        text(
            "INSERT INTO project_module_defaults (project_id, module_id, workspace_id) "
            "VALUES (:p, :m1, :w), (:p, :m2, :w)"
        ),
        {"p": ctx.project_id, "m1": mod1, "m2": mod2, "w": ctx.workspace_id},
    )

    # Create an issue
    i_id = await _create_issue(db_session, ctx, summary="Planned work")

    # Assert exactly 2 issue_modules rows created
    mod_rows = await db_session.execute(
        text("SELECT module_id FROM issue_modules WHERE issue_id = :id ORDER BY module_id"),
        {"id": i_id},
    )
    assigned_mods = {r[0] for r in mod_rows.fetchall()}
    assert assigned_mods == {mod1, mod2}

    # Assert creator auto-subscribed
    sub_rows = await db_session.execute(
        text("SELECT principal_id, source FROM issue_subscriptions WHERE issue_id = :id"),
        {"id": i_id},
    )
    subs = {r[0]: r[1] for r in sub_rows.fetchall()}
    assert ctx.user_id in subs
    assert subs[ctx.user_id] == "CREATOR"

    # Create assignee user and assign
    assignee_id = await _create_user(db_session, ctx.workspace_id, "dev@example.com")
    await db_session.execute(
        text(
            "INSERT INTO issue_assignees (issue_id, principal_id, workspace_id) VALUES (:i, :p, :w)"
        ),
        {"i": i_id, "p": assignee_id, "w": ctx.workspace_id},
    )

    # Assert assignee auto-subscribed with source='ASSIGNEE'
    sub_rows2 = await db_session.execute(
        text("SELECT principal_id, source FROM issue_subscriptions WHERE issue_id = :id"),
        {"id": i_id},
    )
    subs2 = {r[0]: r[1] for r in sub_rows2.fetchall()}
    assert assignee_id in subs2
    assert subs2[assignee_id] == "ASSIGNEE"


# -----------------------------------------------------------------------------
# Case 3: Positive: Exclusive labels auto-replacement
# -----------------------------------------------------------------------------
async def test_case_3_exclusive_labels_autoreplace(db_session: AsyncSession) -> None:
    """Inserting a label in the same exclusive_group deletes previous label in that group."""
    ctx = await _setup_context(db_session)
    i_id = await _create_issue(db_session, ctx, summary="Labeled issue")

    # Create 3 labels in project
    lbl_feature = uuid.uuid4()
    lbl_ui = uuid.uuid4()
    lbl_bug = uuid.uuid4()

    await db_session.execute(
        text(
            "INSERT INTO project_labels ("
            "  id, workspace_id, project_id, name, color_hex, exclusive_group"
            ") VALUES "
            "(:f, :w, :p, 'type:feature', '#3B82F6', 'type'), "
            "(:u, :w, :p, 'ui', '#10B981', NULL), "
            "(:b, :w, :p, 'type:bug', '#EF4444', 'type')"
        ),
        {"f": lbl_feature, "u": lbl_ui, "b": lbl_bug, "w": ctx.workspace_id, "p": ctx.project_id},
    )

    # Attach type:feature and ui
    await db_session.execute(
        text(
            "INSERT INTO issue_labels (issue_id, label_id, workspace_id) "
            "VALUES (:i, :f, :w), (:i, :u, :w)"
        ),
        {"i": i_id, "f": lbl_feature, "u": lbl_ui, "w": ctx.workspace_id},
    )

    # Check attached labels
    rows = await db_session.execute(
        text("SELECT label_id FROM issue_labels WHERE issue_id = :id"),
        {"id": i_id},
    )
    assert {r[0] for r in rows.fetchall()} == {lbl_feature, lbl_ui}

    # Now attach type:bug (same exclusive_group 'type')
    await db_session.execute(
        text("INSERT INTO issue_labels (issue_id, label_id, workspace_id) VALUES (:i, :b, :w)"),
        {"i": i_id, "b": lbl_bug, "w": ctx.workspace_id},
    )

    # Verify type:feature is replaced by type:bug, ui remains
    rows_after = await db_session.execute(
        text("SELECT label_id FROM issue_labels WHERE issue_id = :id"),
        {"id": i_id},
    )
    assert {r[0] for r in rows_after.fetchall()} == {lbl_bug, lbl_ui}


# -----------------------------------------------------------------------------
# Case 4: Negative: Assignee CHECK constraints and vendor non-subscription
# -----------------------------------------------------------------------------
async def test_case_4_assignee_check_and_vendor_nosub(db_session: AsyncSession) -> None:
    """Both principal and free-text, or neither, violates check 23514.

    Free text creates no subscription.
    """
    ctx = await _setup_context(db_session)
    i_id = await _create_issue(db_session, ctx, summary="Assignee issue")
    u_id = await _create_user(db_session, ctx.workspace_id, "user2@example.com")

    # 1. Both principal and free text -> 23514
    with pytest.raises(IntegrityError) as exc_both:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees ("
                    "  issue_id, principal_id, free_text_assignee, workspace_id"
                    ") VALUES (:i, :p, 'Vendor Corp', :w)"
                ),
                {"i": i_id, "p": u_id, "w": ctx.workspace_id},
            )
    assert _get_sqlstate(exc_both.value) == "23514"

    # 2. Neither principal nor free text -> 23514
    with pytest.raises(IntegrityError) as exc_none:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees ("
                    "  issue_id, principal_id, free_text_assignee, workspace_id"
                    ") VALUES (:i, NULL, NULL, :w)"
                ),
                {"i": i_id, "w": ctx.workspace_id},
            )
    assert _get_sqlstate(exc_none.value) == "23514"

    # 3. Free text assignee succeeds
    await db_session.execute(
        text(
            "INSERT INTO issue_assignees (issue_id, free_text_assignee, workspace_id) "
            "VALUES (:i, 'Acme External Vendor', :w)"
        ),
        {"i": i_id, "w": ctx.workspace_id},
    )

    # 4. Check that no extra subscription was created for the vendor
    sub_rows = await db_session.execute(
        text("SELECT principal_id, source FROM issue_subscriptions WHERE issue_id = :id"),
        {"id": i_id},
    )
    subs = list(sub_rows.fetchall())
    # Exactly 1 subscription: the issue creator
    assert len(subs) == 1
    assert subs[0][0] == ctx.user_id
    assert subs[0][1] == "CREATOR"


# -----------------------------------------------------------------------------
# Case 5: Negative / Security: Foreign cross-project and invalid principal guards
# -----------------------------------------------------------------------------
async def test_case_5_security_and_mismatch_guards(db_session: AsyncSession) -> None:
    """Validates cross-project and cross-workspace access control checks."""
    ctx1 = await _setup_context(db_session, identifier="PRJA")
    ctx2 = await _setup_context(db_session, identifier="PRJB")
    i_id1 = await _create_issue(db_session, ctx1, summary="Project 1 Issue")

    # 1. Assigning a GROUP principal raises ASSIGNEE_INVALID_PRINCIPAL
    group_id = await _create_group(db_session, ctx1.workspace_id, name="Security Team")
    with pytest.raises(DBAPIError) as exc_group:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees (issue_id, principal_id, workspace_id) "
                    "VALUES (:i, :g, :w)"
                ),
                {"i": i_id1, "g": group_id, "w": ctx1.workspace_id},
            )
    assert "ASSIGNEE_INVALID_PRINCIPAL" in str(exc_group.value)

    # 2. Assigning a principal from another workspace raises ASSIGNEE_INVALID_PRINCIPAL
    with pytest.raises(DBAPIError) as exc_foreign_user:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees (issue_id, principal_id, workspace_id) "
                    "VALUES (:i, :u2, :w)"
                ),
                {"i": i_id1, "u2": ctx2.user_id, "w": ctx1.workspace_id},
            )
    assert "ASSIGNEE_INVALID_PRINCIPAL" in str(exc_foreign_user.value)

    # 3. Label from another project raises LABEL_PROJECT_MISMATCH
    foreign_lbl = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
            "VALUES (:l, :w, :p, 'foreign-label', '#FFFFFF')"
        ),
        {"l": foreign_lbl, "w": ctx2.workspace_id, "p": ctx2.project_id},
    )
    with pytest.raises(DBAPIError) as exc_lbl_proj:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_labels (issue_id, label_id, workspace_id) "
                    "VALUES (:i, :l, :w)"
                ),
                {"i": i_id1, "l": foreign_lbl, "w": ctx1.workspace_id},
            )
    assert "LABEL_PROJECT_MISMATCH" in str(exc_lbl_proj.value)

    # 4. Cycle from another project raises CYCLE_PROJECT_MISMATCH
    foreign_cycle = await _create_cycle(db_session, ctx2, name="Sprint Foreign")
    with pytest.raises(DBAPIError) as exc_cycle_proj:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET cycle_id = :c WHERE id = :i"),
                {"c": foreign_cycle, "i": i_id1},
            )
    assert "CYCLE_PROJECT_MISMATCH" in str(exc_cycle_proj.value)

    # 5. Insert into issue_modules when modules_enabled=FALSE raises MODULES_DISABLED
    # ctx1 has modules_enabled=False
    mod_id = await _create_module(db_session, ctx1, name="Disabled Module")
    with pytest.raises(DBAPIError) as exc_mod_dis:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_modules (issue_id, module_id, workspace_id) "
                    "VALUES (:i, :m, :w)"
                ),
                {"i": i_id1, "m": mod_id, "w": ctx1.workspace_id},
            )
    assert "MODULES_DISABLED" in str(exc_mod_dis.value)

    # 6. Insert into project_module_defaults when modules_enabled=FALSE raises MODULES_DISABLED
    with pytest.raises(DBAPIError) as exc_pmd_dis:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO project_module_defaults (project_id, module_id, workspace_id) "
                    "VALUES (:p, :m, :w)"
                ),
                {"p": ctx1.project_id, "m": mod_id, "w": ctx1.workspace_id},
            )
    assert "MODULES_DISABLED" in str(exc_pmd_dis.value)

    # 7. Module from another project raises MODULE_PROJECT_MISMATCH
    ctx1_mod_en = await _setup_context(db_session, identifier="PRJC", modules_enabled=True)
    i_id_mod_en = await _create_issue(db_session, ctx1_mod_en, summary="Mod Issue")
    foreign_mod = await _create_module(db_session, ctx2, name="Foreign Module")
    with pytest.raises(DBAPIError) as exc_mod_proj:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_modules (issue_id, module_id, workspace_id) "
                    "VALUES (:i, :m, :w)"
                ),
                {"i": i_id_mod_en, "m": foreign_mod, "w": ctx1_mod_en.workspace_id},
            )
    assert "MODULE_PROJECT_MISMATCH" in str(exc_mod_proj.value)

    # 8. Subscription from another workspace raises SUBSCRIPTION_WORKSPACE_MISMATCH
    with pytest.raises(DBAPIError) as exc_sub_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_subscriptions ("
                    "  issue_id, principal_id, workspace_id, source"
                    ") VALUES (:i, :p, :w, 'MANUAL')"
                ),
                {"i": i_id1, "p": ctx2.user_id, "w": ctx1.workspace_id},
            )
    assert "SUBSCRIPTION_WORKSPACE_MISMATCH" in str(exc_sub_ws.value)


# -----------------------------------------------------------------------------
# Case 6: Boundary tests: Cycle date ranges, single active cycle, free-text bounds
# -----------------------------------------------------------------------------
async def test_case_6_boundary_rules(db_session: AsyncSession) -> None:
    """Cycle date overlap 23P01, adjacent ranges ok, active cycle 23505, text len 120/121."""
    ctx = await _setup_context(db_session)

    # 1. Overlapping date ranges raise 23P01
    await _create_cycle(
        db_session,
        ctx,
        name="Sprint 1",
        dates=(date(2026, 1, 1), date(2026, 1, 14)),
    )

    with pytest.raises(IntegrityError) as exc_overlap:
        async with db_session.begin_nested():
            await _create_cycle(
                db_session,
                ctx,
                name="Sprint Overlap",
                dates=(date(2026, 1, 10), date(2026, 1, 20)),
            )
    assert _get_sqlstate(exc_overlap.value) == "23P01"

    # 2. Adjacent non-overlapping range accepted
    c_adj = await _create_cycle(
        db_session,
        ctx,
        name="Sprint 2 Adjacent",
        dates=(date(2026, 1, 15), date(2026, 1, 28)),
    )
    assert isinstance(c_adj, uuid.UUID)

    # 3. Two active cycles in the same project raise 23505
    c_act1 = await _create_cycle(db_session, ctx, name="Active 1", status="active")
    assert isinstance(c_act1, uuid.UUID)

    with pytest.raises(IntegrityError) as exc_active:
        async with db_session.begin_nested():
            await _create_cycle(db_session, ctx, name="Active 2", status="active")
    assert _get_sqlstate(exc_active.value) == "23505"

    # 4. Free text assignee length boundary (120 ok, 121 rejected with 23514)
    i_id = await _create_issue(db_session, ctx, summary="Text length issue")
    valid_120 = "x" * 120
    await db_session.execute(
        text(
            "INSERT INTO issue_assignees (issue_id, free_text_assignee, workspace_id) "
            "VALUES (:i, :txt, :w)"
        ),
        {"i": i_id, "txt": valid_120, "w": ctx.workspace_id},
    )

    invalid_121 = "y" * 121
    with pytest.raises(IntegrityError) as exc_len:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees (issue_id, free_text_assignee, workspace_id) "
                    "VALUES (:i, :txt, :w)"
                ),
                {"i": i_id, "txt": invalid_121, "w": ctx.workspace_id},
            )
    assert _get_sqlstate(exc_len.value) == "23514"

    # 5. Duplicate free text assignee (case insensitive) raises 23505
    with pytest.raises(IntegrityError) as exc_dup_txt:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issue_assignees (issue_id, free_text_assignee, workspace_id) "
                    "VALUES (:i, :txt, :w)"
                ),
                {"i": i_id, "txt": valid_120.upper(), "w": ctx.workspace_id},
            )
    assert _get_sqlstate(exc_dup_txt.value) == "23505"


# -----------------------------------------------------------------------------
# Case 7: AGENT principal assignee support and spine match guards
# -----------------------------------------------------------------------------
async def test_case_7_agent_assignee_and_spine_guards(db_session: AsyncSession) -> None:
    """AGENT principal can be assigned, and planning spine mismatch guards trigger."""
    ctx = await _setup_context(db_session)
    i_id = await _create_issue(db_session, ctx, summary="Agent work")

    # AGENT principal can be assigned
    agent_id = await _create_agent(db_session, ctx.workspace_id, display_name="Bot Agent")
    await db_session.execute(
        text(
            "INSERT INTO issue_assignees (issue_id, principal_id, workspace_id) VALUES (:i, :a, :w)"
        ),
        {"i": i_id, "a": agent_id, "w": ctx.workspace_id},
    )

    # Cycle spine mismatch raises PLANNING_SPINE_MISMATCH
    fake_cycle_id = uuid.uuid4()
    # Register object with different project_id
    ctx2 = await _setup_context(db_session, identifier="PRJD")
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'cycle'::object_kind, :ws, :proj2, :ckey, 'Mismatched Cycle', :creator, :id"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "proj2": ctx2.project_id,
            "ckey": f"cycle-{fake_cycle_id.hex[:12]}",
            "creator": ctx.user_id,
            "id": fake_cycle_id,
        },
    )
    with pytest.raises(DBAPIError) as exc_spine:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO cycles (id, workspace_id, project_id, name) "
                    "VALUES (:id, :ws, :proj1, 'Mismatched Cycle')"
                ),
                {"id": fake_cycle_id, "ws": ctx.workspace_id, "proj1": ctx.project_id},
            )
    assert "PLANNING_SPINE_MISMATCH" in str(exc_spine.value)

    # Module spine mismatch raises PLANNING_SPINE_MISMATCH
    fake_mod_id = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'module'::object_kind, :ws, :proj2, :ckey, 'Mismatched Module', :creator, :id"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "proj2": ctx2.project_id,
            "ckey": f"mod-{fake_mod_id.hex[:12]}",
            "creator": ctx.user_id,
            "id": fake_mod_id,
        },
    )
    with pytest.raises(DBAPIError) as exc_mod_spine:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO modules (id, workspace_id, project_id, name) "
                    "VALUES (:id, :ws, :proj1, 'Mismatched Module')"
                ),
                {"id": fake_mod_id, "ws": ctx.workspace_id, "proj1": ctx.project_id},
            )
    assert "PLANNING_SPINE_MISMATCH" in str(exc_mod_spine.value)

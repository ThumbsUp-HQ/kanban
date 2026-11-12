"""Unit tests for Phase 1 projects, workflow_states, project_priorities, and project_labels."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.tests.conftest import (
    bind_workspace_admin,
    bootstrap_workspace_admin,
)


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace and bootstrap an admin principal context."""
    ws_id, _ = await bootstrap_workspace_admin(session, slug=slug, name=name)
    return ws_id


async def _create_test_project(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    identifier: str = "KAN",
    name: str = "Kanban Project",
    extra: dict[str, str | int] | None = None,
) -> uuid.UUID:
    """Register and create a project in the database."""
    await bind_workspace_admin(session, workspace_id)
    extra_dict = extra or {}
    description_markdown = str(extra_dict.get("description_markdown", ""))
    auto_archive_raw = extra_dict.get("auto_archive_days")
    auto_archive_days = int(auto_archive_raw) if auto_archive_raw is not None else None
    c_user = uuid.uuid4()
    res = await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, :identifier, :name, :created_by"
            ")"
        ),
        {"ws_id": workspace_id, "identifier": identifier, "name": name, "created_by": c_user},
    )
    proj_id = res.scalar_one()
    assert isinstance(proj_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO projects ("
            "  id, workspace_id, identifier, name, description_markdown, auto_archive_days"
            ") VALUES (:id, :ws_id, :identifier, :name, :desc, :auto_archive)"
        ),
        {
            "id": proj_id,
            "ws_id": workspace_id,
            "identifier": identifier,
            "name": name,
            "desc": description_markdown,
            "auto_archive": auto_archive_days,
        },
    )
    return proj_id


async def test_01_project_creation_and_seeding(app_session: AsyncSession) -> None:
    """Test project insertion seeds exactly 5 states and 5 priorities with Plane defaults."""
    ws_id = await _create_workspace(app_session)
    proj_id = await _create_test_project(app_session, ws_id, identifier="KAN", name="Core Project")

    # Verify seeded workflow states
    st_rows = await app_session.execute(
        text(
            "SELECT name, state_group, color_hex, sort_order, is_default "
            "FROM workflow_states WHERE project_id = :p_id ORDER BY sort_order"
        ),
        {"p_id": proj_id},
    )
    states = [
        (r.name, r.state_group, r.color_hex, r.sort_order, r.is_default) for r in st_rows.fetchall()
    ]
    expected_states = [
        ("Backlog", "backlog", "#A3A3A3", 0, True),
        ("Todo", "unstarted", "#3B82F6", 1, False),
        ("In Progress", "started", "#F59E0B", 2, False),
        ("Done", "completed", "#16A34A", 3, False),
        ("Cancelled", "cancelled", "#DC2626", 4, False),
    ]
    assert states == expected_states

    # Verify seeded project priorities
    pr_rows = await app_session.execute(
        text(
            "SELECT slug, label, emoji, color_hex, sort_order, is_default "
            "FROM project_priorities WHERE project_id = :p_id ORDER BY sort_order"
        ),
        {"p_id": proj_id},
    )
    priorities = [
        (r.slug, r.label, r.emoji, r.color_hex, r.sort_order, r.is_default)
        for r in pr_rows.fetchall()
    ]
    expected_priorities = [
        ("urgent", "Urgent", "🔥", "#DC2626", 0, False),
        ("high", "High", "⚡", "#F97316", 1, False),
        ("medium", "Medium", "🔹", "#EAB308", 2, False),
        ("low", "Low", "💤", "#22C55E", 3, False),
        ("none", "None", None, "#A3A3A3", 4, True),
    ]
    assert priorities == expected_priorities


async def test_02_project_labels_positive(app_session: AsyncSession) -> None:
    """Test inserting project labels with and without exclusive groups."""
    ws_id = await _create_workspace(app_session)
    proj_id = await _create_test_project(app_session, ws_id, identifier="LAB")

    # Label with exclusive group
    await app_session.execute(
        text(
            "INSERT INTO project_labels ("
            "  workspace_id, project_id, name, color_hex, exclusive_group"
            ") VALUES (:ws_id, :p_id, 'type:bug', '#EF4444', 'type')"
        ),
        {"ws_id": ws_id, "p_id": proj_id},
    )

    # Label with NULL exclusive group
    await app_session.execute(
        text(
            "INSERT INTO project_labels ("
            "  workspace_id, project_id, name, color_hex, exclusive_group"
            ") VALUES (:ws_id, :p_id, 'ui', '#3B82F6', NULL)"
        ),
        {"ws_id": ws_id, "p_id": proj_id},
    )

    rows = await app_session.execute(
        text(
            "SELECT name, color_hex, exclusive_group "
            "FROM project_labels WHERE project_id = :p_id ORDER BY name"
        ),
        {"p_id": proj_id},
    )
    records = [(r.name, r.color_hex, r.exclusive_group) for r in rows.fetchall()]
    assert records == [("type:bug", "#EF4444", "type"), ("ui", "#3B82F6", None)]


async def test_03_project_identifier_validation(app_session: AsyncSession) -> None:
    """Test identifier regex validation rejecting invalid formats and accepting valid boundaries."""
    ws_id = await _create_workspace(app_session)

    # Invalid identifiers
    invalid_ids = ["kan", "K", "KANBANBOARD1", "1AB"]
    for bad_id in invalid_ids:
        sp = await app_session.begin_nested()
        user_id = uuid.uuid4()
        res = await app_session.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, :id, 'Bad Project', :user"
                ")"
            ),
            {"ws_id": ws_id, "id": bad_id, "user": user_id},
        )
        obj_id = res.scalar_one()

        with pytest.raises(IntegrityError):
            await app_session.execute(
                text(
                    "INSERT INTO projects (id, workspace_id, identifier, name) "
                    "VALUES (:id, :ws_id, :identifier, 'Bad Project')"
                ),
                {"id": obj_id, "ws_id": ws_id, "identifier": bad_id},
            )
        await sp.rollback()

    # Valid boundaries: 2 characters and 10 characters
    p_min = await _create_test_project(app_session, ws_id, identifier="AB", name="Min Ident")
    assert p_min is not None

    p_max = await _create_test_project(
        app_session, ws_id, identifier="ABCDEFGHIJ", name="Max Ident"
    )
    assert p_max is not None


async def test_04_duplicate_identifier_and_spine_mismatch(app_session: AsyncSession) -> None:
    """Test duplicate identifier in same workspace fails, and spine mismatch raises error."""
    ws1 = await _create_workspace(app_session)
    ws2 = await _create_workspace(app_session)

    await _create_test_project(app_session, ws1, identifier="PRJ", name="First Project")

    # Duplicate in same workspace fails with 23505
    sp = await app_session.begin_nested()
    u_id = uuid.uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        await app_session.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'PRJ', 'Duplicate Project', :user"
                ")"
            ),
            {"ws_id": ws1, "user": u_id},
        )
    assert "23505" in str(exc_info.value) or "unique" in str(exc_info.value).lower()
    await sp.rollback()

    # Same identifier in different workspace succeeds
    p_other_ws = await _create_test_project(
        app_session, ws2, identifier="PRJ", name="Other WS Project"
    )
    assert p_other_ws is not None

    # Spine mismatch: object registered with 'OTHER', but project inserted with 'MIS'
    await bind_workspace_admin(app_session, ws1)
    sp2 = await app_session.begin_nested()
    res2 = await app_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, 'OTHER', 'Mismatch Spine', :user"
            ")"
        ),
        {"ws_id": ws1, "user": u_id},
    )
    mismatch_id = res2.scalar_one()
    with pytest.raises(DBAPIError) as exc_info_spine:
        await app_session.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws_id, 'MIS', 'Mismatch Spine')"
            ),
            {"id": mismatch_id, "ws_id": ws1},
        )
    assert "PROJECT_SPINE_MISMATCH" in str(exc_info_spine.value)
    await sp2.rollback()


async def test_05_workspace_match_and_default_uniqueness(app_session: AsyncSession) -> None:
    """Test child workspace mismatch rejection and single-default constraint enforcement."""
    ws1 = await _create_workspace(app_session)
    ws2 = await _create_workspace(app_session)
    proj_id = await _create_test_project(app_session, ws1, identifier="SEC")

    # Priority with mismatched workspace_id
    sp = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(
            text(
                "INSERT INTO project_priorities ("
                "  workspace_id, project_id, slug, label, color_hex, sort_order"
                ") VALUES (:ws_id, :p_id, 'custom', 'Custom', '#000000', 10)"
            ),
            {"ws_id": ws2, "p_id": proj_id},
        )
    assert "PROJECT_CHILD_WORKSPACE_MISMATCH" in str(exc_info.value)
    await sp.rollback()

    # Workflow state with mismatched workspace_id
    sp2 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info2:
        await app_session.execute(
            text(
                "INSERT INTO workflow_states ("
                "  workspace_id, project_id, name, state_group, color_hex, sort_order"
                ") VALUES (:ws_id, :p_id, 'Custom State', 'started', '#000000', 10)"
            ),
            {"ws_id": ws2, "p_id": proj_id},
        )
    assert "PROJECT_CHILD_WORKSPACE_MISMATCH" in str(exc_info2.value)
    await sp2.rollback()

    # Label with mismatched workspace_id
    sp3 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info3:
        await app_session.execute(
            text(
                "INSERT INTO project_labels ("
                "  workspace_id, project_id, name, color_hex"
                ") VALUES (:ws_id, :p_id, 'custom-label', '#000000')"
            ),
            {"ws_id": ws2, "p_id": proj_id},
        )
    assert "PROJECT_CHILD_WORKSPACE_MISMATCH" in str(exc_info3.value)
    await sp3.rollback()

    # Second is_default priority in same project raises 23505
    sp4 = await app_session.begin_nested()
    with pytest.raises(IntegrityError):
        await app_session.execute(
            text(
                "INSERT INTO project_priorities ("
                "  workspace_id, project_id, slug, label, color_hex, sort_order, is_default"
                ") VALUES (:ws_id, :p_id, 'another_default', 'Another', '#111111', 11, TRUE)"
            ),
            {"ws_id": ws1, "p_id": proj_id},
        )
    await sp4.rollback()

    # Second is_default workflow state in same project raises 23505
    sp5 = await app_session.begin_nested()
    with pytest.raises(IntegrityError):
        await app_session.execute(
            text(
                "INSERT INTO workflow_states ("
                "  workspace_id, project_id, name, state_group, color_hex, sort_order, is_default"
                ") VALUES (:ws_id, :p_id, 'Second Default', 'backlog', '#111111', 11, TRUE)"
            ),
            {"ws_id": ws1, "p_id": proj_id},
        )
    await sp5.rollback()


async def test_06_description_and_auto_archive_boundaries(app_session: AsyncSession) -> None:
    """Test description length boundary (524288 bytes) and auto_archive_days bounds (1-365)."""
    ws_id = await _create_workspace(app_session)

    # 524288 bytes description accepted
    desc_512k = "a" * 524288
    p1 = await _create_test_project(
        app_session, ws_id, identifier="DOK", extra={"description_markdown": desc_512k}
    )
    assert p1 is not None

    # 524289 bytes description rejected (23514)
    desc_oversized = "a" * 524289
    sp = await app_session.begin_nested()
    user_id = uuid.uuid4()
    res = await app_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, 'DTOO', 'Oversized Project', :user"
            ")"
        ),
        {"ws_id": ws_id, "user": user_id},
    )
    bad_id = res.scalar_one()
    with pytest.raises(IntegrityError):
        await app_session.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
                "VALUES (:id, :ws_id, 'DTOO', 'Oversized', :desc)"
            ),
            {"id": bad_id, "ws_id": ws_id, "desc": desc_oversized},
        )
    await sp.rollback()

    # auto_archive_days: 1 and 365 accepted
    p_arch1 = await _create_test_project(
        app_session, ws_id, identifier="ARC1", extra={"auto_archive_days": 1}
    )
    assert p_arch1 is not None

    p_arch365 = await _create_test_project(
        app_session, ws_id, identifier="ARC365", extra={"auto_archive_days": 365}
    )
    assert p_arch365 is not None

    # auto_archive_days: 0 and 366 rejected
    for bad_days in (0, 366):
        sp_a = await app_session.begin_nested()
        res_a = await app_session.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, :ident, 'Bad Days', :user"
                ")"
            ),
            {"ws_id": ws_id, "ident": f"B{bad_days}", "user": user_id},
        )
        bad_arch_id = res_a.scalar_one()
        with pytest.raises(IntegrityError):
            await app_session.execute(
                text(
                    "INSERT INTO projects (id, workspace_id, identifier, name, auto_archive_days) "
                    "VALUES (:id, :ws_id, :ident, 'Bad Days', :days)"
                ),
                {"id": bad_arch_id, "ws_id": ws_id, "ident": f"B{bad_days}", "days": bad_days},
            )
        await sp_a.rollback()


async def test_07_terminal_state_guard_and_seq_counter(app_session: AsyncSession) -> None:
    """Test deletion guard on terminal states and issue_seq_counter decrease guard."""
    ws_id = await _create_workspace(app_session)
    proj_id = await _create_test_project(app_session, ws_id, identifier="GRD")

    # Deleting the only 'completed' state raises LAST_TERMINAL_STATE_REQUIRED
    sp = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(
            text(
                "DELETE FROM workflow_states WHERE project_id = :p_id AND state_group = 'completed'"
            ),
            {"p_id": proj_id},
        )
    assert "LAST_TERMINAL_STATE_REQUIRED" in str(exc_info.value)
    await sp.rollback()

    # Deleting the only 'cancelled' state raises LAST_TERMINAL_STATE_REQUIRED
    sp2 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info2:
        await app_session.execute(
            text(
                "DELETE FROM workflow_states WHERE project_id = :p_id AND state_group = 'cancelled'"
            ),
            {"p_id": proj_id},
        )
    assert "LAST_TERMINAL_STATE_REQUIRED" in str(exc_info2.value)
    await sp2.rollback()

    # Adding a second 'completed' state allows deleting the first
    await app_session.execute(
        text(
            "INSERT INTO workflow_states ("
            "  workspace_id, project_id, name, state_group, color_hex, sort_order"
            ") VALUES (:ws_id, :p_id, 'Shipped', 'completed', '#10B981', 10)"
        ),
        {"ws_id": ws_id, "p_id": proj_id},
    )
    # Deleting 'Done' now succeeds because 'Shipped' remains
    await app_session.execute(
        text("DELETE FROM workflow_states WHERE project_id = :p_id AND name = 'Done'"),
        {"p_id": proj_id},
    )
    check_done = await app_session.execute(
        text("SELECT count(*) FROM workflow_states WHERE project_id = :p_id AND name = 'Done'"),
        {"p_id": proj_id},
    )
    assert check_done.scalar_one() == 0

    # issue_seq_counter decrease guard
    # First increase counter to 5
    await app_session.execute(
        text("UPDATE projects SET issue_seq_counter = 5 WHERE id = :p_id"),
        {"p_id": proj_id},
    )

    # Decreasing counter raises ISSUE_SEQ_DECREASE_FORBIDDEN
    sp3 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc_info3:
        await app_session.execute(
            text("UPDATE projects SET issue_seq_counter = 4 WHERE id = :p_id"),
            {"p_id": proj_id},
        )
    assert "ISSUE_SEQ_DECREASE_FORBIDDEN" in str(exc_info3.value)
    await sp3.rollback()

    # Increasing counter succeeds
    await app_session.execute(
        text("UPDATE projects SET issue_seq_counter = 6 WHERE id = :p_id"),
        {"p_id": proj_id},
    )
    check_seq = await app_session.execute(
        text("SELECT issue_seq_counter FROM projects WHERE id = :p_id"),
        {"p_id": proj_id},
    )
    assert check_seq.scalar_one() == 6


async def test_08_child_workspace_auto_population(app_session: AsyncSession) -> None:
    """Test child table triggers automatically inherit workspace_id when omitted or NULL."""
    ws_id = await _create_workspace(app_session)
    proj_id = await _create_test_project(app_session, ws_id, identifier="INH")

    # Insert workflow_states with NULL workspace_id
    res_st = await app_session.execute(
        text(
            "INSERT INTO workflow_states ("
            "  workspace_id, project_id, name, state_group, color_hex, sort_order"
            ") VALUES (NULL, :p_id, 'Auto State', 'unstarted', '#123456', 99) "
            "RETURNING workspace_id"
        ),
        {"p_id": proj_id},
    )
    assert res_st.scalar_one() == ws_id

    # Insert project_priorities with NULL workspace_id
    res_pr = await app_session.execute(
        text(
            "INSERT INTO project_priorities ("
            "  workspace_id, project_id, slug, label, color_hex, sort_order"
            ") VALUES (NULL, :p_id, 'auto_slug', 'Auto Priority', '#654321', 99) "
            "RETURNING workspace_id"
        ),
        {"p_id": proj_id},
    )
    assert res_pr.scalar_one() == ws_id

    # Insert project_labels with NULL workspace_id
    res_lb = await app_session.execute(
        text(
            "INSERT INTO project_labels ("
            "  workspace_id, project_id, name, color_hex"
            ") VALUES (NULL, :p_id, 'auto_label', '#abcdef') RETURNING workspace_id"
        ),
        {"p_id": proj_id},
    )
    assert res_lb.scalar_one() == ws_id

# ruff: noqa: E501, PLR0915
"""Unit tests for Filter DSL compiler and 2D query engine (S6.4, S3.4)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.models import Project
from database.session import RLSContext, RLSSessionFactory
from database.testing.pg_harness import build_dsn
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.views import (
    FilterSpec,
    GateStatus,
    GroupAxis,
    LabelMatch,
    SortDir,
    SortField,
    ViewLayout,
)
from kanban.services.query_engine import (
    _parse_cursor_val,
    decode_query_cursor,
    encode_query_cursor,
    execute_view_query,
)
from kanban.services.view_dsl import (
    compile_issue_filter_predicates,
    validate_group_axes,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.committed_db


def test_validate_group_axes() -> None:
    """Test group axes validation rules and module gate."""
    project = Project(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        identifier="AXES",
        name="Axes Project",
        modules_enabled=False,
    )

    # Valid none-none
    validate_group_axes(project, GroupAxis.NONE, GroupAxis.NONE)

    # Valid distinct
    validate_group_axes(project, GroupAxis.STATE, GroupAxis.PRIORITY)

    # Duplicate axis
    with pytest.raises(ProblemException) as exc_dup:
        validate_group_axes(project, GroupAxis.STATE, GroupAxis.STATE)
    assert exc_dup.value.code == "DUPLICATE_GROUP_AXIS"

    # Module axis on modules_enabled=False
    with pytest.raises(ProblemException) as exc_mod1:
        validate_group_axes(project, GroupAxis.MODULE, GroupAxis.NONE)
    assert exc_mod1.value.code == "MODULES_DISABLED"

    with pytest.raises(ProblemException) as exc_mod2:
        validate_group_axes(project, GroupAxis.NONE, GroupAxis.MODULE)
    assert exc_mod2.value.code == "MODULES_DISABLED"

    filters_disabled = FilterSpec(module_ids=["none"])
    with pytest.raises(ProblemException) as exc_mod3:
        validate_group_axes(project, GroupAxis.STATE, GroupAxis.PRIORITY, filters_disabled)
    assert exc_mod3.value.code == "MODULES_DISABLED"


def test_cursor_encoding_and_tampering() -> None:
    """Test HMAC query cursor encoding, decoding, tampering, and query hash mismatch."""
    q_hash_a = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    q_hash_b = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    secret = "test-secret"
    target_id = uuid.uuid4()

    cursor = encode_query_cursor("val1", target_id, q_hash_a, secret)
    val, out_id = decode_query_cursor(cursor, q_hash_a, secret)
    assert val == "val1"
    assert out_id == target_id

    # Query hash mismatch
    with pytest.raises(ProblemException) as exc_mismatch:
        decode_query_cursor(cursor, q_hash_b, secret)
    assert exc_mismatch.value.code == "INVALID_CURSOR"

    # Signature mismatch
    with pytest.raises(ProblemException) as exc_sig:
        decode_query_cursor(cursor, q_hash_a, "wrong-secret")
    assert exc_sig.value.code == "INVALID_CURSOR"

    # Corrupted payload
    with pytest.raises(ProblemException) as exc_corrupt:
        decode_query_cursor("not-valid-base64!@#$", q_hash_a, secret)
    assert exc_corrupt.value.code == "INVALID_CURSOR"

    # Invalid issue UUID in payload
    raw_payload = f"val|not-a-uuid|{q_hash_a}"
    sig = hmac.new(secret.encode(), raw_payload.encode(), hashlib.sha256).hexdigest()
    packet = {"v": "val", "i": "not-a-uuid", "q": q_hash_a, "s": sig}
    bad_uuid_cursor = base64.urlsafe_b64encode(json.dumps(packet).encode()).decode()
    with pytest.raises(ProblemException) as exc_uuid:
        decode_query_cursor(bad_uuid_cursor, q_hash_a, secret)
    assert exc_uuid.value.code == "INVALID_CURSOR"

    # Direct test of _parse_cursor_val helper
    assert _parse_cursor_val(SortField.SEQUENCE_ID, "123") == 123
    assert _parse_cursor_val(SortField.SEQUENCE_ID, "not-int") == 0
    assert _parse_cursor_val(SortField.DUE_DATE, "2026-11-20") == dt.date(2026, 11, 20)
    assert _parse_cursor_val(SortField.DUE_DATE, "invalid-date") is None
    assert _parse_cursor_val(SortField.BOARD_RANK, "a0") == "a0"


def test_compile_filter_predicates_coverage(committed_db_session: AsyncSession) -> None:
    """Test compilation of all FilterSpec clauses."""
    project = Project(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        identifier="FLT",
        name="Filter Project",
        modules_enabled=True,
    )
    admin_id = uuid.uuid4()

    state_id = uuid.uuid4()
    priority_id = uuid.uuid4()
    label_id = uuid.uuid4()
    cycle_id = uuid.uuid4()
    module_id = uuid.uuid4()
    parent_id = uuid.uuid4()

    filters = FilterSpec(
        state_ids=[state_id],
        state_groups=["started"],
        priority_ids=[priority_id],
        assignee_ids=["me", "unassigned", str(admin_id)],
        has_free_text_assignee=True,
        label_ids=[label_id],
        label_match=LabelMatch.ALL,
        cycle_ids=["none", "active", str(cycle_id)],
        module_ids=["none", str(module_id)],
        parent_issue_id=str(parent_id),
        start_date_from=dt.date(2026, 11, 1),
        start_date_to=dt.date(2026, 11, 30),
        due_date_from=dt.date(2026, 11, 1),
        due_date_to=dt.date(2026, 11, 30),
        overdue_only=True,
        blocked=True,
        gate_status=GateStatus.PENDING,
        include_archived=True,
        search_query="authentication bug",
    )

    preds = compile_issue_filter_predicates(committed_db_session, project, filters, admin_id)
    assert len(preds) > 5

    # Check unblocked / gate rejected / null parent
    filters_alt = FilterSpec(
        has_free_text_assignee=False,
        label_ids=[label_id],
        label_match=LabelMatch.ANY,
        parent_issue_id="null",
        blocked=False,
        gate_status=GateStatus.REJECTED,
    )
    preds_alt = compile_issue_filter_predicates(
        committed_db_session, project, filters_alt, admin_id
    )
    assert len(preds_alt) > 3


async def test_execute_view_query_2d_and_wip(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Test 2D grouping, WIP limit evaluation, and timeline links under RLS session."""
    session = committed_db_session
    ws_id = await create_workspace(session, name="Eng Workspace")
    admin_id = await create_user(session, ws_id, handle="@admin", display_name="Admin")
    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await session.commit()

    proj_id = await create_project(
        session, ws_id, identifier="ENG", name="Eng Project", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    project = await session.get(Project, proj_id)
    assert project is not None

    states = (
        await session.execute(
            text("SELECT id, name FROM workflow_states WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    todo_state_id = states[0][0]
    in_prog_state_id = states[1][0]

    # Set soft/hard WIP limits on in_prog_state
    await session.execute(
        text("UPDATE workflow_states SET wip_soft_limit = 1, wip_hard_limit = 2 WHERE id = :id"),
        {"id": in_prog_state_id},
    )

    priorities = (
        await session.execute(
            text(
                "SELECT id, label FROM project_priorities WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    urgent_pri_id = priorities[0][0]

    # Create issues
    iss1_id = uuid.uuid4()
    iss2_id = uuid.uuid4()
    iss3_id = uuid.uuid4()

    for iss_id, st_id, pri_id, rnk in [
        (iss1_id, in_prog_state_id, urgent_pri_id, "a000001"),
        (iss2_id, in_prog_state_id, urgent_pri_id, "a000002"),
        (iss3_id, todo_state_id, urgent_pri_id, "a000003"),
    ]:
        seq = (
            await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
        ).scalar_one()
        await session.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"
            ),
            {
                "ws": ws_id,
                "proj": proj_id,
                "ckey": f"ENG-{seq}",
                "title": f"Issue {seq}",
                "cr": admin_id,
                "id": iss_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
                "VALUES (:id, 'issue', :ws, :proj, :seq, :title, :st, :pri, :cr, :cr, :rnk, 'top')"
            ),
            {
                "id": iss_id,
                "ws": ws_id,
                "proj": proj_id,
                "seq": seq,
                "title": f"Issue {seq}",
                "st": st_id,
                "pri": pri_id,
                "cr": admin_id,
                "rnk": rnk,
            },
        )

    # Link iss1 BLOCKS iss2
    link_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, target_id, link_type, link_state, source_type, target_type, created_by_id) "
            "VALUES (:id, :ws, :src, :tgt, 'BLOCKS', 'ACTIVE', 'issue', 'issue', :cr)"
        ),
        {
            "id": link_id,
            "ws": ws_id,
            "src": iss1_id,
            "tgt": iss2_id,
            "cr": admin_id,
        },
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")

    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    rls_ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
    )
    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("session",),
    )

    try:
        async with factory.session(rls_ctx) as rls_session:
            result = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                layout=ViewLayout.TIMELINE,
                group_by=GroupAxis.STATE,
                sub_group_by=GroupAxis.PRIORITY,
                sort_by=SortField.BOARD_RANK,
                sort_dir=SortDir.ASC,
                wip_limits_override={},
                limit=50,
            )

            assert result.total_matching == 3
            assert len(result.items) == 3
            assert len(result.timeline_links) == 1
            assert result.timeline_links[0].source_key == "ENG-1"
            assert result.timeline_links[0].target_key == "ENG-2"
            assert result.timeline_links[0].link_type == "BLOCKS"

            # Verify WIP status on In Progress state (2 issues with soft=1, hard=2 -> exceeded=soft)
            in_prog_group = next(
                g for g in result.groups if g.group_key == f"state:{in_prog_state_id}"
            )
            assert in_prog_group.count == 2
            assert in_prog_group.wip is not None
            assert in_prog_group.wip.soft == 1
            assert in_prog_group.wip.hard == 2
            assert in_prog_group.wip.exceeded == "soft"

            # Sub-group check
            urgent_sub = next(
                sg
                for sg in in_prog_group.sub_groups
                if sg.sub_group_key == f"priority:{urgent_pri_id}"
            )
            assert urgent_sub.count == 2
            assert len(urgent_sub.issue_ids) == 2

            # Query descending with cursor
            q_desc = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                sort_by=SortField.BOARD_RANK,
                sort_dir=SortDir.DESC,
                limit=1,
            )
            assert q_desc.next_cursor is not None
            q_desc_p2 = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                sort_by=SortField.BOARD_RANK,
                sort_dir=SortDir.DESC,
                cursor=q_desc.next_cursor,
                limit=10,
            )
            assert len(q_desc_p2.items) == 2
    finally:
        await app_engine.dispose()


async def test_2d_groups_all_axes(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Test 2D grouping across cycle, module, label, and assignee axes."""
    session = committed_db_session
    ws_id = await create_workspace(session, name="All Axes WS")
    admin_id = await create_user(session, ws_id, handle="@admin", display_name="Admin")
    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await session.commit()

    proj_id = await create_project(
        session, ws_id, identifier="AXIS", name="Axis Project", created_by_id=admin_id
    )
    await session.execute(
        text("UPDATE projects SET modules_enabled = true WHERE id = :p"), {"p": proj_id}
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )

    # Seed cycle
    cyc_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('cycle'::object_kind, :ws, :proj, 'AXIS/cycles/c1', 'Sprint 1', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_id, "cr": admin_id, "id": cyc_id},
    )
    await session.execute(
        text(
            "INSERT INTO cycles (id, object_type, workspace_id, project_id, name) VALUES (:id, 'cycle', :ws, :proj, 'Sprint 1')"
        ),
        {"id": cyc_id, "ws": ws_id, "proj": proj_id},
    )

    # Seed module
    mod_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('module'::object_kind, :ws, :proj, 'AXIS/modules/m1', 'Backend', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_id, "cr": admin_id, "id": mod_id},
    )
    await session.execute(
        text(
            "INSERT INTO modules (id, object_type, workspace_id, project_id, name) VALUES (:id, 'module', :ws, :proj, 'Backend')"
        ),
        {"id": mod_id, "ws": ws_id, "proj": proj_id},
    )

    # Seed label
    lbl_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) VALUES (:id, :ws, :proj, 'infra', '#112233')"
        ),
        {"id": lbl_id, "ws": ws_id, "proj": proj_id},
    )

    # Fetch states and priorities
    states = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    st_id = states[0][0]

    priorities = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    pri_id = priorities[0][0]

    # Seed 2 issues:
    # iss1 has cycle, module, label, assignee
    # iss2 has none
    iss1 = uuid.uuid4()
    iss2 = uuid.uuid4()
    s1 = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    s2 = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()

    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, 'AXIS-1', 'Issue 1', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_id, "cr": admin_id, "id": iss1},
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, state_id, priority_id, cycle_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, 'Issue 1', :st, :pri, :cyc, :cr, :cr, 'a000001', 'top')"
        ),
        {
            "id": iss1,
            "ws": ws_id,
            "proj": proj_id,
            "seq": s1,
            "st": st_id,
            "pri": pri_id,
            "cyc": cyc_id,
            "cr": admin_id,
        },
    )

    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, 'AXIS-2', 'Issue 2', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_id, "cr": admin_id, "id": iss2},
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, 'Issue 2', :st, :pri, :cr, :cr, 'a000002', 'top')"
        ),
        {
            "id": iss2,
            "ws": ws_id,
            "proj": proj_id,
            "seq": s2,
            "st": st_id,
            "pri": pri_id,
            "cr": admin_id,
        },
    )

    await session.execute(
        text("INSERT INTO issue_assignees (issue_id, principal_id) VALUES (:iid, :pid)"),
        {"iid": iss1, "pid": admin_id},
    )
    await session.execute(
        text("INSERT INTO issue_modules (issue_id, module_id) VALUES (:iid, :mid)"),
        {"iid": iss1, "mid": mod_id},
    )
    await session.execute(
        text("INSERT INTO issue_labels (issue_id, label_id) VALUES (:iid, :lid)"),
        {"iid": iss1, "lid": lbl_id},
    )

    await rebuild_era(session, ws_id)
    await session.commit()

    project = await session.get(Project, proj_id)
    assert project is not None

    db_name = pg_worker_db.url.database or "kanban_test"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_engine = create_async_engine(
        build_dsn(database=db_name, host=socket_dir, user="kanban_app"),
        pool_size=5,
        max_overflow=0,
    )
    factory = RLSSessionFactory(app_engine)
    rls_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))
    caller = PrincipalContext(principal_id=admin_id, workspace_id=ws_id, token_scopes=("session",))

    try:
        async with factory.session(rls_ctx) as rls_session:
            # 1. group_by=CYCLE, sub_group_by=STATE
            r_cyc = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                group_by=GroupAxis.CYCLE,
                sub_group_by=GroupAxis.STATE,
            )
            assert len(r_cyc.groups) > 0

            # 2. group_by=MODULE, sub_group_by=PRIORITY
            r_mod = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                group_by=GroupAxis.MODULE,
                sub_group_by=GroupAxis.PRIORITY,
            )
            assert len(r_mod.groups) > 0

            # 3. group_by=LABEL, sub_group_by=ASSIGNEE
            r_lbl = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                group_by=GroupAxis.LABEL,
                sub_group_by=GroupAxis.ASSIGNEE,
            )
            assert len(r_lbl.groups) > 0

            # 4. group_by=ASSIGNEE, sub_group_by=MODULE
            r_ass = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                group_by=GroupAxis.ASSIGNEE,
                sub_group_by=GroupAxis.MODULE,
            )
            assert len(r_ass.groups) > 0

            # 5. group_by=PRIORITY, sub_group_by=LABEL
            r_pri = await execute_view_query(
                session=rls_session,
                caller=caller,
                project=project,
                filters=FilterSpec(),
                group_by=GroupAxis.PRIORITY,
                sub_group_by=GroupAxis.LABEL,
            )
            assert len(r_pri.groups) > 0
    finally:
        await app_engine.dispose()

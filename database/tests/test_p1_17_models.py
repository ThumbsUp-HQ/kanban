"""Unit tests for SQLAlchemy 2.0 ORM models and schema parity (KANBA-55 / KB-P1-17)."""

import hashlib
import importlib.metadata
import sys
import uuid
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Base,
    Doc,
    EffectiveResourceAccess,
    Issue,
    LinkKind,
    LtreeType,
    ObjectKind,
    ObjectLink,
    ObjectRecord,
    Page,
    PageVersion,
    Project,
    ProjectPriority,
    Sticky,
    User,
    View,
    ViewLayout,
    WorkflowState,
    Workspace,
)

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import Dialect


@pytest.mark.asyncio
async def test_orm_schema_parity(db_session: AsyncSession) -> None:
    """Compare Base.metadata.tables against pg_tables for 1:1 set equality (Test Case 1)."""
    result = await db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' "
            "  AND tablename != 'alembic_version' "
            "  AND tablename NOT LIKE 'activity_records_y%' "
            "ORDER BY tablename;"
        )
    )
    pg_tables = {row[0] for row in result.all()}
    orm_tables = set(Base.metadata.tables.keys())

    # Exact set equality across all tables (54 tables incl. setup_claim_tokens)
    assert orm_tables == pg_tables
    assert len(orm_tables) == 54


async def _setup_test_project_spine(
    db_session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, WorkflowState, ProjectPriority]:
    """Provision workspace, user, and project, returning identifiers and default states."""
    ws_id = uuid.uuid4()
    ws = Workspace(id=ws_id, slug=f"ws-{ws_id.hex[:10]}", name="Parity Workspace")
    db_session.add(ws)
    await db_session.flush()

    u_id = uuid.uuid4()
    u_obj = ObjectRecord(
        id=u_id,
        object_type=ObjectKind.USER,
        workspace_id=ws_id,
        canonical_key=f"usr-{u_id.hex}",
        display_title="Test Engineer",
        created_by_id=u_id,
    )
    db_session.add(u_obj)
    await db_session.flush()

    user = User(
        id=u_id,
        object_type=ObjectKind.USER,
        principal_type="USER",
        workspace_id=ws_id,
        email="eng@example.com",
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws_id, 'Test Engineer')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )
    db_session.add(user)
    await db_session.flush()

    p_id = uuid.uuid4()
    p_obj = ObjectRecord(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        canonical_key="CORE",
        display_title="Core Project",
        created_by_id=u_id,
    )
    db_session.add(p_obj)
    await db_session.flush()

    project = Project(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        identifier="CORE",
        name="Core Project",
    )
    db_session.add(project)
    await db_session.flush()

    state_res = await db_session.execute(
        select(WorkflowState).where(
            WorkflowState.project_id == p_id, WorkflowState.is_default.is_(True)
        )
    )
    state = state_res.scalar_one()

    priority_res = await db_session.execute(
        select(ProjectPriority).where(
            ProjectPriority.project_id == p_id, ProjectPriority.slug == "medium"
        )
    )
    priority = priority_res.scalar_one()

    return ws_id, u_id, p_id, state, priority


@pytest.mark.asyncio
async def test_orm_round_trip_issues_and_knowledge(db_session: AsyncSession) -> None:
    """Verify round-trip ORM INSERT + SELECT on Issue, Doc, and Page with Computed SHA-256."""
    ws_id, u_id, p_id, state, priority = await _setup_test_project_spine(db_session)

    # 1. Issue with computed description_sha256 and search_tsv
    seq_id = await db_session.scalar(text("SELECT allocate_issue_sequence(:p_id)"), {"p_id": p_id})
    desc_text = "## High priority defect\nRequires immediate investigation."
    expected_desc_hash = hashlib.sha256(desc_text.encode("utf-8")).digest()
    iss_id = uuid.uuid4()
    iss_obj = ObjectRecord(
        id=iss_id,
        object_type=ObjectKind.ISSUE,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"CORE-{seq_id}",
        display_title="Defect 1",
        created_by_id=u_id,
    )
    db_session.add(iss_obj)
    await db_session.flush()

    issue = Issue(
        id=iss_id,
        object_type=ObjectKind.ISSUE,
        workspace_id=ws_id,
        project_id=p_id,
        sequence_id=seq_id,
        summary="Defect 1",
        description_markdown=desc_text,
        state_id=state.id,
        priority_id=priority.id,
        created_by_id=u_id,
        original_created_by_id=u_id,
        ancestry_path=str(seq_id),
        board_rank="0|hzzzzz:",
    )
    db_session.add(issue)
    await db_session.flush()

    fetched_issue = await db_session.get(Issue, iss_id)
    assert fetched_issue is not None
    assert fetched_issue.description_sha256 == expected_desc_hash
    assert fetched_issue.search_tsv is not None

    # 2. Doc and Page with computed body_sha256
    doc_text = "# Spec Document\nDetailed specification."
    expected_doc_hash = hashlib.sha256(doc_text.encode("utf-8")).digest()
    doc_id = uuid.uuid4()
    doc_obj = ObjectRecord(
        id=doc_id,
        object_type=ObjectKind.DOC,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"doc-{doc_id.hex[:6]}",
        display_title="Spec Document",
        created_by_id=u_id,
    )
    db_session.add(doc_obj)
    await db_session.flush()

    doc = Doc(
        id=doc_id,
        object_type=ObjectKind.DOC,
        workspace_id=ws_id,
        project_id=p_id,
        title="Spec Document",
        body_markdown=doc_text,
        hierarchy_path="spec",
    )
    db_session.add(doc)
    await db_session.flush()

    fetched_doc = await db_session.get(Doc, doc_id)
    assert fetched_doc is not None
    assert fetched_doc.body_sha256 == expected_doc_hash

    # 3. Page and PageVersion
    page_text = "Page content."
    expected_page_hash = hashlib.sha256(page_text.encode("utf-8")).digest()
    page_id = uuid.uuid4()
    page_obj = ObjectRecord(
        id=page_id,
        object_type=ObjectKind.PAGE,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"page-{page_id.hex[:6]}",
        display_title="Architecture Page",
        created_by_id=u_id,
    )
    db_session.add(page_obj)
    await db_session.flush()

    page = Page(
        id=page_id,
        object_type=ObjectKind.PAGE,
        workspace_id=ws_id,
        doc_id=doc_id,
        title="Architecture Page",
        body_markdown=page_text,
        hierarchy_path="spec.arch",
    )
    db_session.add(page)
    await db_session.flush()

    pv = PageVersion(
        page_id=page_id,
        version_seq=1,
        workspace_id=ws_id,
        title="Architecture Page v1",
        body_markdown=page_text,
        created_by_id=u_id,
    )
    db_session.add(pv)
    await db_session.flush()

    fetched_page = await db_session.get(Page, page_id)
    assert fetched_page is not None
    assert fetched_page.body_sha256 == expected_page_hash

    fetched_pv = await db_session.get(PageVersion, (page_id, 1))
    assert fetched_pv is not None
    assert fetched_pv.body_sha256 == expected_page_hash


@pytest.mark.asyncio
async def test_orm_round_trip_stickies_views_and_links(db_session: AsyncSession) -> None:
    """Verify round-trip ORM INSERT + SELECT on Sticky, View, ObjectLink, and ERA."""
    ws_id, u_id, p_id, _state, _priority = await _setup_test_project_spine(db_session)

    # 1. Sticky note
    sticky_text = "Quick note on architecture."
    expected_sticky_hash = hashlib.sha256(sticky_text.encode("utf-8")).digest()
    stk_id = uuid.uuid4()
    stk_obj = ObjectRecord(
        id=stk_id,
        object_type=ObjectKind.STICKY,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"stk-{stk_id.hex[:6]}",
        display_title="Sticky Note",
        created_by_id=u_id,
    )
    db_session.add(stk_obj)
    await db_session.flush()

    sticky = Sticky(
        id=stk_id,
        object_type=ObjectKind.STICKY,
        workspace_id=ws_id,
        project_id=p_id,
        body_markdown=sticky_text,
        color_token="sky",  # noqa: S106
    )
    db_session.add(sticky)
    await db_session.flush()

    fetched_sticky = await db_session.get(Sticky, stk_id)
    assert fetched_sticky is not None
    assert fetched_sticky.body_sha256 == expected_sticky_hash

    # 2. View
    view_text = "Board summary."
    expected_view_hash = hashlib.sha256(view_text.encode("utf-8")).digest()
    view_id = uuid.uuid4()
    view_obj = ObjectRecord(
        id=view_id,
        object_type=ObjectKind.VIEW,
        workspace_id=ws_id,
        project_id=p_id,
        canonical_key=f"view-{view_id.hex[:6]}",
        display_title="Main Board View",
        created_by_id=u_id,
    )
    db_session.add(view_obj)
    await db_session.flush()

    view = View(
        id=view_id,
        object_type=ObjectKind.VIEW,
        workspace_id=ws_id,
        project_id=p_id,
        owner_principal_id=u_id,
        name="Main Board View",
        summary_markdown=view_text,
        layout=ViewLayout.BOARD,
    )
    db_session.add(view)
    await db_session.flush()

    fetched_view = await db_session.get(View, view_id)
    assert fetched_view is not None
    assert fetched_view.summary_sha256 == expected_view_hash

    # 3. ObjectLink and EffectiveResourceAccess
    link_id = uuid.uuid4()
    link = ObjectLink(
        id=link_id,
        workspace_id=ws_id,
        source_id=stk_id,
        source_type=ObjectKind.STICKY,
        target_id=view_id,
        target_type=ObjectKind.VIEW,
        link_type=LinkKind.RELATES_TO,
        source_key_snapshot=f"stk-{stk_id.hex[:6]}",
        target_key_snapshot=f"view-{view_id.hex[:6]}",
        created_by_id=u_id,
    )
    db_session.add(link)
    await db_session.flush()

    fetched_link = await db_session.get(ObjectLink, link_id)
    assert fetched_link is not None
    assert fetched_link.link_state == "ACTIVE"

    era = EffectiveResourceAccess(
        object_id=stk_id,
        principal_id=u_id,
        workspace_id=ws_id,
        allow_mask=7,
        deny_mask=2,
    )
    db_session.add(era)
    await db_session.flush()

    fetched_era = await db_session.get(EffectiveResourceAccess, (stk_id, u_id))
    assert fetched_era is not None
    assert fetched_era.effective_mask == (7 & ~2)


def test_ltree_type_validation() -> None:
    """Verify LtreeType custom type validator rejects malformed paths and permits valid ltree."""
    ltree = LtreeType()
    assert ltree.get_col_spec() == "LTREE"

    dialect = cast("Dialect", DefaultDialect())
    proc = ltree.bind_processor(dialect)
    assert proc is not None
    assert proc(None) is None
    assert proc("root") == "root"
    assert proc("root.sub_1") == "root.sub_1"
    assert proc("a_1.b_2.c_3") == "a_1.b_2.c_3"

    res_proc = ltree.result_processor(dialect, None)
    assert res_proc is not None
    assert res_proc(None) is None
    assert res_proc("root.sub") == "root.sub"

    # Bad hyphen path must raise ValueError
    with pytest.raises(ValueError, match="Invalid ltree path: 'bad-hyphen-label'"):
        proc("bad-hyphen-label")

    with pytest.raises(ValueError, match="Invalid ltree path"):
        proc("bad..path")

    with pytest.raises(ValueError, match="Invalid ltree path"):
        proc("bad path with spaces")


def test_supply_chain_checks() -> None:
    """Verify banned packages (sqlmodel, sqlalchemy-utils) are completely absent."""
    assert "sqlmodel" not in sys.modules
    assert "sqlalchemy_utils" not in sys.modules

    installed = {dist.metadata["Name"].lower() for dist in importlib.metadata.distributions()}
    assert "sqlmodel" not in installed
    assert "sqlalchemy-utils" not in installed

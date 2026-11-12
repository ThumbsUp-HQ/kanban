"""Feature unit tests for prose tables: issue_comments, docs, pages, page_versions, stickies."""

import hashlib
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from database.tests.conftest import (
    bind_ctx,
    bind_workspace_admin,
    bootstrap_workspace_admin,
)


def _is_check_violation(exc: Exception) -> bool:
    """Return True if exception indicates a check constraint violation (23514)."""
    orig = getattr(exc, "orig", None)
    return getattr(exc, "sqlstate", None) == "23514" or getattr(orig, "sqlstate", None) == "23514"


def _is_generated_col_violation(exc: Exception) -> bool:
    """Return True if exception indicates SQLSTATE 428C9 (cannot insert into generated column)."""
    orig = getattr(exc, "orig", None)
    return getattr(exc, "sqlstate", None) == "428C9" or getattr(orig, "sqlstate", None) == "428C9"


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Prose Workspace",
) -> uuid.UUID:
    """Create a test workspace and bootstrap an admin principal context."""
    ws_id, _ = await bootstrap_workspace_admin(session, slug=slug, name=name)
    return ws_id


async def _create_user(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    email: str,
    display_name: str = "Prose User",
) -> uuid.UUID:
    """Create a user principal in principals, objects, and users tables."""
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
    await session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": u_id, "ws_id": workspace_id},
    )
    await bind_ctx(session, principal_id=u_id, workspace_id=workspace_id)
    return u_id


async def _create_project(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    identifier: str = "PRS",
    name: str = "Prose Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a project and return (project_id, default_state_id, default_priority_id)."""
    p_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, :ident, :name, :creator, :id"
            ")"
        ),
        {"ws": workspace_id, "ident": identifier, "name": name, "creator": creator_id, "id": p_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, :name)"
        ),
        {"id": p_id, "ws": workspace_id, "ident": identifier, "name": name},
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


async def _create_issue(
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    user_id: uuid.UUID,
    defaults: tuple[uuid.UUID, uuid.UUID],
) -> uuid.UUID:
    """Create a test issue with sequence allocation."""
    state_id, prio_id = defaults
    seq = (
        await session.execute(
            text("SELECT allocate_issue_sequence(:p)"),
            {"p": proj_id},
        )
    ).scalar_one()

    iss_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, 'Issue 1', :u, :id)"),
        {"ws": ws_id, "p": proj_id, "ckey": f"PRS-{seq}", "u": user_id, "id": iss_id},
    )
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  state_id, priority_id, created_by_id, original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws, :p, :seq, 'Issue Summary', :s, :pr, :u, :u, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "p": proj_id,
            "seq": seq,
            "s": state_id,
            "pr": prio_id,
            "u": user_id,
        },
    )
    return iss_id


async def _create_doc(
    session: AsyncSession,
    ws_id: uuid.UUID,
    creator_id: uuid.UUID,
    body: str = "",
    project_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register and insert a doc object."""
    d_id = uuid.uuid4()
    doc_title = f"Doc {d_id.hex[:8]}"
    await session.execute(
        text("SELECT register_object(  'doc'::object_kind, :ws, :p, :ckey, :title, :creator, :id)"),
        {
            "ws": ws_id,
            "p": project_id,
            "ckey": f"doc-{d_id.hex[:8]}",
            "title": doc_title,
            "creator": creator_id,
            "id": d_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
            "VALUES (:id, :ws, :p, :title, :body)"
        ),
        {"id": d_id, "ws": ws_id, "p": project_id, "title": doc_title, "body": body},
    )
    return d_id


async def _create_page(
    session: AsyncSession,
    doc_id: uuid.UUID,
    creator_id: uuid.UUID,
    body: str = "",
    parent_page_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register and insert a page object."""
    pg_id = uuid.uuid4()
    page_title = f"Page {pg_id.hex[:8]}"
    doc_row = (
        await session.execute(
            text("SELECT workspace_id, project_id FROM docs WHERE id = :d"),
            {"d": doc_id},
        )
    ).fetchone()
    assert doc_row is not None
    ws_id = doc_row.workspace_id
    doc_proj = doc_row.project_id

    await session.execute(
        text(
            "SELECT register_object(  'page'::object_kind, :ws, :p, :ckey, :title, :creator, :id)"
        ),
        {
            "ws": ws_id,
            "p": doc_proj,
            "ckey": f"pg-{pg_id.hex[:8]}",
            "title": page_title,
            "creator": creator_id,
            "id": pg_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO pages (id, workspace_id, doc_id, parent_page_id, title, body_markdown) "
            "VALUES (:id, :ws, :doc, :parent, :title, :body)"
        ),
        {
            "id": pg_id,
            "ws": ws_id,
            "doc": doc_id,
            "parent": parent_page_id,
            "title": page_title,
            "body": body,
        },
    )
    return pg_id


async def _create_sticky(
    session: AsyncSession,
    ws_id: uuid.UUID,
    creator_id: uuid.UUID,
    body: str = "Sticky body",
    palette_color: str = "amber",
) -> uuid.UUID:
    """Register and insert a sticky object."""
    stk_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'sticky'::object_kind, :ws, NULL::uuid, :ckey, 'Sticky Note', :creator, :id"
            ")"
        ),
        {
            "ws": ws_id,
            "ckey": f"stk-{stk_id.hex[:8]}",
            "creator": creator_id,
            "id": stk_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO stickies (id, workspace_id, project_id, body_markdown, color_token) "
            "VALUES (:id, :ws, NULL, :body, :col)"
        ),
        {"id": stk_id, "ws": ws_id, "body": body, "col": palette_color},
    )
    return stk_id


@pytest.mark.asyncio
async def test_01_prose_sha256_hash_verification(app_session: AsyncSession) -> None:
    """Verify comment, sticky, doc, and page body_sha256 match hashlib.sha256."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "author@example.com")
    proj, state, prio = await _create_project(app_session, ws, user)
    iss = await _create_issue(app_session, ws, proj, user, (state, prio))

    comment_body = "This is a **markdown** comment with `code`."
    doc_body = "# Comprehensive Architecture Spec\nDetailed text."
    page_body = "## Nested Subpage Content\nMore text."
    sticky_body = "Quick reminder: check token limits."

    # 1. Comment
    c_id = uuid.uuid4()
    await app_session.execute(
        text(
            "INSERT INTO issue_comments (id, workspace_id, issue_id, author_id, body_markdown) "
            "VALUES (:id, :ws, :iss, :u, :body)"
        ),
        {"id": c_id, "ws": ws, "iss": iss, "u": user, "body": comment_body},
    )
    c_row = (
        await app_session.execute(
            text("SELECT body_sha256 FROM issue_comments WHERE id = :id"),
            {"id": c_id},
        )
    ).fetchone()
    assert c_row is not None
    assert c_row.body_sha256 == hashlib.sha256(comment_body.encode("utf-8")).digest()

    # 2. Doc
    d_id = await _create_doc(app_session, ws, user, body=doc_body, project_id=proj)
    d_row = (
        await app_session.execute(
            text("SELECT body_sha256, hierarchy_path, version_seq FROM docs WHERE id = :id"),
            {"id": d_id},
        )
    ).fetchone()
    assert d_row is not None
    assert d_row.body_sha256 == hashlib.sha256(doc_body.encode("utf-8")).digest()
    assert d_row.version_seq == 1
    assert str(d_row.hierarchy_path) == f"d{d_id.hex}"

    # 3. Page
    pg_id = await _create_page(app_session, d_id, user, body=page_body)
    pg_row = (
        await app_session.execute(
            text("SELECT body_sha256, hierarchy_path, version_seq FROM pages WHERE id = :id"),
            {"id": pg_id},
        )
    ).fetchone()
    assert pg_row is not None
    assert pg_row.body_sha256 == hashlib.sha256(page_body.encode("utf-8")).digest()
    assert pg_row.version_seq == 1
    assert str(pg_row.hierarchy_path) == f"d{d_id.hex}.p{pg_id.hex}"

    # 4. Sticky
    stk_id = await _create_sticky(app_session, ws, user, body=sticky_body, palette_color="mint")
    stk_row = (
        await app_session.execute(
            text("SELECT body_sha256, color_token FROM stickies WHERE id = :id"),
            {"id": stk_id},
        )
    ).fetchone()
    assert stk_row is not None
    assert stk_row.body_sha256 == hashlib.sha256(sticky_body.encode("utf-8")).digest()
    assert stk_row.color_token == "mint"


@pytest.mark.asyncio
async def test_02_page_versioning_and_snapshots(app_session: AsyncSession) -> None:
    """Verify updating a page body twice yields version_seq=3 and two snapshot rows."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "editor@example.com")
    proj, _, _ = await _create_project(app_session, ws, user)
    d_id = await _create_doc(app_session, ws, user, project_id=proj)

    # Initial page insert (version_seq = 1)
    body_v1 = "Initial Draft Content"
    pg_id = await _create_page(app_session, d_id, user, body=body_v1)

    # First update: body change -> increments version_seq to 2, snapshots v1
    body_v2 = "Second Revision Content"
    await app_session.execute(
        text("UPDATE pages SET body_markdown = :body WHERE id = :id"),
        {"body": body_v2, "id": pg_id},
    )

    p_after_1 = (
        await app_session.execute(
            text("SELECT version_seq, body_markdown FROM pages WHERE id = :id"),
            {"id": pg_id},
        )
    ).fetchone()
    assert p_after_1 is not None
    assert p_after_1.version_seq == 2
    assert p_after_1.body_markdown == body_v2

    # Second update: body change -> increments version_seq to 3, snapshots v2
    body_v3 = "Third Final Revision Content"
    await app_session.execute(
        text("UPDATE pages SET body_markdown = :body WHERE id = :id"),
        {"body": body_v3, "id": pg_id},
    )

    p_after_2 = (
        await app_session.execute(
            text("SELECT version_seq, body_markdown FROM pages WHERE id = :id"),
            {"id": pg_id},
        )
    ).fetchone()
    assert p_after_2 is not None
    assert p_after_2.version_seq == 3
    assert p_after_2.body_markdown == body_v3

    # Query page_versions table
    v_rows = (
        await app_session.execute(
            text(
                "SELECT version_seq, title, body_markdown, body_sha256 "
                "FROM page_versions "
                "WHERE page_id = :id "
                "ORDER BY version_seq ASC"
            ),
            {"id": pg_id},
        )
    ).fetchall()
    assert len(v_rows) == 2
    assert v_rows[0].version_seq == 1
    assert v_rows[0].body_markdown == body_v1
    assert v_rows[0].body_sha256 == hashlib.sha256(body_v1.encode("utf-8")).digest()
    assert v_rows[1].version_seq == 2
    assert v_rows[1].body_markdown == body_v2
    assert v_rows[1].body_sha256 == hashlib.sha256(body_v2.encode("utf-8")).digest()

    # Also verify updating doc body increments doc.version_seq without page_versions rows
    doc_initial = (
        await app_session.execute(
            text("SELECT version_seq FROM docs WHERE id = :id"),
            {"id": d_id},
        )
    ).scalar_one()
    assert doc_initial == 1

    await app_session.execute(
        text("UPDATE docs SET body_markdown = '# Updated Doc Body' WHERE id = :id"),
        {"id": d_id},
    )
    doc_updated = (
        await app_session.execute(
            text("SELECT version_seq FROM docs WHERE id = :id"),
            {"id": d_id},
        )
    ).scalar_one()
    assert doc_updated == 2


@pytest.mark.asyncio
async def test_03_pages_hierarchy_tree_and_rebase(app_session: AsyncSession) -> None:
    """Verify tree hierarchy and reparenting rebases descendant ltree paths."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "tree@example.com")
    proj, _, _ = await _create_project(app_session, ws, user)

    d_id = await _create_doc(app_session, ws, user, project_id=proj)
    p1_id = await _create_page(app_session, d_id, user)
    p2_id = await _create_page(app_session, d_id, user, parent_page_id=p1_id)
    p3_id = await _create_page(app_session, d_id, user, parent_page_id=p2_id)

    # Initial paths: D.P1, D.P1.P2, D.P1.P2.P3
    d_label = f"d{d_id.hex}"
    p1_label = f"p{p1_id.hex}"
    p2_label = f"p{p2_id.hex}"
    p3_label = f"p{p3_id.hex}"

    paths_before = (
        await app_session.execute(
            text("SELECT id, hierarchy_path::text AS hp FROM pages WHERE doc_id = :d"),
            {"d": d_id},
        )
    ).fetchall()
    path_map_b = {r.id: r.hp for r in paths_before}
    assert path_map_b[p1_id] == f"{d_label}.{p1_label}"
    assert path_map_b[p2_id] == f"{d_label}.{p1_label}.{p2_label}"
    assert path_map_b[p3_id] == f"{d_label}.{p1_label}.{p2_label}.{p3_label}"

    # Move P2 under root of doc (parent_page_id = NULL)
    await app_session.execute(
        text("UPDATE pages SET parent_page_id = NULL WHERE id = :id"),
        {"id": p2_id},
    )

    paths_after = (
        await app_session.execute(
            text("SELECT id, hierarchy_path::text AS hp FROM pages WHERE doc_id = :d"),
            {"d": d_id},
        )
    ).fetchall()
    path_map_a = {r.id: r.hp for r in paths_after}
    assert path_map_a[p1_id] == f"{d_label}.{p1_label}"
    assert path_map_a[p2_id] == f"{d_label}.{p2_label}"
    assert path_map_a[p3_id] == f"{d_label}.{p2_label}.{p3_label}"


@pytest.mark.asyncio
async def test_05a_negative_color_cycle_and_hierarchy(app_session: AsyncSession) -> None:
    """Verify security rejections for invalid colors, cycles, and cross-doc parents."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "neg1@example.com")
    proj, _, _ = await _create_project(app_session, ws, user)
    d_id = await _create_doc(app_session, ws, user, project_id=proj)

    # 1. Invalid color raises 23514
    sp1 = await app_session.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError)) as exc1:
        await _create_sticky(app_session, ws, user, palette_color="red")
    assert _is_check_violation(exc1.value)
    await sp1.rollback()

    # 2. Page cycle: self-parent raises PAGE_CYCLE
    p1 = await _create_page(app_session, d_id, user)
    sp2 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc2:
        await app_session.execute(
            text("UPDATE pages SET parent_page_id = :id WHERE id = :id"),
            {"id": p1},
        )
    assert "PAGE_CYCLE" in str(exc2.value)
    await sp2.rollback()

    # 3. Page cycle: indirect cycle P1 <- P2; UPDATE P1 parent_page_id = P2
    p2 = await _create_page(app_session, d_id, user, parent_page_id=p1)
    sp3 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc3:
        await app_session.execute(
            text("UPDATE pages SET parent_page_id = :p2 WHERE id = :p1"),
            {"p1": p1, "p2": p2},
        )
    assert "PAGE_CYCLE" in str(exc3.value)
    await sp3.rollback()

    # 4. Parent page from another doc raises PAGE_PARENT_DOC_MISMATCH
    d2_id = await _create_doc(app_session, ws, user, project_id=proj)
    sp4 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc4:
        await _create_page(app_session, d2_id, user, parent_page_id=p1)
    assert "PAGE_PARENT_DOC_MISMATCH" in str(exc4.value)
    await sp4.rollback()


@pytest.mark.asyncio
async def test_05b_negative_immutability_and_promotions(  # noqa: PLR0915
    app_session: AsyncSession,
) -> None:
    """Verify security rejections for page version immutability and invalid sticky promotions."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "neg2@example.com")
    proj, state, prio = await _create_project(app_session, ws, user)
    iss = await _create_issue(app_session, ws, proj, user, (state, prio))
    d_id = await _create_doc(app_session, ws, user, project_id=proj)

    p1 = await _create_page(app_session, d_id, user)
    await app_session.execute(
        text("UPDATE pages SET body_markdown = 'New Body' WHERE id = :id"),
        {"id": p1},
    )

    # 1. Direct UPDATE page_versions raises PAGE_VERSION_IMMUTABLE
    sp1 = await app_session.begin_nested()
    await app_session.execute(text("RESET SESSION AUTHORIZATION"))
    with pytest.raises(DBAPIError) as exc1:
        await app_session.execute(
            text("UPDATE page_versions SET title = 'Tampered' WHERE page_id = :id"),
            {"id": p1},
        )
    assert "PAGE_VERSION_IMMUTABLE" in str(exc1.value)
    await sp1.rollback()
    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 2. Direct DELETE page_versions raises PAGE_VERSION_IMMUTABLE
    sp2 = await app_session.begin_nested()
    await app_session.execute(text("RESET SESSION AUTHORIZATION"))
    with pytest.raises(DBAPIError) as exc2:
        await app_session.execute(
            text("DELETE FROM page_versions WHERE page_id = :id"),
            {"id": p1},
        )
    assert "PAGE_VERSION_IMMUTABLE" in str(exc2.value)
    await sp2.rollback()
    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 3. Explicit body_sha256 insert raises 428C9 (cannot insert into generated column)
    sp3 = await app_session.begin_nested()
    with pytest.raises((ProgrammingError, DBAPIError)) as exc3:
        await app_session.execute(
            text(
                "INSERT INTO issue_comments ("
                "  id, workspace_id, issue_id, author_id, body_markdown, body_sha256"
                ") VALUES (:id, :ws, :iss, :u, 'Body', '\\x1234')"
            ),
            {"id": uuid.uuid4(), "ws": ws, "iss": iss, "u": user},
        )
    assert _is_generated_col_violation(exc3.value)
    await sp3.rollback()

    # 4. Parent comment belonging to another issue raises COMMENT_PARENT_MISMATCH
    iss2 = await _create_issue(app_session, ws, proj, user, (state, prio))
    c1 = uuid.uuid4()
    await app_session.execute(
        text(
            "INSERT INTO issue_comments (id, workspace_id, issue_id, author_id, body_markdown) "
            "VALUES (:id, :ws, :iss, :u, 'Comment 1 on issue 1')"
        ),
        {"id": c1, "ws": ws, "iss": iss, "u": user},
    )
    sp4 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc4:
        await app_session.execute(
            text(
                "INSERT INTO issue_comments ("
                "  id, workspace_id, issue_id, parent_comment_id, author_id, body_markdown"
                ") VALUES (:id, :ws, :iss2, :parent, :u, 'Cross-issue reply')"
            ),
            {"id": uuid.uuid4(), "ws": ws, "iss2": iss2, "parent": c1, "u": user},
        )
    assert "COMMENT_PARENT_MISMATCH" in str(exc4.value)
    await sp4.rollback()

    # 5. Stickies promotion: cross-workspace promotion raises STICKY_PROMOTION_INVALID
    stk = await _create_sticky(app_session, ws, user)
    ws2 = await _create_workspace(app_session, name="Other WS")
    user2 = await _create_user(app_session, ws2, "other@example.com")
    d_ws2 = await _create_doc(app_session, ws2, user2)
    await bind_ctx(app_session, principal_id=user, workspace_id=ws)
    sp5 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc5:
        await app_session.execute(
            text("UPDATE stickies SET promoted_to_doc_id = :d WHERE id = :stk"),
            {"d": d_ws2, "stk": stk},
        )
    assert "STICKY_PROMOTION_INVALID" in str(exc5.value)
    await sp5.rollback()

    # 6. Stickies promotion: valid promote and re-promotion rejection
    await bind_workspace_admin(app_session, ws)
    await app_session.execute(
        text("UPDATE stickies SET promoted_to_doc_id = :d WHERE id = :stk"),
        {"d": d_id, "stk": stk},
    )
    d_id3 = await _create_doc(app_session, ws, user, project_id=proj)
    sp6 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc6:
        await app_session.execute(
            text("UPDATE stickies SET promoted_to_doc_id = :d WHERE id = :stk"),
            {"d": d_id3, "stk": stk},
        )
    assert "STICKY_PROMOTION_INVALID" in str(exc6.value)
    await sp6.rollback()


@pytest.mark.asyncio
async def test_06_boundary_lengths_and_depth(app_session: AsyncSession) -> None:
    """Verify depth limit (10 allowed, 11 rejected) and exact body byte caps."""
    ws = await _create_workspace(app_session)
    user = await _create_user(app_session, ws, "bnd@example.com")
    proj, state, prio = await _create_project(app_session, ws, user)
    iss = await _create_issue(app_session, ws, proj, user, (state, prio))
    d_id = await _create_doc(app_session, ws, user, project_id=proj)

    # 1. Page depth boundary: build chain up to depth 10
    parent_id = None
    for _ in range(1, 11):
        parent_id = await _create_page(
            app_session,
            d_id,
            user,
            parent_page_id=parent_id,
        )

    # Inserting 11th level page must raise PAGE_MAX_DEPTH_EXCEEDED
    sp1 = await app_session.begin_nested()
    with pytest.raises(DBAPIError) as exc1:
        await _create_page(
            app_session,
            d_id,
            user,
            parent_page_id=parent_id,
        )
    assert "PAGE_MAX_DEPTH_EXCEEDED" in str(exc1.value)
    await sp1.rollback()

    # 2. Sticky body length: 65536 bytes accepted, 65537 rejected
    body_exact_sticky = "x" * 65536
    stk_valid = await _create_sticky(app_session, ws, user, body=body_exact_sticky)
    assert stk_valid is not None

    sp2 = await app_session.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError)) as exc2:
        await _create_sticky(app_session, ws, user, body="x" * 65537)
    assert _is_check_violation(exc2.value)
    await sp2.rollback()

    # 3. Comment body length: empty body rejected, 262144 accepted, 262145 rejected
    sp3 = await app_session.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError)) as exc3:
        await app_session.execute(
            text(
                "INSERT INTO issue_comments ("
                "  id, workspace_id, issue_id, author_id, body_markdown"
                ") VALUES (:id, :ws, :iss, :u, '')"
            ),
            {"id": uuid.uuid4(), "ws": ws, "iss": iss, "u": user},
        )
    assert _is_check_violation(exc3.value)
    await sp3.rollback()

    body_max_comment = "c" * 262144
    c_valid = uuid.uuid4()
    await app_session.execute(
        text(
            "INSERT INTO issue_comments ("
            "  id, workspace_id, issue_id, author_id, body_markdown"
            ") VALUES (:id, :ws, :iss, :u, :body)"
        ),
        {"id": c_valid, "ws": ws, "iss": iss, "u": user, "body": body_max_comment},
    )
    assert c_valid is not None

    sp4 = await app_session.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError)) as exc4:
        await app_session.execute(
            text(
                "INSERT INTO issue_comments ("
                "  id, workspace_id, issue_id, author_id, body_markdown"
                ") VALUES (:id, :ws, :iss, :u, :body)"
            ),
            {"id": uuid.uuid4(), "ws": ws, "iss": iss, "u": user, "body": "c" * 262145},
        )
    assert _is_check_violation(exc4.value)
    await sp4.rollback()

    # 4. Doc body length: 1048576 accepted, 1048577 rejected
    body_max_doc = "d" * 1048576
    d_valid = await _create_doc(app_session, ws, user, body=body_max_doc, project_id=proj)
    assert d_valid is not None

    sp5 = await app_session.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError)) as exc5:
        await _create_doc(app_session, ws, user, body="d" * 1048577, project_id=proj)
    assert _is_check_violation(exc5.value)
    await sp5.rollback()

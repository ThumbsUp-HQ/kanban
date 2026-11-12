"""Feature unit tests for Phase 1 parent DAG hierarchy and ltree triggers."""

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ParentDagContext:
    """Project and user context for parent DAG tests."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    identifier: str
    user_id: uuid.UUID
    state_id: uuid.UUID
    priority_id: uuid.UUID


def _label(u: uuid.UUID) -> str:
    """Format UUID as an ltree label (hex without hyphens)."""
    return u.hex


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace and return its UUID."""
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
            "ckey": email,
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


async def _create_project_with_defaults(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    identifier: str,
    name: str = "Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register and create project, returning (project_id, state_id, priority_id)."""
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
            "creator": user_id,
            "id": p_id,
        },
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
    assert isinstance(state_id, uuid.UUID)

    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    prio_id = prio_row.scalar_one()
    assert isinstance(prio_id, uuid.UUID)

    return p_id, state_id, prio_id


async def _create_issue(
    session: AsyncSession,
    ctx: ParentDagContext,
    summary: str = "Sample Issue",
    parent_issue_id: uuid.UUID | None = None,
    custom_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create an issue in objects and issues tables."""
    seq_row = await session.execute(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": ctx.project_id},
    )
    seq = seq_row.scalar_one()
    assert isinstance(seq, int)

    i_id = custom_id or uuid.uuid4()
    canonical_key = f"{ctx.identifier}-{seq}"

    await session.execute(
        text(
            "SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, :summary, :user, :id)"
        ),
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
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, board_rank, parent_issue_id"
            ") VALUES ("
            "  :id, :ws, :p, :seq, :summary, "
            "  '', :state, :prio, "
            "  :user, :user, '0|hzzzzz:', :parent_id"
            ")"
        ),
        {
            "id": i_id,
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "seq": seq,
            "summary": summary,
            "state": ctx.state_id,
            "prio": ctx.priority_id,
            "user": ctx.user_id,
            "parent_id": parent_issue_id,
        },
    )
    return i_id


async def _get_ancestry(session: AsyncSession, issue_id: uuid.UUID) -> tuple[str, int]:
    """Fetch (ancestry_path, nlevel) for an issue."""
    row = await session.execute(
        text(
            "SELECT ancestry_path::text AS path, nlevel(ancestry_path) AS depth "
            "FROM issues WHERE id = :id"
        ),
        {"id": issue_id},
    )
    r = row.mappings().one()
    return str(r["path"]), int(r["depth"])


async def _setup_context(session: AsyncSession, identifier: str = "DAG") -> ParentDagContext:
    """Set up workspace, user, and project context."""
    ws_id = await _create_workspace(session)
    u_id = await _create_user(session, ws_id, f"user-{uuid.uuid4().hex[:8]}@example.com")
    p_id, s_id, prio_id = await _create_project_with_defaults(
        session, ws_id, u_id, identifier=identifier
    )
    return ParentDagContext(
        workspace_id=ws_id,
        project_id=p_id,
        identifier=identifier,
        user_id=u_id,
        state_id=s_id,
        priority_id=prio_id,
    )


@pytest.mark.asyncio
async def test_01_positive_hierarchy_path_and_depth(db_session: AsyncSession) -> None:
    """Verify A (root) <- B <- C establishes correct ancestry_path and depth."""
    ctx = await _setup_context(db_session, identifier="POS")

    a_id = await _create_issue(db_session, ctx, summary="Issue A")
    b_id = await _create_issue(db_session, ctx, summary="Issue B", parent_issue_id=a_id)
    c_id = await _create_issue(db_session, ctx, summary="Issue C", parent_issue_id=b_id)

    a_path, a_depth = await _get_ancestry(db_session, a_id)
    assert a_path == _label(a_id)
    assert a_depth == 1

    b_path, b_depth = await _get_ancestry(db_session, b_id)
    assert b_path == f"{_label(a_id)}.{_label(b_id)}"
    assert b_depth == 2

    c_path, c_depth = await _get_ancestry(db_session, c_id)
    expected_c_path = f"{_label(a_id)}.{_label(b_id)}.{_label(c_id)}"
    assert c_path == expected_c_path
    assert c_depth == 3


@pytest.mark.asyncio
async def test_02_positive_subtree_move_and_rebase(db_session: AsyncSession) -> None:
    """Verify reparenting B from A to X rebases B and all descendants under X."""
    ctx = await _setup_context(db_session, identifier="SUB")

    a_id = await _create_issue(db_session, ctx, summary="Root A")
    b_id = await _create_issue(db_session, ctx, summary="Sub B", parent_issue_id=a_id)
    c_id = await _create_issue(db_session, ctx, summary="Child C", parent_issue_id=b_id)
    x_id = await _create_issue(db_session, ctx, summary="Root X")

    # Initial paths
    b_path_pre, _ = await _get_ancestry(db_session, b_id)
    assert b_path_pre == f"{_label(a_id)}.{_label(b_id)}"
    c_path_pre, _ = await _get_ancestry(db_session, c_id)
    assert c_path_pre == f"{_label(a_id)}.{_label(b_id)}.{_label(c_id)}"

    # Move B under X
    await db_session.execute(
        text("UPDATE issues SET parent_issue_id = :x WHERE id = :b"),
        {"x": x_id, "b": b_id},
    )

    # Post-move verification
    b_path_post, b_depth_post = await _get_ancestry(db_session, b_id)
    assert b_path_post == f"{_label(x_id)}.{_label(b_id)}"
    assert b_depth_post == 2

    c_path_post, c_depth_post = await _get_ancestry(db_session, c_id)
    assert c_path_post == f"{_label(x_id)}.{_label(b_id)}.{_label(c_id)}"
    assert c_depth_post == 3

    # A now has no descendants
    desc_row = await db_session.execute(
        text("SELECT count(*) FROM issues WHERE ancestry_path <@ text2ltree(:a_lbl) AND id <> :a"),
        {"a_lbl": _label(a_id), "a": a_id},
    )
    assert desc_row.scalar_one() == 0


@pytest.mark.asyncio
async def test_03_negative_cycles_and_self_reference(db_session: AsyncSession) -> None:
    """Verify cycle detection and self-parent rejection."""
    ctx = await _setup_context(db_session, identifier="CYC")

    a_id = await _create_issue(db_session, ctx, summary="Node A")
    b_id = await _create_issue(db_session, ctx, summary="Node B", parent_issue_id=a_id)
    c_id = await _create_issue(db_session, ctx, summary="Node C", parent_issue_id=b_id)

    # 1. 2-node cycle: A under B when A is parent of B
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :b WHERE id = :a"),
                {"b": b_id, "a": a_id},
            )
    assert "PARENT_CYCLE" in str(exc_info.value)

    # 2. 3-node cycle: A under C when A is ancestor of C
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :c WHERE id = :a"),
                {"c": c_id, "a": a_id},
            )
    assert "PARENT_CYCLE" in str(exc_info.value)

    # 3. Self-reference on UPDATE
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :a WHERE id = :a"),
                {"a": a_id},
            )
    assert "PARENT_SELF_REFERENCE" in str(exc_info.value)

    # 4. Self-reference on INSERT
    self_id = uuid.uuid4()
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await _create_issue(
                db_session,
                ctx,
                summary="Self Insert",
                parent_issue_id=self_id,
                custom_id=self_id,
            )
    assert "PARENT_SELF_REFERENCE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_04_negative_depth_limits(db_session: AsyncSession) -> None:
    """Verify maximum tree depth of 6 is enforced on insert and subtree move."""
    ctx = await _setup_context(db_session, identifier="DEP")

    # Build chain of 6 levels: N1 -> N2 -> N3 -> N4 -> N5 -> N6
    nodes: list[uuid.UUID] = []
    parent: uuid.UUID | None = None
    for i in range(1, 7):
        n_id = await _create_issue(db_session, ctx, summary=f"Level {i}", parent_issue_id=parent)
        nodes.append(n_id)
        parent = n_id

    # Level 6 node has depth 6
    _, n6_depth = await _get_ancestry(db_session, nodes[5])
    assert n6_depth == 6

    # Inserting 7th-level child raises PARENT_MAX_DEPTH_EXCEEDED
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await _create_issue(db_session, ctx, summary="Level 7", parent_issue_id=nodes[5])
    assert "PARENT_MAX_DEPTH_EXCEEDED" in str(exc_info.value) or "issues_ancestry_depth_chk" in str(
        exc_info.value
    )

    # Build a separate 3-level subtree: S1 -> S2 -> S3
    s1_id = await _create_issue(db_session, ctx, summary="Subtree Root S1")
    s2_id = await _create_issue(db_session, ctx, summary="Subtree Child S2", parent_issue_id=s1_id)
    await _create_issue(db_session, ctx, summary="Subtree Grandchild S3", parent_issue_id=s2_id)

    # Moving 3-level subtree (height 2) under Level 4 node (depth 4):
    # 4 + 1 + 2 = 7 > 6 -> raises PARENT_MAX_DEPTH_EXCEEDED
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :target WHERE id = :subtree_root"),
                {"target": nodes[3], "subtree_root": s1_id},
            )
    assert "PARENT_MAX_DEPTH_EXCEEDED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_05_negative_cross_project_and_nonexistent_parent(
    db_session: AsyncSession,
) -> None:
    """Verify parent in another project and nonexistent parent are rejected."""
    ctx_a = await _setup_context(db_session, identifier="PJA")
    ctx_b = await _setup_context(db_session, identifier="PJB")

    parent_a = await _create_issue(db_session, ctx_a, summary="Project A Parent")

    # 1. Insert issue in Project B with parent in Project A -> PARENT_CROSS_PROJECT
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await _create_issue(
                db_session, ctx_b, summary="Cross Project Insert", parent_issue_id=parent_a
            )
    assert "PARENT_CROSS_PROJECT" in str(exc_info.value)

    # 2. Update issue in Project B with parent in Project A -> PARENT_CROSS_PROJECT
    issue_b = await _create_issue(db_session, ctx_b, summary="Issue in B")
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :p WHERE id = :i"),
                {"p": parent_a, "i": issue_b},
            )
    assert "PARENT_CROSS_PROJECT" in str(exc_info.value)

    # 3. Nonexistent parent on insert -> PARENT_NOT_FOUND or foreign key violation (23503)
    fake_parent = uuid.uuid4()
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await _create_issue(
                db_session, ctx_a, summary="Ghost Parent", parent_issue_id=fake_parent
            )
    err = str(exc_info.value)
    assert "PARENT_NOT_FOUND" in err or "23503" in err

    # 4. Nonexistent parent on update -> PARENT_NOT_FOUND or 23503
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET parent_issue_id = :p WHERE id = :i"),
                {"p": fake_parent, "i": parent_a},
            )
    err = str(exc_info.value)
    assert "PARENT_NOT_FOUND" in err or "23503" in err


@pytest.mark.asyncio
async def test_06_boundary_parent_delete_and_unparent(db_session: AsyncSession) -> None:
    """Verify unparenting B (setting parent_issue_id = NULL) promotes B to root and rebases C."""
    ctx = await _setup_context(db_session, identifier="UNP")

    a_id = await _create_issue(db_session, ctx, summary="Root A")
    b_id = await _create_issue(db_session, ctx, summary="Sub B", parent_issue_id=a_id)
    c_id = await _create_issue(db_session, ctx, summary="Child C", parent_issue_id=b_id)

    # Unparent B (simulates ON DELETE SET NULL on parent deletion)
    await db_session.execute(
        text("UPDATE issues SET parent_issue_id = NULL WHERE id = :b"),
        {"b": b_id},
    )

    # B becomes a root issue with depth 1
    b_path, b_depth = await _get_ancestry(db_session, b_id)
    assert b_path == _label(b_id)
    assert b_depth == 1

    # C is rebased to B.C with depth 2
    c_path, c_depth = await _get_ancestry(db_session, c_id)
    assert c_path == f"{_label(b_id)}.{_label(c_id)}"
    assert c_depth == 2

    # A has no descendants
    desc_row = await db_session.execute(
        text("SELECT count(*) FROM issues WHERE ancestry_path <@ text2ltree(:a_lbl) AND id <> :a"),
        {"a_lbl": _label(a_id), "a": a_id},
    )
    assert desc_row.scalar_one() == 0

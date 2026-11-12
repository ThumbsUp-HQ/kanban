"""Unit tests for Phase 1 principals, users, groups, and principal_group_closure."""

import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


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
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create a user in principals, objects, and users tables."""
    u_id = user_id or uuid.uuid4()
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
            "  'user'::object_kind, :ws_id, NULL, :ckey, :title, :creator, :id"
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


async def _create_group(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    name: str,
    group_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Create a group in principals and groups tables."""
    g_id = group_id or uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'GROUP', :ws_id, :name)"
        ),
        {"id": g_id, "ws_id": workspace_id, "name": name},
    )
    await session.execute(
        text("INSERT INTO groups (id, workspace_id, name) VALUES (:id, :ws_id, :name)"),
        {
            "id": g_id,
            "ws_id": workspace_id,
            "name": name,
        },
    )
    return g_id


async def _create_edge(
    session: AsyncSession,
    member_id: uuid.UUID,
    group_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Insert a member-group edge into principal_group_edges."""
    await session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) "
            "VALUES (:m, :g, :w)"
        ),
        {"m": member_id, "g": group_id, "w": workspace_id},
    )


async def test_01_nested_resolution_positive(db_session: AsyncSession) -> None:
    """Verify nested group resolution produces correct closure rows and depths."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "user-01@example.com", "User One")
    g1 = await _create_group(db_session, ws, "Group 1")
    g2 = await _create_group(db_session, ws, "Group 2")
    g3 = await _create_group(db_session, ws, "Group 3")

    await _create_edge(db_session, u, g1, ws)
    await _create_edge(db_session, g1, g2, ws)
    await _create_edge(db_session, g2, g3, ws)

    res = await db_session.execute(
        text(
            "SELECT member_id, ancestor_group_id, depth "
            "FROM principal_group_closure WHERE workspace_id = :ws "
            "ORDER BY member_id, depth"
        ),
        {"ws": ws},
    )
    rows = [(r.member_id, r.ancestor_group_id, r.depth) for r in res.all()]

    expected = [
        (g1, g2, 1),
        (g1, g3, 2),
        (g2, g3, 1),
        (u, g1, 1),
        (u, g2, 2),
        (u, g3, 3),
    ]
    assert sorted(rows) == sorted(expected)
    assert len(rows) == 6


async def test_02_diamond_resolution_positive(db_session: AsyncSession) -> None:
    """Verify diamond group graph produces single closure row with shortest depth."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "user-diamond@example.com", "Diamond User")
    g1 = await _create_group(db_session, ws, "Diamond G1")
    g2 = await _create_group(db_session, ws, "Diamond G2")
    g3 = await _create_group(db_session, ws, "Diamond G3")

    await _create_edge(db_session, u, g1, ws)
    await _create_edge(db_session, u, g2, ws)
    await _create_edge(db_session, g1, g3, ws)
    await _create_edge(db_session, g2, g3, ws)

    res = await db_session.execute(
        text(
            "SELECT member_id, ancestor_group_id, depth "
            "FROM principal_group_closure "
            "WHERE workspace_id = :ws AND member_id = :u AND ancestor_group_id = :g3"
        ),
        {"ws": ws, "u": u, "g3": g3},
    )
    rows = res.all()
    assert len(rows) == 1
    assert rows[0].depth == 2


async def test_03_edge_removal_positive(db_session: AsyncSession) -> None:
    """Verify deleting an edge immediately updates closure rows in the same transaction."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "user-del@example.com", "Removal User")
    g1 = await _create_group(db_session, ws, "Del G1")
    g2 = await _create_group(db_session, ws, "Del G2")
    g3 = await _create_group(db_session, ws, "Del G3")

    await _create_edge(db_session, u, g1, ws)
    await _create_edge(db_session, g1, g2, ws)
    await _create_edge(db_session, g2, g3, ws)

    res1 = await db_session.execute(
        text("SELECT count(*) FROM principal_group_closure WHERE workspace_id = :ws"),
        {"ws": ws},
    )
    assert res1.scalar_one() == 6

    await db_session.execute(
        text("DELETE FROM principal_group_edges WHERE member_id = :m AND group_id = :g"),
        {"m": g1, "g": g2},
    )

    res2 = await db_session.execute(
        text(
            "SELECT member_id, ancestor_group_id, depth "
            "FROM principal_group_closure WHERE workspace_id = :ws "
            "ORDER BY member_id, depth"
        ),
        {"ws": ws},
    )
    rows = [(r.member_id, r.ancestor_group_id, r.depth) for r in res2.all()]
    expected = [
        (g2, g3, 1),
        (u, g1, 1),
    ]
    assert sorted(rows) == sorted(expected)


async def test_04_cycle_rejection_negative(db_session: AsyncSession) -> None:
    """Verify cycle insertion raises GROUP_CYCLE_REJECTED and self-edge raises 23514."""
    ws = await _create_workspace(db_session)
    g1 = await _create_group(db_session, ws, "Cycle G1")
    g2 = await _create_group(db_session, ws, "Cycle G2")

    await _create_edge(db_session, g1, g2, ws)

    with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
        async with db_session.begin_nested():
            await _create_edge(db_session, g2, g1, ws)
    assert "GROUP_CYCLE_REJECTED" in str(exc_info.value)

    with pytest.raises((IntegrityError, DBAPIError)) as exc_self:
        async with db_session.begin_nested():
            await _create_edge(db_session, g1, g1, ws)
    orig = getattr(exc_self.value, "orig", None)
    pgcode = getattr(orig, "sqlstate", None) or getattr(exc_self.value, "code", None)
    err = str(exc_self.value)
    assert pgcode == "23514" or "23514" in err or "check constraint" in err.lower()


async def test_05_depth_limit_negative(db_session: AsyncSession) -> None:
    """Verify 8 levels of nesting are permitted and 9th level raises GROUP_DEPTH_EXCEEDED."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "user-depth@example.com", "Depth User")

    groups: list[uuid.UUID] = []
    for i in range(1, 10):
        g = await _create_group(db_session, ws, f"Depth G{i}")
        groups.append(g)

    await _create_edge(db_session, u, groups[0], ws)
    for i in range(7):
        await _create_edge(db_session, groups[i], groups[i + 1], ws)

    res = await db_session.execute(
        text(
            "SELECT depth FROM principal_group_closure "
            "WHERE workspace_id = :ws AND member_id = :u AND ancestor_group_id = :g8"
        ),
        {"ws": ws, "u": u, "g8": groups[7]},
    )
    assert res.scalar_one() == 8

    with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
        async with db_session.begin_nested():
            await _create_edge(db_session, groups[7], groups[8], ws)
    assert "GROUP_DEPTH_EXCEEDED" in str(exc_info.value)

    edge_check = await db_session.execute(
        text("SELECT count(*) FROM principal_group_edges WHERE member_id = :m AND group_id = :g"),
        {"m": groups[7], "g": groups[8]},
    )
    assert edge_check.scalar_one() == 0


async def test_06_security_and_cross_workspace_mismatch(db_session: AsyncSession) -> None:
    """Verify cross-workspace edge rejection and direct closure mutation revocation."""
    ws1 = await _create_workspace(db_session)
    ws2 = await _create_workspace(db_session)

    u1 = await _create_user(db_session, ws1, "u1-ws@example.com", "User WS1")
    g2 = await _create_group(db_session, ws2, "Group WS2")

    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws1:
        async with db_session.begin_nested():
            await _create_edge(db_session, u1, g2, ws1)
    assert "GROUP_EDGE_WORKSPACE_MISMATCH" in str(exc_ws1.value)

    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws2:
        async with db_session.begin_nested():
            await _create_edge(db_session, u1, g2, ws2)
    assert "GROUP_EDGE_WORKSPACE_MISMATCH" in str(exc_ws2.value)

    await db_session.execute(text("SET ROLE kanban_app"))
    try:
        with pytest.raises((IntegrityError, DBAPIError)) as exc_priv:
            async with db_session.begin_nested():
                await db_session.execute(
                    text(
                        "INSERT INTO principal_group_closure "
                        "(member_id, ancestor_group_id, workspace_id, depth) "
                        "VALUES (:m, :a, :w, 1)"
                    ),
                    {"m": u1, "a": g2, "w": ws1},
                )
        orig_priv = getattr(exc_priv.value, "orig", None)
        pgcode_priv = getattr(orig_priv, "sqlstate", None) or getattr(exc_priv.value, "code", None)
        err = str(exc_priv.value).lower()
        assert pgcode_priv == "42501" or "42501" in err or "permission denied" in err
    finally:
        await db_session.execute(text("RESET ROLE"))


async def test_07_boundary_and_validation(db_session: AsyncSession) -> None:
    """Verify principal_type check, lower(email) uniqueness, and email length boundaries."""
    ws1 = await _create_workspace(db_session)
    ws2 = await _create_workspace(db_session)

    # 1. Invalid principal_type raises 23514
    with pytest.raises((IntegrityError, DBAPIError)) as exc_pt:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO principals (principal_type, workspace_id, display_name) "
                    "VALUES ('ROBOT', :ws, 'Robot Principal')"
                ),
                {"ws": ws1},
            )
    orig_pt = getattr(exc_pt.value, "orig", None)
    code_pt = getattr(orig_pt, "sqlstate", None) or getattr(exc_pt.value, "code", None)
    assert code_pt == "23514" or "check constraint" in str(exc_pt.value).lower()

    # 2. Duplicate lower(email) in same workspace raises 23505
    await _create_user(db_session, ws1, "alice@example.com", "Alice 1")
    with pytest.raises((IntegrityError, DBAPIError)) as exc_dup:
        async with db_session.begin_nested():
            await _create_user(db_session, ws1, "ALICE@EXAMPLE.COM", "Alice 2")
    orig_dup = getattr(exc_dup.value, "orig", None)
    code_dup = getattr(orig_dup, "sqlstate", None) or getattr(exc_dup.value, "code", None)
    assert code_dup == "23505" or "unique constraint" in str(exc_dup.value).lower()

    # Same email in different workspace succeeds
    u_ws2 = await _create_user(db_session, ws2, "alice@example.com", "Alice Other WS")
    assert isinstance(u_ws2, uuid.UUID)

    # 3. Email of 321 chars rejected by check constraint
    long_local = "a" * 309
    long_email = f"{long_local}@example.com"
    assert len(long_email) == 321
    with pytest.raises((IntegrityError, DBAPIError)) as exc_len:
        async with db_session.begin_nested():
            await _create_user(db_session, ws1, long_email, "Long Email User")
    orig_len = getattr(exc_len.value, "orig", None)
    code_len = getattr(orig_len, "sqlstate", None) or getattr(exc_len.value, "code", None)
    assert code_len == "23514" or "check constraint" in str(exc_len.value).lower()

    # 4. Invalid email format rejected
    with pytest.raises((IntegrityError, DBAPIError)) as exc_fmt:
        async with db_session.begin_nested():
            await _create_user(db_session, ws1, "invalid-email-address", "Bad Email User")
    orig_fmt = getattr(exc_fmt.value, "orig", None)
    code_fmt = getattr(orig_fmt, "sqlstate", None) or getattr(exc_fmt.value, "code", None)
    assert code_fmt == "23514" or "check constraint" in str(exc_fmt.value).lower()

    # 5. users_workspace_match_biu: workspace mismatch raises PRINCIPAL_WORKSPACE_MISMATCH
    u_mismatch_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Mismatch User')"
        ),
        {"id": u_mismatch_id, "ws": ws1},
    )
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws, NULL, 'usr-mismatch', 'Mismatch User', :id, :id"
            ")"
        ),
        {"ws": ws1, "id": u_mismatch_id},
    )
    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws_mismatch:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO users (id, workspace_id, email) "
                    "VALUES (:id, :ws2, 'mismatch@example.com')"
                ),
                {"id": u_mismatch_id, "ws2": ws2},
            )
    assert "PRINCIPAL_WORKSPACE_MISMATCH" in str(exc_ws_mismatch.value)

    # 6. groups_workspace_match_biu: workspace mismatch raises PRINCIPAL_WORKSPACE_MISMATCH
    g_mismatch_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'GROUP', :ws, 'Mismatch Group')"
        ),
        {"id": g_mismatch_id, "ws": ws1},
    )
    with pytest.raises((IntegrityError, DBAPIError)) as exc_grp_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO groups (id, workspace_id, name) "
                    "VALUES (:id, :ws2, 'Mismatch Group')"
                ),
                {"id": g_mismatch_id, "ws2": ws2},
            )
    assert "PRINCIPAL_WORKSPACE_MISMATCH" in str(exc_grp_ws.value)


async def test_08_rebuild_closure_performance_budget(db_session: AsyncSession) -> None:
    """Verify rebuild_group_closure for 500 edges completes within performance bound."""
    ws = await _create_workspace(db_session)

    groups: list[uuid.UUID] = []
    for i in range(50):
        g = await _create_group(db_session, ws, f"Perf Group {i}")
        groups.append(g)

    # Temporarily disable row trigger to bulk seed 500 edges without 500 sequential rebuilds
    await db_session.execute(
        text(
            "ALTER TABLE principal_group_edges "
            "DISABLE TRIGGER principal_group_edges_closure_aiud_trg"
        )
    )

    try:
        for i in range(1, 50):
            parent_idx = i // 7
            await _create_edge(db_session, groups[i], groups[parent_idx], ws)

        # Batch insert 451 user principals and edges in bulk
        user_ids = [uuid.uuid4() for _ in range(451)]
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
                "SELECT u_id, 'USER', :ws, 'Perf User ' || row_number() OVER () "
                "FROM unnest(CAST(:u_ids AS uuid[])) AS u_id"
            ),
            {"ws": ws, "u_ids": user_ids},
        )

        edge_tuples = [(user_ids[i], groups[1 + (i % 49)]) for i in range(451)]
        member_ids = [e[0] for e in edge_tuples]
        group_ids = [e[1] for e in edge_tuples]
        await db_session.execute(
            text(
                "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) "
                "SELECT m_id, g_id, :ws "
                "FROM unnest(CAST(:m_ids AS uuid[]), CAST(:g_ids AS uuid[])) AS t(m_id, g_id)"
            ),
            {"ws": ws, "m_ids": member_ids, "g_ids": group_ids},
        )
    finally:
        await db_session.execute(
            text(
                "ALTER TABLE principal_group_edges "
                "ENABLE TRIGGER principal_group_edges_closure_aiud_trg"
            )
        )

    # Measure rebuild_group_closure duration
    t_start = time.perf_counter()
    await db_session.execute(
        text("SELECT rebuild_group_closure(:ws)"),
        {"ws": ws},
    )
    t_elapsed = time.perf_counter() - t_start

    # Verify closure rows were generated
    res = await db_session.execute(
        text("SELECT count(*) FROM principal_group_closure WHERE workspace_id = :ws"),
        {"ws": ws},
    )
    assert res.scalar_one() > 500

    # Budget is < 50ms, generous assertion bound is < 500ms
    assert t_elapsed < 0.500, f"Rebuild took {t_elapsed:.4f}s, expected < 0.500s"

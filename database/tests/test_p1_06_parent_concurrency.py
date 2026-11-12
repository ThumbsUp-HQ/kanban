"""Concurrency tests for parent DAG triggers and opposite reparenting."""

import asyncio
import os
import uuid

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def _seed_concurrency_issues(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed workspace, user, project, and two root issues for concurrency testing."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    user_id = uuid.uuid4()
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()

    # 1. Workspace
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Conc WS')"),
        {"id": ws_id, "slug": f"ws-conc-{uuid.uuid4().hex[:8]}"},
    )

    # 2. User
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Conc User')"
        ),
        {"id": user_id, "ws": ws_id},
    )
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws, NULL::uuid, :ckey, 'Conc User', :u, :id"
            ")"
        ),
        {"ws": ws_id, "ckey": f"conc-{user_id.hex[:8]}@example.com", "u": user_id, "id": user_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws, :email)"),
        {"id": user_id, "ws": ws_id, "email": f"conc-{user_id.hex[:8]}@example.com"},
    )

    # 3. Project
    await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, 'OPP', 'Opp Project', :u, :id"
            ")"
        ),
        {"ws": ws_id, "u": user_id, "id": proj_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, 'OPP', 'Opp Project')"
        ),
        {"id": proj_id, "ws": ws_id},
    )

    state_row = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND is_default = true"),
        {"p": proj_id},
    )
    state_id = state_row.scalar_one()

    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": proj_id},
    )
    prio_id = prio_row.scalar_one()

    # 4. Issue A and Issue B
    for i_id, seq, summary in ((a_id, 1, "Issue A"), (b_id, 2, "Issue B")):
        await session.execute(
            text(
                "SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, :summary, :u, :id)"
            ),
            {
                "ws": ws_id,
                "p": proj_id,
                "ckey": f"OPP-{seq}",
                "summary": summary,
                "u": user_id,
                "id": i_id,
            },
        )
        await session.execute(
            text("SELECT allocate_issue_sequence(:p)"),
            {"p": proj_id},
        )
        await session.execute(
            text(
                "INSERT INTO issues ("
                "  id, workspace_id, project_id, sequence_id, summary, "
                "  description_markdown, state_id, priority_id, "
                "  created_by_id, original_created_by_id, board_rank"
                ") VALUES ("
                "  :id, :ws, :p, :seq, :summary, "
                "  '', :s, :pr, :u, :u, '0|:'"
                ")"
            ),
            {
                "id": i_id,
                "ws": ws_id,
                "p": proj_id,
                "seq": seq,
                "summary": summary,
                "s": state_id,
                "pr": prio_id,
                "u": user_id,
            },
        )

    await session.commit()
    return a_id, b_id


@pytest.mark.committed_db
async def test_07_concurrent_opposite_reparenting(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify concurrent opposite reparenting results in exactly one commit and no cycles."""
    a_id, b_id = await _seed_concurrency_issues(committed_db_session)

    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = str(pg_worker_db.url.database)

    start_barrier = asyncio.Barrier(2)

    async def _attempt_move(child_id: uuid.UUID, parent_id: uuid.UUID, tag: str) -> str:
        conn = await asyncpg.connect(user=user, database=db_name, host=socket_dir)
        try:
            await start_barrier.wait()
            async with conn.transaction():
                await conn.execute(
                    "UPDATE issues SET parent_issue_id = $1 WHERE id = $2",
                    parent_id,
                    child_id,
                )
        except Exception as exc:  # noqa: BLE001
            return f"FAILED_{tag}: {exc}"
        else:
            return f"SUCCESS_{tag}"
        finally:
            await conn.close()

    res_a, res_b = await asyncio.gather(
        _attempt_move(a_id, b_id, "A_UNDER_B"),
        _attempt_move(b_id, a_id, "B_UNDER_A"),
    )
    results = [res_a, res_b]

    successes = [r for r in results if r.startswith("SUCCESS_")]
    failures = [r for r in results if r.startswith("FAILED_")]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}: {results}"

    fail_msg = failures[0]
    is_cycle_or_deadlock = (
        "PARENT_CYCLE" in fail_msg or "40P01" in fail_msg or "deadlock detected" in fail_msg
    )
    assert is_cycle_or_deadlock, f"Expected PARENT_CYCLE or 40P01, got: {fail_msg}"

    # Verify no cycles in the database
    conn = await asyncpg.connect(user=user, database=db_name, host=socket_dir)
    try:
        rows = await conn.fetch(
            "SELECT id, parent_issue_id, ancestry_path::text AS path "
            "FROM issues WHERE id IN ($1, $2)",
            a_id,
            b_id,
        )
        row_map = {r["id"]: r for r in rows}
        a_row = row_map[a_id]
        b_row = row_map[b_id]

        assert not (a_row["parent_issue_id"] == b_id and b_row["parent_issue_id"] == a_id)

        moved_id, root_id = (a_id, b_id) if a_row["parent_issue_id"] is not None else (b_id, a_id)
        moved_row = row_map[moved_id]
        root_row = row_map[root_id]
        assert moved_row["parent_issue_id"] == root_id
        assert moved_row["path"] == f"{root_id.hex}.{moved_id.hex}"
        assert root_row["parent_issue_id"] is None
        assert root_row["path"] == root_id.hex
    finally:
        await conn.close()

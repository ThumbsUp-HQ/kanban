"""Concurrency tests for allocate_issue_sequence."""

import asyncio
import os
import uuid

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.mark.committed_db
async def test_06_sequence_concurrency_20_connections(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify 20 concurrent connections allocate unique sequential sequence_ids."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    # 1. Create workspace
    await committed_db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Conc WS')"),
        {"id": ws_id, "slug": f"ws-conc-{uuid.uuid4().hex[:8]}"},
    )

    # 2. Register project object spine and project
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, 'CONC', 'Conc Project', :creator, :id"
            ")"
        ),
        {"ws": ws_id, "creator": creator_id, "id": proj_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, 'CONC', 'Conc Project')"
        ),
        {"id": proj_id, "ws": ws_id},
    )
    await committed_db_session.commit()

    # 20 concurrent callers using independent asyncpg connections
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = str(pg_worker_db.url.database)

    async def _allocate() -> int:
        conn = await asyncpg.connect(user=user, database=db_name, host=socket_dir)
        try:
            val = await conn.fetchval(
                "SELECT allocate_issue_sequence($1)",
                proj_id,
            )
            assert isinstance(val, int)
            return val
        finally:
            await conn.close()

    results = await asyncio.gather(*[_allocate() for _ in range(20)])

    # Returned set equals {1..20}, no duplicates
    assert len(results) == 20
    assert set(results) == set(range(1, 21))

    # Final counter equals 20
    res = await committed_db_session.execute(
        text("SELECT issue_seq_counter FROM projects WHERE id = :id"),
        {"id": proj_id},
    )
    assert res.scalar_one() == 20

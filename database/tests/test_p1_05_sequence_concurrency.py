"""Concurrency and batch tests for allocate_issue_sequences allocator."""

import asyncio
import os
import uuid

import asyncpg  # type: ignore[import-untyped]
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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
    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
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


@pytest.mark.committed_db
async def test_07_sequence_concurrency_150_connections_batches(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify 150+ concurrent connections allocate batches without duplicates."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    await committed_db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Conc150 WS')"),
        {"id": ws_id, "slug": f"ws-conc150-{uuid.uuid4().hex[:8]}"},
    )
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, 'C150', 'Conc150 Project', :creator, :id"
            ")"
        ),
        {"ws": ws_id, "creator": creator_id, "id": proj_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO projects ("
            "  id, workspace_id, identifier, name, skip_loaded_sequence_numbers"
            ") VALUES (:id, :ws, 'C150', 'Conc150 Project', FALSE)"
        ),
        {"id": proj_id, "ws": ws_id},
    )
    await committed_db_session.commit()

    socket_dir = os.environ.get(
        "KB_TEST_PGSOCKET_DIR", os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    )
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = str(pg_worker_db.url.database)

    # 150 concurrent workers allocating batch of 2 sequences each = 300 total sequences
    num_workers = 150
    batch_size = 2

    # Semaphore to ensure we stay under max connection limits while exercising extreme concurrency
    sem = asyncio.Semaphore(50)

    async def _allocate_batch() -> list[int]:
        async with sem:
            conn = await asyncpg.connect(user=user, database=db_name, host=socket_dir)
            try:
                row = await conn.fetchrow(
                    "SELECT allocated_sequences, skipped_sequences "
                    "FROM allocate_issue_sequences($1, $2, FALSE)",
                    proj_id,
                    batch_size,
                )
                assert row is not None
                return list(row["allocated_sequences"])
            finally:
                await conn.close()

    batches = await asyncio.gather(*[_allocate_batch() for _ in range(num_workers)])

    all_allocated: list[int] = []
    for b in batches:
        assert len(b) == batch_size
        all_allocated.extend(b)

    total_expected = num_workers * batch_size
    assert len(all_allocated) == total_expected
    assert len(set(all_allocated)) == total_expected
    assert set(all_allocated) == set(range(1, total_expected + 1))

    res = await committed_db_session.execute(
        text("SELECT issue_seq_counter FROM projects WHERE id = :id"),
        {"id": proj_id},
    )
    assert res.scalar_one() == total_expected


@pytest.mark.asyncio
async def test_08_compute_agent_safe_sequence_batch_exact_skipping_1_to_1500(
    db_session: AsyncSession,
) -> None:
    """Verify exact-match skipping across 1..1500 and substring preservation."""
    # 1. skip_loaded = TRUE with batches covering 1..1500
    res = await db_session.execute(
        text(
            "SELECT allocated_sequences, skipped_sequences "
            "FROM compute_agent_safe_sequence_batch(0, 1000, TRUE)"
        )
    )
    row1 = res.one()
    allocated1 = list(row1[0])
    skipped1 = list(row1[1])

    # Exactly 13, 69, 88, 404, 420, 666 must be skipped in 1..1000
    expected_first_1000_skips = [13, 69, 88, 404, 420, 666]
    assert skipped1 == expected_first_1000_skips
    assert len(allocated1) == 1000
    for s in expected_first_1000_skips:
        assert s not in allocated1

    # Substrings must NEVER be skipped (substring preservation)
    assert 113 in allocated1

    # Second batch covering 1000..1500
    res2 = await db_session.execute(
        text(
            "SELECT allocated_sequences, skipped_sequences "
            "FROM compute_agent_safe_sequence_batch(:curr, 500, TRUE)"
        ),
        {"curr": allocated1[-1]},
    )
    row2 = res2.one()
    allocated2 = list(row2[0])
    skipped2 = list(row2[1])

    # In 1000..1500: 1337 and 1488 are skipped
    assert skipped2 == [1337, 1488]
    assert len(allocated2) == 500
    assert 1337 not in allocated2
    assert 1488 not in allocated2

    # Verify all 8 exact integers across 1..1500
    all_skipped = skipped1 + skipped2
    assert all_skipped == [13, 69, 88, 404, 420, 666, 1337, 1488]

    # Verify substring preservation in a specific batch near 4040
    res_sub = await db_session.execute(
        text(
            "SELECT allocated_sequences, skipped_sequences "
            "FROM compute_agent_safe_sequence_batch(4035, 10, TRUE)"
        )
    )
    row_sub = res_sub.one()
    alloc_sub = list(row_sub[0])
    assert 4040 in alloc_sub
    assert list(row_sub[1]) == []

    # Verify skip_loaded = FALSE does NOT skip anything
    res_noskip = await db_session.execute(
        text(
            "SELECT allocated_sequences, skipped_sequences "
            "FROM compute_agent_safe_sequence_batch(0, 100, FALSE)"
        )
    )
    row_noskip = res_noskip.one()
    assert list(row_noskip[0]) == list(range(1, 101))
    assert list(row_noskip[1]) == []


@pytest.mark.asyncio
async def test_09_invalid_sequence_count_bounds(
    db_session: AsyncSession,
) -> None:
    """Enforce 1 <= p_count <= 1000 (INVALID_SEQUENCE_COUNT)."""
    for bad_count in [0, -1, 1001, None]:
        sp = await db_session.begin_nested()
        try:
            with pytest.raises(DBAPIError, match="INVALID_SEQUENCE_COUNT"):
                await db_session.execute(
                    text("SELECT * FROM compute_agent_safe_sequence_batch(0, :cnt, TRUE)"),
                    {"cnt": bad_count},
                )
        finally:
            await sp.rollback()

    # Valid boundary checks: 1 and 1000 succeed
    res1 = await db_session.execute(
        text(
            "SELECT cardinality(allocated_sequences) "
            "FROM compute_agent_safe_sequence_batch(0, 1, TRUE)"
        )
    )
    assert res1.scalar_one() == 1

    res1000 = await db_session.execute(
        text(
            "SELECT cardinality(allocated_sequences) "
            "FROM compute_agent_safe_sequence_batch(0, 1000, TRUE)"
        )
    )
    assert res1000.scalar_one() == 1000


@pytest.mark.committed_db
async def test_10_allocate_issue_sequences_and_verify_activity_chain(
    committed_db_session: AsyncSession,
) -> None:
    """Verify allocate_issue_sequences activity emission and cryptographic chain validity."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    await committed_db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Act WS')"),
        {"id": ws_id, "slug": f"ws-act-{uuid.uuid4().hex[:8]}"},
    )
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, 'ACTP', 'Act Project', :creator, :id"
            ")"
        ),
        {"ws": ws_id, "creator": creator_id, "id": proj_id},
    )
    # Start counter at 12 with skip_loaded_sequence_numbers = TRUE
    await committed_db_session.execute(
        text(
            "INSERT INTO projects ("
            "  id, workspace_id, identifier, name, issue_seq_counter, skip_loaded_sequence_numbers"
            ") VALUES (:id, :ws, 'ACTP', 'Act Project', 12, TRUE)"
        ),
        {"id": proj_id, "ws": ws_id},
    )
    await committed_db_session.commit()

    # 1. Allocate 1 sequence with p_emit_activity = TRUE (default)
    # From counter 12 -> 13 is loaded, so it skips 13 and allocates 14
    res = await committed_db_session.execute(
        text(
            "SELECT allocated_sequences, skipped_sequences "
            "FROM allocate_issue_sequences(:p, 1, TRUE)"
        ),
        {"p": proj_id},
    )
    row = res.one()
    assert list(row[0]) == [14]
    assert list(row[1]) == [13]

    # Verify SEQUENCE_SKIPPED event written to activity_records
    act_res = await committed_db_session.execute(
        text(
            "SELECT event_type, payload FROM activity_records "
            "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
        ),
        {"ws": ws_id},
    )
    act_row = act_res.one()
    assert act_row[0] == "SEQUENCE_SKIPPED"
    payload = act_row[1]
    assert payload["project_key"] == "ACTP"
    assert payload["skipped_sequences"] == [13]
    assert payload["allocated_sequence"] == 14
    assert payload["reason"] == "agent_safe_sequence_numbering"

    # Verify cryptographic hash chain remains intact
    chain_check = await committed_db_session.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
        {"ws": ws_id},
    )
    chain_row = chain_check.one()
    assert chain_row[0] is True
    assert chain_row[1] >= 1

    # 2. Backward compatibility: delegate allocate_issue_sequence(UUID) -> returns 15
    seq_val = await committed_db_session.execute(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": proj_id},
    )
    assert seq_val.scalar_one() == 15

    # 3. Non-existent project raises PROJECT_NOT_FOUND
    with pytest.raises(DBAPIError, match="PROJECT_NOT_FOUND"):
        await committed_db_session.execute(
            text("SELECT * FROM allocate_issue_sequences(:p, 1, TRUE)"),
            {"p": uuid.uuid4()},
        )

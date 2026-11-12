"""Unit tests for PostgreSQL clean-database test harness."""

import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import asyncpg
import pytest
import pytest_socket
from _pytest.outcomes import Exit
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from database.testing.pg_harness import (
    HarnessConfigError,
    build_dsn,
    check_pg_ready,
    committed_db_session,
    compute_template_fingerprint,
    ensure_template,
    pytest_configure,
)


async def test_01_a_positive_isolation_insert(db_session: AsyncSession) -> None:
    """Test A: Insert row into kb_harness.probe and commit within outer savepoint."""
    await db_session.execute(
        text("INSERT INTO kb_harness.probe (note) VALUES ('isolation_test_row_a')")
    )
    await db_session.commit()
    cnt = await db_session.scalar(text("SELECT count(*) FROM kb_harness.probe"))
    assert cnt == 1


async def test_01_b_positive_isolation_assert_clean(db_session: AsyncSession) -> None:
    """Test B: Verify database is clean (count 0) after preceding test teardown."""
    cnt = await db_session.scalar(text("SELECT count(*) FROM kb_harness.probe"))
    assert cnt == 0


async def test_02_savepoint_join_outer_transaction_open(
    db_session: AsyncSession,
    db_conn: AsyncConnection,
) -> None:
    """Test savepoint commit leaves outer transaction active on raw connection."""
    await db_session.execute(
        text("INSERT INTO kb_harness.probe (note) VALUES ('savepoint_join_probe')")
    )
    await db_session.commit()
    txid = await db_conn.scalar(text("SELECT txid_current_if_assigned()"))
    assert txid is not None
    assert txid > 0


@pytest.mark.committed_db
async def test_03_a_committed_db_insert(committed_db_session: AsyncSession) -> None:
    """Commit real transaction to worker DB, expecting TRUNCATE cleanup on teardown."""
    await committed_db_session.execute(
        text("INSERT INTO kb_harness.probe (note) VALUES ('committed_probe')")
    )
    await committed_db_session.commit()
    cnt = await committed_db_session.scalar(text("SELECT count(*) FROM kb_harness.probe"))
    assert cnt == 1


@pytest.mark.committed_db
async def test_03_b_committed_db_truncate_and_identity_restart(
    committed_db_session: AsyncSession,
) -> None:
    """Verify committed_db teardown truncated table and restarted identity sequence."""
    cnt = await committed_db_session.scalar(text("SELECT count(*) FROM kb_harness.probe"))
    assert cnt == 0
    new_id = await committed_db_session.scalar(
        text("INSERT INTO kb_harness.probe (note) VALUES ('restarted_probe') RETURNING id")
    )
    await committed_db_session.commit()
    assert new_id == 1


def test_04_negative_security_socket_and_dsn_rejections(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify pytest-socket blocks TCP connections and DSN builder rejects TCP hosts."""
    with pytest.raises(pytest_socket.SocketBlockedError):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 9))

    with pytest.raises(HarnessConfigError, match="TCP test hosts are forbidden"):
        build_dsn(database="testdb", host="127.0.0.1")

    monkeypatch.setenv("KB_TEST_PGHOST", "127.0.0.1")
    with pytest.raises(HarnessConfigError, match="TCP test hosts are forbidden"):
        build_dsn(database="testdb")


async def test_05_boundary_ensure_template_caching(tmp_path: Path) -> None:
    """Verify golden template caching preserves OID until SQL fingerprint changes."""
    host = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")

    conn = await asyncpg.connect(user=user, database="postgres", host=host)
    try:
        oid_initial = await conn.fetchval(
            "SELECT oid FROM pg_database WHERE datname = 'kanban_template'"
        )
    finally:
        await conn.close()

    fp1 = await ensure_template(socket_dir=host, user=user)

    conn = await asyncpg.connect(user=user, database="postgres", host=host)
    try:
        oid_reused = await conn.fetchval(
            "SELECT oid FROM pg_database WHERE datname = 'kanban_template'"
        )
    finally:
        await conn.close()

    assert oid_initial == oid_reused

    modified_dir = tmp_path / "sql_modified"
    modified_dir.mkdir()
    (modified_dir / "000_kb_harness.sql").write_text(
        "CREATE SCHEMA IF NOT EXISTS kb_harness;\n"
        "CREATE TABLE IF NOT EXISTS kb_harness.probe (id bigint generated always as identity primary key, note text not null);\n"
        "CREATE TABLE IF NOT EXISTS kb_harness.extra (id bigint primary key);\n",
        encoding="utf-8",
    )

    fp2 = await ensure_template(socket_dir=host, user=user, sql_dir=modified_dir)
    assert fp1 != fp2

    conn = await asyncpg.connect(user=user, database="postgres", host=host)
    try:
        oid_changed = await conn.fetchval(
            "SELECT oid FROM pg_database WHERE datname = 'kanban_template'"
        )
    finally:
        await conn.close()

    assert oid_changed != oid_initial

    # Restore canonical template state
    await ensure_template(socket_dir=host, user=user)


async def test_06_negative_committed_db_session_without_marker(
    request: pytest.FixtureRequest,
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify committed_db_session raises UsageError when marker is missing."""
    with pytest.raises(pytest.UsageError, match="requires the '@pytest.mark.committed_db' marker"):
        async for _ in committed_db_session.__wrapped__(request, pg_worker_db):
            pass


def test_07_build_dsn_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_dsn with explicit environment variables."""
    monkeypatch.setenv("KB_TEST_PGHOST", "/tmp/custom-kb-sock")
    monkeypatch.setenv("KB_TEST_PGUSER", "custom_tester")
    dsn = build_dsn(database="kanban_custom")
    assert dsn == "postgresql+asyncpg://custom_tester@/kanban_custom?host=/tmp/custom-kb-sock"


def test_08_check_pg_ready_failure_branches() -> None:
    """Test check_pg_ready returns False for non-existent socket or runtime errors."""
    ready = check_pg_ready(socket_dir="/tmp/non_existent_kb_socket_path", timeout_seconds=0.2)
    assert ready is False

    with patch("database.testing.pg_harness._is_pg_ready_async", side_effect=RuntimeError("boom")):
        assert check_pg_ready(socket_dir="/tmp/kb-pgsock", timeout_seconds=0.1) is False


def test_09_compute_fingerprint_variations(tmp_path: Path) -> None:
    """Test fingerprint computation across permutations (alembic present, absent, None)."""
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "000.sql").write_text("SELECT 1;", encoding="utf-8")

    # 1. No repo_root
    fp_no_root = compute_template_fingerprint(sql_dir, repo_root=None)
    assert len(fp_no_root) == 64

    # 2. repo_root without alembic.ini
    repo_empty = tmp_path / "empty_repo"
    repo_empty.mkdir()
    fp_empty = compute_template_fingerprint(sql_dir, repo_root=repo_empty)
    assert fp_empty == fp_no_root

    # 3. repo_root with alembic.ini and script_location
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alembic_ini = repo_dir / "alembic.ini"
    alembic_ini.write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    mig_dir = repo_dir / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_init.py").write_text("# migration", encoding="utf-8")

    fp_with_alembic = compute_template_fingerprint(sql_dir, repo_root=repo_dir)
    assert len(fp_with_alembic) == 64
    assert fp_with_alembic != fp_no_root


async def test_10_ensure_template_tcp_rejection() -> None:
    """Verify ensure_template rejects non-Unix socket hosts."""
    with pytest.raises(HarnessConfigError, match="TCP test hosts are forbidden"):
        await ensure_template(socket_dir="127.0.0.1")


def test_11_pytest_configure_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pytest_configure handling for workers, skip flags, and unavailable server."""
    cfg_worker = MagicMock()
    cfg_worker.workerinput = {"workerid": "gw0"}
    pytest_configure(cfg_worker)

    cfg_master = MagicMock(spec=[])
    monkeypatch.setenv("KB_TEST_SKIP_PG_CHECK", "1")
    pytest_configure(cfg_master)

    monkeypatch.delenv("KB_TEST_SKIP_PG_CHECK", raising=False)
    monkeypatch.setenv("KB_TEST_PGHOST", "/tmp/non_existent_kb_socket_path")
    with pytest.raises(Exit) as exc_info:
        pytest_configure(cfg_master)
    assert exc_info.value.returncode == 3

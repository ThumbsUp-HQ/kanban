"""PostgreSQL test harness fixture and lifecycle management.

Provides RAM-backed PostgreSQL 16 test server integration, golden
kanban_template creation, per-worker database cloning under pytest-xdist,
and sub-millisecond per-test SAVEPOINT isolation.
"""

import asyncio
import configparser
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

logger = logging.getLogger("database.testing.pg_harness")

_TRUNCATE_STATEMENTS: dict[AsyncEngine, str | None] = {}


class HarnessConfigError(RuntimeError):
    """Raised when harness configuration violates security or connection constraints."""


class HarnessUnavailableError(RuntimeError):
    """Raised when PostgreSQL test instance is unavailable."""


def build_dsn(
    database: str,
    host: str | None = None,
    user: str | None = None,
) -> str:
    """Build a PostgreSQL DSN enforcing Unix domain socket connection paths."""
    resolved_host = host if host is not None else os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    resolved_user = user if user is not None else os.environ.get("KB_TEST_PGUSER", "kanban_test")

    if not resolved_host.startswith("/"):
        raise HarnessConfigError("TCP test hosts are forbidden; use a Unix socket directory")

    return f"postgresql+asyncpg://{resolved_user}@/{database}?host={resolved_host}"


async def _is_pg_ready_async(
    socket_dir: str,
    user: str,
    timeout_seconds: float = 10.0,
) -> bool:
    """Poll Unix domain socket until PostgreSQL accepts connections or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(
                user=user,
                database="postgres",
                host=socket_dir,
                timeout=1.0,
            )
            await conn.close()
            return True
        except Exception:
            await asyncio.sleep(0.1)
    return False


def check_pg_ready(
    socket_dir: str,
    user: str = "kanban_test",
    timeout_seconds: float = 10.0,
) -> bool:
    """Synchronous entry point checking PostgreSQL readiness."""
    try:
        return asyncio.run(
            _is_pg_ready_async(
                socket_dir=socket_dir,
                user=user,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception:
        return False


def compute_template_fingerprint(
    sql_dir: Path,
    repo_root: Path | None = None,
) -> str:
    """Compute sha256 fingerprint over template SQL files and alembic migrations."""
    hasher = hashlib.sha256()
    sql_files = sorted(sql_dir.glob("*.sql"))
    for sql_file in sql_files:
        hasher.update(sql_file.name.encode("utf-8"))
        hasher.update(sql_file.read_bytes())

    if repo_root is not None:
        alembic_ini = repo_root / "alembic.ini"
        if alembic_ini.is_file():
            config = configparser.ConfigParser()
            config.read(alembic_ini)
            script_loc = config.get("alembic", "script_location", fallback=None)
            if script_loc:
                script_path = repo_root / script_loc
                if script_path.is_dir():
                    for migration_file in sorted(p for p in script_path.rglob("*") if p.is_file()):
                        hasher.update(migration_file.name.encode("utf-8"))
                        hasher.update(migration_file.read_bytes())
        else:
            logger.info("HARNESS_ALEMBIC_SKIPPED: alembic.ini not found at repo root")
    else:
        logger.info("HARNESS_ALEMBIC_SKIPPED: repo_root not provided")

    return hasher.hexdigest()


async def ensure_template(
    socket_dir: str | None = None,
    user: str | None = None,
    sql_dir: Path | None = None,
    repo_root: Path | None = None,
    template_db_name: str = "kanban_template",
) -> str:
    """Build or reuse the golden template database using SHA-256 fingerprinting."""
    resolved_host = socket_dir if socket_dir is not None else os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    resolved_user = user if user is not None else os.environ.get("KB_TEST_PGUSER", "kanban_test")

    if not resolved_host.startswith("/"):
        raise HarnessConfigError("TCP test hosts are forbidden; use a Unix socket directory")

    resolved_sql_dir = sql_dir if sql_dir is not None else Path(__file__).resolve().parent / "template_sql"
    resolved_root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]

    fingerprint = compute_template_fingerprint(resolved_sql_dir, resolved_root)

    conn = await asyncpg.connect(user=resolved_user, database="postgres", host=resolved_host)
    try:
        row = await conn.fetchrow(
            "SELECT d.oid, pg_catalog.shobj_description(d.oid, 'pg_database') AS comment "
            "FROM pg_catalog.pg_database d WHERE d.datname = $1",
            template_db_name,
        )
        if row is not None and row["comment"] == fingerprint:
            logger.info("Reusing golden %s database (fingerprint=%s)", template_db_name, fingerprint)
            return fingerprint

        logger.info("Rebuilding golden %s database (fingerprint=%s)", template_db_name, fingerprint)
        await conn.execute(f"DROP DATABASE IF EXISTS {template_db_name} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {template_db_name}")
    finally:
        await conn.close()

    tmpl_conn = await asyncpg.connect(user=resolved_user, database=template_db_name, host=resolved_host)
    try:
        for sql_file in sorted(resolved_sql_dir.glob("*.sql")):
            content = sql_file.read_text(encoding="utf-8")
            if content.strip():
                await tmpl_conn.execute(content)
    finally:
        await tmpl_conn.close()

    conn = await asyncpg.connect(user=resolved_user, database="postgres", host=resolved_host)
    try:
        await conn.execute(f"COMMENT ON DATABASE {template_db_name} IS '{fingerprint}'")
        await conn.execute(f"ALTER DATABASE {template_db_name} WITH ALLOW_CONNECTIONS false")
    finally:
        await conn.close()

    return fingerprint


def pytest_configure(config: pytest.Config) -> None:
    """Validate PostgreSQL readiness and build template DB in controller process."""
    if hasattr(config, "workerinput"):
        return

    if os.environ.get("KB_TEST_SKIP_PG_CHECK") == "1":
        return

    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")

    if not check_pg_ready(socket_dir=socket_dir, user=user, timeout_seconds=10.0):
        pytest.exit(f"PG test server unavailable at {socket_dir}; run make testdb-up", returncode=3)

    asyncio.run(ensure_template(socket_dir=socket_dir, user=user))


@pytest.fixture(scope="session")
async def pg_worker_db(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncEngine, None]:
    """Provide an isolated worker database cloned from golden kanban_template."""
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    db_name = f"kanban_test_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")

    admin_conn = await asyncpg.connect(user=user, database="postgres", host=socket_dir)
    try:
        await admin_conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
        await admin_conn.execute(f"CREATE DATABASE {db_name} TEMPLATE kanban_template")
    finally:
        await admin_conn.close()

    dsn = build_dsn(database=db_name, host=socket_dir, user=user)
    engine = create_async_engine(dsn, pool_size=2, max_overflow=0)

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname IN ('public', 'kb_harness') "
                "AND tablename != 'alembic_version'"
            )
        )
        tables = [f'"{r[0]}"."{r[1]}"' for r in rows.all()]
        truncate_stmt = f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE" if tables else None
        _TRUNCATE_STATEMENTS[engine] = truncate_stmt

    try:
        yield engine
    finally:
        _TRUNCATE_STATEMENTS.pop(engine, None)
        await engine.dispose()
        cleanup_conn = await asyncpg.connect(user=user, database="postgres", host=socket_dir)
        try:
            await cleanup_conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
        finally:
            await cleanup_conn.close()


@pytest.fixture
async def _test_db_context(
    pg_worker_db: AsyncEngine,
) -> AsyncGenerator[tuple[AsyncConnection, AsyncSession], None]:
    """Open connection and outer transaction, binding AsyncSession with savepoint join."""
    async with pg_worker_db.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield conn, session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def db_conn(_test_db_context: tuple[AsyncConnection, AsyncSession]) -> AsyncConnection:
    """Provide the raw AsyncConnection within the outer test transaction."""
    return _test_db_context[0]


@pytest.fixture
def db_session(_test_db_context: tuple[AsyncConnection, AsyncSession]) -> AsyncSession:
    """Provide the AsyncSession bound to the outer transaction via savepoints."""
    return _test_db_context[1]


@pytest.fixture
async def committed_db_session(
    request: pytest.FixtureRequest,
    pg_worker_db: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for real commits, running TRUNCATE on fixture teardown."""
    marker = request.node.get_closest_marker("committed_db")
    if not marker:
        raise pytest.UsageError("Fixture 'committed_db_session' requires the '@pytest.mark.committed_db' marker")

    session = AsyncSession(bind=pg_worker_db, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        truncate_stmt = _TRUNCATE_STATEMENTS.get(pg_worker_db)
        if truncate_stmt:
            async with pg_worker_db.connect() as conn:
                await conn.execute(text(truncate_stmt))
                await conn.commit()

"""PostgreSQL 16 clean-DB test harness supporting SAVEPOINT isolation and tmpfs."""

import asyncio
import configparser
import contextlib
import hashlib
import logging
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]  # asyncpg does not distribute PEP 561 py.typed marker
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from database.bootstrap import bootstrap_cluster

logger = logging.getLogger("database.testing.pg_harness")

_TRUNCATE_STATEMENTS: dict[AsyncEngine, str | None] = {}


class HarnessConfigError(ValueError):
    """Raised when harness configuration violates security or operational policies."""


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
        msg = "TCP test hosts are forbidden; use a Unix socket directory"
        raise HarnessConfigError(msg)

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
        except (asyncpg.PostgresError, OSError):
            await asyncio.sleep(0.1)
        else:
            await conn.close()
            return True
    return False


def check_pg_ready(
    socket_dir: str,
    user: str = "kanban_test",
    timeout_seconds: float = 10.0,
) -> bool:
    """Check PostgreSQL readiness synchronously."""
    try:
        return asyncio.run(
            _is_pg_ready_async(
                socket_dir=socket_dir,
                user=user,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _hash_sql_dir(hasher: "hashlib._Hash", sql_dir: Path) -> None:
    """Update hash with all SQL files in directory."""
    for sql_file in sorted(sql_dir.glob("*.sql")):
        hasher.update(sql_file.name.encode("utf-8"))
        hasher.update(sql_file.read_bytes())


def _hash_migrations(hasher: "hashlib._Hash", migrations_dir: Path) -> None:
    """Update hash with migration source files excluding pycache."""
    for m_file in sorted(migrations_dir.rglob("*")):
        if m_file.is_file() and "__pycache__" not in m_file.parts:
            hasher.update(m_file.name.encode("utf-8"))
            hasher.update(m_file.read_bytes())


def _hash_alembic_config(hasher: "hashlib._Hash", repo_root: Path) -> None:
    """Update hash with alembic.ini and script location contents."""
    for ini_candidate in (repo_root / "database" / "alembic.ini", repo_root / "alembic.ini"):
        if ini_candidate.is_file():
            hasher.update(ini_candidate.read_bytes())
            config = configparser.ConfigParser(interpolation=None)
            config.read(ini_candidate)
            script_loc = config.get("alembic", "script_location", fallback=None)
            if script_loc and "%(here)s" not in script_loc:
                script_path = repo_root / script_loc
                if script_path.is_dir():
                    for mf in sorted(p for p in script_path.rglob("*") if p.is_file()):
                        hasher.update(mf.name.encode("utf-8"))
                        hasher.update(mf.read_bytes())
            break


def compute_template_fingerprint(
    sql_dir: Path,
    repo_root: Path | None = None,
) -> str:
    """Compute sha256 fingerprint over template SQL, bootstrap SQL, and alembic migrations."""
    hasher = hashlib.sha256()
    _hash_sql_dir(hasher, sql_dir)

    if repo_root is not None:
        bootstrap_dir = repo_root / "database" / "bootstrap"
        if bootstrap_dir.is_dir():
            _hash_sql_dir(hasher, bootstrap_dir)

        migrations_dir = repo_root / "database" / "migrations"
        if migrations_dir.is_dir():
            _hash_migrations(hasher, migrations_dir)

        _hash_alembic_config(hasher, repo_root)

    return hasher.hexdigest()


def _run_template_alembic(alembic_ini_path: Path, superuser_dsn: str) -> None:
    """Execute alembic upgrade to head in synchronous thread."""
    old_url = os.environ.get("KANBAN_MIGRATOR_DATABASE_URL")
    old_role = os.environ.get("KANBAN_MIGRATOR_SET_ROLE")
    os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = superuser_dsn
    os.environ["KANBAN_MIGRATOR_SET_ROLE"] = "kanban_migrator"
    try:
        cfg = Config(str(alembic_ini_path))
        command.upgrade(cfg, "head")
    finally:
        if old_url is not None:
            os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = old_url
        else:
            os.environ.pop("KANBAN_MIGRATOR_DATABASE_URL", None)
        if old_role is not None:
            os.environ["KANBAN_MIGRATOR_SET_ROLE"] = old_role
        else:
            os.environ.pop("KANBAN_MIGRATOR_SET_ROLE", None)


async def _apply_template_sql(
    resolved_sql_dir: Path,
    template_db_name: str,
    resolved_host: str,
    resolved_user: str,
) -> None:
    """Apply custom template SQL files in lexical order."""
    tmpl_conn = await asyncpg.connect(
        user=resolved_user, database=template_db_name, host=resolved_host
    )
    try:
        for sql_file in sorted(resolved_sql_dir.glob("*.sql")):
            content = sql_file.read_text(encoding="utf-8")
            if content.strip():
                await tmpl_conn.execute(content)
    finally:
        await tmpl_conn.close()


async def ensure_template(
    socket_dir: str | None = None,
    user: str | None = None,
    sql_dir: Path | None = None,
    repo_root: Path | None = None,
    template_db_name: str = "kanban_template",
) -> str:
    """Build or reuse the golden template database using SHA-256 fingerprinting."""
    default_host = "/tmp/kb-pgsock"
    resolved_host = (
        socket_dir if socket_dir is not None else os.environ.get("KB_TEST_PGHOST", default_host)
    )
    resolved_user = user if user is not None else os.environ.get("KB_TEST_PGUSER", "kanban_test")

    if not resolved_host.startswith("/"):
        msg = "TCP test hosts are forbidden; use a Unix socket directory"
        raise HarnessConfigError(msg)

    default_sql_dir = Path(__file__).resolve().parent / "template_sql"
    resolved_sql_dir = sql_dir if sql_dir is not None else default_sql_dir
    resolved_root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]

    fingerprint = compute_template_fingerprint(resolved_sql_dir, resolved_root)

    conn = await asyncpg.connect(user=resolved_user, database="postgres", host=resolved_host)
    try:
        row = await conn.fetchrow(
            "SELECT d.oid, pg_catalog.shobj_description(d.oid, 'pg_database') AS comment "
            "FROM pg_catalog.pg_database d WHERE d.datname = $1",
            template_db_name,
        )
        if row is not None:
            if row["comment"] == fingerprint:
                return fingerprint
            with contextlib.suppress(asyncpg.PostgresError):
                await conn.execute(f"ALTER DATABASE {template_db_name} WITH is_template = false")
            await conn.execute(f"DROP DATABASE IF EXISTS {template_db_name} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {template_db_name}")
    finally:
        await conn.close()

    # Step A: Bootstrap cluster roles and extensions
    superuser_dsn = build_dsn(database=template_db_name, host=resolved_host, user=resolved_user)
    await bootstrap_cluster(superuser_dsn)

    # Step B: Run Alembic migrations if alembic.ini is present
    alembic_ini_path: Path | None = None
    for candidate in (resolved_root / "database" / "alembic.ini", resolved_root / "alembic.ini"):
        if candidate.is_file():
            alembic_ini_path = candidate
            break

    if alembic_ini_path is not None:
        await asyncio.to_thread(_run_template_alembic, alembic_ini_path, superuser_dsn)

    # Step C: Apply custom template SQL files
    await _apply_template_sql(resolved_sql_dir, template_db_name, resolved_host, resolved_user)

    # Step D: Record fingerprint and lock connections
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
    tmpl_db = os.environ.get("KB_TEST_TEMPLATE_DB", "kanban_template")

    if not check_pg_ready(socket_dir=socket_dir, user=user, timeout_seconds=10.0):
        pytest.exit(f"PG test server unavailable at {socket_dir}; run make testdb-up", returncode=3)

    asyncio.run(ensure_template(socket_dir=socket_dir, user=user, template_db_name=tmpl_db))


@pytest.fixture(scope="session")
async def pg_worker_db(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncEngine, None]:
    """Provide an isolated worker database cloned from golden kanban_template."""
    worker_id = getattr(request.config, "workerinput", {}).get(
        "workerid", os.environ.get("PYTEST_XDIST_WORKER", "master")
    )
    prefix = os.environ.get("KB_TEST_DB_PREFIX", "kanban_test")
    db_name = f"{prefix}_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    tmpl_db = os.environ.get("KB_TEST_TEMPLATE_DB", "kanban_template")

    admin_conn = await asyncpg.connect(user=user, database="postgres", host=socket_dir)
    try:
        await admin_conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")
        await admin_conn.execute(f"CREATE DATABASE {db_name} TEMPLATE {tmpl_db}")
    finally:
        await admin_conn.close()

    dsn = build_dsn(database=db_name, host=socket_dir, user=user)
    engine = create_async_engine(dsn, pool_size=2, max_overflow=0)

    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname IN ('public', 'kb_harness') "
                "AND tablename NOT IN ('alembic_version', 'link_type_matrix')"
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
        msg = "Fixture 'committed_db_session' requires the '@pytest.mark.committed_db' marker"
        raise pytest.UsageError(msg)

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


@pytest.fixture(autouse=True)
async def _auto_cleanup_direct_pg_worker_db(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[None, None]:
    """Truncate worker DB when a test uses pg_worker_db directly without db_session."""
    yield
    fixturenames = request.fixturenames
    if "committed_db_session" in fixturenames:
        return
    has_committed_marker = request.node.get_closest_marker("committed_db") is not None
    uses_direct_engine = (
        "pg_worker_db" in fixturenames
        and "_test_db_context" not in fixturenames
        and "db_session" not in fixturenames
        and "db_conn" not in fixturenames
    )
    if (has_committed_marker or uses_direct_engine) and "pg_worker_db" in fixturenames:
        engine: AsyncEngine = request.getfixturevalue("pg_worker_db")
        truncate_stmt = _TRUNCATE_STATEMENTS.get(engine)
        if truncate_stmt:
            async with engine.connect() as conn:
                await conn.execute(text(truncate_stmt))
                await conn.commit()

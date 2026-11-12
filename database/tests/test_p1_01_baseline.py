"""Unit tests for Phase 1 database baseline: roles, extensions, and uuidv7."""

import asyncio
import os
import uuid

import asyncpg  # type: ignore[import-untyped]  # asyncpg does not distribute PEP 561 py.typed marker
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from database.bootstrap import _to_asyncpg_kwargs, bootstrap_cluster
from database.testing.pg_harness import build_dsn
from database.tests.conftest import bind_ctx


async def test_01_role_attributes(superuser_session: AsyncSession) -> None:
    """Verify least-privilege role configurations match S3.3 and S9.3 specifications."""
    result = await superuser_session.execute(
        text(
            "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolconfig "
            "FROM pg_roles "
            "WHERE rolname IN ('kanban_migrator', 'kanban_app', 'app_rls_reader')"
        )
    )
    roles = {r[0]: r for r in result.all()}

    # kanban_app: NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    app = roles["kanban_app"]
    assert app.rolsuper is False
    assert app.rolbypassrls is False
    assert app.rolcreatedb is False
    assert app.rolcreaterole is False

    # kanban_migrator: NOSUPERUSER BYPASSRLS (for table ownership and migrations)
    migrator = roles["kanban_migrator"]
    assert migrator.rolsuper is False
    assert migrator.rolbypassrls is True

    # app_rls_reader: NOSUPERUSER NOBYPASSRLS default_transaction_read_only = on
    reader = roles["app_rls_reader"]
    assert reader.rolsuper is False
    assert reader.rolbypassrls is False
    assert reader.rolconfig is not None
    assert "default_transaction_read_only=on" in reader.rolconfig


async def test_02_extensions_installed(superuser_session: AsyncSession) -> None:
    """Verify exactly the five required extensions are present."""
    result = await superuser_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname != 'plpgsql' ORDER BY extname")
    )
    extensions = {r[0] for r in result.all()}
    expected = {"pgcrypto", "ltree", "pg_trgm", "btree_gist", "vector"}
    assert extensions == expected


async def test_03_uuidv7_properties(db_session: AsyncSession) -> None:
    """Verify 1000 uuidv7 values satisfy RFC 9562 v7 nibble, variant 10xx, and ordering."""
    # 1. 1000 values are distinct
    result = await db_session.execute(text("SELECT uuidv7() FROM generate_series(1, 1000)"))
    uuids = [r[0] for r in result.all()]
    assert len(uuids) == 1000
    assert len(set(uuids)) == 1000

    # 2. Version nibble 7 and variant bits 10xx
    for u in uuids:
        raw_bytes = u.bytes
        version_nibble = (raw_bytes[6] >> 4) & 0x0F
        assert version_nibble == 7
        variant_bits = (raw_bytes[8] >> 6) & 0x03
        assert variant_bits == 2  # binary 10

    # 3. Monotonic ascending ordering across sleep
    u1_str = await db_session.scalar(text("SELECT uuidv7()"))
    await asyncio.sleep(0.005)
    u2_str = await db_session.scalar(text("SELECT uuidv7()"))
    assert u1_str is not None
    assert u2_str is not None
    u1 = uuid.UUID(str(u1_str))
    u2 = uuid.UUID(str(u2_str))
    assert u1.bytes < u2.bytes


async def test_04_security_kanban_app_restrictions(app_session: AsyncSession) -> None:
    """Verify kanban_app cannot create tables in public or escalate to kanban_migrator."""
    # CREATE TABLE in public raises 42501 (insufficient_privilege)
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_create:
        async with app_session.begin_nested():
            await app_session.execute(text("CREATE TABLE public.forbidden_probe (i int)"))
    orig = getattr(exc_create.value, "orig", None)
    pgcode = getattr(orig, "sqlstate", None) or getattr(exc_create.value, "code", None)
    assert pgcode == "42501" or "permission denied" in str(exc_create.value).lower()

    # SET ROLE kanban_migrator raises 42501
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_role:
        async with app_session.begin_nested():
            await app_session.execute(text("SET ROLE kanban_migrator"))
    orig_role = getattr(exc_role.value, "orig", None)
    pgcode_role = getattr(orig_role, "sqlstate", None) or getattr(exc_role.value, "code", None)
    assert pgcode_role == "42501" or "permission denied" in str(exc_role.value).lower()


async def test_05_security_bootstrap_attribute_reassertion() -> None:
    """Verify bootstrap_cluster downgrades pre-existing compromised roles."""
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    superuser_dsn = build_dsn(database="postgres", host=socket_dir, user=user)

    # Artificially grant BYPASSRLS to kanban_app
    conn = await asyncpg.connect(user=user, database="postgres", host=socket_dir)
    try:
        await conn.execute("ALTER ROLE kanban_app BYPASSRLS")
        compromised = await conn.fetchval(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = 'kanban_app'"
        )
        assert compromised is True
    finally:
        await conn.close()

    # Re-run bootstrap_cluster
    await bootstrap_cluster(superuser_dsn)

    conn = await asyncpg.connect(user=user, database="postgres", host=socket_dir)
    try:
        reasserted = await conn.fetchval(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = 'kanban_app'"
        )
        assert reasserted is False
    finally:
        await conn.close()


async def test_06_boundary_app_current_principal_and_workspace(
    db_session: AsyncSession,
) -> None:
    """Verify app_current_principal_id and app_current_workspace_id behavior and error handling."""
    # 1. NULL when unset
    p_null = await db_session.scalar(text("SELECT app_current_principal_id()"))
    assert p_null is None
    w_null = await db_session.scalar(text("SELECT app_current_workspace_id()"))
    assert w_null is None

    # 2. NULL after empty string set_config
    await db_session.execute(text("SELECT set_config('app.principal_id', '', true)"))
    p_empty = await db_session.scalar(text("SELECT app_current_principal_id()"))
    assert p_empty is None

    # 3. Returns valid uuid when set via bind_ctx
    test_principal = uuid.uuid4()
    test_workspace = uuid.uuid4()
    await bind_ctx(db_session, principal_id=test_principal, workspace_id=test_workspace)

    p_val = await db_session.scalar(text("SELECT app_current_principal_id()"))
    assert p_val == test_principal
    w_val = await db_session.scalar(text("SELECT app_current_workspace_id()"))
    assert w_val == test_workspace

    # 4. Malformed uuid raises 22P02
    await db_session.execute(text("SELECT set_config('app.principal_id', 'not-a-uuid', true)"))
    with pytest.raises((DataError, DBAPIError)) as exc_info:
        await db_session.execute(text("SELECT app_current_principal_id()"))
    orig = getattr(exc_info.value, "orig", None)
    pgcode = getattr(orig, "sqlstate", None) or getattr(exc_info.value, "code", None)
    assert pgcode == "22P02" or "invalid input syntax for type uuid" in str(exc_info.value).lower()


def test_to_asyncpg_kwargs_parsing() -> None:
    """Verify parsing DSN into asyncpg connection arguments with password, port, and host."""
    kw1 = _to_asyncpg_kwargs("postgresql+asyncpg://user:pass@/dbname?host=/tmp/sock")
    assert kw1 == {"user": "user", "password": "pass", "database": "dbname", "host": "/tmp/sock"}

    kw2 = _to_asyncpg_kwargs("postgresql+asyncpg://u:p@localhost:5433/db")
    expected2 = {
        "user": "u",
        "password": "p",
        "database": "db",
        "host": "localhost",
        "port": 5433,
    }
    assert kw2 == expected2

    kw3 = _to_asyncpg_kwargs("postgresql:///")
    assert kw3 == {"user": "postgres", "database": "postgres"}

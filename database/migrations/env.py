"""Async Alembic migration environment configuration."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Offline migration execution is prohibited."""
    msg = "Offline mode is disabled; execute migrations online"
    raise RuntimeError(msg)


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active database connection."""
    set_role = os.environ.get("KANBAN_MIGRATOR_SET_ROLE")
    if set_role:
        connection.execute(text(f"SET ROLE {set_role}"))

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        transaction_per_migration=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations asynchronously using an async engine."""
    dsn = os.environ.get("KANBAN_MIGRATOR_DATABASE_URL")
    if not dsn:
        msg = "KANBAN_MIGRATOR_DATABASE_URL is required"
        raise RuntimeError(msg)

    section = config.get_section(config.config_ini_section) or {}
    configuration = dict(section)
    configuration["sqlalchemy.url"] = dsn

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

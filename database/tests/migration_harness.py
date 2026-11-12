"""Migration test harness for isolated Alembic up/down verification."""

import asyncio
import os
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

import asyncpg  # type: ignore[import-untyped]  # asyncpg does not distribute PEP 561 py.typed marker
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from database.bootstrap import bootstrap_cluster
from database.testing.pg_harness import build_dsn


class MigrationHarness:
    """Async context manager creating isolated template0 databases for migration tests."""

    def __init__(self) -> None:
        """Initialize migration harness with a unique template0 clone name."""
        self.db_name: str = f"kanban_mig_{uuid.uuid4().hex}"
        self.socket_dir: str = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
        self.user: str = os.environ.get("KB_TEST_PGUSER", "kanban_test")
        self.dsn: str = build_dsn(database=self.db_name, host=self.socket_dir, user=self.user)
        self.ini_path: Path = Path(__file__).resolve().parents[1] / "alembic.ini"
        self.alembic_cfg: Config = Config(str(self.ini_path))
        self.script_dir: ScriptDirectory = ScriptDirectory.from_config(self.alembic_cfg)

    async def __aenter__(self) -> Self:
        """Create fresh database cloned from template0 and apply bootstrap."""
        conn = await asyncpg.connect(user=self.user, database="postgres", host=self.socket_dir)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {self.db_name} WITH (FORCE)")
            await conn.execute(f"CREATE DATABASE {self.db_name} TEMPLATE template0")
        finally:
            await conn.close()

        await bootstrap_cluster(self.dsn)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Drop isolated test database on teardown."""
        conn = await asyncpg.connect(user=self.user, database="postgres", host=self.socket_dir)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {self.db_name} WITH (FORCE)")
        finally:
            await conn.close()

    async def upgrade(self, revision: str = "head") -> None:
        """Upgrade database to specified revision under kanban_migrator role."""

        def _run() -> None:
            old_url = os.environ.get("KANBAN_MIGRATOR_DATABASE_URL")
            old_role = os.environ.get("KANBAN_MIGRATOR_SET_ROLE")
            os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = self.dsn
            os.environ["KANBAN_MIGRATOR_SET_ROLE"] = "kanban_migrator"
            try:
                command.upgrade(self.alembic_cfg, revision)
            finally:
                if old_url is not None:
                    os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = old_url
                else:
                    os.environ.pop("KANBAN_MIGRATOR_DATABASE_URL", None)
                if old_role is not None:
                    os.environ["KANBAN_MIGRATOR_SET_ROLE"] = old_role
                else:
                    os.environ.pop("KANBAN_MIGRATOR_SET_ROLE", None)

        await asyncio.to_thread(_run)

    async def downgrade(self, revision: str = "base") -> None:
        """Downgrade database to specified revision under kanban_migrator role."""

        def _run() -> None:
            old_url = os.environ.get("KANBAN_MIGRATOR_DATABASE_URL")
            old_role = os.environ.get("KANBAN_MIGRATOR_SET_ROLE")
            os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = self.dsn
            os.environ["KANBAN_MIGRATOR_SET_ROLE"] = "kanban_migrator"
            try:
                command.downgrade(self.alembic_cfg, revision)
            finally:
                if old_url is not None:
                    os.environ["KANBAN_MIGRATOR_DATABASE_URL"] = old_url
                else:
                    os.environ.pop("KANBAN_MIGRATOR_DATABASE_URL", None)
                if old_role is not None:
                    os.environ["KANBAN_MIGRATOR_SET_ROLE"] = old_role
                else:
                    os.environ.pop("KANBAN_MIGRATOR_SET_ROLE", None)

        await asyncio.to_thread(_run)

    def previous_of(self, revision: str) -> str:
        """Resolve previous revision identifier in the migration graph."""
        rev = self.script_dir.get_revision(revision)
        if rev.down_revision is None:
            return "base"
        if isinstance(rev.down_revision, tuple):
            return str(rev.down_revision[0])
        return str(rev.down_revision)

    async def fetch(self, sql: str, *args: object) -> list[Any]:
        """Fetch rows from test database."""
        conn = await asyncpg.connect(user=self.user, database=self.db_name, host=self.socket_dir)
        try:
            records = await conn.fetch(sql, *args)
            return list(records)
        finally:
            await conn.close()

    async def fetchval(self, sql: str, *args: object) -> object | None:
        """Fetch single value from test database."""
        conn = await asyncpg.connect(user=self.user, database=self.db_name, host=self.socket_dir)
        try:
            val = await conn.fetchval(sql, *args)
            return cast("object | None", val)
        finally:
            await conn.close()

    async def execute(self, sql: str, *args: object) -> None:
        """Execute statement on test database."""
        conn = await asyncpg.connect(user=self.user, database=self.db_name, host=self.socket_dir)
        try:
            await conn.execute(sql, *args)
        finally:
            await conn.close()

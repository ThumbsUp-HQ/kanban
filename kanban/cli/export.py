# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI commands for workspace export (KB-P6-03)."""
# ruff: noqa: E501, TC003, ASYNC240, BLE001

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kanban.api.deps import PrincipalContext
from kanban.exporter.portable_bundle import PortableWorkspaceExporter

logger = logging.getLogger(__name__)


def _get_admin_dsn() -> str:
    """Resolve administrative database connection DSN from environment."""
    dsn = (
        os.environ.get("KANBAN_ADMIN_DATABASE_URL")
        or os.environ.get("KANBAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if dsn:
        return dsn

    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")  # noqa: S108
    user = os.environ.get("KB_ADMIN_PGUSER", "kanban_migrator")
    dbname = os.environ.get("PGDATABASE", "kanban")
    return f"postgresql+asyncpg://{user}@/{dbname}?host={socket_dir}"


def register_export_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'export' root subcommand and portable export utilities."""
    export_parser = subparsers.add_parser(
        "export",
        help="Workspace export utilities",
        description="Deterministic workspace and graph export utilities",
    )
    export_subparsers = export_parser.add_subparsers(dest="export_subcommand", required=True)

    portable_parser = export_subparsers.add_parser(
        "portable",
        help="Export deterministic portable workspace bundle (.tar.gz)",
        description="Lossless deterministic portable workspace exporter with manifest SHA-256 digests",
    )
    portable_parser.add_argument(
        "--workspace",
        required=True,
        help="Target workspace slug to export",
    )
    portable_parser.add_argument(
        "--out",
        required=True,
        help="Destination path for output .tar.gz bundle archive",
    )
    portable_parser.add_argument(
        "--scrub",
        action="store_true",
        default=False,
        help="Scrub credentials and secrets from exported text and markdown",
    )
    portable_parser.set_defaults(func=_run_portable_export)


def _run_portable_export(args: argparse.Namespace) -> int:
    """Execute portable workspace bundle export."""
    return asyncio.run(_execute_portable_export(args))


async def _execute_portable_export(
    args: argparse.Namespace,
    session: AsyncSession | None = None,
) -> int:
    engine = None
    try:
        ctx: Any
        if session is not None:

            @asynccontextmanager
            async def _scoped_session() -> AsyncIterator[AsyncSession]:
                yield session

            ctx = _scoped_session()
        else:
            dsn = _get_admin_dsn()
            engine = create_async_engine(dsn, isolation_level="READ COMMITTED")
            session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            ctx = session_maker()

        async with ctx as active_session:
            ws_res = await active_session.execute(
                text("SELECT id, slug FROM workspaces WHERE slug = :slug"),
                {"slug": args.workspace},
            )
            row = ws_res.mappings().one_or_none()
            if not row:
                sys.stderr.write(f"Error: Workspace slug '{args.workspace}' not found.\n")
                return 2

            ws_id = row["id"]
            principal_res = await active_session.execute(
                text(
                    "SELECT principal_id FROM role_bindings "
                    "WHERE workspace_id = :ws "
                    "AND role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN') "
                    "LIMIT 1"
                ),
                {"ws": ws_id},
            )
            principal_id = principal_res.scalar_one_or_none() or uuid.uuid4()

            await active_session.execute(
                text(
                    "SELECT set_config('app.principal_id', :pid, true), "
                    "set_config('app.workspace_id', :ws, true), "
                    "set_config('app.aal_level', '2', true)"
                ),
                {"pid": str(principal_id), "ws": str(ws_id)},
            )

            caller = PrincipalContext(
                principal_id=principal_id,
                workspace_id=ws_id,
                aal_level=2,
            )

            exporter = PortableWorkspaceExporter(
                session=active_session,
                workspace_id=ws_id,
                caller=caller,
            )

            out_path = Path(args.out).resolve()
            await exporter.export_to_file(out_path, scrub=args.scrub)
            sys.stdout.write(f"Exported portable workspace bundle to {out_path}\n")
            return 0
    except Exception as exc:
        sys.stderr.write(f"Export Error: {exc}\n")
        return 1
    finally:
        if engine is not None:
            await engine.dispose()

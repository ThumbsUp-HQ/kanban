"""CLI handlers for background jobs execution (S7.2 8p)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

from kanban.jobs.auto_archive import run_auto_archive

if TYPE_CHECKING:
    import argparse


def _get_engine_dsn() -> str:
    """Resolve database DSN from environment."""
    dsn = os.environ.get("KANBAN_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        return dsn

    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")  # noqa: S108
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    return f"postgresql+asyncpg://{user}@/postgres?host={socket_dir}"


def handle_run_auto_archive(args: argparse.Namespace) -> int:
    """Execute auto-archive pass from CLI args."""
    now: datetime | None = None
    if getattr(args, "now", None):
        try:
            now = datetime.fromisoformat(args.now)
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
        except ValueError as err:
            sys.stderr.write(f"Invalid --now timestamp: {err}\n")
            return 2

    dsn = _get_engine_dsn()
    engine = create_async_engine(dsn)

    async def _run() -> int:
        try:
            report = await run_auto_archive(engine, now=now)
            sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        except Exception as err:  # noqa: BLE001
            sys.stderr.write(f"Auto-archive failed: {err}\n")
            return 1
        else:
            return 0
        finally:
            await engine.dispose()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_run())).result()
    return asyncio.run(_run())


def register_jobs_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register jobs command trees under the root kanban-ctl CLI."""
    jobs_parser = subparsers.add_parser(
        "jobs",
        help="Background jobs and maintenance operations",
    )
    jobs_subs = jobs_parser.add_subparsers(dest="jobs_subcommand", required=True)

    run_parser = jobs_subs.add_parser("run", help="Run background jobs immediately")
    run_subs = run_parser.add_subparsers(dest="job_name", required=True)

    auto_archive_parser = run_subs.add_parser(
        "auto-archive",
        help="Run periodic auto-archive pass for eligible projects",
    )
    auto_archive_parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Optional ISO-8601 reference timestamp (e.g. 2026-11-11T00:00:00Z)",
    )
    auto_archive_parser.set_defaults(
        func=handle_run_auto_archive,
        handler=handle_run_auto_archive,
    )

"""CLI handlers for background jobs execution (KB-P3-12, KB-P3-09a)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models.projects import Project, WorkflowState
from database.testing.pg_harness import build_dsn
from kanban.jobs.auto_archive import run_auto_archive
from kanban.jobs.board_rebalance import rebalance_column
from kanban.jobs.trash_purge import run_trash_purge

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


def handle_run_trash_purge(args: argparse.Namespace) -> int:
    """Execute trash retention purge pass from CLI args."""
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
            report = await run_trash_purge(engine, now=now)
            sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
        except Exception as err:  # noqa: BLE001
            sys.stderr.write(f"Trash-purge failed: {err}\n")
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


def _handle_board_rebalance(args: argparse.Namespace) -> int:
    """Execute board-rebalance job synchronously across matching project columns."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_board_rebalance(getattr(args, "project", None)))
            return future.result()

    return asyncio.run(_run_board_rebalance(getattr(args, "project", None)))


async def _run_board_rebalance(project_filter: str | None = None) -> int:
    """Run board rebalancing across columns."""
    db_name = os.environ.get("KB_DB_NAME") or os.environ.get("PGDATABASE", "kanban_test")
    socket_dir = os.environ.get("KB_TEST_PGHOST") or os.environ.get("PGHOST")
    user = os.environ.get("KB_TEST_PGUSER") or os.environ.get("PGUSER")
    dsn = build_dsn(database=db_name, host=socket_dir, user=user)
    engine = create_async_engine(dsn)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        proj_stmt = select(Project)
        if project_filter:
            clean_proj = project_filter.strip().upper()
            proj_stmt = proj_stmt.where(Project.identifier == clean_proj)

        projects = list((await session.execute(proj_stmt)).scalars().all())
        if not projects:
            sys.stdout.write(f"No projects found matching filter '{project_filter}'\n")
            await engine.dispose()
            return 0

        total_reindexed = 0
        columns_processed = 0

        for project in projects:
            states_stmt = (
                select(WorkflowState)
                .where(WorkflowState.project_id == project.id)
                .order_by(WorkflowState.sort_order.asc())
            )
            states = list((await session.execute(states_stmt)).scalars().all())

            for state in states:
                columns_processed += 1
                reindexed = await rebalance_column(session, project.id, state.id)
                total_reindexed += reindexed
                if reindexed > 0:
                    sys.stdout.write(
                        f"Project {project.identifier} state '{state.name}' "
                        f"({state.id}): reindexed {reindexed} cards\n"
                    )

        await session.commit()

    await engine.dispose()
    sys.stdout.write(
        f"Board rebalance complete: {columns_processed} columns inspected, "
        f"{total_reindexed} cards reindexed across {len(projects)} projects\n"
    )
    return 0


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

    rebalance_p = run_subs.add_parser(
        "board-rebalance",
        help="Rebalance column board ranks that exceed threshold or require compaction",
    )
    rebalance_p.add_argument(
        "--project",
        default=None,
        help="Optional project identifier to restrict rebalancing",
    )
    rebalance_p.set_defaults(
        func=_handle_board_rebalance,
        handler=_handle_board_rebalance,
    )

    trash_purge_parser = run_subs.add_parser(
        "trash-purge",
        help="Run periodic trash retention purge pass for expired issues",
    )
    trash_purge_parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Optional ISO-8601 reference timestamp (e.g. 2026-11-11T00:00:00Z)",
    )
    trash_purge_parser.set_defaults(
        func=handle_run_trash_purge,
        handler=handle_run_trash_purge,
    )

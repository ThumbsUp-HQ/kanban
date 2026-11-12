"""Jobs CLI subcommands for background maintenance tasks (KB-P3-12)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import sys
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models.projects import Project, WorkflowState
from database.testing.pg_harness import build_dsn
from kanban.jobs.board_rebalance import rebalance_column

if TYPE_CHECKING:
    import argparse


def register_jobs_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'jobs' subcommands under kanban-ctl."""
    jobs_parser = subparsers.add_parser("jobs", help="Background job runner commands")
    jobs_sub = jobs_parser.add_subparsers(dest="jobs_command", required=True)

    run_parser = jobs_sub.add_parser("run", help="Execute a scheduled maintenance job")
    run_sub = run_parser.add_subparsers(dest="job_name", required=True)

    rebalance_p = run_sub.add_parser(
        "board-rebalance",
        help="Rebalance column board ranks that exceed threshold or require compaction",
    )
    rebalance_p.add_argument(
        "--project",
        default=None,
        help="Optional project identifier to restrict rebalancing",
    )
    rebalance_p.set_defaults(func=_handle_board_rebalance)


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

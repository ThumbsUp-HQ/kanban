# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI subcommand run-gate-worker executing GateWorker against transition gates (KAN-45)."""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    import argparse

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
)
from agent.gates.runner import GateWorkerRunner
from database.session import RLSSessionFactory


def configure_run_gate_worker_parser(parser: argparse.ArgumentParser) -> None:
    """Configure CLI argument flags for run-gate-worker."""
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds for pending gate executions.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Poll once and exit immediately.",
    )


async def handle_run_gate_worker(
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber = default_context_scrubber,
) -> tuple[ValidationReport, ExitCode]:
    """Execute gate worker runner loop or single poll."""
    del scrubber
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://kanban_app:kanban@localhost:5432/kanban"
    )
    engine = create_async_engine(db_url, pool_pre_ping=True)
    sf = RLSSessionFactory(engine)
    runner = GateWorkerRunner(session_factory=sf, poll_interval_s=args.poll_interval)

    if args.once:
        count = await runner.poll_once()
        report = ValidationReport(
            command="run-gate-worker",
            rendered_context=f"Processed {count} gate dispatches.",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(valid=True, status="passed"),
        )
        return report, ExitCode.OK

    stop_event = asyncio.Event()
    with contextlib.suppress(asyncio.CancelledError, KeyboardInterrupt):
        await runner.run(stop_event)

    report = ValidationReport(
        command="run-gate-worker",
        rendered_context="Gate worker runner stopped cleanly.",
        tool_trace=(),
        metrics=ReportMetrics(total_latency_ms=0.0),
        schema_status=SchemaStatus(valid=True, status="passed"),
    )
    return report, ExitCode.OK

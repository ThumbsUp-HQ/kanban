# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI commands for cutover verification and parity auditing (KB-P6-02, S15.5)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from kanban.importer.cutover_verifier import CutoverAuditReport, verify_cutover

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
    dbname = os.environ.get("KB_DATABASE_NAME", "kanban_test_master")
    return f"postgresql+asyncpg://{user}@/{dbname}?host={socket_dir}"


def register_cutover_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'cutover' command and nested subcommands."""
    cutover_parser = subparsers.add_parser(
        "cutover",
        help="Cutover verification and validation tools",
    )
    cutover_sub = cutover_parser.add_subparsers(dest="cutover_action", required=True)

    verify_parser = cutover_sub.add_parser(
        "verify",
        help="Verify 1:1 entity parity, zero invalid links, hash-chain and markdown purity",
    )
    verify_parser.add_argument(
        "--bundle-dir",
        required=True,
        help="Path to snapshot bundle directory exported from Plane",
    )
    verify_parser.add_argument(
        "--workspace",
        required=True,
        help="Target workspace slug under verification",
    )
    verify_parser.add_argument(
        "--project",
        required=True,
        help="Project identifier key (e.g. KANBA)",
    )
    verify_parser.add_argument(
        "--qa-root",
        default="./docs/qa",
        help="Root path containing QA proof bundles (default: ./docs/qa)",
    )
    verify_parser.add_argument(
        "--pre-cutover-exempt-keys",
        default="",
        help="Comma-separated issue keys exempt from mandatory QA proof bundles",
    )
    verify_parser.add_argument(
        "--json-out",
        help="Optional path to write raw JSON format verification report",
    )
    verify_parser.set_defaults(func=_run_cutover_verify)


def _run_cutover_verify(args: argparse.Namespace) -> int:
    """Execute cutover verification command."""
    bundle_path = Path(args.bundle_dir).resolve()
    if not bundle_path.is_dir():
        sys.stderr.write(f"Error: Bundle directory '{bundle_path}' not found.\n")
        return 2

    qa_root_path = Path(args.qa_root).resolve()

    exempt_keys: list[str] = []
    if args.pre_cutover_exempt_keys:
        exempt_keys = [k.strip() for k in args.pre_cutover_exempt_keys.split(",") if k.strip()]

    try:
        return asyncio.run(
            _execute_verify(
                bundle_path=bundle_path,
                workspace_slug=args.workspace,
                project_identifier=args.project,
                qa_root=qa_root_path,
                exempt_keys=exempt_keys,
                json_out=args.json_out,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
        sys.stderr.write(f"Runtime Error: {exc}\n")
        return 1


async def _execute_verify(  # noqa: PLR0913, PLR0917
    bundle_path: Path,
    workspace_slug: str,
    project_identifier: str,
    qa_root: Path,
    exempt_keys: list[str],
    json_out: str | None,
) -> int:
    """Run verification checks inside administrative async session."""
    dsn = _get_admin_dsn()
    engine = create_async_engine(dsn, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # Set migration/admin role authorization
            await session.execute(text("SET SESSION AUTHORIZATION kanban_migrator"))

            report: CutoverAuditReport = await verify_cutover(
                session=session,
                bundle_dir=bundle_path,
                workspace_slug=workspace_slug,
                project_identifier=project_identifier,
                qa_root=qa_root,
                pre_cutover_exempt_keys=exempt_keys,
            )

            # Output formatted report
            _print_console_report(report)

            if json_out:
                await asyncio.to_thread(_write_json_report, json_out, report)
                sys.stdout.write(f"Wrote full JSON report to {json_out}\n")

            return 0 if report.overall_passed else 2
    finally:
        await engine.dispose()


def _print_console_report(report: CutoverAuditReport) -> None:
    """Print readable table summary of cutover verification report."""
    status_str = "PASSED" if report.overall_passed else "FAILED"
    passed = report.summary.get("passed_checks", 0)
    total = report.summary.get("total_checks", 0)
    sys.stdout.write("\n=== Cutover Verification Audit Report ===\n")
    sys.stdout.write(f"Workspace: {report.workspace_slug} | Project: {report.project_identifier}\n")
    sys.stdout.write(f"Overall Status: {status_str} ({passed}/{total} checks passed)\n")
    sys.stdout.write("-" * 88 + "\n")
    sys.stdout.write(f"{'Check Name':<34} {'Status':<8} {'Details / Error'}\n")
    sys.stdout.write("-" * 88 + "\n")

    for chk in report.checks:
        chk_status = "PASS" if chk.passed else "FAIL"
        err_prefix = f"[{chk.error_code}] " if chk.error_code else ""
        detail_msg = chk.detail or ""
        sys.stdout.write(f"{chk.name:<34} {chk_status:<8} {err_prefix}{detail_msg}\n")

    sys.stdout.write("-" * 88 + "\n\n")


def _write_json_report(path_str: str, report: CutoverAuditReport) -> None:
    """Write audit report in JSON format to filesystem."""
    out_path = Path(path_str).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")

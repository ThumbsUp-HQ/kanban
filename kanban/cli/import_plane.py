# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI commands for Plane export import and snapshot fetching (KB-P6-01, S1.3)."""
# ruff: noqa: C901, PLR0911, PLR0912, PLR0915, E501

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import argparse

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kanban.api.deps import PrincipalContext
from kanban.importer.github_importer import GitHubIssuesImporter
from kanban.importer.jira_importer import JiraImporter
from kanban.importer.linear_importer import LinearImporter
from kanban.importer.plane_client import (
    PlaneBundle,
    PlaneClient,
    PlaneClientError,
    PlaneSecurityError,
)
from kanban.importer.plane_importer import (
    ImportDiffReport,
    ImportIntegrityError,
    PlaneImporter,
)

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


def register_import_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'import' root subcommand and Plane import/fetch utilities."""
    import_parser = subparsers.add_parser(
        "import",
        help="Data migration and external import utilities",
        description="Lossless migration utilities for external issue tracking systems",
    )
    import_subparsers = import_parser.add_subparsers(dest="import_subcommand", required=True)

    # 1. kanban-ctl import plane
    plane_parser = import_subparsers.add_parser(
        "plane",
        help="Import Plane export bundle or fetch live snapshot",
        description="Lossless Plane importer with exact sequence continuity (KB-P6-01)",
    )

    plane_subparsers = plane_parser.add_subparsers(dest="plane_action")

    # kanban-ctl import plane fetch-snapshot ...
    fetch_parser = plane_subparsers.add_parser(
        "fetch-snapshot",
        help="Fetch snapshot from live Plane instance into export directory",
    )
    fetch_parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL of Plane instance (e.g. https://kanban.hackedyour.info/kanban/)",
    )
    fetch_parser.add_argument(
        "--workspace-slug",
        required=True,
        help="Plane workspace slug",
    )
    fetch_parser.add_argument(
        "--project-identifier",
        required=True,
        help="Plane project identifier (e.g. KANBA)",
    )
    fetch_parser.add_argument(
        "--out-dir",
        required=True,
        help="Directory to write exported snapshot JSON files and attachments",
    )
    fetch_parser.add_argument(
        "--allow-loopback-http",
        action="store_true",
        help="Permit http:// scheme on loopback addresses for testing",
    )
    fetch_parser.add_argument(
        "--allow-private-cidr",
        action="store_true",
        help="Permit private/link-local CIDRs for testing",
    )
    fetch_parser.set_defaults(func=_run_fetch_snapshot)

    # Default import arguments on plane_parser
    plane_parser.add_argument(
        "--bundle-dir",
        help="Directory containing exported Plane JSON pages and attachments",
    )
    plane_parser.add_argument(
        "--workspace",
        help="Target Kanban workspace slug",
    )
    plane_parser.add_argument(
        "--user-map",
        help="Path to YAML or JSON file mapping Plane user IDs to Kanban handles",
    )
    plane_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import and output diff report without committing database changes",
    )
    plane_parser.add_argument(
        "--report-out",
        help="Optional path to write JSON format diff report",
    )
    plane_parser.set_defaults(func=_run_plane_import)

    # 2. kanban-ctl import jira
    jira_parser = import_subparsers.add_parser(
        "jira",
        help="Import Jira Cloud or Server/DC JSON export",
        description="Jira issue importer converting ADF/HTML to Markdown and creating issue aliases",
    )
    jira_parser.add_argument("--file", help="Path to Jira export JSON file")
    jira_parser.add_argument("--bundle-dir", help="Directory containing Jira export JSON")
    jira_parser.add_argument("--workspace", required=True, help="Target Kanban workspace slug")
    jira_parser.add_argument(
        "--project-key", default="JIRA", help="Target project key (default: JIRA)"
    )
    jira_parser.add_argument(
        "--user-map", help="Path to YAML or JSON file mapping Jira user IDs to Kanban handles"
    )
    jira_parser.add_argument(
        "--dry-run", action="store_true", help="Simulate import and output diff report"
    )
    jira_parser.add_argument("--report-out", help="Optional path to write JSON format diff report")
    jira_parser.set_defaults(func=lambda a: _run_generic_import(a, "jira"))

    # 3. kanban-ctl import github
    github_parser = import_subparsers.add_parser(
        "github",
        help="Import GitHub Issues JSON export",
        description="GitHub Issues importer creating GH-<number> aliases",
    )
    github_parser.add_argument("--file", help="Path to GitHub issues JSON file")
    github_parser.add_argument("--bundle-dir", help="Directory containing GitHub issues JSON")
    github_parser.add_argument("--workspace", required=True, help="Target Kanban workspace slug")
    github_parser.add_argument(
        "--project-key", default="GH", help="Target project key (default: GH)"
    )
    github_parser.add_argument(
        "--user-map", help="Path to YAML or JSON file mapping GitHub logins to Kanban handles"
    )
    github_parser.add_argument(
        "--dry-run", action="store_true", help="Simulate import and output diff report"
    )
    github_parser.add_argument(
        "--report-out", help="Optional path to write JSON format diff report"
    )
    github_parser.set_defaults(func=lambda a: _run_generic_import(a, "github"))

    # 4. kanban-ctl import linear
    linear_parser = import_subparsers.add_parser(
        "linear",
        help="Import Linear JSON or CSV export",
        description="Linear importer creating ENG-<number> aliases and DAG relationships",
    )
    linear_parser.add_argument("--file", help="Path to Linear export JSON or CSV file")
    linear_parser.add_argument("--bundle-dir", help="Directory containing Linear export files")
    linear_parser.add_argument("--workspace", required=True, help="Target Kanban workspace slug")
    linear_parser.add_argument(
        "--project-key", default="LIN", help="Target project key (default: LIN)"
    )
    linear_parser.add_argument(
        "--user-map", help="Path to YAML or JSON file mapping Linear users to Kanban handles"
    )
    linear_parser.add_argument(
        "--dry-run", action="store_true", help="Simulate import and output diff report"
    )
    linear_parser.add_argument(
        "--report-out", help="Optional path to write JSON format diff report"
    )
    linear_parser.set_defaults(func=lambda a: _run_generic_import(a, "linear"))


def _run_fetch_snapshot(args: argparse.Namespace) -> int:
    """Execute live Plane snapshot fetch."""
    client = PlaneClient(
        allow_loopback_http=args.allow_loopback_http,
        allow_private_cidr=args.allow_private_cidr,
    )
    try:
        asyncio.run(
            client.fetch_snapshot(
                base_url=args.base_url,
                workspace_slug=args.workspace_slug,
                project_identifier=args.project_identifier,
                out_dir=args.out_dir,
            )
        )
        sys.stdout.write(f"Snapshot fetched successfully to {args.out_dir}\n")
    except (PlaneSecurityError, PlaneClientError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 1
    else:
        return 0


def _run_plane_import(args: argparse.Namespace) -> int:
    """Execute Plane import against database."""
    if not args.bundle_dir or not args.workspace:
        sys.stderr.write("Error: --bundle-dir and --workspace are required for plane import.\n")
        return 2

    bundle_path = Path(args.bundle_dir).resolve()
    if not bundle_path.is_dir():
        sys.stderr.write(f"Error: Bundle directory not found: {bundle_path}\n")
        return 2

    # Load user map if provided
    user_map: dict[str, str] = {}
    if args.user_map:
        user_map_path = Path(args.user_map).resolve()
        if not user_map_path.is_file():
            sys.stderr.write(f"Error: User map file not found: {user_map_path}\n")
            return 2
        try:
            content = user_map_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                user_map = {str(k): str(v) for k, v in loaded.items()}
        except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
            sys.stderr.write(f"Error: Failed to parse user map file: {exc}\n")
            return 2

    # Load Plane bundle
    client = PlaneClient()
    try:
        bundle = client.load_bundle_from_dir(bundle_path)
    except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
        sys.stderr.write(f"Error loading bundle: {exc}\n")
        return 2

    return asyncio.run(_execute_import_db(args, bundle, user_map))


async def _execute_import_db(
    args: argparse.Namespace,
    bundle: PlaneBundle,
    user_map: dict[str, str],
) -> int:
    dsn = _get_admin_dsn()
    engine = create_async_engine(dsn, isolation_level="READ COMMITTED")
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_maker() as session:
            # 1. Resolve workspace
            ws_res = await session.execute(
                text("SELECT id FROM workspaces WHERE slug = :slug"),
                {"slug": args.workspace},
            )
            ws_id = ws_res.scalar_one_or_none()
            if not ws_id:
                sys.stderr.write(f"Error: Workspace slug '{args.workspace}' not found.\n")
                return 2

            # 2. Resolve admin principal in workspace
            principal_res = await session.execute(
                text(
                    "SELECT principal_id FROM role_bindings "
                    "WHERE workspace_id = :ws "
                    "AND role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN') "
                    "LIMIT 1"
                ),
                {"ws": ws_id},
            )
            principal_id = principal_res.scalar_one_or_none()
            if not principal_id:
                # Fallback to any user principal
                p_fallback = await session.execute(
                    text(
                        "SELECT id FROM principals "
                        "WHERE workspace_id = :ws AND principal_type = 'USER' LIMIT 1"
                    ),
                    {"ws": ws_id},
                )
                principal_id = p_fallback.scalar_one_or_none()

            if not principal_id:
                principal_id = uuid.uuid4()

            # Set session GUCs
            await session.execute(
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

            importer = PlaneImporter(
                session=session,
                caller=caller,
                user_map=user_map,
            )

            try:
                report = await importer.run_import(bundle, dry_run=args.dry_run)
                if not args.dry_run:
                    await session.commit()
            except ImportIntegrityError as exc:
                await session.rollback()
                sys.stderr.write(f"Integrity Error: {exc}\n")
                return 2
            except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
                await session.rollback()
                sys.stderr.write(f"Runtime Error: {exc}\n")
                return 1

            # Format console output
            mode_str = "DRY-RUN" if args.dry_run else "LIVE"
            sys.stdout.write(f"=== Plane Import Complete ({mode_str}) ===\n")
            sys.stdout.write(f"To Create: {report.to_create}\n")
            sys.stdout.write(f"To Update: {report.to_update}\n")
            sys.stdout.write(f"Unchanged: {report.unchanged}\n")
            sys.stdout.write(f"Sequence High Water Mark: {report.sequence_high_water_mark}\n")
            sys.stdout.write(f"Rewritten Attachments: {report.rewritten_attachments}\n")
            sys.stdout.write(f"Invalid Links: {report.invalid_link_count}\n")
            if report.warnings:
                sys.stdout.write(f"Warnings ({len(report.warnings)}):\n")
                for w in report.warnings:
                    sys.stdout.write(f"  - {w}\n")

            if args.report_out:
                await asyncio.to_thread(_write_report_file, args.report_out, report)
                sys.stdout.write(f"Wrote report to {args.report_out}\n")

            return 0
    finally:
        await engine.dispose()


def _write_report_file(path_str: str, report: ImportDiffReport) -> None:
    """Write import diff report to filesystem synchronously."""
    out_path = Path(path_str).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")


def _run_generic_import(args: argparse.Namespace, source: str) -> int:
    """Execute generic source import (jira, github, linear) against database."""
    target_path_str = getattr(args, "file", None) or getattr(args, "bundle_dir", None)
    if not target_path_str:
        sys.stderr.write(f"Error: Either --file or --bundle-dir is required for {source} import.\n")
        return 2

    p = Path(target_path_str).resolve()
    if not p.exists():
        sys.stderr.write(f"Error: Path not found: {p}\n")
        return 2

    raw_data: Any = None
    if p.is_file():
        content = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".csv" or (
            source == "linear" and not content.strip().startswith(("{", "["))
        ):
            raw_data = content
        else:
            try:
                raw_data = json.loads(content)
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"Error: Failed to parse JSON file {p}: {exc}\n")
                return 2
    elif p.is_dir():
        for cand in (
            "issues.json",
            "export.json",
            "bundle.json",
            f"{source}.json",
            f"{source}.csv",
        ):
            cand_p = p / cand
            if cand_p.is_file():
                content = cand_p.read_text(encoding="utf-8")
                if cand.endswith(".csv"):
                    raw_data = content
                else:
                    try:
                        raw_data = json.loads(content)
                    except Exception as exc:  # noqa: BLE001
                        sys.stderr.write(f"Error: Failed to parse JSON file {cand_p}: {exc}\n")
                        return 2
                break
        if raw_data is None:
            sys.stderr.write(f"Error: No valid JSON/CSV export found inside {p}\n")
            return 2

    user_map: dict[str, str] = {}
    if getattr(args, "user_map", None):
        user_map_path = Path(args.user_map).resolve()
        if not user_map_path.is_file():
            sys.stderr.write(f"Error: User map file not found: {user_map_path}\n")
            return 2
        try:
            content = user_map_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                user_map = {str(k): str(v) for k, v in loaded.items()}
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"Error: Failed to parse user map file: {exc}\n")
            return 2

    return asyncio.run(_execute_generic_import_db(args, source, raw_data, user_map))


async def _execute_generic_import_db(
    args: argparse.Namespace,
    source: str,
    data: object,
    user_map: dict[str, str],
) -> int:
    dsn = _get_admin_dsn()
    engine = create_async_engine(dsn, isolation_level="READ COMMITTED")
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_maker() as session:
            ws_res = await session.execute(
                text("SELECT id FROM workspaces WHERE slug = :slug"),
                {"slug": args.workspace},
            )
            ws_id = ws_res.scalar_one_or_none()
            if not ws_id:
                sys.stderr.write(f"Error: Workspace slug '{args.workspace}' not found.\n")
                return 2

            principal_res = await session.execute(
                text(
                    "SELECT principal_id FROM role_bindings "
                    "WHERE workspace_id = :ws "
                    "AND role::text IN ('WORKSPACE_ADMIN', 'SERVER_ADMIN') "
                    "LIMIT 1"
                ),
                {"ws": ws_id},
            )
            principal_id = principal_res.scalar_one_or_none()
            if not principal_id:
                p_fallback = await session.execute(
                    text(
                        "SELECT id FROM principals "
                        "WHERE workspace_id = :ws AND principal_type = 'USER' LIMIT 1"
                    ),
                    {"ws": ws_id},
                )
                principal_id = p_fallback.scalar_one_or_none()
            if not principal_id:
                principal_id = uuid.uuid4()

            await session.execute(
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

            importer: JiraImporter | GitHubIssuesImporter | LinearImporter
            if source == "jira":
                importer = JiraImporter(session=session, caller=caller, user_map=user_map)
            elif source == "github":
                importer = GitHubIssuesImporter(session=session, caller=caller, user_map=user_map)
            elif source == "linear":
                importer = LinearImporter(session=session, caller=caller, user_map=user_map)
            else:
                sys.stderr.write(f"Error: Unsupported source system: {source}\n")
                return 2

            target_key = getattr(args, "project_key", None) or source.upper()

            try:
                report = await importer.run_import(
                    cast("Any", data), target_project_key=target_key, dry_run=args.dry_run
                )
                if not args.dry_run:
                    await session.commit()
            except ImportIntegrityError as exc:
                await session.rollback()
                sys.stderr.write(f"Integrity Error: {exc}\n")
                return 2
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                sys.stderr.write(f"Runtime Error: {exc}\n")
                return 1

            mode_str = "DRY-RUN" if args.dry_run else "LIVE"
            sys.stdout.write(f"=== {source.capitalize()} Import Complete ({mode_str}) ===\n")
            sys.stdout.write(f"To Create: {report.to_create}\n")
            sys.stdout.write(f"To Update: {report.to_update}\n")
            sys.stdout.write(f"Unchanged: {report.unchanged}\n")
            sys.stdout.write(f"Sequence High Water Mark: {report.sequence_high_water_mark}\n")
            sys.stdout.write(f"Rewritten Attachments: {report.rewritten_attachments}\n")
            sys.stdout.write(f"Invalid Links: {report.invalid_link_count}\n")
            if report.warnings:
                sys.stdout.write(f"Warnings ({len(report.warnings)}):\n")
                for w in report.warnings:
                    sys.stdout.write(f"  - {w}\n")

            if getattr(args, "report_out", None):
                await asyncio.to_thread(_write_report_file, args.report_out, report)
                sys.stdout.write(f"Wrote report to {args.report_out}\n")

            return 0
    finally:
        await engine.dispose()

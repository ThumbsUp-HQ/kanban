# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI entrypoint for database migration operations.

Exposes:
- new-migration: Generate a new Alembic migration with paired .up.sql / .down.sql
- check-migrations: Validate migration consistency, naming, and single-head linear chain
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.migrations.scaffold import scaffold_migration
from database.migrations.validator import validate_migrations_full, validate_migrations_static
from database.session import create_rls_engine

if TYPE_CHECKING:
    from collections.abc import Sequence


def _cmd_new_migration(args: argparse.Namespace) -> int:
    """Handle new-migration command."""
    try:
        result = scaffold_migration(
            rev_id=args.rev_id,
            message=args.message,
            table=args.table,
            template=args.template,
            alembic_ini_path=args.alembic_ini,
            base_dir=args.base_dir,
        )
    except (ValueError, RuntimeError, FileExistsError) as err:
        sys.stderr.write(f"Error creating migration: {err}\n")
        return 2

    out = {
        "status": "created",
        "rev_id": result.rev_id,
        "down_revision": result.down_revision,
        "files": {
            "version": str(result.version_file),
            "up_sql": str(result.up_sql_file),
            "down_sql": str(result.down_sql_file),
            "test": str(result.test_file),
        },
    }
    if args.json_out:
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
    else:
        sys.stdout.write(f"Successfully generated migration '{result.rev_id}':\n")
        sys.stdout.write(f"  Version:   {result.version_file}\n")
        sys.stdout.write(f"  Up SQL:    {result.up_sql_file}\n")
        sys.stdout.write(f"  Down SQL:  {result.down_sql_file}\n")
        sys.stdout.write(f"  Test:      {result.test_file}\n")
        sys.stdout.write(f"  Revises:   {result.down_revision}\n")

    return 0


async def _run_full_validation(args: argparse.Namespace) -> Any:  # noqa: ANN401
    """Run full validation connecting to PostgreSQL."""
    engine = create_rls_engine(args.db_url)
    async with AsyncSession(engine) as session:
        return await validate_migrations_full(
            session,
            alembic_ini_path=args.alembic_ini,
            base_dir=args.base_dir,
        )


def _cmd_check_migrations(args: argparse.Namespace) -> int:
    """Handle check-migrations command."""
    if args.static_only or not getattr(args, "db_url", None):
        report = validate_migrations_static(
            alembic_ini_path=args.alembic_ini,
            base_dir=args.base_dir,
        )
    else:
        report = asyncio.run(_run_full_validation(args))

    if args.json_out:
        sys.stdout.write(report.to_json(indent=2) + "\n")
    elif report.valid:
        head_name = report.heads[0] if report.heads else "none"
        sys.stdout.write(
            f"OK: All {report.total_revisions} migrations valid. Single head: {head_name}\n"
        )
    else:
        sys.stderr.write(f"FAILED: Found {len(report.issues)} migration consistency issues:\n")
        for issue in report.issues:
            sys.stderr.write(f"  [{issue.severity.upper()}] {issue.check}: {issue.message}\n")

    return 0 if report.valid else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for database migration commands."""
    parser = argparse.ArgumentParser(
        prog="database.migrations.cli",
        description="Database migration and schema governance CLI",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # new-migration
    new_p = subparsers.add_parser(
        "new-migration",
        help="Generate a new linear Alembic migration with SQL and test templates",
    )
    new_p.add_argument(
        "rev_id",
        help="Revision ID (e.g. p4_19_my_feature, must match ^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$)",
    )
    new_p.add_argument(
        "--message",
        "-m",
        required=True,
        help="Human-readable summary of the migration",
    )
    new_p.add_argument(
        "--table",
        "-t",
        default=None,
        help="Target table or function name (defaults to slug from rev_id)",
    )
    new_p.add_argument(
        "--template",
        choices=["tenant", "isolated", "func"],
        default="tenant",
        help="SQL template kind: tenant (default), isolated, or func",
    )
    new_p.add_argument(
        "--alembic-ini",
        default="database/alembic.ini",
        help="Path to alembic.ini (default: database/alembic.ini)",
    )
    new_p.add_argument(
        "--base-dir",
        default="database",
        help="Path to database root directory (default: database)",
    )
    new_p.add_argument(
        "--json-out",
        action="store_true",
        help="Output result as JSON",
    )
    new_p.set_defaults(func=_cmd_new_migration)

    # check-migrations
    check_p = subparsers.add_parser(
        "check-migrations",
        help="Validate migration consistency, naming, and linear chain",
    )
    check_p.add_argument(
        "--static-only",
        action="store_true",
        default=True,
        help="Run fast offline static checks without connecting to PostgreSQL (default: True)",
    )
    check_p.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL connection URL for full catalog validation",
    )
    check_p.add_argument(
        "--alembic-ini",
        default="database/alembic.ini",
        help="Path to alembic.ini (default: database/alembic.ini)",
    )
    check_p.add_argument(
        "--base-dir",
        default="database",
        help="Path to database root directory (default: database)",
    )
    check_p.add_argument(
        "--json-out",
        action="store_true",
        help="Output validation report as JSON",
    )
    check_p.set_defaults(func=_cmd_check_migrations)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute migration CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

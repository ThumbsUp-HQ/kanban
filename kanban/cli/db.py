# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database migration management CLI subcommands for kanban-ctl.

Thin wrapper delegating to database.migrations.cli to preserve layering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from database.migrations.cli import _cmd_check_migrations, _cmd_new_migration

if TYPE_CHECKING:
    import argparse


def register_db_subparsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register 'db' subcommand group on kanban-ctl."""
    db_parser = subparsers.add_parser(
        "db",
        help="Database migration and schema governance commands",
    )
    db_subs = db_parser.add_subparsers(dest="db_action", required=True)

    # kanban-ctl db new-migration
    new_p = db_subs.add_parser(
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

    # kanban-ctl db check-migrations
    check_p = db_subs.add_parser(
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

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Modules schema: description, lead, status, and issue_modules audit (KB-P3-10b).

Revision ID: p3_10b_modules
Revises: p2_05a_mfa_totp_recovery
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_10b_modules"
down_revision: str | None = "p2_05a_mfa_totp_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply modules schema extensions and module_issues view."""
    execute_sql_file("p3_10b_modules.up.sql")


def downgrade() -> None:
    """Revert modules schema extensions and module_issues view."""
    execute_sql_file("p3_10b_modules.down.sql")

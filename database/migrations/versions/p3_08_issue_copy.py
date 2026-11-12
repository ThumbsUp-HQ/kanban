# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Make a copy issue subtree collector function (KB-P3-08).

Revision ID: p3_08_issue_copy
Revises: p2_05a_mfa_totp_recovery
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_08_issue_copy"
down_revision: str | None = "p2_05a_mfa_totp_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply issues_get_copy_subtrees function and permissions."""
    execute_sql_file("p3_08_issue_copy.up.sql")


def downgrade() -> None:
    """Revert issues_get_copy_subtrees function."""
    execute_sql_file("p3_08_issue_copy.down.sql")

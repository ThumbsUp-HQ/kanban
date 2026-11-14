"""Auth card admin ops and public enabled projection (KB-P2-10).

Revision ID: p2_10_auth_card_admin_ops
Revises: p3_08_issue_copy
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_10_auth_card_admin_ops"
down_revision: str | None = "p3_08_issue_copy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply auth card admin ops DDL, functions, and public projection."""
    execute_sql_file("p2_10_auth_card_admin_ops.up.sql")


def downgrade() -> None:
    """Revert auth card admin ops DDL, functions, and public projection."""
    execute_sql_file("p2_10_auth_card_admin_ops.down.sql")

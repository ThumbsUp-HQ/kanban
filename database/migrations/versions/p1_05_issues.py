"""Issues table, atomic sequence allocation, and build_markdown_tsvector.

Revision ID: p1_05_issues
Revises: p1_10_views
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_05_issues"
down_revision: str | None = "p1_10_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply issues table, sequence allocation, and markdown tsvector."""
    execute_sql_file("p1_05_issues.up.sql")


def downgrade() -> None:
    """Revert issues table, sequence allocation, and markdown tsvector."""
    execute_sql_file("p1_05_issues.down.sql")

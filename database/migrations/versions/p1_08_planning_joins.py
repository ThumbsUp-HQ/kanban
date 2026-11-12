"""Cycles, modules, assignees, labels, and subscriptions join tables.

Revision ID: p1_08_planning_joins
Revises: p1_05_issues
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_08_planning_joins"
down_revision: str | None = "p1_05_issues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply cycles, modules, and planning join tables."""
    execute_sql_file("p1_08_planning_joins.up.sql")


def downgrade() -> None:
    """Revert cycles, modules, and planning join tables."""
    execute_sql_file("p1_08_planning_joins.down.sql")

"""Parent DAG trigger with FOR UPDATE ancestor locks and ltree ancestry.

Revision ID: p1_06_parent_dag
Revises: p1_08_planning_joins
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_06_parent_dag"
down_revision: str | None = "p1_08_planning_joins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply parent DAG triggers, GiST index, depth check, and label helper."""
    execute_sql_file("p1_06_parent_dag.up.sql")


def downgrade() -> None:
    """Revert parent DAG triggers, GiST index, and restore KB-P1-05 path logic."""
    execute_sql_file("p1_06_parent_dag.down.sql")

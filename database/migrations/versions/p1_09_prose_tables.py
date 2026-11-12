"""Prose tables: issue_comments, docs, pages, page_versions, and stickies.

Revision ID: p1_09_prose_tables
Revises: p1_06_parent_dag
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_09_prose_tables"
down_revision: str | None = "p1_06_parent_dag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply prose tables, versioning, hierarchy, and immutability triggers."""
    execute_sql_file("p1_09_prose_tables.up.sql")


def downgrade() -> None:
    """Revert prose tables, versioning, hierarchy, and immutability triggers."""
    execute_sql_file("p1_09_prose_tables.down.sql")

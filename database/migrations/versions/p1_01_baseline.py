"""Alembic async baseline migration: roles, extensions, and uuidv7.

Revision ID: p1_01_baseline
Revises: None
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_01_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply baseline schema objects and functions."""
    execute_sql_file("p1_01_baseline.up.sql")


def downgrade() -> None:
    """Revert baseline schema objects and functions."""
    execute_sql_file("p1_01_baseline.down.sql")

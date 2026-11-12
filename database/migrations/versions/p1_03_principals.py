"""Principals, users, groups, and cycle-safe principal_group_closure.

Revision ID: p1_03_principals
Revises: p1_02_objects_spine
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_03_principals"
down_revision: str | None = "p1_02_objects_spine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply principals, users, groups, edges, and closure."""
    execute_sql_file("p1_03_principals.up.sql")


def downgrade() -> None:
    """Revert principals, users, groups, edges, and closure."""
    execute_sql_file("p1_03_principals.down.sql")

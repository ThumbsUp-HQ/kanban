"""Workspaces and objects spine, object_kind enum, and register_object.

Revision ID: p1_02_objects_spine
Revises: p1_01_baseline
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_02_objects_spine"
down_revision: str | None = "p1_01_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply workspaces, object_kind, objects spine, and register_object."""
    execute_sql_file("p1_02_objects_spine.up.sql")


def downgrade() -> None:
    """Revert workspaces, object_kind, objects spine, and register_object."""
    execute_sql_file("p1_02_objects_spine.down.sql")

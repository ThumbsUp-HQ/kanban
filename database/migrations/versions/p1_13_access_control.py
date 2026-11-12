"""Role bindings, resource ACL entries, and effective_resource_access.

Revision ID: p1_13_access_control
Revises: p1_10_views
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_13_access_control"
down_revision: str | None = "p1_10_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply access control tables, enums, functions, and triggers."""
    execute_sql_file("p1_13_access_control.up.sql")


def downgrade() -> None:
    """Revert access control tables, enums, functions, and triggers."""
    execute_sql_file("p1_13_access_control.down.sql")

"""Views table, view_layout enum, and filter/WIP JSON validators.

Revision ID: p1_10_views
Revises: p1_11_object_links
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_10_views"
down_revision: str | None = "p1_11_object_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply view_layout enum, validator functions, and views table."""
    execute_sql_file("p1_10_views.up.sql")


def downgrade() -> None:
    """Revert views table, validator functions, and view_layout enum."""
    execute_sql_file("p1_10_views.down.sql")

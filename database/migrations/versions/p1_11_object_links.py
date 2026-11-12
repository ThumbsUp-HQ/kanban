"""Object links, link_kind enum, and link_type_matrix allowlist.

Revision ID: p1_11_object_links
Revises: p1_02_objects_spine
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_11_object_links"
down_revision: str | None = "p1_02_objects_spine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply link_kind enum, object_links table, and link_type_matrix catalog."""
    execute_sql_file("p1_11_object_links.up.sql")


def downgrade() -> None:
    """Revert object_links table, link_type_matrix catalog, and link_kind enum."""
    execute_sql_file("p1_11_object_links.down.sql")

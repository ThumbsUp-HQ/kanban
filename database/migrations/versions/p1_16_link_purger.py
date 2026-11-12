"""purge_invalid_object_links() admin-only audited purge & INVALID_OBJECT_LINK_PURGED ledger.

Revision ID: p1_16_link_purger
Revises: p1_15_link_auditor
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_16_link_purger"
down_revision: str | None = "p1_15_link_auditor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply purge_invalid_object_links function and delete guard trigger."""
    execute_sql_file("p1_16_link_purger.up.sql")


def downgrade() -> None:
    """Revert purge_invalid_object_links function and delete guard trigger."""
    execute_sql_file("p1_16_link_purger.down.sql")

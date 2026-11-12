"""audit_object_links() 6-reason detector, invalid_object_link_audits & incremental triggers.

Revision ID: p1_15_link_auditor
Revises: p1_14_force_rls
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_15_link_auditor"
down_revision: str | None = "p1_14_force_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply audit_object_links detector, audits table, and incremental triggers."""
    execute_sql_file("p1_15_link_auditor.up.sql")


def downgrade() -> None:
    """Revert audit_object_links detector, audits table, and incremental triggers."""
    execute_sql_file("p1_15_link_auditor.down.sql")

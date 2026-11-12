"""attachments (FORCE RLS, metadata guards, content-addressed storage keys).

Revision ID: p2_15_attachments
Revises: p3_01b_workflow_state_wip_limits
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_15_attachments"
down_revision: str | None = "p3_01b_workflow_state_wip_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply attachments DDL, triggers, FORCE RLS, and access policies."""
    execute_sql_file("p2_15_attachments.up.sql")


def downgrade() -> None:
    """Revert attachments DDL, triggers, and policies."""
    execute_sql_file("p2_15_attachments.down.sql")

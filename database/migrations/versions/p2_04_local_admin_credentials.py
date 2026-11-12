# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Local Admin credentials and kb_auth functions (KB-P2-04).

Revision ID: p2_04_local_admin_credentials
Revises: p2_15_attachments
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_04_local_admin_credentials"
down_revision: str | None = "p2_15_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply local_admin_credentials DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_04_local_admin_credentials.up.sql")


def downgrade() -> None:
    """Revert local_admin_credentials DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_04_local_admin_credentials.down.sql")

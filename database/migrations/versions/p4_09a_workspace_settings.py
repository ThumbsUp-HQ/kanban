# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""DDL workspace_settings table, FORCE RLS, defaults & triggers (KB-P4-09a).

Revision ID: p4_09a_workspace_settings
Revises: p5_12_custom_field_approvals
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_09a_workspace_settings"
down_revision: str | None = "p5_12_custom_field_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply workspace_settings DDL, FORCE RLS, and triggers."""
    execute_sql_file("p4_09a_workspace_settings.up.sql")


def downgrade() -> None:
    """Revert workspace_settings DDL, FORCE RLS, and triggers."""
    execute_sql_file("p4_09a_workspace_settings.down.sql")

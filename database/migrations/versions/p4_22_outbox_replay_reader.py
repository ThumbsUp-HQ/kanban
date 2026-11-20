# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add SECURITY DEFINER outbox replay read routines.

Revision ID: p4_22_outbox_replay_reader
Revises: p4_21_workspace_project_rbac_fix
Create Date: 2026-11-20 10:27:46.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_22_outbox_replay_reader"
down_revision: str | None = "p4_21_workspace_project_rbac_fix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_22_outbox_replay_reader migration."""
    execute_sql_file("p4_22_outbox_replay_reader.up.sql")


def downgrade() -> None:
    """Revert p4_22_outbox_replay_reader migration."""
    execute_sql_file("p4_22_outbox_replay_reader.down.sql")

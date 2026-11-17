# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Persistent sessions and remember_me.

Revision ID: p4_19_persistent_sessions
Revises: p4_18_oauth_mcp_scoping
Create Date: 2026-11-17 23:08:43.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_19_persistent_sessions"
down_revision: str | None = "p4_18_oauth_mcp_scoping"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_19_persistent_sessions migration."""
    execute_sql_file("p4_19_persistent_sessions.up.sql")


def downgrade() -> None:
    """Revert p4_19_persistent_sessions migration."""
    execute_sql_file("p4_19_persistent_sessions.down.sql")

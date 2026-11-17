# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth & MCP scoping helpers, label column, and RLS-safe workspace functions.

Revision ID: p4_18_oauth_mcp_scoping
Revises: p5_22a_remote_runners
Create Date: 2026-11-16 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_18_oauth_mcp_scoping"
down_revision: str | None = "p5_22a_remote_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply OAuth & MCP scoping helpers and RLS-safe functions."""
    execute_sql_file("p4_18_oauth_mcp_scoping.up.sql")


def downgrade() -> None:
    """Revert OAuth & MCP scoping helpers and RLS-safe functions."""
    execute_sql_file("p4_18_oauth_mcp_scoping.down.sql")

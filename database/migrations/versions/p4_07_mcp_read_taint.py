# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""mcp_read_taint table for session read-taint exfiltration guard (KB-P4-07).

Revision ID: p4_07_mcp_read_taint
Revises: p5_13_approved_wasm_modules
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_07_mcp_read_taint"
down_revision: str | None = "p5_19b_project_repo_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply mcp_read_taint DDL, indexes, and RLS policies."""
    execute_sql_file("p4_07_mcp_read_taint.up.sql")


def downgrade() -> None:
    """Revert mcp_read_taint DDL and RLS policies."""
    execute_sql_file("p4_07_mcp_read_taint.down.sql")

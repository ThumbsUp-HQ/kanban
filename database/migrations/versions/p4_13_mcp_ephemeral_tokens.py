# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Ephemeral kb_agt_eph_* read-only MCP tokens (KB-P4-13).

Revision ID: p4_13_mcp_ephemeral_tokens
Revises: p5_12_custom_field_approvals
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_13_mcp_ephemeral_tokens"
down_revision: str | None = "p5_12_custom_field_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply mcp_ephemeral_tokens DDL, constraints, RLS policies, and grants."""
    execute_sql_file("p4_13_mcp_ephemeral_tokens.up.sql")


def downgrade() -> None:
    """Revert mcp_ephemeral_tokens DDL, constraints, and RLS policies."""
    execute_sql_file("p4_13_mcp_ephemeral_tokens.down.sql")

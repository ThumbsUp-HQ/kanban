# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hierarchical scopable MCP API keys, narrowing, RLS & unlimited expiry (KB-P4-14 / KANBA-106).

Revision ID: p4_14_mcp_scopable_keys
Revises: p5_13_approved_wasm_modules
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_14_mcp_scopable_keys"
down_revision: str | None = "p5_13_approved_wasm_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply mcp_api_keys hierarchical scope columns, constraints, RLS, and functions."""
    execute_sql_file("p4_14_mcp_scopable_keys.up.sql")


def downgrade() -> None:
    """Revert mcp_api_keys hierarchical scope columns, constraints, RLS, and functions."""
    execute_sql_file("p4_14_mcp_scopable_keys.down.sql")

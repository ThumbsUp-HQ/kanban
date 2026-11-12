# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Scoped kb_* API keys, surface binding, scopes & token introspection (KB-P4-02a).

Revision ID: p4_02a_mcp_api_keys
Revises: p2_06_oidc_auth_requests
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_02a_mcp_api_keys"
down_revision: str | None = "p2_06_oidc_auth_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply mcp_api_keys DDL, constraints, RLS policies, and grants."""
    execute_sql_file("p4_02a_mcp_api_keys.up.sql")


def downgrade() -> None:
    """Revert mcp_api_keys DDL, constraints, and RLS policies."""
    execute_sql_file("p4_02a_mcp_api_keys.down.sql")

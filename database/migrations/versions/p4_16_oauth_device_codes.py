# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 8628 Headless CLI Device Authorization Codes (KB-P4-16).

Revision ID: p4_16_oauth_device_codes
Revises: p4_13_mcp_ephemeral_tokens
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_16_oauth_device_codes"
down_revision: str | None = "p4_13_mcp_ephemeral_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply oauth_device_codes DDL, constraints, RLS policies, and grants."""
    execute_sql_file("p4_16_oauth_device_codes.up.sql")


def downgrade() -> None:
    """Revert oauth_device_codes DDL, constraints, and RLS policies."""
    execute_sql_file("p4_16_oauth_device_codes.down.sql")

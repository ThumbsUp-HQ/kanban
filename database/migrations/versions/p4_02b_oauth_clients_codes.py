# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth 2.1 authorization server, clients, codes, grants & tokens (KB-P4-02b).

Revision ID: p4_02b_oauth_clients_codes
Revises: p4_02a_mcp_api_keys
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_02b_oauth_clients_codes"
down_revision: str | None = "p4_02a_mcp_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply oauth_clients, oauth_grants, oauth_authorization_codes, oauth_refresh_tokens DDL."""
    execute_sql_file("p4_02b_oauth_clients_codes.up.sql")


def downgrade() -> None:
    """Drop oauth tables and RLS policies."""
    execute_sql_file("p4_02b_oauth_clients_codes.down.sql")

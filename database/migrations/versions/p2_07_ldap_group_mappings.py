# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP group mappings table with FORCE RLS (KB-P2-07).

Revision ID: p2_07_ldap_group_mappings
Revises: p4_02a_mcp_api_keys
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_07_ldap_group_mappings"
down_revision: str | None = "p4_02a_mcp_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply ldap_group_mappings DDL and RLS policies."""
    execute_sql_file("p2_07_ldap_group_mappings.up.sql")


def downgrade() -> None:
    """Revert ldap_group_mappings DDL and RLS policies."""
    execute_sql_file("p2_07_ldap_group_mappings.down.sql")

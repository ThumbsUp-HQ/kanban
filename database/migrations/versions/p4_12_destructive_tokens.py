# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Destructive confirmation tokens table (KB-P4-12, S11.4, S7.2, S12.3).

Revision ID: p4_12_destructive_confirmation_tokens
Revises: p6_01_import_entity_mappings
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_12_destructive_tokens"
down_revision: str | None = "p4_16_oauth_device_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply destructive_confirmation_tokens table, indexes, and RLS policies."""
    execute_sql_file("p4_12_destructive_tokens.up.sql")


def downgrade() -> None:
    """Drop destructive_confirmation_tokens table."""
    execute_sql_file("p4_12_destructive_tokens.down.sql")

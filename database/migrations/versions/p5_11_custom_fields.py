# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Custom field definitions, Admin-only RBAC/RLS WITH CHECK gate & 7-format schema (KB-P5-11).

Revision ID: p5_11_custom_fields
Revises: p2_05a_mfa_totp_recovery
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_11_custom_fields"
down_revision: str | None = "p2_05a_mfa_totp_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply custom_field_definitions and custom_field_values DDL and RLS policies."""
    execute_sql_file("p5_11_custom_fields.up.sql")


def downgrade() -> None:
    """Revert custom_field_definitions and custom_field_values DDL and RLS policies."""
    execute_sql_file("p5_11_custom_fields.down.sql")

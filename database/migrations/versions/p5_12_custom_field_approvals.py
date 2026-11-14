# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Cryptographic manifest_sha256 escalation approvals (KB-P5-12, S13.2, S4.2, S3.2).

Revision ID: p5_12_custom_field_approvals
Revises: p5_11_custom_fields
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_12_custom_field_approvals"
down_revision: str | None = "p2_10_auth_card_admin_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply custom_field_approvals table, indexes, RLS and tamper-revoke trigger."""
    execute_sql_file("p5_12_custom_field_approvals.up.sql")


def downgrade() -> None:
    """Drop trigger, function, and custom_field_approvals table."""
    execute_sql_file("p5_12_custom_field_approvals.down.sql")

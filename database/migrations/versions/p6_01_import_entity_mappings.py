# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lossless Plane importer entity mappings table (KB-P6-01, S1.3, S15.5).

Revision ID: p6_01_import_entity_mappings
Revises: p5_12_custom_field_approvals
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_01_import_entity_mappings"
down_revision: str | None = "p5_12_custom_field_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply import_entity_mappings table, index, and RLS policies."""
    execute_sql_file("p6_01_import_entity_mappings.up.sql")


def downgrade() -> None:
    """Drop import_entity_mappings table."""
    execute_sql_file("p6_01_import_entity_mappings.down.sql")

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add search_tsv generated columns and GIN indexes for search (KB-P3-17).

Revision ID: p3_17_search_indexes
Revises: p3_10b_modules
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_17_search_indexes"
down_revision: str | None = "p2_12_setup_claim_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply search_tsv generated columns and GIN indexes."""
    execute_sql_file("p3_17_search_indexes.up.sql")


def downgrade() -> None:
    """Drop search GIN indexes and search_tsv generated columns."""
    execute_sql_file("p3_17_search_indexes.down.sql")

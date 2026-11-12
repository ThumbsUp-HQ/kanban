"""Partitioned SHA-256 hash-chained activity_records, append_activity & verify_activity_chain.

Revision ID: p1_12_activity_ledger
Revises: p1_11_object_links
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_12_activity_ledger"
down_revision: str | None = "p1_11_object_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply partitioned activity ledger, chain heads, and verify functions."""
    execute_sql_file("p1_12_activity_ledger.up.sql")


def downgrade() -> None:
    """Revert partitioned activity ledger, chain heads, and verify functions."""
    execute_sql_file("p1_12_activity_ledger.down.sql")

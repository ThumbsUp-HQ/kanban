"""Rate limit buckets (PG-backed + Valkey-backed sliding window).

Revision ID: p2_18_rate_limit_buckets
Revises: p1_18_outbox
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_18_rate_limit_buckets"
down_revision: str | None = "p1_18_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply rate_limit_buckets DDL, role, schema, RLS, and functions."""
    execute_sql_file("p2_18_rate_limit_buckets.up.sql")


def downgrade() -> None:
    """Revert rate_limit_buckets DDL, functions, schema, and tables."""
    execute_sql_file("p2_18_rate_limit_buckets.down.sql")

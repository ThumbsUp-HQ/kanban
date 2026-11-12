"""agent_definitions registry (KB-P5-16).

Revision ID: p5_16_agent_definitions
Revises: p2_18_rate_limit_buckets
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_16_agent_definitions"
down_revision: str | None = "p2_18_rate_limit_buckets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply agent_definitions DDL, constraints, RLS policies, and grants."""
    execute_sql_file("p5_16_agent_definitions.up.sql")


def downgrade() -> None:
    """Revert agent_definitions DDL, constraints, and RLS policies."""
    execute_sql_file("p5_16_agent_definitions.down.sql")

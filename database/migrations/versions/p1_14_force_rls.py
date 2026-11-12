"""FORCE ROW LEVEL SECURITY policies, session context helpers, and schema-wide RLS catalog gate.

Revision ID: p1_14_force_rls
Revises: p1_07_creator_provenance
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_14_force_rls"
down_revision: str | None = "p1_07_creator_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply FORCE ROW LEVEL SECURITY policies and context helpers."""
    execute_sql_file("p1_14_force_rls.up.sql")


def downgrade() -> None:
    """Revert FORCE ROW LEVEL SECURITY policies and context helpers."""
    execute_sql_file("p1_14_force_rls.down.sql")

"""Created-by provenance trigger with admin-only override and CREATOR_OVERRIDDEN ledger entry.

Revision ID: p1_07_creator_provenance
Revises: p1_09_prose_tables
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_07_creator_provenance"
down_revision: str | None = "p1_09_prose_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply creator provenance insert and update triggers on issues."""
    execute_sql_file("p1_07_creator_provenance.up.sql")


def downgrade() -> None:
    """Revert creator provenance insert and update triggers on issues."""
    execute_sql_file("p1_07_creator_provenance.down.sql")

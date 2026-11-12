"""Add reason and old/new creator IDs to CREATOR_OVERRIDDEN activity payload (KB-P3-04).

Revision ID: p3_04_creator_override_reason
Revises: p3_10b_modules
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_04_creator_override_reason"
down_revision: str | None = "p3_10b_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Update issues_creator_provenance_bu trigger function to record reason."""
    execute_sql_file("p3_04_creator_override_reason.up.sql")


def downgrade() -> None:
    """Revert issues_creator_provenance_bu trigger function to p1_07 definition."""
    execute_sql_file("p3_04_creator_override_reason.down.sql")

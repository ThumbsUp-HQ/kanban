"""Add LOCKOUT_PREVENTED 3-layer safeguards and emergency unlock (KB-P2-09).

Revision ID: p2_09_lockout_prevented
Revises: p3_04_creator_override_reason
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_09_lockout_prevented"
down_revision: str | None = "p5_11_custom_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply LOCKOUT_PREVENTED 3-layer safeguards and emergency unlock triggers."""
    execute_sql_file("p2_09_lockout_prevented_safeguards.up.sql")


def downgrade() -> None:
    """Revert LOCKOUT_PREVENTED safeguards and drop functions and triggers."""
    execute_sql_file("p2_09_lockout_prevented_safeguards.down.sql")

"""Workflow states WIP limits (KB-P3-01b).

Revision ID: p3_01b_workflow_state_wip_limits
Revises: p2_18_rate_limit_buckets
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_01b_workflow_state_wip_limits"
down_revision: str | None = "p2_18_rate_limit_buckets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply WIP limits columns and constraint to workflow_states."""
    execute_sql_file("p3_01b_workflow_state_wip_limits.up.sql")


def downgrade() -> None:
    """Revert WIP limits columns and constraint from workflow_states."""
    execute_sql_file("p3_01b_workflow_state_wip_limits.down.sql")

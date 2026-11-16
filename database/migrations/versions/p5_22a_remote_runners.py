# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""remote_runners and enrollment tokens registry (KB-P5-22a, S14.2, S11.4).

Revision ID: p5_22a_remote_runners
Revises: p5_16_agent_definitions
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_22a_remote_runners"
down_revision: str | None = "p5_17a_workflow_hooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply remote_runners and enrollment tokens DDL, RLS, and functions."""
    execute_sql_file("p5_22a_remote_runners.up.sql")


def downgrade() -> None:
    """Revert remote_runners and enrollment tokens DDL, RLS, and functions."""
    execute_sql_file("p5_22a_remote_runners.down.sql")

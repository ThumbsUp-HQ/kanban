"""Workflow hook DDL, executions, and invocations (KB-P5-17a).

Revision ID: p5_17a_workflow_hooks
Revises: p5_13_approved_wasm_modules
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_17a_workflow_hooks"
down_revision: str | None = "p4_07_mcp_read_taint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply workflow transition hooks, executions, and guard trigger."""
    execute_sql_file("p5_17a_workflow_hooks.up.sql")


def downgrade() -> None:
    """Revert workflow transition hooks, executions, and guard trigger."""
    execute_sql_file("p5_17a_workflow_hooks.down.sql")

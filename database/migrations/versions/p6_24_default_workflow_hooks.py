# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add default_workflow_hooks templates and inherited_from_template_id."""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_24_default_workflow_hooks"
down_revision: str | None = "p6_23_gate_timeouts_and_project_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_24_default_workflow_hooks migration."""
    execute_sql_file("p6_24_default_workflow_hooks.up.sql")


def downgrade() -> None:
    """Revert p6_24_default_workflow_hooks migration."""
    execute_sql_file("p6_24_default_workflow_hooks.down.sql")

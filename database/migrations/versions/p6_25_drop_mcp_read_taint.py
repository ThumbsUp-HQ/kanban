# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Drop mcp_read_taint table (KAN-535).

Revision ID: p6_25_drop_mcp_read_taint
Revises: p6_24_default_workflow_hooks
Create Date: 2026-11-27 05:47:39.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_25_drop_mcp_read_taint"
down_revision: str | None = "p6_24_default_workflow_hooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_25_drop_mcp_read_taint migration."""
    execute_sql_file("p6_25_drop_mcp_read_taint.up.sql")


def downgrade() -> None:
    """Revert p6_25_drop_mcp_read_taint migration."""
    execute_sql_file("p6_25_drop_mcp_read_taint.down.sql")

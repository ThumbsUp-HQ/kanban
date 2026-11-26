# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add project default_gate_timeout_ms, hook timeout_ms, invocation deadline_at, and 600s caps.

Revision ID: p6_23_gate_timeouts_and_project_defaults
Revises: p6_22_mcp_api_keys_capability_mask_boundary
Create Date: 2026-11-26 16:38:56.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_23_gate_timeouts_and_project_defaults"
down_revision: str | None = "p6_22_mcp_api_keys_capability_mask_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_23_gate_timeouts_and_project_defaults migration."""
    execute_sql_file("p6_23_gate_timeouts_and_project_defaults.up.sql")


def downgrade() -> None:
    """Revert p6_23_gate_timeouts_and_project_defaults migration."""
    execute_sql_file("p6_23_gate_timeouts_and_project_defaults.down.sql")

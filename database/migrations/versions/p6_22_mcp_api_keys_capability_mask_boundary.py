# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Allow capability_mask 0 for deny-all MCP keys.

Revision ID: p6_22_mcp_api_keys_capability_mask_boundary
Revises: p6_21_agent_onboarding_preferences
Create Date: 2026-11-25 23:32:36.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_22_mcp_api_keys_capability_mask_boundary"
down_revision: str | None = "p6_21_agent_onboarding_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_22_mcp_api_keys_capability_mask_boundary migration."""
    execute_sql_file("p6_22_mcp_api_keys_capability_mask_boundary.up.sql")


def downgrade() -> None:
    """Revert p6_22_mcp_api_keys_capability_mask_boundary migration."""
    execute_sql_file("p6_22_mcp_api_keys_capability_mask_boundary.down.sql")

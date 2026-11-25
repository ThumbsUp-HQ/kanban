# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Fix app_principal_has_role for cross-workspace server admin and credential scoping.

Revision ID: p6_19_server_admin_cross_workspace_role_access
Revises: p6_18_websudo_sliding_aal2
Create Date: 2026-11-25 08:08:36.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_19_server_admin_cross_workspace_role_access"
down_revision: str | None = "p6_18_websudo_sliding_aal2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_19_server_admin_cross_workspace_role_access migration."""
    execute_sql_file("p6_19_server_admin_cross_workspace_role_access.up.sql")


def downgrade() -> None:
    """Revert p6_19_server_admin_cross_workspace_role_access migration."""
    execute_sql_file("p6_19_server_admin_cross_workspace_role_access.down.sql")

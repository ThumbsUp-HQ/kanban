# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""workspace project rbac fix.

Revision ID: p4_21_workspace_project_rbac_fix
Revises: p4_20_user_personal_settings
Create Date: 2026-11-18 00:36:23.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_21_workspace_project_rbac_fix"
down_revision: str | None = "p4_20_user_personal_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_21_workspace_project_rbac_fix migration."""
    execute_sql_file("p4_21_workspace_project_rbac_fix.up.sql")


def downgrade() -> None:
    """Revert p4_21_workspace_project_rbac_fix migration."""
    execute_sql_file("p4_21_workspace_project_rbac_fix.down.sql")

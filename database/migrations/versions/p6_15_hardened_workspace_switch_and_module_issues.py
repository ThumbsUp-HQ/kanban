# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hardened workspace switch and module_issues security invoker.

Revision ID: p6_15_hardened_workspace_switch_and_module_issues
Revises: p6_12_granular_rbac_roles
Create Date: 2026-11-23 10:28:13.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_15_hardened_workspace_switch_and_module_issues"
down_revision: str | None = "p6_12_granular_rbac_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_15_hardened_workspace_switch_and_module_issues migration."""
    execute_sql_file("p6_15_hardened_workspace_switch_and_module_issues.up.sql")


def downgrade() -> None:
    """Revert p6_15_hardened_workspace_switch_and_module_issues migration."""
    execute_sql_file("p6_15_hardened_workspace_switch_and_module_issues.down.sql")

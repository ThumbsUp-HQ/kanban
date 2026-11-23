# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Granular rbac roles.

Revision ID: p6_12_granular_rbac_roles
Revises: p6_10_issue_workpads_and_rework_breaker
Create Date: 2026-11-23 00:01:52.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_12_granular_rbac_roles"
down_revision: str | None = "p6_10_issue_workpads_and_rework_breaker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_12_granular_rbac_roles migration."""
    execute_sql_file("p6_12_granular_rbac_roles.up.sql")


def downgrade() -> None:
    """Revert p6_12_granular_rbac_roles migration."""
    execute_sql_file("p6_12_granular_rbac_roles.down.sql")

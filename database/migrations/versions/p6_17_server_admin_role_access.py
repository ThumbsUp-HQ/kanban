# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Update app_principal_has_role for server admin scope.

Revision ID: p6_17_server_admin_role_access
Revises: p6_16_oauth_confidential_clients
Create Date: 2026-11-25 05:20:47.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_17_server_admin_role_access"
down_revision: str | None = "p6_16_oauth_confidential_clients"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_17_server_admin_role_access migration."""
    execute_sql_file("p6_17_server_admin_role_access.up.sql")


def downgrade() -> None:
    """Revert p6_17_server_admin_role_access migration."""
    execute_sql_file("p6_17_server_admin_role_access.down.sql")

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Update oauth_clients status check constraint for suspended and revoked

Revision ID: p6_20_oauth_clients_status_check
Revises: p6_19_server_admin_cross_workspace_role_access
Create Date: 2026-11-25 08:56:39.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_20_oauth_clients_status_check"
down_revision: str | None = "p6_19_server_admin_cross_workspace_role_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_20_oauth_clients_status_check migration."""
    execute_sql_file("p6_20_oauth_clients_status_check.up.sql")


def downgrade() -> None:
    """Revert p6_20_oauth_clients_status_check migration."""
    execute_sql_file("p6_20_oauth_clients_status_check.down.sql")

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Support confidential OAuth 2.1 clients

Revision ID: p6_16_oauth_confidential_clients
Revises: p6_15_hardened_workspace_switch_and_module_issues
Create Date: 2026-11-24 13:01:34.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_16_oauth_confidential_clients"
down_revision: str | None = "p6_15_hardened_workspace_switch_and_module_issues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_16_oauth_confidential_clients migration."""
    execute_sql_file("p6_16_oauth_confidential_clients.up.sql")


def downgrade() -> None:
    """Revert p6_16_oauth_confidential_clients migration."""
    execute_sql_file("p6_16_oauth_confidential_clients.down.sql")

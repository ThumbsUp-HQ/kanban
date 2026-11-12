# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OIDC and OAuth2 authentication requests and state tracking (KB-P2-06).

Revision ID: p2_06_oidc_auth_requests
Revises: p2_02_sessions
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_06_oidc_auth_requests"
down_revision: str | None = "p2_02_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply oidc_auth_requests DDL and security definer functions."""
    execute_sql_file("p2_06_oidc_auth_requests.up.sql")


def downgrade() -> None:
    """Revert oidc_auth_requests DDL and security definer functions."""
    execute_sql_file("p2_06_oidc_auth_requests.down.sql")

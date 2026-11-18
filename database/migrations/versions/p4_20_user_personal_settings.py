# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""User personal settings preferences.

Revision ID: p4_20_user_personal_settings
Revises: p4_19_persistent_sessions
Create Date: 2026-11-17 23:44:45.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_20_user_personal_settings"
down_revision: str | None = "p4_19_persistent_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_20_user_personal_settings migration."""
    execute_sql_file("p4_20_user_personal_settings.up.sql")


def downgrade() -> None:
    """Revert p4_20_user_personal_settings migration."""
    execute_sql_file("p4_20_user_personal_settings.down.sql")

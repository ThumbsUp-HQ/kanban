# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add agent_onboarding_prefs_json to user_preferences

Revision ID: p6_21_agent_onboarding_preferences
Revises: p6_20_oauth_clients_status_check
Create Date: 2026-11-25 11:26:46.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_21_agent_onboarding_preferences"
down_revision: str | None = "p6_20_oauth_clients_status_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_21_agent_onboarding_preferences migration."""
    execute_sql_file("p6_21_agent_onboarding_preferences.up.sql")


def downgrade() -> None:
    """Revert p6_21_agent_onboarding_preferences migration."""
    execute_sql_file("p6_21_agent_onboarding_preferences.down.sql")

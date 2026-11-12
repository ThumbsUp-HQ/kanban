# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue subscriptions, auto-subscribe rules, per-event mute & notifications (KB-P3-06).

Revision ID: p3_06_notifications
Revises: p3_05_comment_threads_reactions
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_06_notifications"
down_revision: str | None = "p3_05_comment_threads_reactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply subscriptions columns, notifications table, and RLS policies."""
    execute_sql_file("p3_06_notifications.up.sql")


def downgrade() -> None:
    """Revert subscriptions columns, notifications table, and RLS policies."""
    execute_sql_file("p3_06_notifications.down.sql")

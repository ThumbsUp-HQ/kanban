# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Threaded comments, reactions, permalinks and access-checked mentions (KB-P3-05).

Revision ID: p3_05_comment_threads_reactions
Revises: p2_02_sessions
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_05_comment_threads_reactions"
down_revision: str | None = "p2_02_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply comment reactions table, RLS policies, and grants."""
    execute_sql_file("p3_05_comment_threads_reactions.up.sql")


def downgrade() -> None:
    """Revert comment reactions table, RLS policies, and grants."""
    execute_sql_file("p3_05_comment_threads_reactions.down.sql")

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Server-side sessions, HMAC-signed __Host- cookies, rotation, timeouts and CSRF (KB-P2-02).

Revision ID: p2_02_sessions
Revises: p2_18_rate_limit_buckets
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_02_sessions"
down_revision: str | None = "p2_18_rate_limit_buckets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply sessions DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_02_sessions.up.sql")


def downgrade() -> None:
    """Revert sessions DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_02_sessions.down.sql")

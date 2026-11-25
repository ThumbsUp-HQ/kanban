# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WebSudo sliding window and request replay."""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_18_websudo_sliding_aal2"
down_revision: str | None = "p6_17_server_admin_role_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_18_websudo_sliding_aal2 migration."""
    execute_sql_file("p6_18_websudo_sliding_aal2.up.sql")


def downgrade() -> None:
    """Revert p6_18_websudo_sliding_aal2 migration."""
    execute_sql_file("p6_18_websudo_sliding_aal2.down.sql")

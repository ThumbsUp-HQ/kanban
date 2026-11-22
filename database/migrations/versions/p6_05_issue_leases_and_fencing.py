# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue leases and fencing.

Revision ID: p6_05_issue_leases_and_fencing
Revises: p6_04_enforce_credential_boundary_rls_gucs
Create Date: 2026-11-22 19:20:42.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_05_issue_leases_and_fencing"
down_revision: str | None = "p6_04_enforce_credential_boundary_rls_gucs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_05_issue_leases_and_fencing migration."""
    execute_sql_file("p6_05_issue_leases_and_fencing.up.sql")


def downgrade() -> None:
    """Revert p6_05_issue_leases_and_fencing migration."""
    execute_sql_file("p6_05_issue_leases_and_fencing.down.sql")

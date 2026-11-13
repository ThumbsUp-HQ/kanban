# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security Definer helpers for issue blast radius calculation.

Also adds child unparenting under RLS (KB-P3-09b).

Revision ID: p3_09b_issue_delete_blast_radius
Revises: p2_06_oidc_auth_requests
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p3_09b_issue_delete_blast_radius"
down_revision: str | None = "p3_08_issue_copy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply blast radius and child unparenting privileged helper functions."""
    execute_sql_file("p3_09b_issue_delete_blast_radius.up.sql")


def downgrade() -> None:
    """Revert blast radius and child unparenting privileged helper functions."""
    execute_sql_file("p3_09b_issue_delete_blast_radius.down.sql")

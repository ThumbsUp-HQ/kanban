# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue workpads and rework breaker.

Revision ID: p6_10_issue_workpads_and_rework_breaker
Revises: p6_14_jinja_report_templates
Create Date: 2026-11-23 00:05:15.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_10_issue_workpads_and_rework_breaker"
down_revision: str | None = "p6_14_jinja_report_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_10_issue_workpads_and_rework_breaker migration."""
    execute_sql_file("p6_10_issue_workpads_and_rework_breaker.up.sql")


def downgrade() -> None:
    """Revert p6_10_issue_workpads_and_rework_breaker migration."""
    execute_sql_file("p6_10_issue_workpads_and_rework_breaker.down.sql")

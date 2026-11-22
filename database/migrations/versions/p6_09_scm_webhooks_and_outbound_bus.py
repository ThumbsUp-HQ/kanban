# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SCM webhooks, artifacts, and outbound webhook bus (KB-DEVSECOPS-BUS-01).

Revision ID: p6_09_scm_webhooks_and_outbound_bus
Revises: p6_05_issue_leases_and_fencing
Create Date: 2026-11-22 20:30:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_09_scm_webhooks_and_outbound_bus"
down_revision: str | None = "p6_05_issue_leases_and_fencing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_09_scm_webhooks_and_outbound_bus migration."""
    execute_sql_file("p6_09_scm_webhooks_and_outbound_bus.up.sql")


def downgrade() -> None:
    """Revert p6_09_scm_webhooks_and_outbound_bus migration."""
    execute_sql_file("p6_09_scm_webhooks_and_outbound_bus.down.sql")

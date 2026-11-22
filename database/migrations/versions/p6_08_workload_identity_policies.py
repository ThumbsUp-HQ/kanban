# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Workload identity policies and JTI replay prevention (KB-AUTH-OIDC-EXCHANGE-01, KAN-74).

Revision ID: p6_08_workload_identity_policies
Revises: p6_07_content_provenance_and_taint
Create Date: 2026-11-22 21:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_08_workload_identity_policies"
down_revision: str | None = "p6_07_content_provenance_and_taint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_08_workload_identity_policies migration."""
    execute_sql_file("p6_08_workload_identity_policies.up.sql")


def downgrade() -> None:
    """Revert p6_08_workload_identity_policies migration."""
    execute_sql_file("p6_08_workload_identity_policies.down.sql")

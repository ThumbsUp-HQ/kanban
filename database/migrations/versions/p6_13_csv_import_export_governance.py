# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""csv import export governance

Revision ID: p6_13_csv_import_export_governance
Revises: p6_09_scm_webhooks_and_outbound_bus
Create Date: 2026-11-23 00:03:31.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_13_csv_import_export_governance"
down_revision: str | None = "p6_09_scm_webhooks_and_outbound_bus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_13_csv_import_export_governance migration."""
    execute_sql_file("p6_13_csv_import_export_governance.up.sql")


def downgrade() -> None:
    """Revert p6_13_csv_import_export_governance migration."""
    execute_sql_file("p6_13_csv_import_export_governance.down.sql")

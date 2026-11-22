# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Content provenance trust tiers and untrusted content taint tracking.

Revision ID: p6_07_content_provenance_and_taint
Revises: p6_06_crypto_shredded_activity_ledger
Create Date: 2026-11-22 20:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_07_content_provenance_and_taint"
down_revision: str | None = "p6_06_crypto_shredded_activity_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_07_content_provenance_and_taint migration."""
    execute_sql_file("p6_07_content_provenance_and_taint.up.sql")


def downgrade() -> None:
    """Revert p6_07_content_provenance_and_taint migration."""
    execute_sql_file("p6_07_content_provenance_and_taint.down.sql")

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Envelope-encrypted activity records payloads and AAL2 two-stage crypto-shredding.

Revision ID: p6_06_crypto_shredded_activity_ledger
Revises: p6_05_issue_leases_and_fencing
Create Date: 2026-11-22 21:29:29.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_06_crypto_shredded_activity_ledger"
down_revision: str | None = "p6_05_issue_leases_and_fencing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_06_crypto_shredded_activity_ledger migration."""
    execute_sql_file("p6_06_crypto_shredded_activity_ledger.up.sql")


def downgrade() -> None:
    """Revert p6_06_crypto_shredded_activity_ledger migration."""
    execute_sql_file("p6_06_crypto_shredded_activity_ledger.down.sql")

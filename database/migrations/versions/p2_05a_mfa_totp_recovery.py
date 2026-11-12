# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 6238 TOTP, recovery codes, and kb_auth functions (KB-P2-05a).

Revision ID: p2_05a_mfa_totp_recovery
Revises: p3_05_comment_threads_reactions
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_05a_mfa_totp_recovery"
down_revision: str | None = "p3_05_comment_threads_reactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply totp_factors and recovery_codes DDL and security definer functions."""
    execute_sql_file("p2_05a_mfa_totp_recovery.up.sql")


def downgrade() -> None:
    """Revert totp_factors and recovery_codes DDL and security definer functions."""
    execute_sql_file("p2_05a_mfa_totp_recovery.down.sql")

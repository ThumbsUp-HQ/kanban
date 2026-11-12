# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""First-boot setup claim tokens and kb_auth functions (KB-P2-12).

Revision ID: p2_12_setup_claim_tokens
Revises: p2_05b_webauthn_credentials, p3_10b_modules
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_12_setup_claim_tokens"
down_revision: str | Sequence[str] | None = "p2_05b_webauthn_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply first-boot setup claim tokens and functions."""
    execute_sql_file("p2_12_setup_claim_tokens.up.sql")


def downgrade() -> None:
    """Revert first-boot setup claim tokens and functions."""
    execute_sql_file("p2_12_setup_claim_tokens.down.sql")

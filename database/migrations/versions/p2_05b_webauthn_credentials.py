# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WebAuthn and Passkeys registration, assertion, credentials, and challenges (KB-P2-05b).

Revision ID: p2_05b_webauthn_credentials
Revises: p2_05a_mfa_totp_recovery
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_05b_webauthn_credentials"
down_revision: str | None = "p3_10b_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply webauthn_credentials and webauthn_challenges DDL and security definer functions."""
    execute_sql_file("p2_05b_webauthn_credentials.up.sql")


def downgrade() -> None:
    """Revert webauthn_credentials and webauthn_challenges DDL and security definer functions."""
    execute_sql_file("p2_05b_webauthn_credentials.down.sql")

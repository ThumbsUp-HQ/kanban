# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Identity linking without email auto-merge: user_identities and identity_link_intents (KB-P2-08).

Revision ID: p2_08_user_identities
Revises: p3_08_issue_copy
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_08_user_identities"
down_revision: str | None = "p4_02b_oauth_clients_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply user_identities, identity_link_intents, and kb_auth identity functions."""
    execute_sql_file("p2_08_user_identities.up.sql")


def downgrade() -> None:
    """Revert user_identities, identity_link_intents, and kb_auth identity functions."""
    execute_sql_file("p2_08_user_identities.down.sql")

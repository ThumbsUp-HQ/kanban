# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Fix oidc_auth_requests link_intent_id foreign key to reference identity_link_intents.

Revision ID: p4_23_oidc_link_intent_fk
Revises: p4_22_outbox_replay_reader
Create Date: 2026-11-20 12:56:42.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_23_oidc_link_intent_fk"
down_revision: str | None = "p4_22_outbox_replay_reader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_23_oidc_link_intent_fk migration."""
    execute_sql_file("p4_23_oidc_link_intent_fk.up.sql")


def downgrade() -> None:
    """Revert p4_23_oidc_link_intent_fk migration."""
    execute_sql_file("p4_23_oidc_link_intent_fk.down.sql")

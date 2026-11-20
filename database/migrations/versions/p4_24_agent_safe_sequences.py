# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Add swarm batch sequence allocator, skip loaded sequences and SEQUENCE_SKIPPED event.

Revision ID: p4_24_agent_safe_sequences
Revises: p4_23_oidc_link_intent_fk
Create Date: 2026-11-20 18:35:08.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p4_24_agent_safe_sequences"
down_revision: str | None = "p4_23_oidc_link_intent_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p4_24_agent_safe_sequences migration."""
    execute_sql_file("p4_24_agent_safe_sequences.up.sql")


def downgrade() -> None:
    """Revert p4_24_agent_safe_sequences migration."""
    execute_sql_file("p4_24_agent_safe_sequences.down.sql")

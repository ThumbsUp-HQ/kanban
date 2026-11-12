"""Transactional outbox_events, OutboxRelay (SKIP LOCKED) and RealtimeBroker.

Revision ID: p1_18_outbox
Revises: p1_16_link_purger
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p1_18_outbox"
down_revision: str | None = "p1_16_link_purger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply outbox_events DDL, trigger, and SKIP LOCKED functions."""
    execute_sql_file("p1_18_outbox.up.sql")


def downgrade() -> None:
    """Revert outbox_events DDL, trigger, and SKIP LOCKED functions."""
    execute_sql_file("p1_18_outbox.down.sql")

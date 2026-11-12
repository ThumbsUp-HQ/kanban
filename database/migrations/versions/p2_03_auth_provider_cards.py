"""auth_provider_cards DDL, kb_auth data boundary and envelope encryption (KB-P2-03).

Revision ID: p2_03_auth_provider_cards
Revises: p1_18_outbox
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p2_03_auth_provider_cards"
down_revision: str | None = "p5_06_object_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply auth_provider_cards DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_03_auth_provider_cards.up.sql")


def downgrade() -> None:
    """Revert auth_provider_cards DDL, kb_auth boundary, and security definer functions."""
    execute_sql_file("p2_03_auth_provider_cards.down.sql")

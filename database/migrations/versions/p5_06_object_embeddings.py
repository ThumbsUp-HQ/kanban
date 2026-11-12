"""object_embeddings (pgvector HNSW + FORCE RLS).

Revision ID: p5_06_object_embeddings
Revises: p1_18_outbox
Create Date: 2026-11-12 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_06_object_embeddings"
down_revision: str | None = "p1_18_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply object_embeddings DDL, HNSW index, FORCE RLS, and policies."""
    execute_sql_file("p5_06_object_embeddings.up.sql")


def downgrade() -> None:
    """Revert object_embeddings DDL, HNSW index, and policies."""
    execute_sql_file("p5_06_object_embeddings.down.sql")

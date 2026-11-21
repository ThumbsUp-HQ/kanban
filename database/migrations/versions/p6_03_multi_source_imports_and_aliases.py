# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Multi source imports and issue key aliases.

Revision ID: p6_03_multi_source_imports_and_aliases
Revises: p6_02_pdf_attachments
Create Date: 2026-11-21 18:16:41.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_03_multi_source_imports_and_aliases"
down_revision: str | None = "p6_02_pdf_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_03_multi_source_imports_and_aliases migration."""
    execute_sql_file("p6_03_multi_source_imports_and_aliases.up.sql")


def downgrade() -> None:
    """Revert p6_03_multi_source_imports_and_aliases migration."""
    execute_sql_file("p6_03_multi_source_imports_and_aliases.down.sql")

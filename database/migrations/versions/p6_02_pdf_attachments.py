# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Allow application/pdf attachments and page_count.

Revision ID: p6_02_pdf_attachments
Revises: p4_24_agent_safe_sequences
Create Date: 2026-11-21 18:17:04.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_02_pdf_attachments"
down_revision: str | None = "p4_24_agent_safe_sequences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_02_pdf_attachments migration."""
    execute_sql_file("p6_02_pdf_attachments.up.sql")


def downgrade() -> None:
    """Revert p6_02_pdf_attachments migration."""
    execute_sql_file("p6_02_pdf_attachments.down.sql")

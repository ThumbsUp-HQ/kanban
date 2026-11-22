# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Enforce credential boundary rls gucs.

Revision ID: p6_04_enforce_credential_boundary_rls_gucs
Revises: p6_03_multi_source_imports_and_aliases
Create Date: 2026-11-22 17:48:39.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p6_04_enforce_credential_boundary_rls_gucs"
down_revision: str | None = "p6_03_multi_source_imports_and_aliases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply p6_04_enforce_credential_boundary_rls_gucs migration."""
    execute_sql_file("p6_04_enforce_credential_boundary_rls_gucs.up.sql")


def downgrade() -> None:
    """Revert p6_04_enforce_credential_boundary_rls_gucs migration."""
    execute_sql_file("p6_04_enforce_credential_boundary_rls_gucs.down.sql")

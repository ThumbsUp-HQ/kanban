# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""project_repo_bindings registry for hardened bare git mirrors (KB-P5-19b).

Revision ID: p5_19b_project_repo_bindings
Revises: p5_13_approved_wasm_modules
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_19b_project_repo_bindings"
down_revision: str | None = "p4_14_mcp_scopable_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply project_repo_bindings DDL, constraints, indexes, and RLS policies."""
    execute_sql_file("p5_19b_project_repo_bindings.up.sql")


def downgrade() -> None:
    """Revert project_repo_bindings DDL and RLS policies."""
    execute_sql_file("p5_19b_project_repo_bindings.down.sql")

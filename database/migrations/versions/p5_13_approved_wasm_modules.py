# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""approved_wasm_modules table for sandboxed custom fields and sync hooks (KB-P5-13).

Revision ID: p5_13_approved_wasm_modules
Revises: p4_12_destructive_tokens
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_13_approved_wasm_modules"
down_revision: str | None = "p4_12_destructive_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply approved_wasm_modules DDL, indexes, and RLS policies."""
    execute_sql_file("p5_13_approved_wasm_modules.up.sql")


def downgrade() -> None:
    """Revert approved_wasm_modules DDL and RLS policies."""
    execute_sql_file("p5_13_approved_wasm_modules.down.sql")

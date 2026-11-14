# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""ai_provider_configs (KMS-wrapped keys), ai_token_ledgers & atomic BudgetEnforcer (KB-P5-05a).

Revision ID: p5_05a_ai_providers_and_ledgers
Revises: p6_01_import_entity_mappings
Create Date: 2026-11-13 00:00:00.000000
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "p5_05a_ai_providers_and_ledgers"
down_revision: str | None = "p6_01_import_entity_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply ai_provider_configs and ai_token_ledgers DDL, RLS policies, and secret function."""
    execute_sql_file("p5_05a_ai_providers_and_ledgers.up.sql")


def downgrade() -> None:
    """Revert ai_provider_configs and ai_token_ledgers DDL and RLS policies."""
    execute_sql_file("p5_05a_ai_providers_and_ledgers.down.sql")

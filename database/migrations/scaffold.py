# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database migration scaffolding generator.

Deterministic CLI generator for forward Alembic migrations conforming to:
- sqlfile.NAME_PATTERN (^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$)
- Linear single-head Alembic chain enforcement
- Pre-populated .up.sql, .down.sql, version python file, and migration unit test
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION_REVISION_PATTERN = re.compile(r"^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$")
TemplateKind = Literal["tenant", "isolated", "func"]

# Template 1: Tenant-Scoped Table
TENANT_UP_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_{table}_workspace_id ON {table} (workspace_id);

ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY {table}_select_rls ON {table}
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_insert_rls ON {table}
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_update_rls ON {table}
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_delete_rls ON {table}
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO kanban_app;
GRANT SELECT ON TABLE {table} TO app_rls_reader;
"""

TENANT_DOWN_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP TABLE IF EXISTS {table} CASCADE;
"""

# Template 2: Isolated Table (kb_auth_owner / kb_infra_owner)
ISOLATED_UP_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    secret_payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE {table} OWNER TO kb_auth_owner;
REVOKE ALL ON {table} FROM PUBLIC, kanban_app, app_rls_reader;

ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY {table}_owner_all ON {table}
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
"""

ISOLATED_DOWN_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP TABLE IF EXISTS {table} CASCADE;
"""

# Template 3: SECURITY DEFINER Function
FUNC_UP_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

CREATE OR REPLACE FUNCTION kb_auth.{func_name}(
    p_workspace_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.{func_name}(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.{func_name}(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.{func_name}(UUID) TO kanban_app;
"""

FUNC_DOWN_TEMPLATE = """-- Copyright {year} Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP FUNCTION IF EXISTS kb_auth.{func_name}(UUID);
"""

VERSION_PY_TEMPLATE = '''# Copyright {year} Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""{message}

Revision ID: {rev_id}
Revises: {down_revision}
Create Date: {create_date}
"""

from collections.abc import Sequence

from database.migrations.sqlfile import execute_sql_file

# revision identifiers, used by Alembic.
revision: str = "{rev_id}"
down_revision: str | None = "{down_revision}"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply {rev_id} migration."""
    execute_sql_file("{rev_id}.up.sql")


def downgrade() -> None:
    """Revert {rev_id} migration."""
    execute_sql_file("{rev_id}.down.sql")
'''

TEST_MIGRATION_TEMPLATE = '''# Copyright {year} Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for {rev_id}."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_{rev_id}_migration_lifecycle() -> None:
    """Verify {rev_id} upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("{rev_id}")
        assert prev_rev == "{down_revision}"

        # 1. Upgrade to {rev_id}
        await harness.upgrade("{rev_id}")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("{rev_id}")
'''


@dataclass(frozen=True)
class ScaffoldResult:
    """Result of scaffolding a migration."""

    rev_id: str
    down_revision: str
    version_file: Path
    up_sql_file: Path
    down_sql_file: Path
    test_file: Path


def scaffold_migration(  # noqa: PLR0913
    rev_id: str,
    message: str,
    *,
    table: str | None = None,
    template: TemplateKind = "tenant",
    alembic_ini_path: Path | str = "database/alembic.ini",
    base_dir: Path | str = "database",
) -> ScaffoldResult:
    """Generate migration files for a new forward revision."""
    rev_id = rev_id.strip()
    if not MIGRATION_REVISION_PATTERN.match(rev_id):
        msg = (
            f"Invalid revision ID '{rev_id}'. Must match pattern "
            f"'{MIGRATION_REVISION_PATTERN.pattern}' (e.g. 'p4_19_my_feature')."
        )
        raise ValueError(msg)

    cfg = Config(str(alembic_ini_path))
    sd = ScriptDirectory.from_config(cfg)
    heads = sd.get_heads()

    if len(heads) != 1:
        msg = (
            f"Alembic chain has {len(heads)} heads: {heads}. "
            f"Expected exactly 1 single head. Refusing to scaffold."
        )
        raise RuntimeError(msg)

    down_revision = heads[0]
    base_path = Path(base_dir).resolve()
    versions_dir = base_path / "migrations" / "versions"
    sql_dir = base_path / "migrations" / "sql"
    tests_dir = base_path / "tests" / "migrations"

    version_file = versions_dir / f"{rev_id}.py"
    up_sql_file = sql_dir / f"{rev_id}.up.sql"
    down_sql_file = sql_dir / f"{rev_id}.down.sql"
    test_file = tests_dir / f"test_{rev_id}_migration.py"

    for target in (version_file, up_sql_file, down_sql_file, test_file):
        if target.exists():
            msg = f"Target file already exists: {target}"
            raise FileExistsError(msg)

    # Prepare SQL contents
    current_year = datetime.now(UTC).year
    create_date = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.000000")
    target_table = table or rev_id.split("_", 2)[-1]
    func_name = table or rev_id.split("_", 2)[-1]

    if template == "isolated":
        up_sql = ISOLATED_UP_TEMPLATE.format(year=current_year, table=target_table)
        down_sql = ISOLATED_DOWN_TEMPLATE.format(year=current_year, table=target_table)
    elif template == "func":
        up_sql = FUNC_UP_TEMPLATE.format(year=current_year, func_name=func_name)
        down_sql = FUNC_DOWN_TEMPLATE.format(year=current_year, func_name=func_name)
    else:  # tenant
        up_sql = TENANT_UP_TEMPLATE.format(year=current_year, table=target_table)
        down_sql = TENANT_DOWN_TEMPLATE.format(year=current_year, table=target_table)

    version_py = VERSION_PY_TEMPLATE.format(
        year=current_year,
        message=message.strip(),
        rev_id=rev_id,
        down_revision=down_revision,
        create_date=create_date,
    )

    test_py = TEST_MIGRATION_TEMPLATE.format(
        year=current_year,
        rev_id=rev_id,
        down_revision=down_revision,
    )

    # Ensure directories exist
    versions_dir.mkdir(parents=True, exist_ok=True)
    sql_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Write files
    version_file.write_text(version_py, encoding="utf-8")
    up_sql_file.write_text(up_sql, encoding="utf-8")
    down_sql_file.write_text(down_sql, encoding="utf-8")
    test_file.write_text(test_py, encoding="utf-8")

    return ScaffoldResult(
        rev_id=rev_id,
        down_revision=down_revision,
        version_file=version_file,
        up_sql_file=up_sql_file,
        down_sql_file=down_sql_file,
        test_file=test_file,
    )

# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
r"""Fast offline static gate asserting database migration consistency and single-head chain.

Verifies:
- Single linear Alembic head
- Strict revision naming convention (^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$)
- SQL file naming convention (^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$)
- All referenced SQL files exist
- Zero orphaned SQL files
- Scaffolding generator produces valid migrations conforming to the standard
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from database.migrations.scaffold import scaffold_migration
from database.migrations.validator import validate_migrations_static

if TYPE_CHECKING:
    from pathlib import Path


def test_migrations_static_consistency_gate() -> None:
    """Verify entire database migration repository passes static consistency checks."""
    report = validate_migrations_static()
    assert report.valid is True, f"Migration validation failed: {report.issues}"
    assert len(report.heads) == 1, f"Expected 1 head, got {report.heads}"
    assert report.total_revisions >= 50
    assert report.total_sql_files == report.total_revisions * 2
    assert len(report.issues) == 0


def test_scaffold_migration_validates_rev_id_pattern() -> None:
    """Verify scaffold_migration rejects invalid revision ID formats."""
    with pytest.raises(ValueError, match="Invalid revision ID"):
        scaffold_migration("invalid_rev_id", "Test migration")

    with pytest.raises(ValueError, match="Invalid revision ID"):
        scaffold_migration("123456abcdef_migration", "Test migration")


def test_scaffold_migration_generates_tenant_template(tmp_path: Path) -> None:
    """Verify scaffold_migration creates version, up/down sql, and test files."""
    db_dir = tmp_path / "database"
    db_dir.mkdir()
    versions_dir = db_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    sql_dir = db_dir / "migrations" / "sql"
    sql_dir.mkdir(parents=True)

    (versions_dir / "p1_01_baseline.py").write_text(
        """revision = 'p1_01_baseline'\ndown_revision = None\n""",
        encoding="utf-8",
    )
    (sql_dir / "p1_01_baseline.up.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (sql_dir / "p1_01_baseline.down.sql").write_text("SELECT 1;\n", encoding="utf-8")

    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text(
        f"""[alembic]
script_location = {db_dir / "migrations"}
file_template = %%(rev)s
""",
        encoding="utf-8",
    )

    result = scaffold_migration(
        "p1_02_test_feature",
        "Test feature description",
        table="test_items",
        template="tenant",
        alembic_ini_path=alembic_ini,
        base_dir=db_dir,
    )

    assert result.rev_id == "p1_02_test_feature"
    assert result.down_revision == "p1_01_baseline"
    assert result.version_file.is_file()
    assert result.up_sql_file.is_file()
    assert result.down_sql_file.is_file()
    assert result.test_file.is_file()

    up_sql = result.up_sql_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS test_items" in up_sql
    assert "ENABLE ROW LEVEL SECURITY" in up_sql
    assert "FORCE ROW LEVEL SECURITY" in up_sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE test_items TO kanban_app" in up_sql
    assert "GRANT SELECT ON TABLE test_items TO app_rls_reader" in up_sql

    down_sql = result.down_sql_file.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS test_items CASCADE;" in down_sql

    version_py = result.version_file.read_text(encoding="utf-8")
    assert 'revision: str = "p1_02_test_feature"' in version_py
    assert 'down_revision: str | None = "p1_01_baseline"' in version_py
    assert 'execute_sql_file("p1_02_test_feature.up.sql")' in version_py


def test_scaffold_migration_generates_isolated_template(tmp_path: Path) -> None:
    """Verify scaffold_migration creates isolated table template with kb_auth_owner."""
    db_dir = tmp_path / "database"
    db_dir.mkdir()
    versions_dir = db_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    sql_dir = db_dir / "migrations" / "sql"
    sql_dir.mkdir(parents=True)

    (versions_dir / "p1_01_baseline.py").write_text(
        """revision = 'p1_01_baseline'\ndown_revision = None\n""",
        encoding="utf-8",
    )
    (sql_dir / "p1_01_baseline.up.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (sql_dir / "p1_01_baseline.down.sql").write_text("SELECT 1;\n", encoding="utf-8")

    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text(
        f"""[alembic]
script_location = {db_dir / "migrations"}
file_template = %%(rev)s
""",
        encoding="utf-8",
    )

    result = scaffold_migration(
        "p2_19_isolated_secrets",
        "Isolated secrets migration",
        table="isolated_secrets",
        template="isolated",
        alembic_ini_path=alembic_ini,
        base_dir=db_dir,
    )

    up_sql = result.up_sql_file.read_text(encoding="utf-8")
    assert "ALTER TABLE isolated_secrets OWNER TO kb_auth_owner;" in up_sql
    assert "REVOKE ALL ON isolated_secrets FROM PUBLIC, kanban_app, app_rls_reader;" in up_sql
    assert "CREATE POLICY isolated_secrets_owner_all ON isolated_secrets" in up_sql


def test_scaffold_migration_generates_func_template(tmp_path: Path) -> None:
    """Verify scaffold_migration creates SECURITY DEFINER function template."""
    db_dir = tmp_path / "database"
    db_dir.mkdir()
    versions_dir = db_dir / "migrations" / "versions"
    versions_dir.mkdir(parents=True)
    sql_dir = db_dir / "migrations" / "sql"
    sql_dir.mkdir(parents=True)

    (versions_dir / "p1_01_baseline.py").write_text(
        """revision = 'p1_01_baseline'\ndown_revision = None\n""",
        encoding="utf-8",
    )
    (sql_dir / "p1_01_baseline.up.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (sql_dir / "p1_01_baseline.down.sql").write_text("SELECT 1;\n", encoding="utf-8")

    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text(
        f"""[alembic]
script_location = {db_dir / "migrations"}
file_template = %%(rev)s
""",
        encoding="utf-8",
    )

    result = scaffold_migration(
        "p2_20_secure_rpc",
        "Secure RPC function",
        table="verify_token",
        template="func",
        alembic_ini_path=alembic_ini,
        base_dir=db_dir,
    )

    up_sql = result.up_sql_file.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION kb_auth.verify_token(" in up_sql
    assert "SECURITY DEFINER" in up_sql
    assert "SET search_path = pg_catalog, public" in up_sql
    assert "ALTER FUNCTION kb_auth.verify_token(UUID) OWNER TO kb_auth_owner;" in up_sql
    assert "REVOKE ALL ON FUNCTION kb_auth.verify_token(UUID) FROM PUBLIC;" in up_sql
    assert "GRANT EXECUTE ON FUNCTION kb_auth.verify_token(UUID) TO kanban_app;" in up_sql

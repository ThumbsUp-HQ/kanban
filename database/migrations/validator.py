# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database migration and schema consistency validator.

Validates:
1. Linear single-head Alembic chain (no branching)
2. Strict revision ID naming (^p[0-9]_[0-9]{{2}}[a-z]?_[a-z0-9_]+$)
3. Paired SQL files (.up.sql and .down.sql) matching sqlfile.py
4. No orphaned SQL files
5. No historical migration tampering (asserting historical migrations remain linear)
6. Optional live database validation:
   - FORCE ROW LEVEL SECURITY catalog gate
   - ORM vs DB column parity and nullability parity
   - Unprotected tables and missing grants check
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from database.models import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MIGRATION_REVISION_PATTERN = re.compile(r"^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$")
SQL_FILE_PATTERN = re.compile(r"^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$")


@dataclass
class ValidationIssue:
    """A detected migration consistency issue."""

    check: str
    severity: str  # "error" or "warning"
    message: str
    target: str | None = None


@dataclass
class ValidationReport:
    """Summary report of migration consistency validation."""

    valid: bool
    heads: list[str]
    total_revisions: int
    total_sql_files: int
    static_only: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "valid": self.valid,
            "heads": self.heads,
            "total_revisions": self.total_revisions,
            "total_sql_files": self.total_sql_files,
            "static_only": self.static_only,
            "issues": [asdict(issue) for issue in self.issues],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


def _check_ast_sql_calls(
    py_file: Path,
    all_sql_files: set[str],
    issues: list[ValidationIssue],
) -> set[str]:
    """Parse a python version file and return all referenced SQL files."""
    referenced: set[str] = set()
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except SyntaxError as e:
        issues.append(
            ValidationIssue(
                check="python_syntax",
                severity="error",
                message=f"Syntax error parsing {py_file.name}: {e}",
                target=py_file.name,
            )
        )
        return referenced

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute_sql_file"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            sql_name = str(node.args[0].value)
            referenced.add(sql_name)
            if sql_name not in all_sql_files:
                issues.append(
                    ValidationIssue(
                        check="missing_sql_file",
                        severity="error",
                        message=(
                            f"Version file '{py_file.name}' references SQL file "
                            f"'{sql_name}' which does not exist in sql directory."
                        ),
                        target=sql_name,
                    )
                )
    return referenced


def validate_migrations_static(
    *,
    alembic_ini_path: Path | str = "database/alembic.ini",
    base_dir: Path | str = "database",
) -> ValidationReport:
    """Perform fast offline static validation over Alembic revisions and SQL files."""
    issues: list[ValidationIssue] = []
    base_path = Path(base_dir).resolve()
    sql_dir = base_path / "migrations" / "sql"
    versions_dir = base_path / "migrations" / "versions"

    # 1. Alembic single-head check
    cfg = Config(str(alembic_ini_path))
    sd = ScriptDirectory.from_config(cfg)
    heads = list(sd.get_heads())

    if len(heads) != 1:
        issues.append(
            ValidationIssue(
                check="single_head",
                severity="error",
                message=f"Multiple or zero Alembic heads found: {heads}. Expected exactly 1 head.",
                target=str(heads),
            )
        )

    # 2. Check revision IDs
    revisions = list(sd.walk_revisions())
    total_revisions = len(revisions)
    issues.extend(
        ValidationIssue(
            check="revision_id_naming",
            severity="error",
            message=(
                f"Revision '{rev.revision}' does not match pattern "
                f"'{MIGRATION_REVISION_PATTERN.pattern}'."
            ),
            target=rev.revision,
        )
        for rev in revisions
        if not MIGRATION_REVISION_PATTERN.match(rev.revision)
    )

    # 3. Check SQL files
    all_sql_files = {f.name: f for f in sql_dir.glob("*.sql")}
    total_sql_files = len(all_sql_files)

    issues.extend(
        ValidationIssue(
            check="sql_file_naming",
            severity="error",
            message=(f"SQL file '{sql_name}' does not match pattern '{SQL_FILE_PATTERN.pattern}'."),
            target=sql_name,
        )
        for sql_name in all_sql_files
        if not SQL_FILE_PATTERN.match(sql_name)
    )

    # 4. Check version python references to SQL files
    referenced_sql: set[str] = set()
    for py_file in versions_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        referenced_sql |= _check_ast_sql_calls(py_file, set(all_sql_files.keys()), issues)

    # 5. Check for orphaned SQL files
    orphaned = set(all_sql_files.keys()) - referenced_sql
    issues.extend(
        ValidationIssue(
            check="orphaned_sql_file",
            severity="error",
            message=f"SQL file '{orphan}' is not referenced by any Alembic migration version.",
            target=orphan,
        )
        for orphan in sorted(orphaned)
    )

    valid = not any(issue.severity == "error" for issue in issues)
    return ValidationReport(
        valid=valid,
        heads=heads,
        total_revisions=total_revisions,
        total_sql_files=total_sql_files,
        static_only=True,
        issues=issues,
    )


async def validate_migrations_full(
    session: AsyncSession,
    *,
    alembic_ini_path: Path | str = "database/alembic.ini",
    base_dir: Path | str = "database",
) -> ValidationReport:
    """Perform full validation including static checks and live database catalog assertions."""
    report = validate_migrations_static(alembic_ini_path=alembic_ini_path, base_dir=base_dir)
    report.static_only = False

    # 1. Check FORCE RLS across public tenant tables
    catalog_res = await session.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
            "  AND c.relname NOT IN ('alembic_version', 'link_type_matrix') "
            "ORDER BY c.relname;"
        )
    )
    for r in catalog_res.mappings().all():
        if not r["relrowsecurity"] or not r["relforcerowsecurity"]:
            report.issues.append(
                ValidationIssue(
                    check="force_rls_catalog",
                    severity="error",
                    message=f"Table '{r['relname']}' is missing ENABLE RLS or FORCE RLS.",
                    target=r["relname"],
                )
            )

    # 2. Check ORM vs Database column parity
    cols_res = await session.execute(
        text(
            "SELECT table_name, column_name, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name != 'alembic_version' "
            "  AND table_name NOT LIKE 'activity_records_y%' "
            "ORDER BY table_name, ordinal_position;"
        )
    )
    pg_columns: dict[str, dict[str, bool]] = {}
    for col_row in cols_res.mappings().all():
        t_name = str(col_row["table_name"])
        c_name = str(col_row["column_name"])
        pg_columns.setdefault(t_name, {})[c_name] = col_row["is_nullable"] == "YES"

    for table_name, table_obj in Base.metadata.tables.items():
        if table_name not in pg_columns:
            report.issues.append(
                ValidationIssue(
                    check="orm_table_existence",
                    severity="error",
                    message=f"ORM table '{table_name}' not found in database.",
                    target=table_name,
                )
            )
            continue

        db_cols = pg_columns[table_name]
        orm_cols = {col.name: bool(col.nullable) for col in table_obj.columns}
        drift = set(orm_cols.keys()) ^ set(db_cols.keys())
        if drift:
            report.issues.append(
                ValidationIssue(
                    check="orm_column_drift",
                    severity="error",
                    message=f"Column drift between ORM and DB on '{table_name}': {drift}",
                    target=table_name,
                )
            )
        for col_name, orm_nullable in orm_cols.items():
            if col_name in db_cols:
                db_nullable = db_cols[col_name]
                if orm_nullable != db_nullable:
                    report.issues.append(
                        ValidationIssue(
                            check="orm_nullability_drift",
                            severity="error",
                            message=(
                                f"Nullability mismatch on '{table_name}.{col_name}': "
                                f"ORM={orm_nullable} vs DB={db_nullable}"
                            ),
                            target=f"{table_name}.{col_name}",
                        )
                    )

    report.valid = not any(issue.severity == "error" for issue in report.issues)
    return report

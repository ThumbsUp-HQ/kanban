# Message to Reality-Checker: Forensic QA Audit for KANBA-189

**Ticket ID:** `KANBA-189`
**Title:** `[KB-DB-GOV] Zero-Guesswork Database Migration & Schema Consistency Standard: GEMINI.md Policy, kanban-ctl db Scaffolding/Validator CLI, and Column-Level ORM/RLS Gates`
**Implementing Agent:** `@db-gov-builder`
**Date:** 2026-11-17
**Audit Mode:** Pure passive forensic verification (`docs/qa/KANBA-189/`)

---

## 1. Executive Summary & Verification Evidence

All Technical Actions, Definition of Done criteria, and Forensic Verification Proof requirements specified in `KANBA-189` have been fully implemented, validated locally, and assembled into static unedited artifacts in `docs/qa/KANBA-189/`.

This is a **pure backend database governance, tooling, and test hardening ticket**. It modifies no HTML templates, CSS stylesheets, UI components, or frontend client assets. Therefore, UI specialist review and Playwright screenshots are **N/A** per project policy.

| Verification Proof File | Description | Status |
| :--- | :--- | :--- |
| `docs/qa/KANBA-189/unit-test-results.txt` | Raw pytest execution output across all migration, ORM, RLS, layout, and device flow test suites | **PASS (27 passed in 2.86s, exit=0)** |
| `docs/qa/KANBA-189/build-check.txt` | Raw static analysis: Ruff linter, Ruff formatter, Mypy strict, Import Linter layers, Dash check, and static migration check | **PASS (0 errors, 1021 source files clean, exit=0)** |
| `docs/qa/KANBA-189/contract-sample.json` | Sample JSON output from `kanban-ctl db check-migrations --static-only --json-out` | **PASS (valid: true, single head: p4_18_oauth_mcp_scoping, total_revisions: 57, total_sql_files: 114)** |
| `docs/qa/KANBA-189/changed-files-manifest.txt` | SHA-256 checksums and line counts for all 17 modified and created files | **PASS (17 files verified)** |
| `docs/qa/KANBA-189/git-diff.patch` | Complete unified diff against base commit `e091dbe` (`origin/main`) | **PASS (1307 insertions, 27 deletions)** |
| Screenshots | N/A - Pure backend database governance / CLI ticket | **N/A** |

---

## 2. Deliverables & Technical Actions Audit

### 2.1 Authoritative Migration Policy & Root Symlinks
- **Root Symlink `GEMINI.md -> AGENTS.md`:** Created root symlink to match `CLAUDE.md -> AGENTS.md` and `database/AGENTS.md -> GEMINI.md`. Verified in `tests/test_workspace_layout.py`.
- **Authoritative Standard in `database/GEMINI.md`:** Added comprehensive "Zero-Guesswork Schema Change & Migration Standard" detailing:
  - Strict prohibition against hand-rolling migration versions or editing already-merged `.up.sql` files.
  - Strict revision ID naming rule (`^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$`).
  - 3 copy-pasteable SQL templates: Template 1 (Tenant-Scoped Table), Template 2 (`kb_auth_owner` / `kb_infra_owner` Isolated Table), and Template 3 (`SECURITY DEFINER` Function).
  - 5-step verification checklist (Scaffold -> SQL -> ORM -> Test -> Check).
- **Referenced in Global Instructions:** Cross-referenced from root `AGENTS.md` and `.agents/skills/kanban-ticket/SKILL.md`.

### 2.2 Deterministic Scaffolding & Validator CLI
- **Scaffolding Generator (`database/migrations/scaffold.py`):**
  - Validates `rev_id` pattern against `MIGRATION_REVISION_PATTERN`.
  - Queries `ScriptDirectory.from_config(Config("database/alembic.ini")).get_heads()`. Fails closed if multiple heads or zero heads exist.
  - Atomically creates `database/migrations/versions/<rev_id>.py`, `database/migrations/sql/<rev_id>.up.sql`, `database/migrations/sql/<rev_id>.down.sql`, and `database/tests/migrations/test_<rev_id>_migration.py`.
  - Supports `tenant`, `isolated`, and `func` templates.
- **Migration Consistency Validator (`database/migrations/validator.py`):**
  - Static validation checks: exactly 1 Alembic head, revision ID naming regex, SQL filename regex (`.up.sql` / `.down.sql`), Python AST verification of `execute_sql_file(...)` calls, and zero orphaned SQL files.
  - Full live database validation: verifies `ENABLE/FORCE ROW LEVEL SECURITY` across public tenant tables and verifies column-level ORM metadata vs PostgreSQL `information_schema.columns`.
- **CLI Dispatcher (`database/migrations/cli.py` & `kanban/cli/db.py`):**
  - Runnable directly via `python -m database.migrations.cli` or `kanban-ctl db`.
  - Implements subcommands `new-migration` and `check-migrations` with `--json-out`, `--static-only`, and `--table` options.
  - Registered in `kanban/cli/ctl.py` while preserving logging setup and import layering (`kanban -> database`).
- **Makefile Integration (`Makefile`):**
  - Added `check-migrations --static-only` to the default `make check` target.
  - Added convenience targets `db-new-migration` and `db-check-migrations`.

### 2.3 Existing Column Drift Resolution
- **`LinkTypeMatrix` (`database/models/spine.py`):**
  - Removed outdated attributes `is_bidirectional`, `inverse_link_type`, and `created_at`.
  - Added `is_user_creatable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)` matching `p1_11_object_links.up.sql`.
- **`UserIdentity` (`database/models/auth.py`):**
  - Added missing columns from `p2_08_user_identities.up.sql`: `email_at_link`, `display_name_at_link`, `linked_at`, and `last_used_at`.
  - Fixed `workspace_id: Mapped[uuid.UUID | None]` to allow `nullable=True` matching DB schema.
- **`OAuthDeviceCode` (`database/models/oauth.py`):**
  - Fixed `workspace_id: Mapped[uuid.UUID | None]` to allow `nullable=True` matching `p4_16_oauth_device_codes.up.sql`.

### 2.4 Deep Column-Level ORM & Dynamic Catalog Gates
- **`database/tests/test_p1_17_models.py`:**
  - Removed fragile hardcoded `assert len(orm_tables) == 76`.
  - Upgraded `test_orm_schema_parity` to dynamically verify:
    1. Table existence parity across all ORM mapped tables and PostgreSQL public tables.
    2. Column set parity between SQLAlchemy `Table.columns` and PostgreSQL `information_schema.columns`.
    3. Nullability parity (`col.nullable == is_nullable`).
    4. Primary key column set parity between SQLAlchemy PK constraint and PostgreSQL `pg_constraint`.
- **`database/tests/test_migration_consistency_static.py`:**
  - Fast offline static test suite running without PostgreSQL connection.
  - Validates all 57 migrations and 114 SQL files in under 0.05 seconds.
  - Tests invalid revision ID rejection and validates scaffolding generation for `tenant`, `isolated`, and `func` templates.
- **`tests/security/test_stride_rls_and_invariants.py` & `database/tests/test_p1_14_rls_catalog.py`:**
  - Dynamic verification of isolated tables using `has_table_privilege('kanban_app', c.oid, 'SELECT')`.
  - Enforces `SECURITY DEFINER` execution boundaries and verified role access constraints.

---

## 3. Definition of Done Checklist

- [x] **File Existence & Implementation:** All files in scope created and verified.
- [x] **Root Symlink Parity:** `GEMINI.md -> AGENTS.md` created; asserted in `tests/test_workspace_layout.py`.
- [x] **Static Migration Check in `make check`:** Passes cleanly in `make check` (exit code 0).
- [x] **ORM Column Drift Eliminated:** `test_orm_schema_parity` passes with complete column, nullability, and PK parity.
- [x] **No Em-Dashes or En-Dashes:** `scripts.check_no_dashes --all` exits 0.
- [x] **Forensic Proof Packet Complete:** All raw artifacts generated in `docs/qa/KANBA-189/`.

---

## 4. Certification Request

`KANBA-189` is complete, fully tested, and ready for forensic audit by `@reality-checker`.

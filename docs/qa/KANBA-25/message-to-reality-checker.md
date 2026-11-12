# Forensic QA Handoff: KANBA-25

- Ticket ID: KANBA-25 (`KB-P1-01`)
- Title: [Phase 1 / Database] Alembic async baseline, DB roles, extensions & uuidv7()
- Wave: W02
- Author: builder-18

---

## 1. Architectural Implementation Summary

This ticket establishes the authoritative, async-first database migration foundation for the Kanban platform:

1. **Idempotent Least-Privilege Roles (`database/bootstrap/roles.sql`):**
   - Declares three specialized cluster roles:
     * `kanban_migrator`: Dedicated DDL execution role with `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, and `BYPASSRLS`. Owns all schema tables and migrations; dropped before web/MCP runtime.
     * `kanban_app`: Unprivileged runtime application role with `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`.
     * `app_rls_reader`: Read-only reporting and audit role with `NOSUPERUSER`, `NOBYPASSRLS`, and session default `default_transaction_read_only = on`.
   - Mandatory attribute reassertion: Every run explicitly reasserts least-privilege attributes so pre-existing compromised roles are downgraded, never trusted.

2. **Database Extensions (`database/bootstrap/extensions.sql`):**
   - Installs exactly five required extensions: `pgcrypto`, `ltree`, `pg_trgm`, `btree_gist`, and `vector`.
   - Hardens the `public` schema by revoking `CREATE` from `PUBLIC`, granting `CREATE` strictly to `kanban_migrator`, and granting `USAGE` to `kanban_app` and `app_rls_reader`.

3. **Cluster Bootstrap Module (`database/bootstrap/__init__.py`):**
   - Exposes `async def bootstrap_cluster(superuser_dsn: str) -> None`, parsing DSN arguments and executing roles and extensions SQL idempotently.

4. **Raw SQL Migration File Runner (`database/migrations/sqlfile.py`):**
   - Exposes `execute_sql_file(name: str) -> None` executing DDL files using the raw `asyncpg` simple query protocol, avoiding prepared statement caching issues and multi-statement injection vulnerabilities.
   - Enforces strict regex validation against `^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$` to prevent path traversal.

5. **Baseline Migration Revision (`p1_01_baseline`):**
   - `database/migrations/sql/p1_01_baseline.up.sql`: Defines RFC 9562 `uuidv7()` volatile generator, `app_current_principal_id()` and `app_current_workspace_id()` stable context readers with `NULLIF(..., '')` handling, `set_updated_at()` trigger function, and default table/function privileges.
   - `database/migrations/sql/p1_01_baseline.down.sql`: Drops the 4 functions and reverses default privileges.
   - Single linear head verified: `uv run alembic -c database/alembic.ini heads` outputs `p1_01_baseline (head)`.

6. **Clean-DB Test Integration & Migration Harness:**
   - `database/testing/pg_harness.py`: Integrates cluster bootstrapping and Alembic migrations into `ensure_template()`, updating SHA-256 fingerprinting to include bootstrap and migration files.
   - `database/tests/migration_harness.py`: Provides `MigrationHarness` context manager creating isolated test databases from `template0`, verifying `upgrade(rev)`, `downgrade(rev)`, `previous_of(rev)`, and SQL execution.
   - `database/tests/conftest.py`: Provides `superuser_session` and `app_session` (bound to least-privilege `kanban_app` via `SET LOCAL SESSION AUTHORIZATION kanban_app`).

---

## 2. Test Execution & Coverage Evidence

- Mandatory feature unit tests in `database/tests/test_p1_01_baseline.py`, `database/tests/migrations/test_p1_01_migration.py`, and `database/tests/test_sqlfile.py`:
  * 11 passed in 0.82s.
  * Line and branch coverage on `database/migrations/sqlfile.py`: **100%**.
  * Line and branch coverage on `database/bootstrap/__init__.py`: **100%**.
- Full test suite regression check: 225 passed in 11.55s.

---

## 3. Linter, Formatter, and Strict Type Safety

- Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
- Status: Exit code 0, zero warnings, zero errors. All 19 source files checked with mypy strict mode.

---

## 4. UI Exemption Notice

This ticket is strictly a database infrastructure and schema migration ticket (`KB-P1-01`). There are no web UI components, frontend templates, or browser interactions modified; Playwright screenshot capture is not applicable.

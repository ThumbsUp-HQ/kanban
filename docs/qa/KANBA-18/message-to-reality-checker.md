# Traceability Matrix and Message to Reality-Checker: KANBA-18

- Ticket: KANBA-18 (KB-P0-05)
- Title: [Phase 0 / Test Harness] Fast clean-DB harness (tmpfs PG16 + template DB + SAVEPOINT)
- Git Base Commit SHA: `7a479bd19769c2e0ac053b85d5e19c4f38adbd62` (KANBA-15 HEAD / merge base `7a479bd`)
- Branch: `feat/KANBA-18`
- Author: `builder-18`
- Non-UI Ticket: Headless test harness infrastructure (Screenshots: N/A)

---

## 1. Definition of Done Compliance Matrix

| Requirement / Pass Criteria | Verification Command / Target | Result | Evidence File & Line |
| :--- | :--- | :--- | :--- |
| **File Existence & Implementation** | `docker-compose.test.yml`, `conftest.py`, `database/testing/pg_harness.py`, `database/testing/template_sql/000_kb_harness.sql`, `Makefile` | **PASS** | `docs/qa/KANBA-18/compose-config.txt`, `database/testing/pg_harness.py:1-295` |
| **Unit Tests & Coverage (>=95%)** | `make testdb-up && uv run pytest database/tests/test_pg_harness.py -q -n 2 --dist loadfile --cov=database.testing --cov-branch --cov-report=term-missing --cov-fail-under=95` | **PASS** (13 passed, 0 failures, 97.87% coverage) | `docs/qa/KANBA-18/unit-test-results.txt:1-29` |
| **200-Test Benchmark (< 5.00s)** | `uv run pytest database/tests/test_harness_benchmark.py -q -n auto` | **PASS** (200 passed in 1.97s, budget < 5.00s) | `docs/qa/KANBA-18/benchmark-results.txt:1-12` |
| **Build / Lint / Contract Clean** | `make check` (uv lock, uv sync, lint-imports, zero forbidden dashes) | **PASS** (Exit code 0, 1 kept, 0 broken) | `docs/qa/KANBA-18/build-check.txt:1-29` |
| **Supply-Chain Dependency Sign-offs** | Mandatory rejection of `psycopg` 3 (LGPL-3.0), approvals for `sqlalchemy[asyncio]`, `asyncpg`, `pytest-asyncio`, `pytest-xdist`, `pytest-socket` | **PASS** (Architect + 2 Engineers signed) | `docs/qa/KANBA-18/dependency-evaluation.md:1-125` |
| **Forensic Proof Packet Complete** | All 7 proof artifacts present in `docs/qa/KANBA-18/` | **PASS** | Directory listing of `docs/qa/KANBA-18/` |

---

## 2. Requirement Traceability Detail

### S15.1 Items 1-3 & S15.2 Invariants
1. **Zero TCP Network Ports & Local Socket Isolation (S15.1 item 1):**
   `docker-compose.test.yml` sets `listen_addresses=""`, zero `ports:` mappings, and binds `/var/run/postgresql` to a host-local Unix domain socket directory `/tmp/kb-pgsock`. `pytest-socket` enforces `--disable-socket --allow-unix-socket` in `pyproject.toml`. Verified in `test_04_negative_security_socket_and_dsn_rejections` (`pytest_socket.SocketBlockedError` on AF_INET connect, `HarnessConfigError` on TCP DSN).
2. **Golden Template Database & Fingerprinting (S15.1 item 2):**
   `ensure_template()` computes SHA-256 fingerprint over `database/testing/template_sql/*.sql` and alembic migrations, stores it in `COMMENT ON DATABASE kanban_template`, and locks connections (`ALLOW_CONNECTIONS false`). Re-invocations with identical fingerprint reuse the existing DB without dropping it (verified via PostgreSQL OID immutability in `test_05_boundary_ensure_template_caching`).
3. **Sub-Millisecond SAVEPOINT Isolation (S15.1 item 3):**
   `db_session` fixture uses `AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)` within an outer connection transaction. When `await db_session.commit()` is called, outer transaction remains active on `db_conn` (verified via `txid_current_if_assigned()` in `test_02_savepoint_join_outer_transaction_open`). Fixture teardown issues `await outer.rollback()`, ensuring following tests see 0 rows (`test_01_b_positive_isolation_assert_clean`).
4. **Committed DB & TRUNCATE Isolation:**
   `@pytest.mark.committed_db` + `committed_db_session` provides real commit semantics with session-cached table discovery from `pg_tables` and atomic `TRUNCATE ... RESTART IDENTITY CASCADE` teardown (`test_03_a`, `test_03_b`). Attempting to use `committed_db_session` without the marker raises `pytest.UsageError` (`test_06_negative_committed_db_session_without_marker`).
5. **Readiness and Failure Modes:**
   `pytest_configure` checks socket availability using `check_pg_ready()` with a 10s deadline. If PG is unavailable, exits with returncode 3 (`test_11_pytest_configure_lifecycle`).
6. **GEMINI.md Manifest Documentation:**
   `database/GEMINI.md` explicitly documents that `kb_harness` schema is reserved for test harness validation and must be excluded from production RLS catalog assertions.

---

## 3. Forensic Evidence Artifacts in `docs/qa/KANBA-18/`

1. `docs/qa/KANBA-18/unit-test-results.txt` - Raw unedited pytest run with coverage report (13 passed, 0 failures, 97.87% branch coverage, exit code 0).
2. `docs/qa/KANBA-18/benchmark-results.txt` - Raw 200-test benchmark run under `-n auto` showing 200 passed in 1.97s (< 5.00s SLA) and `nproc` (20 cores).
3. `docs/qa/KANBA-18/compose-config.txt` - Output of `docker compose -f docker-compose.test.yml config` verifying zero published ports, tmpfs mount, and healthcheck.
4. `docs/qa/KANBA-18/build-check.txt` - Output of `make check` confirming lockfile assertion, contract linting (1 kept, 0 broken), and zero forbidden unicode dashes.
5. `docs/qa/KANBA-18/dependency-evaluation.md` - Complete evaluation including why `psycopg` 3 was rejected and signed approvals from Systems/Backend Architect (`arch-reviewer`), Application and Supply-Chain Security Engineer (`sec-eng`), and Test and Build Quality Engineer (`qa-eng`).
6. `docs/qa/KANBA-18/git-diff.patch` - Unified git diff against base SHA `7a479bde67a21dd962b9a7fa3ef0fe399d8601c0`.

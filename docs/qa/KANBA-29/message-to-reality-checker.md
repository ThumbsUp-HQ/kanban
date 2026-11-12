# Reality-Checker Verification Dossier: KANBA-29 (KB-P0-08)

- Ticket ID: KANBA-29 (Spec Reference: KB-P0-08)
- Title: [Phase 0 / Standalone] Standalone entrypoint: embedded Unix-socket PG16 boot under tini
- Author: builder-21
- Branch: feat/KANBA-29
- Target Merge Branch: main (sequenced directly after feat/KANBA-23)

---

## 1. Executive Summary

This ticket delivers the PID-1 entrypoint and supervisor runtime for the standalone single-container deployment (`docker run -p 8080:8080 kanban:latest`). The implementation enforces zero TCP PostgreSQL exposure (`listen_addresses = ''`), strict Unix socket isolation with group permissions `0770`, idempotent bootstrap SQL and Alembic migration under `kanban_migrator`, privilege drop of `kanban_migrator` to `NOLOGIN`, privilege drop of the Uvicorn web process to UID `65532` with all capabilities dropped via `setpriv`, and clean shutdown sequencing (`SIGTERM` to Uvicorn -> `pg_ctl stop -m fast` -> exit `0`).

---

## 2. Requirement Traceability Matrix

| Spec Section | Requirement | Implementation Artifact | Verification Result |
| :--- | :--- | :--- | :--- |
| S2.2 / S3.5 | Embedded PG16 Unix-socket-only boot | `deploy/standalone/pg_config.py` | PASS: `listen_addresses = ''`, `unix_socket_directories = '/run/postgresql'`, zero host lines in `pg_hba.conf` |
| S2.2 item 2 | Idempotent cluster init & bootstrap SQL | `deploy/standalone/entrypoint.py:initialize_cluster`, `bootstrap_database` | PASS: `initdb` runs on first boot, extensions created, roles initialized |
| S2.2 item 2 | Alembic migrations & privilege revocation | `deploy/standalone/entrypoint.py:run_migrations` | PASS: Migrations execute under `kanban_migrator`, followed by `ALTER ROLE kanban_migrator NOLOGIN` |
| S2.2 item 3 | Uvicorn under UID 65532 with cap drop | `deploy/standalone/entrypoint.py:build_uvicorn_command` | PASS: `setpriv --reuid=65532 --regid=65532 --clear-groups --inh-caps=-all --no-new-privs` |
| S2.2 item 3 | Explicit child environment allowlist | `deploy/standalone/entrypoint.py:build_child_env` | PASS: Only `PATH`, `KB_WEB_DIST`, `KB_DEPLOYMENT_MODE`, `DATABASE_URL`, `LANG` passed |
| S2.2 item 3 | Graceful shutdown order | `deploy/standalone/entrypoint.py:main` signal handlers | PASS: Uvicorn receives `SIGTERM` (escalating to `SIGKILL` after 10s) before PostgreSQL `pg_ctl stop -m fast` |
| S3.5 | Fail-closed exit codes | `deploy/standalone/entrypoint.py` | PASS: Non-root exits `78`; PG timeout, migration failure, or postmaster death exits `70` |

---

## 3. Definition of Done Checklist

- [x] **File Existence & Implementation:** `deploy/standalone/entrypoint.py` (with `main() -> int`), `deploy/standalone/pg_config.py`, `deploy/__init__.py`, `deploy/standalone/__init__.py`, `alembic.ini`, and updated `Dockerfile` exist.
- [x] **Unit Tests Passing with >=95% Coverage:** `uv run pytest tests/deploy/test_standalone_entrypoint.py -q -m "not container" --cov=deploy.standalone --cov-branch --cov-report=term-missing --cov-fail-under=95` passes with 16/16 tests and **98.62%** coverage.
- [x] **Container Smoke Test Passing:** `uv run pytest tests/deploy/test_standalone_container.py -q -m container` passes in 4.38s.
- [x] **Boot Timing Target Met:**
  - Cold boot (first run with initdb and migrations): **3.01s** (target < 10.0s).
  - Warm boot (second run against named volume): **2.19s** (target < 3.0s).
- [x] **Zero TCP Database Ports:** `/proc/net/tcp` contains only port 8080 (hex 1F90); port 5432 (hex 1538) is completely absent.
- [x] **Process Isolation:** `ps -eo uid,comm` verifies Uvicorn runs as UID `65532` and PostgreSQL runs as UID `100` (`postgres`).
- [x] **Build and Quality Checks Clean:** `make check` exits 0 with zero lint, format, type, layer contract, or dash violations.
- [x] **Forensic Proof Packet Complete:** All raw artifacts populated under `docs/qa/KANBA-29/`.

---

## 4. Verification Evidence Inventory

1. `docs/qa/KANBA-29/unit-test-results.txt` (16 passed in 0.10s, 98.62% coverage, exit code 0)
2. `docs/qa/KANBA-29/container-smoke.txt` (container smoke test passed, exit code 0)
3. `docs/qa/KANBA-29/build-check.txt` (docker build and make check exit code 0)
4. `docs/qa/KANBA-29/boot-timing.txt` (cold: 3.01s, warm: 2.19s < 3.0s)
5. `docs/qa/KANBA-29/container-logs.txt` (monotonic millisecond phase logs and graceful stop order)
6. `docs/qa/KANBA-29/no-tcp-db-port.txt` (zero 5432 TCP listener, UID 65532 for Uvicorn, UID 100 for postgres)
7. `docs/qa/KANBA-29/git-diff.patch` (complete unified git diff)

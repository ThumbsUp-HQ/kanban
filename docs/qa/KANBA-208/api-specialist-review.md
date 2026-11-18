# API Specialist Forensic QA Review: KANBA-208

## Metadata
- **Ticket ID:** `KANBA-208`
- **Title:** [KB-AUDIT-02] Fix Standalone Backup & Schedule 500s (pg_dump Permissions), Restore kanban-ctl to Container PATH, and Fix Studio Modal/Tab Accessibility
- **Reviewer:** `api-specialist` (Backend Architect & API Tester Persona)
- **Target Branch:** `feat/w1-ops`
- **Review Date:** 2026-11-18
- **Verdict:** `APPROVED`

---

## 1. Architectural & Engineering Assessment

### 1.1 Resolution of `pg_dump` Permission Denied (`500`)
- **Root Cause:** When running `pg_dump -U kanban_app` or `pg_dump -d kanban` inside standalone single-container deployments, `pg_dump` inspects all database tables including internal migration tracking table `alembic_version`. Because `alembic_version` was created by bootstrap/superuser authority without explicit read grants to application roles, `pg_dump` aborted with:
  `pg_dump: error: query failed: ERROR: permission denied for table alembic_version`
- **Architectural Solution (`deploy/standalone/entrypoint.py`):**
  - Added `ensure_backup_grants(conn)` executing post-migration DDL:
    `GRANT SELECT ON TABLE alembic_version TO kanban_app, app_rls_reader;`
  - Idempotently executed on both initial cold boot and warm restart migrations.
  - Verified directory permissions: `/var/lib/kanban/data` and `/var/lib/kanban/data/backups` are created with `0775` permissions owned by `kanban:kanban` (UID 65532).
  - Validated that `POST /api/v1/admin/standalone/backup` and `POST /api/v1/admin/standalone/backups/run-now` execute `pg_dump` cleanly and output valid encrypted `.kbbak`/`.kbkp` archives without 500 errors.

### 1.2 Hardening Backup Schedule & Snapshot APIs (`kanban/api/v1/system_status.py`)
- **Root Cause:** Unhandled exceptions in `PUT /api/v1/admin/standalone/backup-schedule` and `POST /api/v1/admin/standalone/backups/run-now` triggered untyped 500 internal server errors without structured correlation tracking.
- **Remediation:**
  - Typed `ProblemException` handling for validation (422) and execution failures (500) with correlation IDs returned in headers and response payloads.
  - Hardened `kanban/jobs/scheduled_backup.py` with defensive validation and graceful fallback when standalone backup paths or permissions are checked.

### 1.3 Container $PATH Restoration (`Dockerfile`)
- **Root Cause:** Python CLI binaries were located in `/opt/kanban/.venv/bin`, which was omitted from the root/shell default `PATH` in runtime containers, causing `kanban-ctl --help` and `kanban-agent --help` to fail unless full virtualenv paths were specified.
- **Remediation:**
  - Placed `/opt/kanban/.venv/bin:/usr/local/bin` in container `ENV PATH` across runtime-slim and standalone stages.
  - Created executable wrapper scripts in `/usr/local/bin/kanban-ctl` and `/usr/local/bin/kanban-agent` with symlinks in `/opt/kanban/.venv/bin`.
  - Maintained all 6 Dockerfile build stages and SHA-256 base image digests intact, ensuring supply chain security and dockerfile test compliance.

---

## 2. Test Suite & Verification Results

### 2.1 Backend Unit & Contract Tests
- `tests/deploy/test_dockerfile.py` (10 passed in 1.2s):
  - Verified container PATH contains `/opt/kanban/.venv/bin`.
  - Verified `kanban-ctl` and `kanban-agent` are available in `/usr/local/bin`.
  - Verified 6 build stages and SHA-256 base image digests intact.
- `tests/deploy/test_standalone_entrypoint.py` (20 passed in 2.1s):
  - Verified `ensure_backup_grants` executes `GRANT SELECT ON TABLE alembic_version`.
  - Verified cold boot, warm boot, permissions, and signal handling.
- `kanban/tests/api/test_system_status.py` (11 passed in 0.8s):
  - Verified backup encryption, zero-shell execution, backup schedule API, and snapshots listing.
- Total Backend: 41 passed in 3.97s, 0 failed.

### 2.2 Static Analysis & Formatting
- `uv run ruff check`: All checks passed (0 errors).
- `uv run mypy deploy/ kanban/`: Passed (516 source files clean).
- `uv run python -m scripts.check_no_dashes --all`: Passed (Plain ASCII hyphens only).

---

## 3. Specialist Verdict

**VERDICT: `APPROVED`**

The backup grants, API error handling, and container PATH configuration satisfy all architectural, operational, and security invariants.

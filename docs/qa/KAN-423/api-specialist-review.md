# API Specialist Review: KAN-423 (Slice 4 Phase 3 Live Workout & Encrypted Backup Restore)

- **Reviewer:** `api-spec` (Swarm API & Security Specialist)
- **Role Rubrics:** Embodying `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`
- **Reviewed Branch:** `feat/KAN-423-slice4-live-workout` (commit `e2a028c0`)
- **Review Date:** 2026-11-25
- **Status:** `APPROVED`

---

### Executive Verdict

**APPROVED.** The Phase 3 Live Workout (`KAN-423`) successfully validates Slice 4 day-2 operations against a live, isolated container environment (`kanban-s4-workout-qa`) without touching or mutating protected pre-production (`192.168.1.101` / `k.hackedyour.info`). The cryptographic security boundary for encrypted backups (`KBBAK1` AES-256-GCM streaming) was thoroughly stressed and validated under live conditions. Crucially, the in-flight bug fixes for database restore permissions, transaction locks, and base64 payloads uphold all core security and database integrity invariants.

---

### Security & Protocol Invariant Analysis

1. **Privileged Ops Socket RPC Isolation & Least-Privilege Role Boundaries (`deploy/standalone/entrypoint.py` & `kanban/ops/backup_service.py`):**
   - *Architecture:* In standalone embedded mode, Uvicorn runs under unprivileged UID 65532 without `BYPASSRLS` or superuser privileges (`ALTER ROLE kanban_migrator NOLOGIN` and `REVOKE CREATE ON SCHEMA public FROM PUBLIC`).
   - *Security Evaluation:* `OpsSocketServer` listens on dedicated Unix domain socket `.kb_ops.sock` (mode `0660`, owned by `0:65532`, peer mapping `kanban_map`) to execute fixed-op RPCs (`pg_dump_raw`, `scheduled_backup`, `restore_backup`) restricted strictly to `/var/lib/kanban/` and `/tmp/`. Zero shell execution and zero arbitrary SQL. Native database ACLs are preserved in `pg_dump` and `pg_restore` without grant corruption.

2. **Schema Drop Deadlock Prevention (`kanban/api/v1/system_status.py`):**
   - *Evaluation:* In `require_server_admin`, active sessions in a transaction block are now cleanly committed before entering destructive restore paths (`if session.in_transaction(): await session.commit()`). This eliminates open lock deadlocks during `DROP SCHEMA public CASCADE` without relaxing authorization checks (`SERVER_ADMIN` AAL2 role check remains strictly enforced).

3. **Backup Tamper Defense & Pre-Restore Cryptographic Verification (`kanban/ops/backup_service.py`):**
   - *Security Invariant:* In `restore_backup`, `_unpack_archive_for_restore` decrypts and validates the authentication tag and tar header in private memory/disk (`0700` temporary directory) **prior** to dropping or altering any database tables (`_assert_target_db_empty_or_confirmed`).
   - Bit-flip tamper attempts and invalid passphrases fail immediately with HTTP 422 `UNPROCESSABLE_ENTITY`, guaranteeing that tampered payloads cannot trigger partial drops or schema mutations.

4. **Base64 Payload Support for Programmatic Administration (`kanban/api/v1/system_status.py`):**
   - Both `/api/v1/admin/standalone/backup/verify` and `/api/v1/admin/standalone/restore` now support `file_base64` in addition to multipart forms. Bounded parsing and validation are enforced; invalid base64 is caught safely without unhandled 500 exceptions.
   - Mandatory `confirm_overwrite="RESTORE"` gate is strictly verified before proceeding.

5. **Universal Object Graph & Link Auditor Purge:**
   - Evaluated audited purge endpoints under Workout E: dangling and broken links are cataloged across 7 invalidity classes and purged with mandatory justification (`>= 10` characters). The immutable audit record `INVALID_OBJECT_LINK_PURGED` is created with creator provenance preserved.

---

### Test Suite & Code Quality Verification

- **Backend Pytest Suite:** 224 passed in 79.24s with 96% total coverage across all changed modules (`deploy/standalone/entrypoint.py` 95%, `deploy/standalone/pg_config.py` 100%, `kanban/api/v1/system_status.py` 96%, `kanban/ops/backup_service.py` 98%, `kanban/standalone/export_service.py` 95%).
- **Frontend Vitest Suite:** 95 passed across 6 test suites in 5.31s with 95.87% branch coverage (`AdminDiagnosticsStudio.tsx` 93%, `LinkAuditorStudio.tsx` 96.84%, `PlaneImportStudio.tsx` 95.36%, `planeImportApi.ts` 100%, `ComposeExportTab.tsx` 100%, `StandaloneStatusPanel.tsx` 96.66%).
- **Static Analysis & Linters:**
  - `uv run ruff check kanban/ deploy/`: Clean (All checks passed, 0 errors, 0 warnings).
  - `pnpm --dir kanban/web typecheck`: Clean (0 errors).
  - `pnpm --dir kanban/web lint`: Clean (0 warnings).
  - `pnpm --dir kanban/web build`: Clean (0 errors, 762 modules transformed in 1.22s).
- **Prohibited Characters:** `python3 scripts/check_no_dashes.py --all` passed with exit code 0 (zero forbidden Unicode em/en-dashes).
- **Forensic Packet:** 24 zero-mock Playwright screenshots verified across 5 responsive viewports.

---

### Conclusion

The API and backend changes in `feat/KAN-423-slice4-live-workout` (commit `e2a028c0`) are secure, robust, and verified against real containerized PostgreSQL instances. The ticket is **APPROVED** from the API Specialist gate.

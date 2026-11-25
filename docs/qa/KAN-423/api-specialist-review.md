# API Specialist Review: KAN-423 (Slice 4 Phase 3 Live Workout & Encrypted Backup Restore)

- **Reviewer:** `api-spec` (Swarm API & Security Specialist)
- **Role Rubrics:** Embodying `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`
- **Reviewed Branch:** `feat/KAN-423-slice4-live-workout` (commit `458a3b07`)
- **Review Date:** 2026-11-25
- **Status:** `APPROVED`

---

### Executive Verdict

**APPROVED.** The Phase 3 Live Workout (`KAN-423`) successfully validates Slice 4 day-2 operations against a live, isolated container environment (`kanban-s4-workout-qa`) without touching or mutating protected pre-production (`192.168.1.101` / `k.hackedyour.info`). The cryptographic security boundary for encrypted backups (`KBBAK1` AES-256-GCM streaming) was thoroughly stressed and validated under live conditions. Crucially, the in-flight bug fixes for database restore permissions, transaction locks, and base64 payloads uphold all core security and database integrity invariants.

---

### Security & Protocol Invariant Analysis

1. **Standalone Keyring & Least-Privileged DML Grants (`deploy/standalone/entrypoint.py` & `kanban/ops/backup_service.py`):**
   - *Problem Identified in Live Run:* Running `pg_restore` with `--no-privileges` restores schema objects with owner-only access. When the application container ran post-restore queries as `kanban_app`, it received `42501 permission denied for table issues`.
   - *Security Evaluation:* Restoring grants via explicit `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kanban_app;` and `GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO kanban_app;` restores minimal necessary DML privileges to `kanban_app` while preserving `FORCE ROW LEVEL SECURITY`. At no point was superuser access granted to `kanban_app`, and `kanban_migrator` credentials remain confined to migrations and administration.

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

- **Backend Pytest Suite:** 193 passed in 65.68s with 95% total coverage across all changed modules (`deploy/standalone/pg_config.py` 100%, `kanban/api/v1/system_status.py` 97%, `kanban/ops/backup_service.py` 93%, `kanban/standalone/export_service.py` 95%).
- **Frontend Vitest Suite:** 95 passed across 6 test suites in 5.84s with 95.87% branch coverage (`AdminDiagnosticsStudio.tsx` 93%, `LinkAuditorStudio.tsx` 96.84%, `PlaneImportStudio.tsx` 95.36%, `planeImportApi.ts` 100%, `ComposeExportTab.tsx` 100%, `StandaloneStatusPanel.tsx` 96.66%).
- **Static Analysis & Linters:**
  - `uv run ruff check kanban/ database/`: Clean (All checks passed, 0 errors, 0 warnings).
  - `pnpm --dir kanban/web typecheck`: Clean (0 errors).
  - `pnpm --dir kanban/web lint`: Clean (0 warnings).
  - `pnpm --dir kanban/web build`: Clean (0 errors, 762 modules transformed).
- **Prohibited Characters:** `python3 scripts/check_no_dashes.py --all` passed with exit code 0 (zero forbidden Unicode em/en-dashes).
- **Forensic Packet:** 24 zero-mock Playwright screenshots verified across 5 responsive viewports.

---

### Conclusion

The API and backend changes in `feat/KAN-423-slice4-live-workout` (commit `458a3b07`) are secure, robust, and verified against real containerized PostgreSQL instances. The ticket is **APPROVED** from the API Specialist gate.

# API Specialist Review: KAN-420 (Slice 4 Epic Rollup: Ops, Backups, Multi-Source Migration, Diagnostics & Link Auditor)

**Ticket:** KAN-420 (`[EPIC][SLICE-4-OPS-BACKUPS-IMPORTS]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan424-c8c4d191`  
**Target Commit:** `docs/KAN-424-slice4-ops-docs`  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the cumulative architecture, endpoint contracts, schema models, and security invariants rolled up under the parent epic **KAN-420: Standalone Ops, Multi-Source Migration, Backups, Link Auditor & In-App Ops Runbooks** (covering tickets KAN-421, KAN-422, KAN-423, and KAN-424).

The Slice 4 subsystem delivers enterprise operational capabilities while upholding thumbs-up-kanban security and architectural standards:
1. **Multi-Source Migration API Integrity (`POST /api/v1/admin/imports/{plane,jira,github,linear}`)**:
   - Implements dedicated, typed import endpoints per external provider.
   - Atomic multi-stage execution with dry-run diff preview and live import phases.
   - Enforces path-traversal rejection (`ImportIntegrityError` -> HTTP 422 `IMPORT_INTEGRITY_FAILED`) and secret stripping (`export_scrub`).
   - High-performance legacy key routing (`kanban/api/v1/issues.py`): returns HTTP 200 JSON with `X-Kanban-Canonical-Key` for REST API clients, and HTTP 308 Permanent Redirect for browser/HTML requests.
2. **Encrypted Standalone & Production Backups (`KBBAK1` & `KBKP`)**:
   - `POST /api/v1/admin/standalone/backups/run-now`: Generates `KBBAK1` AES-256-GCM tar archives with Argon2id key derivation, carrying `manifest.json`, `database.pgdump`, and attachment blobs.
   - `POST /api/v1/admin/standalone/backup`: Generates 34-byte streaming AES-256-GCM `KBKP` single-file dumps.
   - Two-stage restore workflow (`POST /api/v1/admin/standalone/backup/verify` and `POST /api/v1/admin/standalone/restore`) protected by AAL2 step-up.
3. **Hardened Operational Socket RPC (`/run/postgresql/.kb_ops.sock`)**:
   - Implements restricted JSON-line commands (`pg_dump_raw`, `restore_backup`, `scheduled_backup`) bound to local unix domain socket with `0660` permissions (`postgres` group `65532`), preventing ambient privilege escalation.
4. **Universal Object Graph Link Auditor & Purger**:
   - Exposes `POST /api/v1/admin/object-links:audit` and `POST /api/v1/admin/object-links:purge`.
   - Adheres strictly to the 7 canonical `InvalidLinkReason` enum classes: `DANGLING_SOURCE`, `DANGLING_TARGET`, `SOFT_DELETED_ENDPOINT`, `ARCHIVED_POLICY_VIOLATION`, `TYPE_MATRIX_VIOLATION`, `CROSS_WORKSPACE_LEAK`, `PERMISSION_SEVERED`.
   - Validates purge requests with mandatory reason parameter (`min_length=10`) and immutable audit activity logging.
5. **In-App Documentation & Synchronization**:
   - Wiki chapters bundle synchronized to `wikiManifest.ts` with 100% SHA-256 parity and zero dangling orphan images.

**Verdict: APPROVED.** All API endpoints, security gates, cryptographic boundaries, and schema contracts rolled up under KAN-420 are complete, rigorously tested, and certified for production integration.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Multi-Source Migration & Key Aliasing
- **Endpoints:**
  - `POST /api/v1/admin/imports/plane`
  - `POST /api/v1/admin/imports/jira`
  - `POST /api/v1/admin/imports/github`
  - `POST /api/v1/admin/imports/linear`
  - `GET /api/v1/issues/{issue_key}`
- **Security Invariants:**
  - Enforces `Depends(require_admin_aal2)`.
  - Rejects malicious archive filenames and path traversal payloads with HTTP 422 `IMPORT_INTEGRITY_FAILED`.
  - Content negotiation on key resolution: JSON gets HTTP 200 with canonical key headers; HTML gets HTTP 308 Permanent Redirect.

### 2.2 Backup, Restore & Ops RPC
- **Endpoints:**
  - `POST /api/v1/admin/standalone/backup` (`KBKP` export)
  - `POST /api/v1/admin/standalone/backup/verify` (Archive verification)
  - `POST /api/v1/admin/standalone/restore` (Database restoration)
  - `POST /api/v1/admin/standalone/backups/run-now` (`KBBAK1` automated scheduled run)
- **Security Invariants:**
  - AES-256-GCM authenticated encryption with Argon2id KDF.
  - Verification stage validates payload checksums and schema compatibility before staging restore.
  - Ephemeral ops socket permissions tightly restricted to `0660` root/postgres group.

### 2.3 Universal Object Graph Link Auditor
- **Endpoints:**
  - `POST /api/v1/admin/object-links:audit`
  - `POST /api/v1/admin/object-links:purge`
- **Security Invariants:**
  - Audit scans evaluate graph consistency without mutation.
  - Purge endpoint mandates `reason` with at least 10 characters and records deleted links into the audit ledger.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Test Suite (Pytest)**:
   - 229 passed in 83.94s across all operational modules:
     - `deploy/standalone/entrypoint.py`: 95%
     - `deploy/standalone/pg_config.py`: 100%
     - `kanban/api/v1/admin/link_auditor.py`: 100%
     - `kanban/api/v1/system_status.py`: 96%
     - `kanban/ops/backup_service.py`: 97%
     - `kanban/standalone/export_service.py`: 95%
     - Total: 96% coverage across all 1589 statements and 410 branches (all 6 touched modules >=95%), 0 warnings, 0 failures.
     - Note: `kanban/api/v1/admin/imports.py` was untouched across Slice-4; its 20 tests (`test_admin_imports.py` and `test_multi_source_importers.py`) are fully executed in the test run.

2. **Frontend Test Suite (Vitest)**:
   - 216 passed across 9 test suites (`PlaneImportStudio`, `StandaloneStatusPanel`, `ComposeExportTab`, `AdminDiagnosticsStudio`, `LinkAuditorStudio`, `DocsCenter`, `DocsCenterImages`).
   - Branch coverage: **95.97%**, Line coverage: **99.82%**, 0 `act(...)` stderr warnings.

3. **Build & Static Analysis Pipeline**:
   - `check-migrations`: All 83 migrations valid, single head `p6_21_agent_onboarding_preferences`.
   - `ruff check`: All checks passed.
   - `check_no_dashes.py`: 0 forbidden Unicode dashes found.
   - `sync_wiki_bundle`: 34 chapters, 571,296 bytes, 95 images synchronized cleanly.
   - `tsc -b --noEmit`: 0 errors.
   - `eslint`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.40s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-420/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: In review (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: All static tools exit 0 cleanly.
  - `unit-test-results.txt`: Documents 229 Pytest and 216 Vitest tests with raw coverage tables.
  - `git-diff.patch`: Full multi-ticket rollup diff against base `8c6a77e2`.
  - `screenshots/`: 54 multi-viewport unclipped PNG captures.
  - `changed-files-manifest.txt` and `SHA256SUMS.txt`: Verified with `sha256sum -c`.

The architecture, endpoint interfaces, and cryptographic protocols for Epic KAN-420 are fully verified and approved.

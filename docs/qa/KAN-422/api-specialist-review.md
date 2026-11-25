# API Specialist & Security Review: KAN-422

## Ticket Reference
- **Ticket ID**: `KAN-422` (`[KB-SETTINGS-EPIC-PHASE2-SLICE4] Ops, Backups, Diagnostics & Link Auditor Simplification & Hardening`)
- **Reviewer Persona**: API & Security Architect (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Branch**: `feat/KAN-422-slice4-ops-simplify`
- **Base Commit**: `ea30b70a`
- **Head Commit**: `1f3c6969` (Feature commit `a03a20b3`)
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. Executive Summary & Verification Objective

Ticket `KAN-422` completes Phase 2 Simplification for Slice 4 (Operations, Backups, Migration Imports, Diagnostics, and Link Auditor). It eliminates disconnected/orphan form controls from migration importers, wires real user mapping payloads into import dry-run and execution routes, eliminates fake latency simulation in WebSocket diagnostics, standardizes standalone database telemetry on PostgreSQL 16 (Unix domain socket `/var/run/postgresql`), hardens standalone backups with the canonical `.kbbak` format (KBBAK1 AES-256-GCM), and migrates all 11 raw browser `fetch` calls to `apiFetch` for seamless CSRF and WebSudo AAL2 step-up replay (KAN-404).

This review specifically audits:
1. **API Contract & Payload Wiring**: Proper typing and validation of `user_map` within `PlaneImportStudio.tsx` and `planeImportApi.ts`, verifying payloads match backend import schemas (`kanban/api/v1/admin/imports.py`).
2. **WebSudo AAL2 Step-Up & CSRF Protection**: Verification that all Slice 4 endpoints (`/api/v1/admin/standalone/*`, `/api/v1/admin/exports/portable`, `/api/v1/admin/imports/*`) route through `apiFetch` / `fetchStandalone`, preserving automatic 403 step-up modal dispatch and singleflight request replay.
3. **Diagnostics & Telemetry Integrity**: Verification of removal of fake 12/14/15 ms simulated ping latency in `AdminDiagnosticsStudio.tsx`, real WebSocket error states, and 7-class Link Auditor alignment.
4. **Standalone Backup Encryption & Security Invariants**: Validation of canonical `.kbbak` filename extension and header validation (`KBKP` envelope format), `FORCE ROW LEVEL SECURITY` enforcement, zero shell execution in backup streaming, and admin route protection (`require_admin_aal2`).
5. **Unit Test Coverage & Hygiene**: Achieving `>=95%` unit test coverage on all modified backend modules (`link_auditor.py`: 100%, `system_status.py`: 97%) with 0 warnings, and `>=95%` coverage on all modified web modules (99.56% statements, 95.11% branches) with 0 errors across 96 tests.

---

## 2. API Architecture & Security Audit

### A. Migration Import Wiring & Schema Integrity
- **User Mapping Validation (`PlaneImportStudio.tsx`)**:
  - Replaced unvalidated text with structured client-side JSON parser `parseUserMap(raw: string)` that enforces key-value string mappings.
  - Returns informative error messages for non-object JSON payloads (`User mapping must be a JSON object mapping source identifiers to local usernames or emails`).
  - Passed as `user_map: Record<string, string> | undefined` in both `dry_run: true` (preview) and `dry_run: false` (execution) API payloads.
- **Orphan Control Pruning**:
  - Completely removed disconnected UI controls (`batchSize`, `conflictStrategy`, `preserveLegacyUuids`) that had no backend parameter bindings, preventing user confusion and phantom configurations.
  - Retained strict backward compatibility with multi-source import routers (`Plane`, `Jira`, `GitHub Issues`, `Linear`).

### B. WebSudo AAL2 Step-Up & CSRF Replay Architecture
- **Elimination of Raw Browser `fetch`**:
  - Migrated 9 endpoints in `StandaloneStatusPanel.tsx` (`/status`, `/backup/snapshots`, `/backup/now`, `/backup/verify`, `/backup/restore`, `/backup/schedule`, `/backup/history`, `/backup/download/{filename}`) to use `fetchStandalone` and `apiFetch`.
  - Migrated `/api/v1/admin/standalone/compose-export` in `ComposeExportTab.tsx` to `apiFetch`.
  - Migrated `/api/v1/admin/exports/portable` in `planeImportApi.ts` to `apiFetch` with automatic CSRF bootstrap retry on 403.
- **Security Invariant**:
  - By routing through `apiFetch`, any 403 response with `code: "AAL2_REQUIRED"` triggers `dispatchAal2StepUpIfRequired`, prompting the user for step-up authentication and replaying the in-flight mutation transparently without losing form state or file uploads.

### C. Standalone Engine & Backup Standardization
- **PostgreSQL 16 & Unix Socket Telemetry**:
  - Replaced outdated legacy copy referencing SQLite WAL mode with embedded PostgreSQL 16 on Unix domain socket (`/var/run/postgresql`).
  - Correctly surfaces active `FORCE ROW LEVEL SECURITY` status across all tenant tables.
  - Standardized Docker command snippet on canonical image slug `thumbs-up-kanban:latest`.
- **Canonical Backup Format (`.kbbak`)**:
  - Updated `create_standalone_backup` in `kanban/api/v1/system_status.py` to stream attachments with filename `kanban-backup-{timestamp}.kbbak`.
  - Maintained cryptographic verification: AES-256-GCM authenticated payload with SHA-256 manifest integrity checks and `STANDALONE_BACKUP_CREATED` activity ledger records.
  - Zero shell command execution: database dump and encryption occur entirely in-memory and via secure subprocesses without shell injection risk.

### D. Diagnostics Studio Telemetry Honesty
- **Removal of Fake Latency**:
  - Excised hardcoded synthetic latency fallback (`12/14/15 ms`) in `AdminDiagnosticsStudio.tsx:runWsProbe`.
  - Offline or failing WebSocket connections now honestly report `wsProbeState: 'error'`, setting badge styling to `admin-diag-badge--danger` with label `WS Disconnected / Error`.
  - Subnav cleanly passes `isServerAdmin={user?.is_server_admin}` to prevent privilege leakage.
  - Aligned summary strip with backend 7-class Link Auditor architecture.

---

## 3. Test Suite & Coverage Verification

### A. Python Backend Test Suite
Executed test suite under clean-DB `SAVEPOINT` isolation:
```bash
pytest kanban/tests/api/test_admin_imports.py kanban/tests/importer/test_multi_source_importers.py kanban/tests/resolve/test_legacy_key_aliases.py kanban/tests/api/test_admin_diagnostics.py kanban/tests/api/test_admin_link_auditor.py kanban/tests/api/test_system_status.py -v --cov=kanban/api/v1/admin/link_auditor --cov=kanban/api/v1/system_status --cov-report=term-missing
```
**Results**:
- 47/47 passed in 40.69s with **0 warnings** and 0 errors.
- Coverage:
  - `kanban/api/v1/admin/link_auditor.py`: **100%**
  - `kanban/api/v1/system_status.py`: **97%**
  - Total: **97%** (exceeds `>=95%` gate).

### B. Frontend Vitest Suite
Executed Vitest suite with v8 coverage:
```bash
pnpm vitest run src/features/admin-imports/__tests__/planeImportApi.test.ts src/features/standalone/__tests__/ComposeExportTab.test.tsx src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx src/features/admin/LinkAuditorStudio.test.tsx src/features/admin/AdminDiagnosticsStudio.test.tsx src/features/standalone/__tests__/StandaloneStatusPanel.test.tsx --coverage
```
**Results**:
- 96/96 passed across all 6 test suites in 5.20s.
- Coverage on touched Slice 4 modules:
  - Statements: **99.56%**
  - Branches: **95.11%** (exceeds `>=95%` gate)
  - Functions: **99.37%**
  - Lines: **99.70%**

### C. Build & Hygiene
- `ruff check .`: All checks passed.
- `mypy`: 678 files checked, 0 errors.
- `scripts/check_no_dashes.py --all`: 0 violations across all files.
- `pnpm typecheck`: Clean TypeScript compilation.
- `pnpm lint`: 0 warnings.
- `pnpm build`: Clean production build (1.26s).

---

## 4. Final Verdict & Sign-Off

**`APPROVED`**

The Slice 4 refactoring in `KAN-422` meets all security, architectural, and test quality gates. Disconnected controls have been removed, API communication is fully CSRF- and WebSudo-protected, telemetry reflects ground truth, and comprehensive tests validate all positive and negative paths with zero warnings.

# Message to Reality-Checker: KAN-421 Forensic QA Audit (Round 1 Remediation)

## Ticket Overview
- **Ticket ID:** `KAN-421` (`[SLICE-4-P1][KB-OPS-AUDIT] Phase 1: Migration Import, Backups/Promotion, Diagnostics & Link Auditor Setting Inventory & Audit`)
- **Parent Epic:** `KAN-420` (`[EPIC][SLICE-4-OPS-BACKUPS-IMPORTS]`)
- **Downstream Ticket:** `KAN-422` (`[SLICE-4-P2][KB-OPS-SIMPLIFY]`)
- **Git Branch:** `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`, base branch `fix/KAN-421-rc1`)
- **Reality Checker Gate Status:** Pending Clean-Room Reality-Checker re-audit

---

## Deliverables Summary

1. **`docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md`:**
   - **Complete Setting-by-Setting Inventory:** Audits 100% of UI controls and backend target endpoints across all 12 Slice-4 target files (`PlaneImportStudio.tsx`, `planeImportApi.ts`, `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, `AdminDiagnosticsStudio.tsx`, `LinkAuditorStudio.tsx`, `admin/imports.py`, `admin/exports.py`, `admin/diagnostics.py`, `admin/link_auditor.py`, `system_status.py`, `system.py`).
   - **Inventory Tables & Disposition Counts (96 items total):**
     - **Table 1 (Frontend UI Controls - 68 items):** 46 KEEP, 19 SIMPLIFY, 3 CUT (`batchSize`, `conflictStrategy`, `preserveLegacyUuids`).
     - **Table 2 (Backend Target Files - 28 items):** 26 KEEP, 2 SIMPLIFY (`admin/link_auditor.py:61` docstring drift and `system_status.py:274,341` `.kbkp` drift), 0 CUT.
     - **Combined Dispositions (96 items):** 72 KEEP, 21 SIMPLIFY, 3 CUT.
   - **Simplification Proposals & Focus Areas:**
     - 4-Source Migration Import Studio: unambiguous `CUT` dispositions for orphan disconnected controls (`batchSize`, `conflictStrategy`, `preserveLegacyUuids`); wires disconnected `userMappingJson` into `user_map`; migrates raw `fetch` in `planeImportApi.ts` line 73 (`downloadPortableExport`) to `apiFetch`.
     - Standalone vs Multi-Container & Encrypted Backups: unifies `.kbbak` as canonical extension with AES-256-GCM and `KBBAK1` framing while retaining legacy `.kbkp` support; removes outdated SQLite copy in favor of embedded PostgreSQL 16; fixes image slug drift (`kanban:latest` -> `thumbs-up-kanban:latest` at lines 266, 703).
     - Raw `fetch` to `apiFetch` in `StandaloneStatusPanel.tsx`: maps all 9 endpoints (across 7 unique routes plus line 950 `<a href>`) and `ComposeExportTab.tsx` (line 35) and `planeImportApi.ts` (line 73) to `apiFetch` for automatic CSRF, correlation ID, and `KAN-404` WebSudo sliding-window replay (11 raw calls total).
     - Critical Admin Diagnostics WS Probe Simulation Fix: flags `AdminDiagnosticsStudio.tsx:316-335` where `runWsProbe` silently fakes `wsProbeState('connected')` with hardcoded 12/14/15 ms RTT on `onerror`, timeout, and `catch`.
     - Copy and Docstring Drift: fixes 6-class vs 7-class drift in `AdminDiagnosticsStudio.tsx:493` and `admin/link_auditor.py:61` to match authoritative 7 classes.
     - Anti-Enumeration System Status Split: documents `GET /system/status` vs `GET /admin/standalone/status` split with `use_master_kek` support.
   - **Phase 2 (`KAN-422`) File-Scoped Action Checklist:** Fully updated with all remediation items and deduplicated against `KAN-404` and `KAN-397`.
   - **Phase 3 (`KAN-423`) Credential & Container Checklist:** Zero-mutation guard for `192.168.1.101` / `k.hackedyour.info`, isolated container setup, test bundles, and key material.

2. **Validation & Test Results:**
   - `docs/qa/KAN-421/unit-test-results.txt`: Confirms 0 forbidden Unicode em/en-dashes and verifies 18 / 18 cited repository paths exist on disk.
   - `docs/qa/KAN-421/build-check.txt`: Confirms positional and global `scripts/check_no_dashes.py` passes with exit code 0 and working tree has zero source-code mutations.
   - `docs/qa/KAN-421/git-diff.patch`: Cleanly generated against `01-audit-and-cuts.md` ONLY (`git diff e975ab96 -- docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md`).

3. **Screenshots:**
   - `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-422 and KAN-423)`.

4. **Handoff Packet Comments:**
   - Posted updated `## Phase 1 Handoff Packet (Rev 2)` via `kanban` MCP `add_comment` to both `KAN-420` (comment ID `KAN-420#c-01a2115c`) and `KAN-422` (comment ID `KAN-422#c-01a2115c`).

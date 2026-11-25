# Message to Reality-Checker: KAN-421 Forensic QA Audit

## Ticket Overview
- **Ticket ID:** `KAN-421` (`[SLICE-4-P1][KB-OPS-AUDIT] Phase 1: Migration Import, Backups/Promotion, Diagnostics & Link Auditor Setting Inventory & Audit`)
- **Parent Epic:** `KAN-420` (`[EPIC][SLICE-4-OPS-BACKUPS-IMPORTS]`)
- **Downstream Ticket:** `KAN-422` (`[SLICE-4-P2][KB-OPS-SIMPLIFY]`)
- **Git Branch:** `docs/KAN-421-slice4-audit` (branched from `main` at commit `2673a4c9`)

---

## Deliverables Summary

1. **`docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md`:**
   - **Complete Setting-by-Setting Inventory Table:** Audits 100% of UI controls, labels, options, defaults, validation rules, and backend bindings across all Slice-4 files (`PlaneImportStudio.tsx`, `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, `AdminDiagnosticsStudio.tsx`, `LinkAuditorStudio.tsx`, and `admin/imports.py`, `admin/exports.py`, `admin/diagnostics.py`, `admin/link_auditor.py`, `system_status.py`, `system.py`).
   - **Simplification Proposals & Focus Areas:**
     - 4-Source Migration Import Studio: wires orphan `userMappingJson` into `user_map`, cuts/simplifies disconnected batching and strategy dials.
     - Standalone vs Multi-Container & Encrypted Backups: unifies `.kbbak` as canonical extension with AES-256-GCM and `KBBAK1` framing while retaining legacy `.kbkp` support; removes outdated SQLite copy in favor of embedded PostgreSQL 16.
     - Raw `fetch` to `apiFetch` in `StandaloneStatusPanel.tsx`: maps all 9 endpoints to `apiFetch` for automatic CSRF, correlation ID, and `KAN-404` WebSudo sliding-window replay.
     - 5-Network Compose Export options: multi-container vs standalone Compose specifications and secret-free `.env.example`.
     - Admin Diagnostics & Telemetry: live WebSocket `/ws` ping and PostgreSQL LISTEN/NOTIFY latency probes.
     - Universal Object Graph Link Auditor & Purger: 7 invalidity classes, batch purge, mandatory 10-character justification gate, and immutable Activity Ledger provenance.
   - **Phase 2 (`KAN-422`) File-Scoped Action Checklist:** Deduplicated against `KAN-404` (WebSudo) and `KAN-397` (Migration Import Studio rename).
   - **Phase 3 (`KAN-423`) Credential & Container Checklist:** Zero-mutation guard for `192.168.1.101` / `k.hackedyour.info`, isolated container setup, test bundles, and key material.

2. **Validation & Test Results:**
   - `docs/qa/KAN-421/unit-test-results.txt`: Confirms 0 forbidden Unicode em/en-dashes and verifies 100% of cited repository paths exist on disk.
   - `docs/qa/KAN-421/build-check.txt`: Confirms global `scripts/check_no_dashes.py --all` passes with 0 violations and working tree has zero source-code mutations.

3. **Screenshots:**
   - `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-422 and KAN-423)`.

4. **Handoff Packet Comments:**
   - Posted `## Phase 1 Handoff Packet: slice-4-ops-backups-imports (P1 -> P2)` via `kanban` MCP `add_comment` to both `KAN-420` and `KAN-422`.

# API Specialist Review & Verification: KAN-421

- **Ticket ID:** KAN-421 (`[SLICE-4-P1][KB-OPS-AUDIT] Phase 1: Migration Import Studio, Standalone Backups/Promotion, Diagnostics & Link Auditor Setting Inventory & Technical Audit`)
- **Reviewer Persona:** Senior Backend & API Security Architect (`@api-spec`)
- **Target Surfaces:** Slice 4 Backend Wiring & Setting Inventory Audit (`docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md`)
- **Audit Date:** 2026-11-25
- **Verdict:** APPROVED (Zero API Contract Regressions; 100% Backend Wiring Traceability Verified)

---

## 1. Scope & Backend Topology Audit

A comprehensive forensic audit of the Slice 4 setting inventory and technical audit document (`docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md`) was performed against all relevant backend routers, services, and diagnostic probes:
- `kanban/api/v1/admin/imports.py`:
  - `POST /api/v1/admin/imports/{source}`: Correctly inventoried; verifies multi-source parsers (`plane`, `jira`, `github`, `linear`), dry-run simulation mode, and atomic database transaction boundary.
  - Identifies orphan frontend state `userMappingJson` to be properly wired into backend `user_map: dict[str, str]` in Phase 2.
- `kanban/api/v1/admin/exports.py`:
  - `POST /api/v1/admin/exports/portable`: Correctly mapped; verifies streaming deterministic `.tar.gz` archive export of workspace entities, JSON manifests, and CAS attachments with SHA-256 integrity.
- `kanban/api/v1/admin/diagnostics.py`:
  - `GET /api/v1/admin/diagnostics`: Correctly mapped; audits 7 subsystems (database, migrations, outbox, workers, RLS policies, runners, caches) and scrubs credentials.
  - `POST /api/v1/admin/diagnostics/probes/realtime`: Correctly mapped; verifies active `/ws` ping and PostgreSQL `LISTEN`/`NOTIFY` roundtrip latency.
- `kanban/api/v1/admin/link_auditor.py`:
  - `POST /api/v1/admin/object-links:audit`: Correctly mapped; tallies all 7 relational invalidity classes across Universal Object Graph links without locking tables.
  - `POST /api/v1/admin/object-links:purge`: Correctly mapped; enforces mandatory 10-character justification, deletes invalid links, and logs immutable Activity Ledger entries.
- `kanban/api/v1/system_status.py` & `kanban/api/v1/system.py`:
  - Standalone single-container operations: status, disk metrics, encrypted backups (`.kbbak` framing with PBKDF2/AES-256-GCM), automated schedules, and 2-stage destructive database restore.
  - Correctly details migration from raw `fetch` to `apiFetch` in `StandaloneStatusPanel.tsx` to automatically inherit `KAN-404` WebSudo sliding-window replay.

---

## 2. API Contract & Security Invariant Verification

1. **Setting-by-Setting Mapping Parity:**
   Every administrative control identified in the inventory table maps to an authentic backend endpoint, diagnostic probe, or backup utility. No fabricated routes or invalid schemas exist in the specification.
2. **Security & Boundary Invariants:**
   - 2-stage confirmation tokens with mandatory justification reason for destructive link purging and standalone restores are strictly maintained.
   - All diagnostic configuration dumps scrub passwords, KEK/DEK keys, and session secrets before returning responses.
   - `bare_mirror_ro` and SSRF validation for remote git endpoints are preserved.
   - Traceability to downstream tasks cleanly isolates Phase 2 implementation (`KAN-422`) from KAN-404 (WebSudo) and KAN-397 (Studio rename).

---

## 3. Verdict

**APPROVED.** The Slice 4 Phase 1 audit is technically rigorous, security-focused, and provides an authoritative foundation for Phase 2 implementation.

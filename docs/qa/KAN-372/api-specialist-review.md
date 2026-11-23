# API Specialist Review & Verification: KAN-372

- **Ticket ID:** KAN-372
- **Reviewer Persona:** Senior Backend & API Architect (`@backend-architect`)
- **Target Surfaces:** REST Export Endpoints (`POST /api/v1/projects/{project_ref}/issues/export`), Report Templates (`/api/v1/reports/templates`), Request Payload Boundaries, and Client Wire Invariants
- **Audit Date:** 2026-11-23
- **Verdict:** APPROVED (Zero REST or MCP Contract Deviations; Request Payload and Wire Invariants 100% Preserved)

---

## 1. Scope & System Topology Audit

A comprehensive forensic audit of all route and component modifications under KAN-372 was conducted:
- **Modified Components & API Payloads:**
  - `kanban/web/src/features/views/CsvImportExportModal.tsx`:
    - Extended `CsvImportExportModalProps` to accept `selectedIssueIds?: string[] | undefined` and `initialExportFormat?: 'csv' | 'zip_csv' | undefined`.
    - Wired `issue_ids: selectedIssueIds ?? null` into the JSON payload of `POST /api/v1/projects/{project_ref}/issues/export` and `/api/v1/workspaces/{workspace_ref}/issues/export`.
    - Verified strict schema parity with backend `IssueExportRequest` (`issue_ids: list[str] | None = Field(default=None)` in `kanban/api/v1/issue_csv.py`), which supports filtering exported rows by specific issue UUIDs or key sequence identifiers.
    - Synchronized `initialExportFormat` cleanly on mount and prop changes without cascading render effects.
  - `kanban/web/src/features/drawer/IssueSurface.tsx`:
    - Integrated `CsvImportExportModal` and `ReportExportModal` into the issue surface rendering hierarchy.
    - Wired single-issue scoping: `selectedIssueIds={[currentIssue.id ?? currentIssue.key]}`.
    - Preserved existing route and realtime event contracts: `useIssueSurfaceRoute`, `qk.issue`, `fetchComments`, and `patchIssue`.
  - `kanban/web/src/features/views/__tests__/CsvImportExportModal.test.tsx`:
    - Added unit test assertions verifying `issue_ids` transmission in the HTTP POST body and format synchronization.
  - `kanban/web/src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx`:
    - Added integration tests covering modal launch and parameter binding for CSV, AES-256 ZIP, and Report templates.

Zero backend Python files, database migration schemas, or MCP tool definitions required modification because the backend `IssueExportRequest` Pydantic model already defined `issue_ids: list[str] | None`.

---

## 2. Protocol, Routing, and Data Invariant Verification

1. **REST API Endpoint Contracts:**
   - The export request to `POST /api/v1/projects/{project_ref}/issues/export` transmits valid JSON with format, zip_password, search query, filter IDs, and `issue_ids`.
   - Single-issue export filters the export query strictly to the target issue ID via `Issue.id.in_(...)` or sequence ID, preventing unauthorized bulk data exfiltration.
2. **Report Template API Contracts:**
   - `ReportExportModal` correctly receives `selectedIssueIds={[currentIssue.id ?? currentIssue.key]}` and `projectKey={resolvedProjectForAux}` to invoke `/api/v1/reports/templates` and `/api/v1/reports/generate`.
3. **Data Integrity & Governance:**
   - Both CSV and AES-256 encrypted ZIP exports respect server-side export governance checks (`_check_export_governance`) and CSRF token transmission (`X-CSRF-Token`).
   - Formula injection sanitization and lone surrogate rejection remain fully enforced on the wire.

---

## 3. Specialist Sign-Off

The changes for KAN-372 cleanly fulfill all API integration requirements, preserving strict wire compatibility, Pydantic schema validation, and security invariants. Status: APPROVED.

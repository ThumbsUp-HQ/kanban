# Slice 4: Migration Import Studio, Standalone Backups/Promotion, Diagnostics & Link Auditor
## Phase 1 Read-Only Inventory and Simplification Audit (`KAN-421`)

- **Author:** `s4-p1-rc1` (Swarm Agent)
- **Target Branch:** git branch `fix/KAN-421-rc1` (created from `main`)
- **Parent Epic:** `KAN-420` (`[EPIC][SLICE-4-OPS-BACKUPS-IMPORTS]`)
- **Downstream Phase Tickets:** `KAN-422` (Phase 2 UI Simplification & Wiring), `KAN-423` (Phase 3 Live Workouts), `KAN-424` (Phase 4 Wiki Documentation)
- **Requirement Traceability:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 2 (System Topology & Multi-Container Architecture)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 12 (Universal Object Graph & Invalid Link Auditor)
  - `docs/PROMOTION_AND_BACKUP.md` (Production Promotion & Encrypted Backup Runbook)
- **Zero Source-Code Mutations:** Phase 1 is strictly read-only audit and markdown handoff.

---

### Executive Summary

Slice 4 encapsulates all administrative day-2 operations across the platform:
1. Multi-source migration importing from Plane, Jira, GitHub Issues, and Linear.
2. Deterministic portable workspace bundle exporting (`.tar.gz`).
3. Single-container standalone health, encrypted AES-256-GCM backups (`.kbbak`), automated backup schedules, and 2-stage destructive database restore.
4. Production Docker Compose export and promotion runbooks.
5. Unified administrative diagnostics across 7 core subsystems with live WebSocket and PostgreSQL pub/sub broker probes.
6. Universal Object Graph Link Auditor and Purger enforcing relational integrity across 7 invalidity classes with mandatory justification and audit ledger recording.

This audit establishes a complete setting-by-setting inventory across all 11 Slice-4 frontend and backend files plus `planeImportApi.ts`:
- Frontend (6 files): `PlaneImportStudio.tsx`, `planeImportApi.ts`, `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, `AdminDiagnosticsStudio.tsx`, `LinkAuditorStudio.tsx`.
- Backend (6 files): `kanban/api/v1/system.py`, `kanban/api/v1/admin/imports.py`, `kanban/api/v1/admin/exports.py`, `kanban/api/v1/admin/diagnostics.py`, `kanban/api/v1/admin/link_auditor.py`, `kanban/api/v1/system_status.py`.

Key findings identified in this audit:
1. Orphan and unmapped controls in `PlaneImportStudio.tsx` (`batchSize`, `conflictStrategy`, `preserveLegacyUuids`) are assigned unambiguous `CUT` dispositions.
2. Disconnected `userMappingJson` state in `PlaneImportStudio.tsx` must be wired to backend `user_map`.
3. Terminology and extension drift: `.kbkp` vs canonical `.kbbak` in `system_status.py:274,341`.
4. Outdated SQLite copy in `StandaloneStatusPanel.tsx:778-784` must reflect embedded PostgreSQL 16.
5. Docker image slug drift in `StandaloneStatusPanel.tsx:266,703` (`kanban:latest` vs canonical `thumbs-up-kanban:latest`).
6. Raw `fetch()` migration across 11 calls: 9 calls across 7 endpoints in `StandaloneStatusPanel.tsx` (plus direct `<a href>` at line 950), 1 in `ComposeExportTab.tsx:35`, and 1 in `planeImportApi.ts:73` (`downloadPortableExport`).
7. Critical simulation mock finding in `AdminDiagnosticsStudio.tsx:316-335`: `runWsProbe` silently fakes `wsProbeState('connected')` with hardcoded 12/14/15 ms RTT on `onerror`, timeout, and `catch`.
8. Copy and docstring drift: 6-class vs 7-class invalidity copy in `AdminDiagnosticsStudio.tsx:493` and `admin/link_auditor.py:61` vs authoritative 7 classes.
9. Backend anti-enumeration split in `system_status.py`: unauthenticated/general `GET /system/status` redacts sensitive mount points and local LLM host, while `GET /admin/standalone/status` requires `require_admin_aal2`.

---

### Deduplication and Dependency Boundaries

- **`KAN-404` (Global Sliding-Window WebSudo & Singleflight Replay):** Owns the global WebSudo session timer, idle refresh, and `apiFetch` in-place modal retry. Slice 4 Phase 2 will migrate all raw `fetch` calls in `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, and `planeImportApi.ts` to `apiFetch` so that administrative actions automatically inherit `KAN-404` transparent replay.
- **`KAN-397` (Migration Import Studio Rename):** Owns renaming page headings, Topbar menu links, and subnav tabs from "Plane Migration Import Studio" to "Migration Import Studio". Slice 4 Phase 1 and Phase 2 focus on controls, data mapping, and backend wiring.

---

### Complete Setting-by-Setting Inventory Table

#### 1. Frontend UI Controls Inventory

| Screen / Drawer | Setting Label & Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Source Selector (`source`) | Buttons: `plane`, `jira`, `github`, `linear` | Switches the active migration source parser and target schema mapping. | Fully Wired: routes to `/api/v1/admin/imports/{source}` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Input Mode (`inputMode`) | Buttons: `upload` vs `paste` | Toggles between uploading an export bundle file and pasting raw JSON/CSV text. | Fully Wired: client-side mode toggle | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | File Dropzone (`file-input`) | File Picker (`.json`, `.csv`) | Ingests export bundle file from disk into client memory. | Fully Wired: reads via FileReader to `bundle_data` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Paste Textarea (`paste-textarea`) | Textarea (JSON or CSV) | Ingests raw export text directly into client memory. | Fully Wired: parsed into `bundle_data` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Target Workspace Slug (`target-ws-slug-input`) | Text Input (Optional) | Specifies an alternative target workspace slug instead of the caller active workspace. | Fully Wired: maps to `req.workspace_slug` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Target Project Key (`target-project-key-input`) | Text Input (Optional, default JIRA/GH/LIN) | Specifies the project prefix key under which imported issues will be grouped. | Fully Wired: maps to `req.project_key` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Advanced Import Options (`advanced-import-options`) | Collapsible Accordion | Groups tuning parameters for batching, UUID preservation, conflicts, and user mapping. | Fully Wired: UI container component | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Import Batch Size (`import-batch-size-input`) | Number Input (10 to 1000, default 100) | Sets the number of database entities processed per transaction batch. | Orphan / Disconnected: NOT present in backend schemas (`AdminPlaneImportRequest` / `AdminGenericImportRequest`) | `CUT` (Remove from UI; ingestion engine batches transactions deterministically) |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Conflict Resolution Strategy (`import-conflict-strategy-select`) | Dropdown: `skip`, `overwrite`, `rename` | Dictates behavior when an entity identifier matches an existing record. | Orphan / Disconnected: NOT present in backend schemas | `CUT` (Remove from UI; platform enforces idempotent entity upsert with key stability) |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Preserve Legacy UUIDs (`import-preserve-uuids-checkbox`) | Checkbox (default true) | Controls whether source UUIDs are preserved for deterministic migration idempotency. | Orphan / Disconnected: NOT present in backend schemas | `CUT` (Remove from UI; UUID preservation is a mandatory platform invariant) |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Custom User Mapping JSON (`import-user-mapping-json`) | Textarea (JSON object) | Maps source user IDs and email handles to local workspace user handles. | Disconnected in UI: Backend supports `user_map`, but frontend never includes it in payload | `SIMPLIFY` (Wire `user_map` into payload in `handleRunDryRun` and `handleExecuteImport`) |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Preview Dry-Run Diff Button (`run-dry-run-btn`) | Action Button | Executes simulation without database mutations and renders diff metrics. | Fully Wired: `POST /api/v1/admin/imports/{source}` with `dry_run: true` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Execute Live Import Button (`execute-import-btn`) | Action Button | Commits the validated import transaction to the persistent universal object graph. | Fully Wired: `POST /api/v1/admin/imports/{source}` with `dry_run: false` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Back to Input Button (`back-to-input-btn`) | Action Button | Resets the preview stage back to the input selection screen. | Fully Wired: client-side stage reset | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Import Another Bundle Button (`import-another-btn`) | Action Button | Resets execution state to allow importing an additional bundle. | Fully Wired: client-side stage reset | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Return to MCP Button (`return-admin-btn`) | Navigation Link (`/admin/mcp`) | Navigates back to the MCP & Governance studio. | Fully Wired: React Router link | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Export Workspace Slug (`export-workspace-slug-input`) | Text Input (Optional) | Specifies workspace slug to extract into a portable deterministic archive. | Fully Wired: maps to `req.workspace_slug` in `POST /api/v1/admin/exports/portable` | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Scrub Secrets Checkbox (`export-scrub-checkbox`) | Checkbox (default false) | Scrubs API tokens, secrets, and sensitive credentials from exported markdown text. | Fully Wired: maps to `req.scrub` in export API | `KEEP` |
| **Migration Import Studio** (`PlaneImportStudio.tsx`) | Download Portable Bundle Button (`export-download-btn`) | Action Button | Generates and downloads a deterministic `.tar.gz` archive with SHA-256 manifests. | Wired via `planeImportApi.ts:downloadPortableExport` using raw `fetch` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch` in `planeImportApi.ts`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Ephemeral Storage Alert | Alert Banner | Warns operator when container runs on overlayfs without a mounted persistent volume. | Fully Wired: derived from `status.persistent_volume` | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Copy Docker Run Command | Button | Copies the canonical persistent container run command to system clipboard. | Contains image slug drift (`kanban:latest` vs `thumbs-up-kanban:latest`) | `SIMPLIFY` (Update image slug to `thumbs-up-kanban:latest`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Persistent Volume Badge | Status Badge | Confirms persistent volume is active with filesystem type and mount path. | Fully Wired: derived from `status.data_mount_point` | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Formula Sandbox Card (Wasm) | Capability Card | Displays Tier-A WebAssembly deterministic script sandbox status (always active). | Fully Wired: client static indicator | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Process Sandbox Card (nsjail) | Capability Card | Displays Tier-B Linux namespace sandbox status (active vs optional in standalone). | Fully Wired: derived from `status.tier_b_sandbox_available` | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 1) | Advanced Technical Details | Collapsible Accordion | Displays runtime database engine, PRAGMA dials, and storage parameters. | Fully Wired container, but contains outdated SQLite copy | `SIMPLIFY` (Update SQLite copy to PostgreSQL 16 embedded engine) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Backup Passphrase (`backup-passphrase`) | Password Input (min 16 chars) | Passphrase used to derive AES-256-GCM encryption key via Argon2id / PBKDF2. | Wired via raw `fetch`: `POST /api/v1/admin/standalone/backup` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`, unify `.kbbak` extension) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Download Encrypted Backup Button | Action Button | Triggers server-side `pg_dump`, encrypts archive, and downloads `.kbbak` file. | Wired via raw `fetch`: `POST /api/v1/admin/standalone/backup` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`, ensure `.kbbak` filename parity) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Enable Automated Backups Checkbox | Checkbox | Toggles background cron worker for periodic automated database snapshots. | Wired via raw `fetch`: `PUT /api/v1/admin/standalone/backup-schedule` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Backup Interval (`schedule-interval`) | Number Input (1 to 168 hours) | Configures periodicity in hours between automated backup passes. | Wired via raw `fetch`: `PUT /api/v1/admin/standalone/backup-schedule` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Keep Latest Snapshots (`schedule-retention`) | Number Input (1 to 90 snapshots) | Configures maximum number of historical snapshots retained before automatic pruning. | Wired via raw `fetch`: `PUT /api/v1/admin/standalone/backup-schedule` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Save Schedule Button | Action Button | Persists updated automated backup schedule and retention limits to disk. | Wired via raw `fetch`: `PUT /api/v1/admin/standalone/backup-schedule` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Run Backup Now Button | Action Button | Triggers an immediate automated backup snapshot pass asynchronously. | Wired via raw `fetch`: `POST /api/v1/admin/standalone/backups/run-now` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Existing Snapshots Table | Data Table & Download Links | Displays list of on-disk server snapshots with size, timestamp, and download link. | Wired via raw `fetch`: `GET /api/v1/admin/standalone/backups`, `<a href>` download link at line 950 | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Select Server Snapshot (`select-snapshot`) | Dropdown | Selects an existing on-disk backup snapshot to restore. | Wired: mutually exclusive with upload input | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Upload Backup File (`upload-backup-file`) | File Picker (`.kbbak`, `.kbkp`, `.dump`) | Uploads an external backup bundle from operator computer to restore. | Wired: mutually exclusive with server snapshot select | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Restore Passphrase (`restore-passphrase`) | Password Input (Optional) | Passphrase required to decrypt user-passphrase encrypted backup archives. | Wired via raw `fetch`: passed in verify and restore requests | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Step 1: Verify Backup Archive Button | Action Button | Validates cryptographic framing, GCM tag, and manifest without database mutations. | Wired via raw `fetch`: `POST /api/v1/admin/standalone/backup/verify` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Destructive Confirmation (`restore-confirm`) | Text Input (Exact string "RESTORE") | Mandatory safety gate preventing accidental database overwrite. | Fully Wired: client and server validation check | `KEEP` |
| **Standalone Status Panel** (`StandaloneStatusPanel.tsx` Tab 2) | Step 2: Restore Database Button | Action Button (Destructive) | Executes database restore, schema migration, and object link audit. | Wired via raw `fetch`: `POST /api/v1/admin/standalone/restore` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Compose Export Tab** (`ComposeExportTab.tsx` Tab 3) | Compose Mode Toggle (`composeMode`) | Buttons: `multi` vs `single` | Toggles between 5-network production stack and single-container standalone Compose spec. | Fully Wired: client mode toggle | `KEEP` |
| **Compose Export Tab** (`ComposeExportTab.tsx` Tab 3) | Download Compose YAML Button | Action Button | Downloads the selected `docker-compose.yml` or `docker-compose.standalone.yml`. | Wired via raw `fetch` at line 35: `GET /api/v1/admin/standalone/compose-export` | `SIMPLIFY` (Migrate raw `fetch` to `apiFetch`) |
| **Compose Export Tab** (`ComposeExportTab.tsx` Tab 3) | Copy .env.example Button | Action Button | Copies production environment variable template with generated secrets to clipboard. | Wired: uses clipboard utility | `KEEP` |
| **Compose Export Tab** (`ComposeExportTab.tsx` Tab 3) | Promotion Runbook Checklist | Static Documentation Box | Outlines the 4-step promotion procedure from standalone to external PostgreSQL 16. | Static Markdown preview | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | WS Probe Badge (`ws-probe-badge`) | Status Badge | Displays live WebSocket connection status and roundtrip latency in milliseconds. | Fake simulation mock in lines 316-335 | `SIMPLIFY` (Remove simulated fake RTT and report real connection failure) |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Run WS Ping Button (`run-ws-ping-btn`) | Action Button | Opens client WebSocket to `/ws`, sends ping frame, and calculates roundtrip latency. | Fake simulation mock in lines 316-335 | `SIMPLIFY` (Fix `runWsProbe` to stop faking 12/14/15 ms on error/timeout/catch) |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Refresh Diagnostics Button (`refresh-diagnostics-btn`) | Action Button | Refetches consolidated diagnostics across all 7 subsystems. | Fully Wired: `apiFetch('GET', '/api/v1/admin/diagnostics')` | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Summary Strip Cards (4 Cards) | Telemetry Strip | Displays at-a-glance status for Realtime, Docker, Configuration, and Object Links. | Fully Wired: Card 4 has copy drift ("6-class Link Auditor") | `SIMPLIFY` (Update Card 4 copy to "7-class Link Auditor") |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Diagnostics Tab Navigation | Tabs: `all`, `health`, `realtime`, `runtime`, `config`, `links` | Filters displayed diagnostics sections for focused administrative inspection. | Fully Wired: client tab state | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Test PG LISTEN/NOTIFY Broker (`run-pg-probe-btn`) | Action Button | Triggers backend self-test verifying PostgreSQL LISTEN/NOTIFY latency roundtrip. | Fully Wired: `POST /api/v1/admin/diagnostics/probes/realtime` via `apiFetch` | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | 7 Subsystems Health Cards | Status Grid | Displays health, descriptions, and operational metrics for 7 core subsystems. | Fully Wired: maps to `diag.subsystems` | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Storage Volumes Table | Data Table | Reports existence, writability, free space, and capacity for persistent mount points. | Fully Wired: maps to `diag.storage.directories` | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Config Search Filter (`config-search-input`) | Text Input | Filters active configuration parameters by key, subsystem, or value string. | Fully Wired: client filter state | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Config Subsystem Filter (`config-subsystem-select`) | Dropdown | Filters active configuration parameters by target subsystem domain. | Fully Wired: client filter state | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Copy Safe JSON Summary Button (`copy-config-btn`) | Action Button | Copies sanitized configuration dump with zero secret leakage to system clipboard. | Fully Wired: clipboard utility | `KEEP` |
| **Admin Diagnostics Studio** (`AdminDiagnosticsStudio.tsx`) | Raw Config Dump Accordion | Collapsible Accordion | Provides complete raw JSON configuration dump for debugging. | Fully Wired: `AdvancedSection` wrapper | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Run Integrity Scan Button (`run-scan-btn`) | Action Button | Scans all workspace object links and tallies flagged invalid links across 7 classes. | Fully Wired: `POST /api/v1/admin/object-links:audit` via `apiFetch` | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Documentation Link (`link-auditor-doc-link`) | Help Link | Links operator to authoritative Universal Object Graph and Link Auditor spec. | Fully Wired: `StudioDocLink` component | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Reason Metrics Cards (7 Cards) | Metric Cards & Quick Filters | Summarizes flagged links per reason code; clicking toggles table filter. | Fully Wired: maps to `REASON_DESCRIPTIONS` and scan results | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Audit Status Filter (`status-filter-{st}`) | Pill Buttons: `unpurged`, `purged`, `resolved`, `all` | Filters flagged link records by remediation lifecycle status. | Fully Wired: query parameter in `list_link_audits` | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Reason Filter Dropdown (`reason-select`) | Dropdown | Filters flagged link records by specific invalidity reason code. | Fully Wired: query parameter in `list_link_audits` | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Select All Checkbox (`select-all-checkbox`) | Checkbox | Selects or deselects all currently visible flagged link records for bulk purge. | Fully Wired: client selection Set | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Row Selection Checkbox (`checkbox-{id}`) | Checkbox | Selects individual flagged link record for purge. | Fully Wired: client selection Set | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Purge Selected Links Button (`purge-selected-btn`) | Action Button (Destructive) | Opens the audited purge confirmation modal for selected link IDs. | Fully Wired: modal trigger | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Row Inspect Button (`inspect-btn-{id}`) | Action Button | Opens the inspection drawer to examine frozen source, target, and link snapshots. | Fully Wired: drawer state | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Row Single Purge Button (`purge-single-btn-{id}`) | Action Button (Destructive) | Opens the audited purge confirmation modal scoped to a single link record. | Fully Wired: modal trigger | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Inspect Drawer (`inspect-drawer`) | Slide-over Drawer | Displays full JSON payloads of source, target, and link snapshots with entity keys. | Fully Wired: slide-over inspection view | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Purge Modal Justification (`purge-reason-input`) | Textarea (min 10 chars, max 500) | Enforces mandatory administrative justification before permitting destructive link purge. | Fully Wired: client validation rule (len >= 10) | `KEEP` |
| **Link Auditor Studio** (`LinkAuditorStudio.tsx`) | Confirm Purge Button (`confirm-purge-btn`) | Action Button (Destructive) | Executes audited purge, removes links from object graph, and logs immutable ledger. | Fully Wired: `POST /api/v1/admin/object-links:purge` via `apiFetch` | `KEEP` |

---

#### 2. Backend Target Files Inventory Table

| File Path | Endpoint & Method | Auth & Dependencies | Models & Parameters | 1-Sentence Plain-English Meaning | Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `kanban/api/v1/system.py` | `GET /system/about` | `Depends(get_principal)` | Response: `SystemAboutResponse` | Returns platform branding, Apache-2.0 license, doc URLs, and CycloneDX SBOM overview. | `KEEP` |
| `kanban/api/v1/system.py` | `GET /system/sbom` | `Depends(get_principal)` | Query: `download: bool = False`. Response: CycloneDX 1.5 JSON | Generates full dependency manifest; sets attachment header when `download=true`. | `KEEP` |
| `kanban/api/v1/system.py` | `GET /system/platform-summary` | Public (Unauthenticated) | Response: `PlatformSummaryResponse` | Exposes verified enterprise capabilities across all 4 pillars and competitive parity matrix. | `KEEP` |
| `kanban/api/v1/system.py` | `GET /system/summary` | Public (Unauthenticated) | Response: `PlatformSummaryResponse` | Hidden alias (`include_in_schema=False`) for `/system/platform-summary`. | `KEEP` |
| `kanban/api/v1/system.py` | `GET /system/skills` | Public (Unauthenticated) | Response: `LlmsSkillsCatalogResponse` | Serves public `/llms.txt` skill descriptors and onboarding prompt for AI agents. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/imports/plane` | Server Admin + AAL2 (`Depends(require_admin_aal2)`) | Request: `AdminPlaneImportRequest(bundle_name, bundle_data, dry_run, user_map, workspace_slug)`. Response: `ImportDiffReport` | Validates, dry-runs, or commits Plane export bundle with deterministic sequence continuity. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/import/plane/preview` | Server Admin + AAL2 | Alias for `/admin/imports/plane` (`include_in_schema=False`) | Legacy preview route retained for backward compatibility with migration tooling. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/import/plane/execute` | Server Admin + AAL2 | Alias for `/admin/imports/plane` (`include_in_schema=False`) | Legacy execute route retained for backward compatibility with migration tooling. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/imports/jira` | Server Admin + AAL2 | Request: `AdminGenericImportRequest(bundle_name, bundle_data, project_key, dry_run, user_map, workspace_slug)`. Response: `ImportDiffReport` | Ingests Jira JSON exports into target project with user mapping and status reconciliation. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/imports/github` | Server Admin + AAL2 | Request: `AdminGenericImportRequest`. Response: `ImportDiffReport` | Ingests GitHub Issues JSON bundles with milestone and label preservation. | `KEEP` |
| `kanban/api/v1/admin/imports.py` | `POST /admin/imports/linear` | Server Admin + AAL2 | Request: `AdminGenericImportRequest`. Response: `ImportDiffReport` | Ingests Linear JSON or CSV bundles into universal object graph entities. | `KEEP` |
| `kanban/api/v1/admin/exports.py` | `POST /admin/exports/portable` | Server Admin + AAL2 | Request: `AdminPortableExportRequest(workspace_slug, scrub)`. Response: Binary `.tar.gz` | Generates deterministic portable workspace archive with SHA-256 manifest and secret scrubbing. | `KEEP` |
| `kanban/api/v1/admin/diagnostics.py` | `GET /admin/diagnostics` (and `/`) | Workspace/Server Admin + AAL2 | Response: `AdminDiagnosticsResponse` | Consolidates operational health and telemetry metrics across 7 core subsystems. | `KEEP` |
| `kanban/api/v1/admin/diagnostics.py` | `POST /admin/diagnostics/probes/realtime` | Workspace/Server Admin + AAL2 | Response: `RealtimeProbeResponse` | Tests PostgreSQL LISTEN/NOTIFY pub/sub roundtrip and database query latency. | `KEEP` |
| `kanban/api/v1/admin/link_auditor.py` | `POST /admin/object-links:audit` | Workspace/Server Admin + AAL2 | Response: `LinkAuditScanResponse`. Line 61 docstring drift says "across 6 classes" | Scans graph links and returns invalidity counts across 7 classes (fix docstring drift). | `SIMPLIFY` (Fix docstring to state 7 classes) |
| `kanban/api/v1/admin/link_auditor.py` | `GET /admin/object-links/audits` | Workspace/Server Admin + AAL2 | Query: `reason_code`, `status_filter` (alias `status`), `limit: int = 50` (ge=1, le=100), `cursor: str or None = None`. Response: `LinkAuditListResponse` | Retrieves keyset-paginated snapshots of flagged invalid object links. | `KEEP` |
| `kanban/api/v1/admin/link_auditor.py` | `POST /admin/object-links:purge` | Workspace/Server Admin + AAL2 | Request: `LinkPurgeRequest(audit_ids, reason: len >= 10)`. Response: `LinkPurgeResponse` | Destructively purges flagged invalid links and emits immutable Activity Ledger audit records. | `KEEP` |
| `kanban/api/v1/system_status.py` | `GET /system/status` | `Depends(get_principal)` | Response: `SystemStatusResponse` | Anti-enumeration split: redacts mount points and local LLM host for non-server admins. | `KEEP` |
| `kanban/api/v1/system_status.py` | `GET /admin/standalone/status` | Server Admin + AAL2 (`Depends(require_admin_aal2)`) | Response: `SystemStatusResponse` | Anti-enumeration split: returns full unredacted topological and storage details for admins. | `KEEP` |
| `kanban/api/v1/system_status.py` | `POST /admin/standalone/backup` | Server Admin + AAL2 | Request: `StandaloneBackupRequest(passphrase, use_master_kek)`. Response: Binary stream. Lines 274,341 docstring and filename drift (`.kbkp`) | Generates AES-256-GCM encrypted database backup; accepts master KEK or passphrase >= 16 chars. | `SIMPLIFY` (Update filename to `.kbbak` and fix docstring drift) |
| `kanban/api/v1/system_status.py` | `GET /admin/standalone/compose-export` | Server Admin + AAL2 | Response: `ComposeExportResponse` | Emits 5-network production and standalone Docker Compose YAML plus `.env.example`. | `KEEP` |
| `kanban/api/v1/system_status.py` | `GET /admin/standalone/backup-schedule` | Server Admin + AAL2 | Response: `BackupScheduleResponse` | Retrieves automated backup periodicity (hours), retention count, and schedule status. | `KEEP` |
| `kanban/api/v1/system_status.py` | `PUT /admin/standalone/backup-schedule` | Server Admin + AAL2 | Request: `BackupScheduleUpdateRequest(enabled, interval_hours >= 1, retention_count >= 1)` | Updates automated background backup schedule parameters. | `KEEP` |
| `kanban/api/v1/system_status.py` | `GET /admin/standalone/backups` | Server Admin + AAL2 | Response: `list[BackupFileItem]` | Lists available on-disk encrypted snapshot files with sizes and timestamps. | `KEEP` |
| `kanban/api/v1/system_status.py` | `POST /admin/standalone/backups/run-now` | Server Admin + AAL2 | Response: `dict[str, str]` | Triggers asynchronous automated backup snapshot pass on demand. | `KEEP` |
| `kanban/api/v1/system_status.py` | `GET /admin/standalone/backups/{filename}` | Server Admin + AAL2 | Path: `filename`. Response: Binary stream | Downloads specific on-disk snapshot archive with path traversal enforcement. | `KEEP` |
| `kanban/api/v1/system_status.py` | `POST /admin/standalone/backup/verify` | Server Admin + AAL2 | Request: multipart form (uploaded file) or JSON body (server snapshot name, passphrase, `use_master_kek`) | Cryptographically verifies backup header, manifest, and GCM authentication tag. | `KEEP` |
| `kanban/api/v1/system_status.py` | `POST /admin/standalone/restore` | Server Admin + AAL2 | Request: multipart or JSON body (passphrase, `use_master_kek`, `confirmation="RESTORE"`) | Destructively restores database from verified backup, runs migrations, and audits links. | `KEEP` |

---

### Simplification Proposals and Focus Areas

#### 1. Migration Import Studio (`PlaneImportStudio.tsx` & `planeImportApi.ts`)
- **Unambiguous Orphan Control Dispositions:**
  - `import-batch-size-input` (`batchSize`): `CUT`. Remove this disconnected number input from the UI. The backend importer automatically chunks transactions in optimal deterministic batches.
  - `import-conflict-strategy-select` (`conflictStrategy`): `CUT`. Remove this disconnected dropdown. The platform enforces idempotent upsert based on source entity identifiers and keys.
  - `import-preserve-uuids-checkbox` (`preserveLegacyUuids`): `CUT`. Remove this disconnected checkbox. UUID preservation is a mandatory platform architectural invariant for deterministic migration reproducibility.
- **Wire Disconnected `userMappingJson`:**
  - In `PlaneImportStudio.tsx` lines 219-224 (`handleRunDryRun`) and lines 251-256 (`handleExecuteImport`), the frontend maintains `userMappingJson` state but omits `user_map` from the request payload. In Phase 2, parse `userMappingJson` (defaulting to empty object `{}` on blank/invalid text) and pass `user_map: parsedUserMap` in both preview and execute payloads.
- **Raw `fetch` Migration in `planeImportApi.ts`:**
  - In `planeImportApi.ts` line 73, `downloadPortableExport` currently uses raw `window.fetch('/api/v1/admin/exports/portable', ...)`. In Phase 2, migrate to `apiFetch` with binary blob handling to inherit automated CSRF headers and centralized error processing.

#### 2. Standalone vs Multi-Container Mode & Encrypted Backup Parity
- **Terminology & Extension Parity (`.kbbak` vs `.kbkp`):**
  - Canonical encrypted backup format across `docs/PROMOTION_AND_BACKUP.md` and `kanban-ctl` is `.kbbak` using magic header `KBBAK1` with AES-256-GCM.
  - In `kanban/api/v1/system_status.py` lines 274 and 341, docstring and filename drift hardcode `.kbkp` (`filename = f"kanban-backup-{timestamp}.kbkp"`).
  - In Phase 2, update `system_status.py` to generate `kanban-backup-{timestamp}.kbbak` as canonical filename and fix the docstring, while maintaining backward-compatible verification and restore for legacy `.kbkp` files.
- **Docker Container Image Slug Drift:**
  - In `StandaloneStatusPanel.tsx` lines 266 and 703, the UI displays:
    `docker run -d -p 8080:8080 -v kanban_data:/var/lib/kanban/data kanban:latest`
  - Per repository branding standards and `GEMINI.md`, container image slugs must use `thumbs-up-kanban` (`thumbs-up-kanban:latest`).
  - In Phase 2, update copy at lines 266 and 703 to `thumbs-up-kanban:latest`.
- **Outdated SQLite Copy Cleanup:**
  - In `StandaloneStatusPanel.tsx` lines 778-784, the "Advanced Technical Details" section hardcodes `Database Storage Engine: SQLite 3.45 (WAL Mode)` and `PRAGMA journal_mode = WAL`.
  - In standalone mode, `👍kanban` runs embedded PostgreSQL 16 on a Unix domain socket (`/var/run/postgresql`), never SQLite.
  - In Phase 2, update this copy to reflect the genuine embedded PostgreSQL 16 engine, socket path, and `FORCE RLS` status.

#### 3. Complete Raw `fetch` to `apiFetch` Migration Across Slice 4 (11 Calls Total)
Currently, Slice 4 contains 11 raw `window.fetch()` calls across frontend files:
1. `kanban/web/src/features/standalone/StandaloneStatusPanel.tsx` (9 raw `fetch` calls across 7 endpoints):
   - Line 213: `fetch('/api/v1/admin/standalone/backup-schedule')`
   - Line 217: `fetch('/api/v1/admin/standalone/backups')`
   - Line 299: `fetch('/api/v1/admin/standalone/backup')`
   - Line 350: `fetch('/api/v1/admin/standalone/backup-schedule')`
   - Line 386: `fetch('/api/v1/admin/standalone/backups/run-now')`
   - Line 423: `fetch('/api/v1/admin/standalone/backup/verify')` (file upload)
   - Line 436: `fetch('/api/v1/admin/standalone/backup/verify')` (snapshot select)
   - Line 501: `fetch('/api/v1/admin/standalone/restore')` (file upload)
   - Line 514: `fetch('/api/v1/admin/standalone/restore')` (snapshot select)
   - Note: Line 950 also uses a direct download `<a href>` (`/api/v1/admin/standalone/backups/${s.filename}`).
2. `kanban/web/src/features/standalone/ComposeExportTab.tsx` (1 raw `fetch` call):
   - Line 35: `fetch('/api/v1/admin/standalone/compose-export')`
3. `kanban/web/src/features/admin-imports/planeImportApi.ts` (1 raw `fetch` call):
   - Line 73: `fetch('/api/v1/admin/exports/portable')` in `downloadPortableExport`

In Phase 2, migrate all 11 raw calls to `apiFetch` from `kanban/web/src/api/client.ts`. This ensures:
- Automatic CSRF header injection.
- Structured `ApiProblem` error parsing.
- Seamless compatibility with `KAN-404` sliding-window WebSudo and transparent request replay without losing modal or tab state.

#### 4. Critical Admin Diagnostics WS Probe Simulation Fix (`AdminDiagnosticsStudio.tsx`)
- In `AdminDiagnosticsStudio.tsx` lines 316-335, `runWsProbe` contains a fake simulation mock:
  ```ts
  sock.onerror = () => {
    // Fallback simulated probe if offline/test environment
    const elapsed = Math.round(performance.now() - start);
    setWsRtt(elapsed > 0 ? elapsed : 12);
    setWsProbeState('connected');
  };

  setTimeout(() => {
    if (sock.readyState === WebSocket.CONNECTING || sock.readyState === WebSocket.OPEN) {
      sock.close();
      if (wsProbeState === 'probing') {
        setWsRtt(14);
        setWsProbeState('connected');
      }
    }
  }, 1500);
  ```
  And on catch at line 333: `setWsRtt(15); setWsProbeState('connected')`.
- This silently fakes a successful WebSocket connection (`connected`) with hardcoded 12/14/15 ms latency when the probe fails, times out, or throws an error.
- In Phase 2, eliminate this mock simulation. The WebSocket probe must accurately report `disconnected` or `error` with clear operator feedback when the `/ws` endpoint cannot be reached.

#### 5. Copy and Docstring Drift: 6-Class vs 7-Class Universal Link Auditor
- Authoritative specification in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 12, `LinkAuditorStudio.tsx` lines 76-115, and `kanban/api/v1/schemas/link_auditor.py` defines **7 invalidity classes**:
  1. `DANGLING_SOURCE`
  2. `DANGLING_TARGET`
  3. `SOFT_DELETED_ENDPOINT`
  4. `ARCHIVED_POLICY_VIOLATION`
  5. `TYPE_MATRIX_VIOLATION`
  6. `CROSS_WORKSPACE_LEAK`
  7. `PERMISSION_SEVERED`
- Identified drift:
  - `AdminDiagnosticsStudio.tsx` line 493 displays `6-class Link Auditor & Purger embedded`.
  - `kanban/api/v1/admin/link_auditor.py` line 61 docstring states `Scan workspace object links and return aggregated invalidity counts across 6 classes.`
- In Phase 2, update both locations to accurately reference the 7 invalidity classes.

#### 6. Anti-Enumeration System Status Split (`system_status.py`)
- `kanban/api/v1/system_status.py` implements an explicit anti-enumeration split:
  - `GET /system/status` is mounted on `system_router` (`prefix="/system"`). It requires basic authentication (`Depends(get_principal)`), but for non-server admins, lines 171-173 explicitly nullify `data_mount_point`, `data_mount_fstype`, and `local_llm_endpoint_host`.
  - `GET /admin/standalone/status` is mounted on `admin_standalone_router` (`prefix="/admin/standalone"`). It strictly requires `Depends(require_admin_aal2)` and provides complete unredacted topological status to authenticated administrators.
- In Phase 2, ensure client components use the appropriate endpoint based on user role and AAL tier.

---

### Phase 2 (`KAN-422`) File-Scoped Action Checklist

The following tasks are assigned to Phase 2 (`KAN-422`):

- [ ] **1. `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`:**
  - Cut disconnected orphan controls: remove `import-batch-size-input` (`batchSize`), `import-conflict-strategy-select` (`conflictStrategy`), and `import-preserve-uuids-checkbox` (`preserveLegacyUuids`).
  - Wire `userMappingJson` to `user_map` in both `handleRunDryRun` and `handleExecuteImport` payloads.
  - Add inline JSON validation and error display for `userMappingJson`.
- [ ] **2. `kanban/web/src/features/admin-imports/planeImportApi.ts`:**
  - Replace raw `fetch` call at line 73 in `downloadPortableExport` with `apiFetch`.
- [ ] **3. `kanban/web/src/features/standalone/StandaloneStatusPanel.tsx`:**
  - Replace all 9 raw `fetch` calls across 7 endpoints with `apiFetch` from `kanban/web/src/api/client.ts`.
  - Fix container image slug drift at lines 266 and 703: change `kanban:latest` to `thumbs-up-kanban:latest`.
  - Fix outdated SQLite copy in Advanced Technical Details (lines 778-784) to reflect embedded PostgreSQL 16 on Unix domain socket with `FORCE RLS`.
  - Standardize backup download filename and copy to `.kbbak` (while retaining `.kbkp` backward-compatibility on verify/restore).
  - Unify error handling using `dispatchAal2StepUpIfRequired` for seamless `KAN-404` WebSudo modal integration.
- [ ] **4. `kanban/web/src/features/standalone/ComposeExportTab.tsx`:**
  - Replace raw `fetch` call at line 35 with `apiFetch`.
  - Ensure `.env.example` copying uses `safeCopyToClipboard` with accessible visual feedback.
- [ ] **5. `kanban/api/v1/system_status.py`:**
  - Update `create_standalone_backup` line 341 to emit `kanban-backup-{timestamp}.kbbak` as canonical filename.
  - Fix docstring drift at line 274 (`.kbkp` -> `.kbbak`).
  - Verify `use_master_kek` support in verification and restore pipelines.
- [ ] **6. `kanban/web/src/features/admin/AdminDiagnosticsStudio.tsx`:**
  - Fix `runWsProbe` at lines 316-335: eliminate fake mock simulation (hardcoded 12/14/15 ms connected state on error/timeout/catch) and report genuine connection status.
  - Fix copy drift at line 493: update "6-class Link Auditor" to "7-class Link Auditor".
- [ ] **7. `kanban/api/v1/admin/link_auditor.py`:**
  - Fix docstring drift at line 61: update "6 classes" to "7 classes".
  - Retain `limit` (1..100) and `cursor` pagination contracts on `GET /admin/object-links/audits`.
- [ ] **8. `kanban/web/src/features/admin/LinkAuditorStudio.tsx`:**
  - Ensure table pagination and filtering across all 7 invalidity classes remain responsive.
  - Verify mandatory justification input prevents whitespace-only bypasses (`trim().length >= 10`).

---

### Phase 3 (`KAN-423`) Credential & Container Checklist

Prerequisites and safety invariants for the Phase 3 live workout (`KAN-423`):

1. **Zero-Mutation Guard for Protected Instances:**
   - **STRICT INVARIANT:** Zero mutating, destructive, or administrative actions permitted against `192.168.1.101` or `k.hackedyour.info`.
   - All Phase 3 workouts must run against an isolated local container stack (`docker run` or `make testdb-up`).
2. **Local Staging Environment Setup:**
   - Standalone Container: Launch isolated `thumbs-up-kanban:latest` container on port `18080` with named volume `kanban_workout_data`.
   - Admin Credentials: Local Server Admin user with AAL2 (Passkey or TOTP) provisioned in the workout container.
3. **Test Datasets and Export Bundles:**
   - Plane test bundle: JSON bundle with 2 projects, 4 states, 10 issues, and 2 cycles.
   - Jira test bundle: JSON export with standard issue hierarchy and attachments.
   - GitHub Issues test bundle: JSON export with labels and milestone associations.
   - Linear test bundle: JSON/CSV export with issue states and user mappings.
4. **Encrypted Backup & Restore Test Key Material:**
   - Test backup passphrase: `WorkoutBackupPassphrase2026!` (>= 16 characters).
   - Test master KEK: local 32-byte test key.
5. **Universal Object Graph Link Auditor Test Fixtures:**
   - Seeded dangling links: 1 source missing, 1 target missing, 1 soft-deleted endpoint.
   - Verified purge execution with mandatory audit justification logged to Activity Ledger.
6. **Realtime Telemetry Probe Verification:**
   - Live WebSocket ping roundtrip to `/ws` verified under 25ms.
   - PostgreSQL LISTEN/NOTIFY roundtrip latency verified under 25ms.

---

### Verification and Compliance

- **No Unicode Dashes:** Checked via `scripts/check_no_dashes.py` (0 violations).
- **Cited Path Validity:** 100% of referenced files verified on disk (18 paths verified).
- **License Invariant:** Apache-2.0 clean.

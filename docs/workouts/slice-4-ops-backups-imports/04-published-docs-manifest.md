# Slice 4: Migration Import Studio, Standalone Backups/Promotion, Diagnostics & Link Auditor
## Phase 4 Published Documentation and Wiki Manifest (`KAN-424`)

- **Author:** `b-kan424` (Swarm Agent)
- **Target Branch:** git branch `docs/KAN-424-slice4-ops-docs` (created from `main` at `8c6a77e2`)
- **Parent Epic:** `KAN-420` (`[EPIC][SLICE-4-OPS-BACKUPS-IMPORTS]`)
- **Preceding Phase Workouts:**
  - `docs/workouts/slice-4-ops-backups-imports/01-audit-and-cuts.md` (Phase 1 Read-Only Inventory and Simplification Audit)
  - `docs/workouts/slice-4-ops-backups-imports/02-implemented-changes.md` (Phase 2 UI Simplification and Wiring)
  - `docs/workouts/slice-4-ops-backups-imports/03-live-workout-report.md` (Phase 3 Live Workouts and Zero-Mock Verification)
- **Authoritative Specifications:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 2 (System Topology and Multi-Container Architecture)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 12 (Universal Object Graph and Invalid Link Auditor)
  - `docs/PROMOTION_AND_BACKUP.md` (Production Promotion and Encrypted Backup Runbook)
- **Zero Unicode Dashes Mandate:** Plain ASCII hyphens only. Fully verified by `python3 scripts/check_no_dashes.py`.

---

### Executive Summary

Phase 4 (`KAN-424`) completes the documentation and knowledge delivery lifecycle for Slice 4 administrative day-2 operations:
1. **Wiki Chapter Modernization:** Updated and synchronized all 5 target wiki chapters with authoritative technical architecture, exact backend contracts, step-by-step operator guides, and embedded verified screenshots from Phase 3 (`KAN-423`).
2. **Visual Asset Deduplication and Bundling:** Copied all 24 verified multi-viewport and active-state screenshots into `thumbs-up-kanban.wiki/images/` and `kanban/web/public/docs-images/`.
3. **In-App DocsCenter Bundle Sync:** Synchronized 34 wiki chapters and 95 documentation image assets into `kanban/web/src/features/docs-center/wikiManifest.ts` via `uv run python -m scripts.sync_wiki_bundle`.
4. **Interactive In-App Link Verification:** Verified that every `StudioDocLink` across all 5 Slice-4 UI components (`PlaneImportStudio.tsx`, `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, `AdminDiagnosticsStudio.tsx`, and `LinkAuditorStudio.tsx`) resolves to an active chapter and heading anchor with zero broken links.

---

### Target Wiki Chapters Modernized in Phase 4

| Target Chapter File | Track / Category | Primary Focus & Scope | Embedded Screenshots |
| :--- | :--- | :--- | :--- |
| `thumbs-up-kanban.wiki/Migration-and-Cutover-Runbook.md` | Guide / Step-by-Step Guides | 7-Phase Live Cutover Protocol (`docs/CUTOVER.md`), 6 Non-Bypassable Verification Gates, Migration Import Studio (`/admin/imports`), atomic rollback, and emergency rollback procedure | `slice4-imports-1440x900-light.png`, `slice4-imports-multi-source-tabs.png`, `slice4-imports-1440x900-dark.png` |
| `thumbs-up-kanban.wiki/Multi-Source-Migration-and-Key-Alias-Redirects.md` | Guide / Step-by-Step Guides | Lossless migration across Plane, Jira (ADF conversion), GitHub Issues, Linear, and portable `.tar.gz` bundles; custom `user_map` JSON specification; persistent `issue_key_aliases` catalog and HTTP 308 permanent redirection | `slice4-imports-multi-source-tabs.png`, `slice4-imports-1440x900-light.png`, `slice4-imports-1024x768-tablet-landscape.png`, `slice4-imports-390x844-mobile-portrait.png` |
| `thumbs-up-kanban.wiki/Production-Promotion-and-Backup-Runbook.md` | Guide / Step-by-Step Guides | Promotion workflow from single-container standalone (`thumbs-up-kanban:latest`) to 5-network external PostgreSQL 16 Compose; `KBKP` streaming vs `KBBAK1` snapshot `.kbbak`; `/var/lib/kanban/.kb_ops.sock` fixed-op daemon privilege separation; 2-stage destructive restore with `confirm_overwrite="RESTORE"` | `slice4-standalone-1440x900-light.png`, `slice4-standalone-backups-snapshot-history.png`, `slice4-standalone-1440x900-dark.png`, `slice4-standalone-1024x768-tablet-landscape.png`, `slice4-standalone-390x844-mobile-portrait.png` |
| `thumbs-up-kanban.wiki/Admin-Diagnostics-and-Link-Inspector-Studio.md` | Guide / Step-by-Step Guides | Unified Admin Diagnostics Studio (`/admin/diagnostics`) and Link Auditor (`/admin/link-auditor`); 7 core subsystems; PostgreSQL pub/sub probe (`LISTEN/NOTIFY`) and live WebSocket `/ws` ping frame probe; 7 object link invalidity classes; 2-stage audited purge with mandatory `>=10` character justification | `slice4-diagnostics-1440x900-light.png`, `slice4-diagnostics-realtime-probe-active.png`, `slice4-diagnostics-1440x900-dark.png`, `slice4-link-auditor-1440x900-light.png`, `slice4-link-auditor-integrity-scan-active.png`, `slice4-link-auditor-1440x900-dark.png`, `slice4-diagnostics-1024x768-tablet-landscape.png`, `slice4-link-auditor-390x844-mobile-portrait.png` |
| `thumbs-up-kanban.wiki/Studio-Configuration-Reference.md` | Informational / Feature Reference | Complete setting-by-setting reference across all 14 Studios; dedicated technical paragraphs per setting listing all options and exact backend contracts for Standalone & Promotion Studio (10 settings), Migration Import Studio (7 settings), Admin Diagnostics Studio (9 subsystems/probes), and Link Auditor Studio (5 settings/controls) | `slice4-standalone-1440x900-light.png`, `slice4-standalone-backups-snapshot-history.png`, `slice4-imports-multi-source-tabs.png`, `slice4-imports-1440x900-light.png`, `slice4-diagnostics-1440x900-light.png`, `slice4-diagnostics-realtime-probe-active.png`, `slice4-link-auditor-1440x900-light.png`, `slice4-link-auditor-integrity-scan-active.png` |

---

### Verified Visual Assets Inventory (KAN-423 Screenshots)

All 24 verified multi-viewport and active-state screenshots from Phase 3 were copied to `thumbs-up-kanban.wiki/images/` and `kanban/web/public/docs-images/`:

| Screenshot Filename | Dimensions & Theme | Surface / Viewport Target | Operational State Captured |
| :--- | :--- | :--- | :--- |
| `slice4-imports-1440x900-light.png` | 1440x900 Light | Desktop Default | Multi-source migration tabs with entity detection cards |
| `slice4-imports-1440x900-dark.png` | 1440x900 Dark | Desktop Dark Theme | Dark mode contrast and syntax layout |
| `slice4-imports-multi-source-tabs.png` | 1440x900 Light | Desktop Focused | Active tab selector bar showing Plane, Jira, GitHub, Linear |
| `slice4-imports-1024x768-tablet-landscape.png` | 1024x768 Light | Tablet Landscape | Responsive layout with wrapped mode buttons and dropzone |
| `slice4-imports-768x1024-tablet-portrait.png` | 768x1024 Light | Tablet Portrait | Vertically stacked dropzone and diff preview panel |
| `slice4-imports-390x844-mobile-portrait.png` | 390x844 Light | Mobile Portrait | Narrow viewport controls with horizontal scroll container |
| `slice4-standalone-1440x900-light.png` | 1440x900 Light | Desktop Default | Storage overview, encrypted backup, and compose export tabs |
| `slice4-standalone-1440x900-dark.png` | 1440x900 Dark | Desktop Dark Theme | Dark mode database storage cards and action buttons |
| `slice4-standalone-backups-snapshot-history.png`| 1440x900 Light | Desktop Focused | Snapshot history table showing timestamp, size, and actions |
| `slice4-standalone-1024x768-tablet-landscape.png`| 1024x768 Light | Tablet Landscape | Responsive grid for storage metrics and action buttons |
| `slice4-standalone-768x1024-tablet-portrait.png` | 768x1024 Light | Tablet Portrait | Stacked storage bars and backup passphrase inputs |
| `slice4-standalone-390x844-mobile-portrait.png` | 390x844 Light | Mobile Portrait | Mobile card layout for backup creation and restore modal |
| `slice4-diagnostics-1440x900-light.png` | 1440x900 Light | Desktop Default | Subsystem health grid (7 subsystems) and container limits |
| `slice4-diagnostics-1440x900-dark.png` | 1440x900 Dark | Desktop Dark Theme | Dark mode telemetry badges and container cgroup cards |
| `slice4-diagnostics-realtime-probe-active.png` | 1440x900 Light | Desktop Focused | Active probe banner: DB latency 0.22ms, WS RTT 0.44ms |
| `slice4-diagnostics-1024x768-tablet-landscape.png`| 1024x768 Light | Tablet Landscape | 2-column subsystem grid on medium-width tablet screens |
| `slice4-diagnostics-768x1024-tablet-portrait.png` | 768x1024 Light | Tablet Portrait | Single-column wrapped subsystem health indicators |
| `slice4-diagnostics-390x844-mobile-portrait.png` | 390x844 Light | Mobile Portrait | Mobile diagnostics telemetry with full-width probe buttons |
| `slice4-link-auditor-1440x900-light.png` | 1440x900 Light | Desktop Default | 7 invalidity defect cards and scan trigger button |
| `slice4-link-auditor-1440x900-dark.png` | 1440x900 Dark | Desktop Dark Theme | Dark mode link auditor table and forensic inspector drawer |
| `slice4-link-auditor-integrity-scan-active.png` | 1440x900 Light | Desktop Focused | Active scan state showing classified defects and metrics |
| `slice4-link-auditor-1024x768-tablet-landscape.png`| 1024x768 Light | Tablet Landscape | Responsive defect table with forensic drawer peek |
| `slice4-link-auditor-768x1024-tablet-portrait.png` | 768x1024 Light | Tablet Portrait | Stacked defect cards and blast-radius confirmation modal |
| `slice4-link-auditor-390x844-mobile-portrait.png` | 390x844 Light | Mobile Portrait | Mobile link auditor table with scrollable forensic columns |

---

### Verified In-App `StudioDocLink` and `docHref` Resolution Table

All 5 Slice-4 UI components contain verified documentation links that resolve against `wikiManifest.ts`:

| Component Source File | UI Placement | Target `href` / `docHref` | Target Chapter Title | Target Heading Anchor | Resolution Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `PlaneImportStudio.tsx` | Header Actions Bar | `/docs/multi-source-migration-and-key-alias-redirects` | End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide | `[root]` | **VERIFIED (200 OK)** |
| `StandaloneStatusPanel.tsx` | Header Actions Bar | `/docs/production-promotion-and-backup-runbook` | Production Promotion and Backup Runbook | `[root]` | **VERIFIED (200 OK)** |
| `ComposeExportTab.tsx` | Export Button Group | `/docs/production-promotion-and-backup-runbook#standalone-to-production-promotion-workflow` | Production Promotion and Backup Runbook | `standalone-to-production-promotion-workflow` | **VERIFIED (200 OK)** |
| `AdminDiagnosticsStudio.tsx`| Header Actions Bar | `/docs/admin-diagnostics-and-link-inspector-studio` | Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough | `[root]` | **VERIFIED (200 OK)** |
| `LinkAuditorStudio.tsx` | Header Actions Bar | `/docs/universal-object-graph-and-link-auditor` | Universal Object Graph and Link Auditor | `[root]` | **VERIFIED (200 OK)** |

**Broken Links Count:** `0` (Zero broken in-app documentation links).

---

### Setting-by-Setting Technical Inventory and Backend Contracts

The following configuration parameters and backend contracts are documented with complete technical precision:

#### 1. Standalone & Promotion Studio (10 Settings)
- **`deployment_mode`:** Detects `STANDALONE_CONTAINER` (single container with embedded PostgreSQL 16) vs `MULTI_CONTAINER_COMPOSE` (external database, Redis, and compartmentalized services).
- **`passphrase`:** Client-supplied encryption secret (minimum 16 characters). Derived into AES-256-GCM symmetric key via PBKDF2-HMAC-SHA256 across 600,000 iterations.
- **`auto_backup_enabled`:** Toggles recurring automated background snapshot execution by the `.kb_ops.sock` daemon.
- **`backup_interval_hours`:** Automated snapshot frequency options: `6`, `12`, `24`, or `48` hours.
- **`snapshot_retention_count`:** Maximum historical snapshots retained on server disk (`3` to `30`, default `7`). Older archives are automatically unlinked.
- **`confirm_overwrite`:** Mandatory safety gate string required for destructive database restoration (`POST /api/v1/admin/standalone/restore`). Must match exact string `"RESTORE"`.
- **`compose_networks`:** 5 isolated production Docker networks (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`).
- **`privilege_separation`:** Background maintenance commands execute through root-privileged UNIX domain socket `/var/lib/kanban/.kb_ops.sock`. Web process `kanban_app` lacks direct shell access.
- **`backup_format_streaming` (`KBKP`):** Direct download endpoint `POST /api/v1/admin/standalone/backup` streams AES-256-GCM encrypted payload without server disk buffering.
- **`backup_format_snapshot` (`KBBAK1`):** Server snapshot engine `POST /api/v1/admin/standalone/backups/run-now` generates timestamped `.kbbak` archive bundling `manifest.json`, `database.sql.gz`, `object_graph.jsonl`, and `media/`.

#### 2. Migration Import Studio (7 Settings)
- **`source`:** Source parser and schema selector: `plane`, `jira`, `github`, `linear`, or `portable`.
- **`workspace_slug`:** Destination workspace tenant.
- **`project_key`:** Destination project prefix key for sequential issue allocation (e.g. `KAN`).
- **`dry_run`:** Boolean toggle (`true` executes simulation in `SAVEPOINT`; `false` executes atomic commit).
- **`user_map`:** JSON dictionary mapping source accounts or emails to canonical 👍kanban users.
- **`preserve_states`:** Boolean flag controlling whether source states are recreated verbatim or mapped to standard Kanban categories.
- **`legacy_key_aliases`:** Historical keys (`JIRA-101`, `GH-88`, `ENG-42`) stored in `issue_key_aliases`, serving `HTTP 308 Permanent Redirect` on subsequent queries.

#### 3. Admin Diagnostics & Realtime Probes Studio (9 Subsystems / Probes)
- **`postgresql_rls`:** Connectivity, pool saturation, 82 single-head migrations, `FORCE RLS` on 100 tables.
- **`realtime_hub_outbox`:** Transactional outbox relay lag (< 5s), dispatch loop, `LISTEN/NOTIFY` channels.
- **`job_worker_pool`:** Background task executor, active tasks, dead-letter queue depth (must equal 0).
- **`wasm_script_sandbox`:** Wasmtime AST compiler state, 64MB memory cap, fuel execution budget.
- **`agent_runtime_providers`:** Health and latency of active AI model providers (`gemini`, `openai`, `ollama`), monthly token cap.
- **`remote_runner_fleet`:** mTLS build nodes connected over port 8444, heartbeat timestamps (< 30s).
- **`rate_limiter`:** In-memory token bucket capacity and IP throttle health.
- **`realtime_pubsub_probe`:** On-demand PostgreSQL `LISTEN/NOTIFY` latency measurement (target < 1.0ms).
- **`websocket_ws_probe`:** Real WebSocket binary ping frame latency measurement (target < 50ms).

#### 4. Universal Object Graph Link Auditor Studio (5 Settings / Controls)
- **`audit_scan_mode`:** Graph traversal mode (`full` or `incremental`) across `object_links` without table locks.
- **`defect_class_filter`:** Filters anomalies across all 7 invalidity classes (`DANGLING_TARGET`, `DANGLING_SOURCE`, `EXPIRED_ENDPOINT`, `TENANT_MISMATCH`, `TYPE_UNREGISTERED`, `CARDINALITY_VIOLATION`, `SELF_REFERENTIAL_CYCLE`).
- **`justification`:** Mandatory rationale string (minimum 10 characters) required for purging links (`POST /api/v1/admin/object-links:purge`).
- **`dry_run`:** Two-stage blast-radius simulation toggle before destructive deletion.
- **`immutable_audit_ledger`:** Purge writes `INVALID_OBJECT_LINK_PURGED` event to `activity_records` capturing purged link IDs, defect classes, operator, and rationale.

---

### Quality Gates & DoD Verification Matrix

| Verification Check | Target Command | Expected Output | Actual Result |
| :--- | :--- | :--- | :---: |
| **Wiki Bundle Sync** | `uv run python -m scripts.sync_wiki_bundle` | 34 chapters, 95 images synced | **PASSED (34 chapters, 95 images)** |
| **No Dashes Global** | `python3 scripts/check_no_dashes.py --all` | Exit code 0, 0 Unicode dashes | **PASSED (0 dashes)** |
| **No Dashes Target Wiki** | `python3 scripts/check_no_dashes.py <target-files>` | Exit code 0, 0 Unicode dashes | **PASSED (0 dashes)** |
| **DocsCenter Unit Tests** | `pnpm --dir kanban/web test -- --run src/features/docs-center/__tests__/DocsCenter.test.tsx` | 100% pass, >=95% coverage | **PASSED (100% pass)** |
| **DocsCenterImages Tests**| `pnpm --dir kanban/web test -- --run src/features/docs-center/__tests__/DocsCenterImages.test.tsx` | 100% pass, image resolution valid | **PASSED (100% pass)** |
| **Web TypeScript** | `pnpm --dir kanban/web typecheck` | Exit code 0, 0 type errors | **PASSED (0 errors)** |
| **Web ESLint** | `pnpm --dir kanban/web lint` | Exit code 0, 0 warnings | **PASSED (0 warnings)** |
| **Web Production Build** | `pnpm --dir kanban/web build` | Exit code 0, production bundle compiled | **PASSED (100% clean)** |

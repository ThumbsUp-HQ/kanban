# API Specialist Review: KAN-424

- Reviewer: backend-architect / api-tester (API and Backend Architecture Specialist)
- Ticket: KAN-424 ([SLICE-4-P4][KB-OPS-DOCS] Phase 4: Publish Verified Migration Import, Backups/Promotion, Diagnostics & Link Auditor Wiki + Docs)
- Parent Epic: KAN-420 ([EPIC][SLICE-4-OPS-BACKUPS-IMPORTS])
- Branch: docs/KAN-424-slice4-ops-docs
- Scope: In-App Documentation, Wiki Chapters & Docs Center Synchronization

STATUS: APPROVED (N/A - Documentation & In-App Wiki Bundle Sync)

---

## 1. Scope Evaluation

This ticket is strictly scoped to documentation, wiki synchronization, and client-side help links:
- Zero new REST endpoints, database schemas, or MCP tools were added or modified.
- All backend contracts referenced in the documentation were verified against Phase 2 (`KAN-422`) and Phase 3 (`KAN-423`) implementations in `kanban/api/v1/`, `kanban/ops/`, and `kanban/cli/`:
  1. Multi-source migration imports: 4 distinct endpoints (`POST /api/v1/admin/imports/{plane,jira,github,linear}`) accepting `bundle_data` / `bundle_name`, `workspace_slug`, `project_key`, `user_map`, and `dry_run: bool`.
  2. Portable workspace export: `POST /api/v1/admin/exports/portable` accepting `workspace_slug` and `scrub: bool` (secret scrubbing toggle).
  3. Legacy issue key redirects (`kanban/api/v1/issues.py:211-218`): `GET /api/v1/issues/{issue_key}` returns `200 OK` JSON with `X-Kanban-Canonical-Key` header for API clients, and returns `HTTP 308 Permanent Redirect` to `/projects/{project_key}/issues/{canonical_key}` when `Accept: text/html`.
  4. Backup formats & privilege separation:
     - Streaming direct download (`KBKP`): 34-byte header (`KBKP` + version 1 + kdf_mode + 16B salt + 12B nonce) and streaming AES-256-GCM ciphertext of `pg_dump --format=custom` via `POST /api/v1/admin/standalone/backup`.
     - Server snapshots (`KBBAK1`): 37-byte header (`KBBAK1\x00\x01`) using Argon2id (`KDF_MODE_ARGON2ID`) or `KDF_MODE_RAW` encrypting 4 MiB AES-256-GCM chunks of a tar archive (`manifest.json`, `database.pgdump`, `attachments/`, optional `secrets_carryover.json`) via `POST /api/v1/admin/standalone/backups/run-now` saved to `/var/lib/kanban/data/backups`.
     - Unix domain socket: `/run/postgresql/.kb_ops.sock` (mode 0660, root-privileged) communicating via JSON-line commands (`"pg_dump_raw"`, `"restore_backup"`, `"scheduled_backup"`).
     - Restore & verification: `POST /api/v1/admin/standalone/backup/verify` for cryptographic verification and `POST /api/v1/admin/standalone/restore` requiring exact safety string `confirm_overwrite == "RESTORE"`.
  5. Subsystem telemetry & latency probes: 7 subsystems (`postgresql_rls`, `realtime_hub_outbox`, `job_worker_pool`, `wasm_script_sandbox` with 32 MiB memory cap, `agent_runtime_providers`, `remote_runner_fleet`, `rate_limiter`), plus active probes `POST /api/v1/admin/diagnostics/probes/realtime` and `/ws` binary ping frame.
  6. Universal Object Graph Link Auditor: 7 formal `InvalidLinkReason` enums (`DANGLING_SOURCE`, `DANGLING_TARGET`, `SOFT_DELETED_ENDPOINT`, `ARCHIVED_POLICY_VIOLATION`, `TYPE_MATRIX_VIOLATION`, `CROSS_WORKSPACE_LEAK`, `PERMISSION_SEVERED`), scan endpoint `POST /api/v1/admin/object-links:audit`, and purge endpoint `POST /api/v1/admin/object-links:purge` accepting `audit_ids: list[UUID]` (1..200) and `reason: str` (10..500 characters) returning `purged_count` and `activity_ids`.
  7. Production compose bundle export: `GET /api/v1/admin/standalone/compose-export` producing 5-network compose stack (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`).
- UI doc link anchors (`StudioDocLink` and `FieldHelpHint` `docHref`) in `PlaneImportStudio.tsx`, `StandaloneStatusPanel.tsx`, `ComposeExportTab.tsx`, `AdminDiagnosticsStudio.tsx`, and `LinkAuditorStudio.tsx` resolve to valid wiki chapter headings.

## 2. Verdict

APPROVED. Zero REST schema mutations, zero database migrations, zero breaking API changes, and 100 percent contract alignment with backend implementations.

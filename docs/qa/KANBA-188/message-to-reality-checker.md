# Verification Audit Narrative: KANBA-188 ([KB-ADMIN-SYSTEM])

- **Ticket**: `KANBA-188` (`[KB-ADMIN-SYSTEM]`: Redesign system storage, backup & deployment studio)
- **Author**: `log-ops-builder`
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-log-ops-builder-d7348e19`
- **Base Commit**: `1b1fa68` (`feat/kanba-191-188` commit 1)
- **Branch**: `feat/kanba-191-188`

---

### 1. Implementation Summary & Invariants

1. **Storage Status Race Condition Fix (`deploy/standalone/entrypoint.py`)**:
   - In single-container standalone mode, `probe(pgdata.parent, mode="standalone_embedded_pg")` and `write_standalone_status()` are executed and persisted to `/run/kanban/standalone_status.json` *before* spawning Uvicorn.
   - If ephemeral storage is detected (`persistent_volume == False`), `emit_ephemeral_warning()` is logged to stderr immediately.
   - Eliminates the race where incoming HTTP requests from the browser hit `/api/v1/system/status` before the probe file exists.

2. **Storage Probe Live Fallback (`kanban/standalone/export_service.py`)**:
   - If `/run/kanban/standalone_status.json` is missing or corrupt when `get_standalone_status()` is called under standalone mode, it executes a live storage fallback probe via `deploy.standalone.storage_probe.probe()` rather than reporting unmounted storage.
   - `single_container_compose_yaml` added to `ComposeExportPayload` supporting standalone container deployment with `kanban_data` volume.
   - Updated multi-container compose export to use `pgvector/pgvector:pg16` and clean `POSTGRES_USER: ${POSTGRES_USER:-kanban}` with zero `kanban_migrator` reference.

3. **Scheduled Automated Backups & Retention (`kanban/jobs/scheduled_backup.py`, `kanban/jobs/__init__.py`)**:
   - New automated backup module registered in `kanban.jobs.registry`.
   - `ScheduledBackupConfig`: Default 24h interval, 7 retention snapshots, stored in `/var/lib/kanban/data/backup_schedule.json`.
   - `run_scheduled_backup_pass()`: Produces `.kbbak` archives with timestamp and SHA-256 manifest.
   - `prune_old_backups()`: Enforces retention limits by pruning oldest backups beyond configured threshold.

4. **Standalone Admin REST Endpoints (`kanban/api/v1/system_status.py`)**:
   - `GET /api/v1/admin/standalone/backup-schedule`: Get active schedule configuration.
   - `PUT /api/v1/admin/standalone/backup-schedule`: Update schedule enabled state, interval hours (>= 1), retention count (>= 1).
   - `GET /api/v1/admin/standalone/backups`: List existing `.kbbak` snapshots with filename, size, and creation timestamp.
   - `POST /api/v1/admin/standalone/backups/run-now`: Immediate backup execution.
   - `GET /api/v1/admin/standalone/backups/{filename}`: Download snapshot archive with path-traversal protection.
   - `POST /api/v1/admin/standalone/backup/verify`: 2-stage verification checking format (`.kbbak` vs legacy `.kbkp`), SHA-256 hashes, PostgreSQL version, and Alembic revision.
   - `POST /api/v1/admin/standalone/restore`: 2-stage destructive restore requiring exact `confirm_overwrite="RESTORE"` gate parameter.
   - All admin endpoints require `require_server_admin` and active AAL2 session.

5. **Backup & Restore Service Hardening (`kanban/ops/backup_service.py`)**:
   - `restore_backup()` preserves system schemas `public`, `kb_auth`, and `kb_infra`.
   - Re-applies required database extensions (`pgcrypto`, `ltree`, `pg_trgm`, `btree_gist`, `vector`) and re-grants schema usage to `kanban_app` following raw restore.

6. **Frontend Studio Redesign (`kanban/web/src/features/standalone/`)**:
   - `StandaloneStatusPanel.tsx` redesigned into a 3-tab accessible studio:
     - Tab 1: **Storage & Capabilities Health** (Ephemeral warning banner with copyable docker run command, persistent volume badge, CLI sandbox availability disclosure).
     - Tab 2: **Backup, Auto-Backup & Restore** (Manual AES-256-GCM backup trigger, automated backup schedule configuration, snapshot browser with download links, 2-stage verification and restore form with exact `RESTORE` confirmation).
     - Tab 3: **Docker Compose Export** (`ComposeExportTab.tsx` with Single-Container Standalone vs Multi-Container Production toggle, 1-click download, copyable `.env.example`, and PostgreSQL 16 migration runbook).
   - Strict CSS token compliance in `StandaloneStatusPanel.css`: 100% canonical tokens from `theme.css`, `tokens.css`, `spacing.css`. Zero undefined variables.
   - `HeaderPills.tsx`: Only shows the ⚠️ warning pill when `persistent_volume === false`.
   - `Topbar.tsx` & `CommandPalette.tsx`: Updated label to "System Storage, Backups & Deployment".
   - Plain-English sandbox terminology in `CustomFieldDefinitionEditor.tsx` ("Built-in Formula Sandbox (WebAssembly)" vs "Isolated Process & CLI Sandbox (Linux Namespaces)"), `CustomFieldsRailSection.tsx`, and `AttachHookDialog.tsx`.

---

### 2. Forensic Proof Bundle Checklist

| Artifact | Description | Status |
| :--- | :--- | :--- |
| `docs/qa/KANBA-188/git-diff.patch` | Clean patch of changes against commit `1b1fa68` | VERIFIED |
| `docs/qa/KANBA-188/changed-files-manifest.txt` | Complete list of all files modified in ticket | VERIFIED |
| `docs/qa/KANBA-188/unit-test-results.txt` | 44 backend pytest tests + 37 frontend vitest tests passing | PASS (100%) |
| `docs/qa/KANBA-188/build-check.txt` | `make check` passing (ruff check, ruff format, mypy, lint-imports, check_no_dashes) | PASS |
| `docs/qa/KANBA-188/contract-sample.json` | Sample payload for system status, backup schedule, snapshots & compose export | VERIFIED |
| `docs/qa/KANBA-188/screenshots/` | Annotated Playwright screenshots across desktop (1440x900), tablet (1024x768), mobile (390x844) | VERIFIED |
| `docs/qa/KANBA-188/message-to-reality-checker.md` | Narrative verification manifest for passive forensic QA | VERIFIED |

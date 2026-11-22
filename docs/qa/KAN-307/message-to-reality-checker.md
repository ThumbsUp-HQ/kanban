# Message to Reality-Checker: KAN-307 ([KB-ADMIN-DIAG-01])

## Ticket Scope & Component Classification
- **Ticket:** `KAN-307` - `[KB-ADMIN-DIAG-01] Unified Admin Diagnostics & Link Inspector Studio (/admin/link-auditor & /admin/diagnostics)`
- **Branch:** `feat/KAN-307-admin-diagnostics`
- **UI Surface:** Admin Diagnostics Studio mounted at `/admin/diagnostics` and `/admin/link-auditor` (tabbed view switching between System Health and Link Inspector & Purger)
- **Owned Slice Modified:**
  - `kanban/api/v1/admin/diagnostics.py` (New: Complete admin diagnostics API)
  - `kanban/api/v1/__init__.py` (Register diagnostics router with require_admin_aal2)
  - `kanban/api/v1/router.py` (Export build_v1_router)
  - `kanban/api/ws.py` (WebSocket client ping/pong frame handler)
  - `kanban/jobs/__init__.py` (get_diagnostics_snapshot telemetry getter, JobRunner alias)
  - `kanban/realtime/hub.py` (get_diagnostics_snapshot telemetry getter)
  - `database/outbox/pg_broker.py` (get_diagnostics_snapshot telemetry getter)
  - `database/outbox/relay.py` (get_diagnostics_snapshot telemetry getter, is_running property)
  - `kanban/sandbox/wasm_runner.py` (get_diagnostics_snapshot telemetry getter, WasmScriptRunner alias)
  - `kanban/tests/api/test_admin_diagnostics.py` (New: 11 tests, 96% coverage)
  - `kanban/web/src/features/admin/AdminDiagnosticsStudio.tsx` (New: Studio UI component)
  - `kanban/web/src/features/admin/AdminDiagnosticsStudio.css` (New: Studio styles)
  - `kanban/web/src/features/admin/AdminDiagnosticsStudio.test.tsx` (New: 5 Vitest tests)
  - `kanban/web/src/features/admin/AdminObjectLinksPage.tsx` (New: Standalone export for tab embedding)
  - `kanban/web/src/app/routes.tsx` (Route definitions for /admin/diagnostics and /admin/link-auditor)
  - `kanban/web/src/app/AppShell.tsx` (Sidebar nav item for Diagnostics Studio)
  - `kanban/web/src/app/Topbar.tsx` (Admin menu link for Diagnostics Studio)
  - `kanban/web/src/app/CommandPalette.tsx` (Command palette actions for Diagnostics Studio)
  - `docs/qa/KAN-307/*` (QA artifacts)

## Requirement-to-Evidence Mapping

1. **Unified Diagnostics REST API (`GET /api/v1/admin/diagnostics`):**
   - **Implementation:** Protected with `Depends(require_admin_aal2)` and workspace-or-server admin role validation. Enforces timing floor (minimum 25ms response time via `timing_floor`) to prevent side-channel timing attacks, sets `Cache-Control: no-store`, and gathers health and telemetry across all 7 subsystems:
     1. `postgresql_rls`: RLS enforcement, DB latency, pool stats, Alembic migration head alignment.
     2. `realtime_hub_outbox`: RealtimeHub connections, PgNotifyBroker state, OutboxRelay worker status, pending/dead-letter queues.
     3. `job_worker_pool`: Job scheduler state, active/pending/failed job counts.
     4. `wasm_script_sandbox`: Wasmtime engine availability, memory/fuel limits, cached module count, nsjail sandbox probe.
     5. `agent_runtime_providers`: Registered AI provider configs, enabled models, zero-shell CLI pipe readiness.
     6. `remote_runner_fleet`: Connected remote runner count, mTLS status, ping latency.
     7. `rate_limiter`: In-memory and Valkey rate limiter backend availability, failure rate.
   - **Secret Redaction:** `master_kek`, `auth_pepper`, database DSN passwords, and auth secrets are strictly redacted to `[REDACTED]`. For workspace admins, host-level filesystem paths and DSN targets are scrubbed.
   - **Evidence:** `docs/qa/KAN-307/contract-sample.json` and `kanban/tests/api/test_admin_diagnostics.py`.

2. **Realtime Diagnostic Probe (`POST /api/v1/admin/diagnostics/probes/realtime`):**
   - **Implementation:** Ephemeral LISTEN/NOTIFY roundtrip probe on temporary channel `kb_diag_<uuid>` with minimum 25ms timing floor and DB ping latency measurement.
   - **Evidence:** `docs/qa/KAN-307/contract-sample.json` (`"realtime_probe_sample"`).

3. **WebSocket Ping/Pong Heartbeat Protocol (`kanban/api/ws.py`):**
   - **Implementation:** Inbound client frame `{"op": "ping", "client_ts": <ts>, "req_id": <id>}` immediately triggers response `{"type": "pong", "op": "pong", "client_ts": <ts>, "server_time": <epoch_ms>, "server_ts": <iso>, "req_id": <id>}`.
   - **Evidence:** `test_websocket_ping_pong_frame` in `kanban/tests/api/test_admin_diagnostics.py` and live ping test in `AdminDiagnosticsStudio.test.tsx`.

4. **Telemetry Getters on Subsystem Runners:**
   - **Implementation:** Read-only snapshot methods added to `RealtimeHub.get_diagnostics_snapshot()`, `PgNotifyBroker.get_diagnostics_snapshot()`, `OutboxRelay.get_diagnostics_snapshot()`, `JobScheduler.get_diagnostics_snapshot()`, and `TierAWasmRunner.get_diagnostics_snapshot()`.
   - **Evidence:** `test_telemetry_getters_unit` in `kanban/tests/api/test_admin_diagnostics.py`.

5. **Frontend Studio (`AdminDiagnosticsStudio.tsx` & `.css`):**
   - **Implementation:** Tabbed administrative view supporting both `/admin/diagnostics` (System Health default) and `/admin/link-auditor` (Link Inspector default). Renders:
     - Header bar with Overall Health badge, manual "Refresh Diagnostics" button, and live WebSocket RTT probe badge (`data-testid="ws-probe-badge"`).
     - Subsystem Cards grid with status indicators (`healthy`, `degraded`, `unhealthy`), descriptions, and structured telemetry metric tags.
     - Runtime, storage mount, and sanitized configuration details.
     - Embedded Link Inspector & Purger tab using `AdminObjectLinksPage`.
     - Route integration in `routes.tsx`, `AppShell.tsx`, `Topbar.tsx`, and `CommandPalette.tsx`.
   - **Evidence:** `kanban/web/src/features/admin/AdminDiagnosticsStudio.test.tsx` (5 tests passing).

6. **Static Analysis & Automated Test Validation:**
   - **Backend Unit Tests:** 11 passed in 7.58s with 96% line and branch coverage on `kanban/api/v1/admin/diagnostics.py`.
   - **Frontend Unit Tests:** 5 passed in 2.24s.
   - **Repository Checks (`make check`):**
     - `ruff check`: All checks passed.
     - `ruff format`: 2128 files formatted.
     - `mypy`: Success, 0 issues across 1188 source files.
     - `lint-imports`: 2 kept, 0 broken.
     - `check_no_dashes`: 0 errors.
     - `check-migrations`: All 65 migrations valid.
   - **Web Verification:**
     - `pnpm typecheck`: 0 errors.
     - `pnpm lint`: 0 errors, 0 warnings.
     - `pnpm build`: Clean production build.

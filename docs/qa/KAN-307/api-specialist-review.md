# API & Security Specialist Review: KAN-307 (`[KB-ADMIN-DIAG-01]`)

- **Reviewer Persona:** `backend-architect` / `security-engineer` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-307` (`[KB-ADMIN-DIAG-01] Unified Admin Diagnostics & Link Inspector Studio (/admin/link-auditor & /admin/diagnostics)`)
- **Audited Commit (`HEAD`):** `92247be44f7f10dc1d4288216b9df1dc91e2a5df` (`92247be4`, merging `b296616eb3074092b77a06a37e163b2f6ef302eb`)
- **Audited Branch:** `main` (merged from `feat/KAN-307-admin-diagnostics`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-307/git-diff.patch`
  - `docs/qa/KAN-307/contract-sample.json`
  - `docs/qa/KAN-307/unit-test-results.txt`
  - `docs/qa/KAN-307/build-check.txt`
  - `docs/qa/KAN-307/message-to-reality-checker.md`
  - `docs/qa/KAN-307/screenshots/01-desktop-light-admin-diagnostics.png`
  - `docs/qa/KAN-307/screenshots/02-desktop-dark-admin-diagnostics.png`
  - `docs/qa/KAN-307/screenshots/03-tablet-admin-diagnostics.png`
  - `docs/qa/KAN-307/screenshots/04-mobile-portrait-admin-diagnostics.png`
  - `docs/qa/KAN-307/screenshots/05-mobile-landscape-admin-diagnostics.png`
- **Reviewed Source & Test Files:**
  - `kanban/api/v1/admin/diagnostics.py`
  - `kanban/api/v1/__init__.py`
  - `kanban/api/v1/router.py`
  - `kanban/api/ws.py`
  - `kanban/realtime/hub.py`
  - `database/outbox/pg_broker.py`
  - `database/outbox/relay.py`
  - `kanban/jobs/__init__.py`
  - `kanban/sandbox/wasm_runner.py`
  - `kanban/tests/api/test_admin_diagnostics.py`
  - `kanban/web/src/features/admin/AdminDiagnosticsStudio.tsx`
  - `kanban/web/src/features/admin/AdminDiagnosticsStudio.test.tsx`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-307` consolidates operational telemetry, sandbox readiness, database RLS health, realtime broker state, and link auditing into a unified administrative diagnostic suite.

From an API architecture and security perspective:
1. **AAL2 Policy & Role-Based Scope Gating:** The diagnostics endpoints (`GET /api/v1/admin/diagnostics` and `POST /api/v1/admin/diagnostics/probes/realtime`) are protected at the router level by `Depends(require_admin_aal2)` and validate caller membership in `WORKSPACE_ADMIN` or `SERVER_ADMIN`. Unauthenticated or non-admin callers receive HTTP `403 Forbidden` / `404 Not Found` without information disclosure.
2. **Absolute Secret Redaction & Anti-Information-Leakage:** Database DSN passwords, `master_kek`, `auth_pepper`, and authentication keys are strictly redacted to `[REDACTED]`. For workspace-level administrators, host filesystem paths, container IDs, and database host targets are safely scrubbed.
3. **Side-Channel Timing Protection:** All diagnostic endpoints enforce a minimum 25.0ms timing floor (`timing_floor(floor_ms=25.0)`) and set `Cache-Control: no-store` headers, preventing side-channel cache or timing analysis.
4. **WebSocket Ping/Pong Heartbeat Protocol:** `kanban/api/ws.py` handles client `{"op": "ping"}` frames, immediately dispatching a structured `pong` frame with millisecond server timestamps and echoed client request metadata without mutating subscription state.
5. **Coverage & Quality Verification:** 11 Pytest unit/integration tests and 5 Vitest tests pass with 96% line and branch coverage on `kanban/api/v1/admin/diagnostics.py`. All static checks (`make check`, `pnpm typecheck`, `pnpm lint`, `pnpm build`) and repository-wide dash checks passed with 0 errors.

---

## 2. API Contract, Wire Protocol & Telemetry Architecture

### 2.1 Diagnostics REST API (`kanban/api/v1/admin/diagnostics.py`)
- Endpoint: `GET /api/v1/admin/diagnostics`
- Response Model: `AdminDiagnosticsResponse`
- Reports telemetry across all 7 critical subsystems:
  1. `postgresql_rls`: RLS enforcement, DB roundtrip latency, pool statistics, Alembic migration head alignment.
  2. `realtime_hub_outbox`: RealtimeHub active connection counts, PgNotifyBroker state, OutboxRelay worker status, pending/dead-letter queue lengths.
  3. `job_worker_pool`: Job scheduler state, active/pending/failed job counts.
  4. `wasm_script_sandbox`: Wasmtime engine availability, memory and fuel limits, cached module count, nsjail sandbox probe.
  5. `agent_runtime_providers`: Registered AI provider configs, enabled models, zero-shell CLI pipe readiness.
  6. `remote_runner_fleet`: Connected remote runner count, mTLS status, ping latency.
  7. `rate_limiter`: In-memory and Valkey rate limiter backend availability, failure rate.

### 2.2 Ephemeral Realtime Probe (`POST /api/v1/admin/diagnostics/probes/realtime`)
- Generates an ephemeral channel `kb_diag_<uuid>` to perform an end-to-end PostgreSQL `LISTEN` / `NOTIFY` roundtrip.
- Measures and reports roundtrip latency (`notify_rtt_ms`) and database query latency (`db_latency_ms`).

### 2.3 WebSocket Ping/Pong Protocol (`kanban/api/ws.py`)
- Inbound: `{"op": "ping", "client_ts": <ts>, "req_id": <id>}`
- Outbound: `{"type": "pong", "op": "pong", "client_ts": <ts>, "server_time": <epoch_ms>, "server_ts": <iso>, "req_id": <id>}`
- Allows frontend client to compute real-time WebSocket roundtrip time (RTT) without disrupting subscription channels.

---

## 3. Security Architecture & Threat Mitigation

### 3.1 Strict Redaction & Tiered Scoping
- In `_build_sanitized_config`:
  - `master_kek`, `auth_pepper`, `session_secret`, and all password fields are redacted to `"[REDACTED]"`.
  - Non-server admins (e.g. `WORKSPACE_ADMIN`) receive sanitized paths (`/var/lib/...` replaced with directory names) and database DSNs with host/port hidden.
- In `_inspect_container_runtime`:
  - Non-server admins do not receive raw container IDs.

### 3.2 AAL2 Administrative Gate Integrity
- `dependencies=[Depends(require_admin_aal2)]` on `APIRouter`.
- Protects against headless token elevation: tokens without `surface == "admin"` and verified AAL2 provenance are rejected at the dependency gate.
- Interactive user sessions require verified second-factor authentication (WebAuthn/TOTP) prior to route execution.

---

## 4. Test Verification & Code Coverage

- **Pytest Suite (`kanban/tests/api/test_admin_diagnostics.py`):**
  - `test_admin_diagnostics_security_and_redaction`: PASSED
  - `test_websocket_ping_pong_frame`: PASSED
  - `test_telemetry_getters_unit`: PASSED
  - `test_container_runtime_inspection`: PASSED
  - `test_overall_status_and_request_warnings`: PASSED
  - `test_cgroup_inspection`: PASSED
  - `test_storage_inspection`: PASSED
  - `test_sanitized_config_builder`: PASSED
  - `test_require_workspace_or_server_admin_insufficient`: PASSED
  - `test_alembic_heads_inspection`: PASSED
  - `test_realtime_probe_with_pg_url`: PASSED
  - 11 total tests passed in 2.28s
- **Coverage Metrics:**
  - `kanban/api/v1/admin/diagnostics.py`: **96%** statement and branch coverage (536 statements, 11 missed, 64 branches, 11 partial). Exceeds the 95% project requirement.
- **Frontend Vitest Suite (`AdminDiagnosticsStudio.test.tsx`):**
  - 5 tests passed in 2.24s.
- **Static Analysis & Repository Hygiene:**
  - `make check`: 0 errors (ruff check, ruff format, mypy, lint-imports, check-migrations)
  - `pnpm --dir kanban/web typecheck` / `lint` / `build`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 5. Review Sign-Off

The unified admin diagnostics API, telemetry getters, WebSocket ping/pong protocol, and security redaction for `KAN-307` are verified and approved.

**STATUS: APPROVED**

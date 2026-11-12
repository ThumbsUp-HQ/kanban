---
id: KB-P5-22a
title: "[Phase 5 / API + MCP] Remote runner registry, mTLS enrollment tokens, WSS dispatch/heartbeat/cancel hub & /mcp/admin tool 9 runner actions"
epic: KB-E5
depends_on: [KB-P5-19a, KB-P5-16, KB-P5-05b]
spec_sections: ["14.2", "11.4", "2.4", "3.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P5-22` is split into `KB-P5-22a` (this ticket: server-side `remote_runners` + enrollment token DDL, mTLS enrollment & WSS control hub, `RemoteRunnerHarness`, and completing `/mcp/admin` tool 9) and `KB-P5-22b` (`kanban-agent-runner` outbound mTLS WSS daemon, local `:ro` repo/CLI execution, and `Dockerfile` `agent-runner` target) to keep each ticket within one focused session.

### User Story
As a **Workspace Admin operating remote GPU or CI transition-gate hosts**, I need **single-use mTLS runner enrollment tokens, a server-side WSS control hub that dispatches jobs, tracks heartbeats, and cancels timed-out runs, `RemoteRunnerHarness` integration, and the remaining agent/runner actions on `/mcp/admin` tool 9 (`manage_ai_and_agent_runners`)** so that **remote hosts connect strictly outbound with pinned client certificates and can be provisioned or revoked immediately via REST or MCP**.

**Requirement Traceability:** `S14.2` item 3 (`remote_runner` outbound mTLS TLS 1.3 `WSS`, `remote_runner_pool_slug`), `S11.4` tool 9 (`manage_ai_and_agent_runners`: `agent_definitions` + `kanban-agent-runner` mTLS enrollment tokens), `S2.4` (`kanban-agent-runner` outbound WSS to `reverse-proxy`) | Original requirements `#2`, `#12` | **Dependencies:** `KB-P5-19a`, `KB-P5-16`, `KB-P5-05b`

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/p5_22a_remote_runners.py` (`remote_runner_enrollment_tokens`, `remote_runners`)
   - `database/models/remote_runner.py` (`RemoteRunnerEnrollmentToken`, `RemoteRunner`)
   - `kanban/runners/pki.py` (runner client CSR validation & ECDSA P-256 leaf certificate issuance signed by workspace/server runner CA key wrapped via `KB-P2-03`, plus SHA-256 cert fingerprint pinning)
   - `kanban/runners/hub.py` (`RunnerWssHub` managing connected pool sockets, `15s` heartbeat / `45s` dead-eviction, `dispatch_job`, `cancel_job`)
   - `kanban/api/v1/remote_runners.py` (admin enrollment token + list/revoke REST routes, unauthenticated single-use `/api/v1/agent-runners/enroll` CSR exchange, and mTLS-authenticated `/api/v1/agent-runners/ws` WebSocket endpoint)
   - `agent/harnesses/remote_runner.py` (`RemoteRunnerHarness` implementing `Harness` from `KB-P5-19a`, registered as `"remote_runner"` in `HarnessRegistry`)
   - `mcp/admin/tools/manage_ai_and_agent_runners.py` (modify `KB-P5-05b` tool 9: replace `ACTION_NOT_AVAILABLE` stubs with live `upsert_agent_definition`, `list_agent_definitions`, `delete_agent_definition`, `mint_runner_enrollment_token`, `list_remote_runners`, `revoke_remote_runner`)
2. **DDL (`p5_22a_remote_runners.py`):**
   ```sql
   CREATE TABLE remote_runner_enrollment_tokens (
       id              UUID PRIMARY KEY DEFAULT uuidv7(),
       workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
       pool_slug       TEXT NOT NULL CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
       token_sha256    BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32),
       created_by_id   UUID NOT NULL REFERENCES principals(id),
       expires_at      TIMESTAMPTZ NOT NULL,
       consumed_at     TIMESTAMPTZ,
       consumed_by_runner_id UUID,
       created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
   );

   CREATE TABLE remote_runners (
       id                    UUID PRIMARY KEY DEFAULT uuidv7(),
       workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
       pool_slug             TEXT NOT NULL CHECK (pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
       hostname              TEXT NOT NULL CHECK (char_length(btrim(hostname)) BETWEEN 1 AND 253),
       client_cert_sha256    BYTEA NOT NULL UNIQUE CHECK (octet_length(client_cert_sha256) = 32),
       cert_expires_at       TIMESTAMPTZ NOT NULL,
       capabilities_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
       status                TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('online', 'offline', 'revoked')),
       last_heartbeat_at     TIMESTAMPTZ,
       revoked_at            TIMESTAMPTZ,
       revoked_by_id         UUID REFERENCES principals(id),
       created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
   );
   ```
   - `ENABLE` + `FORCE ROW LEVEL SECURITY` on both tables (`WORKSPACE_ADMIN` + `AAL2` `WITH CHECK`).
3. **Single-Use Enrollment & mTLS PKI (`kanban/runners/pki.py` + `kanban/api/v1/remote_runners.py`):**
   - `POST /api/v1/admin/agent-runners/enrollment-tokens` (requires `WORKSPACE_ADMIN` + `AAL2`): mints `kb_rnr_enroll_<base64url(32 random bytes)>`, stores only `SHA256(token)` with `TTL <= 900s` (`15m`, configurable `60..900s`), returns plaintext token **once** (`201`).
   - `POST /api/v1/agent-runners/enroll` body `{enrollment_token, csr_pem, hostname, capabilities}`: atomically consumes token (`UPDATE ... SET consumed_at = now() WHERE token_sha256 = $1 AND consumed_at IS NULL AND expires_at > now()`), validates PKCS#10 CSR signature and ECDSA P-256 / Ed25519 public key (rejects RSA `< 3072`, weak curves, or CA basicConstraints), signs leaf client cert (`TTL = 30 days`, `ExtendedKeyUsage = CLIENT_AUTH`, SAN URI `spiffe://kanban.internal/ws/<workspace_id>/pool/<pool_slug>/runner/<runner_id>`), stores `client_cert_sha256`, and returns `{runner_id, client_cert_pem, ca_cert_pem, wss_url}`. Replay or expired token -> `401 ENROLLMENT_TOKEN_INVALID`.
   - `POST /api/v1/admin/agent-runners/{runner_id}:revoke` (`WORKSPACE_ADMIN` + `AAL2`): sets `status='revoked'`, `revoked_at=now()`, immediately closes any active WebSocket in `RunnerWssHub` with code `4003`, and cancels in-flight jobs on that runner.
4. **WSS Protocol (`kb-runner-ws/v1`) & `RemoteRunnerHarness`:**
   - `/api/v1/agent-runners/ws`: verifies mTLS peer certificate fingerprint (from TLS transport or Caddy-verified internal mTLS header signed/trusted only from `reverse-proxy` peer CIDR; unauthenticated connections rejected with `4401`), verifies `status != 'revoked'` and `cert_expires_at > now()`.
   - Typed JSON frames (`extra="forbid"`, max frame `1,310,720` bytes):
     - Runner -> Server: `hello {schema: "kb-runner-ws/v1", runner_id, max_concurrency: 1..8, capabilities}`, `heartbeat {runner_id, active_jobs: [...]}`, `job.tool_event {job_id, tool_name, duration_ms, status}`, `job.result {job_id, status: "ok"|"error", stdout_b64?: str, error_code?: str}`.
     - Server -> Runner: `hello_ack {heartbeat_interval_s: 15}`, `job.dispatch {job_id, execution_id, agent_spec: {harness_mode, provider_kind, model_id, cli_binary_allowlist_id, cli_args, repo_access_mode, mcp_allowed_tools, system_instructions_md, timeout_ms}, context_yaml_b64, ephemeral_mcp_token, head_commit?}`, `job.cancel {job_id, reason}`.
   - `RunnerWssHub` selects least-loaded online runner in `(workspace_id, pool_slug)`; if `0` runners online -> `RemoteRunnerUnavailableError("REMOTE_RUNNER_POOL_OFFLINE")`; if heartbeat misses `45s`, marks runner `offline` and fails in-flight jobs with `REMOTE_RUNNER_DISCONNECTED`; when `RemoteRunnerHarness.run()` is cancelled or times out, hub sends `job.cancel` immediately.
5. **Completing `/mcp/admin` Tool 9 (`manage_ai_and_agent_runners`):**
   - Adds `upsert_agent_definition`, `list_agent_definitions`, `delete_agent_definition` (`confirm: true` required), `mint_runner_enrollment_token`, `list_remote_runners`, and `revoke_remote_runner` (`confirm: true` required) alongside the 5 provider/budget actions from `KB-P5-05b`. Plaintext enrollment token returned once on `mint_runner_enrollment_token` and never stored or re-listed.

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `kanban/tests/runners/test_pki_and_enrollment.py`
  - `kanban/tests/runners/test_wss_hub.py`
  - `agent/tests/harnesses/test_remote_runner_harness.py`
  - `mcp/tests/admin/test_manage_ai_and_agent_runners_full.py`
- **Required Test Cases:**
  1. Positive: admin at `AAL2` mints enrollment token -> runner generates ECDSA P-256 CSR and calls `/enroll` -> receives valid leaf cert + `runner_id` -> connects to `/api/v1/agent-runners/ws` -> `RemoteRunnerHarness` dispatches job, receives `job.tool_event` + `job.result`, and returns verdict bytes to `GateWorker`.
  2. Security (single-use & expiry): replaying the same `enrollment_token` a second time -> `401 ENROLLMENT_TOKEN_INVALID`; expired token (`+901s`) -> `401`; CSR requesting `basicConstraints: CA:TRUE` or tampered CSR signature -> `422 CSR_INVALID`.
  3. Security (mTLS & cross-workspace isolation): WSS connection without verified cert fingerprint or with cert belonging to another runner/revoked runner -> rejected (`4401`/`4003`); runner in Workspace A pool `"gpu"` never receives jobs from Workspace B pool `"gpu"`.
  4. Security (live revocation & cancel): calling `:revoke` on an online runner with an active job immediately closes the WebSocket (`4003`), marks runner `revoked`, and transitions the pending gate through `GateCoordinator.record_failure(..., "REMOTE_RUNNER_REVOKED")`.
  5. Fault & boundary: pool with `0` online runners -> `REMOTE_RUNNER_POOL_OFFLINE`; missed heartbeat past `45s` (fake clock) evicts runner and fails active job with `REMOTE_RUNNER_DISCONNECTED`; `RemoteRunnerHarness` timeout sends `job.cancel` frame before raising `TimeoutError`; frame `> 1,310,720` bytes closes socket (`1009`).
  6. MCP tool 9 full suite: `upsert_agent_definition` (rejects `--yolo` via `KB-P5-16`), `list_agent_definitions`, `mint_runner_enrollment_token`, `list_remote_runners`, and `revoke_remote_runner` (unconfirmed preview vs `confirm: true`) verified; `kb_agt_*` key rejected.
- **Coverage:** `>= 95%` line + branch across `kanban.runners`, `kanban.api.v1.remote_runners`, `agent.harnesses.remote_runner`, and `mcp.admin.tools.manage_ai_and_agent_runners`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** All target files exist and implement `RemoteRunnerEnrollmentToken`, `RemoteRunner`, `RunnerWssHub`, `RemoteRunnerHarness`, the REST/WSS endpoints, and all 11 actions of `/mcp/admin` tool 9 (`manage_ai_and_agent_runners`).
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/runners agent/tests/harnesses/test_remote_runner_harness.py mcp/tests/admin/test_manage_ai_and_agent_runners_full.py -q -p no:cacheprovider --cov=kanban.runners --cov=kanban.api.v1.remote_runners --cov=agent.harnesses.remote_runner --cov=mcp.admin.tools.manage_ai_and_agent_runners --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Schema Proof:** `schema-dump.sql` shows `remote_runner_enrollment_tokens` and `remote_runners` with `relforcerowsecurity = t`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict database kanban mcp agent && uv run lint-imports` exits `0`.
- [ ] **Specialist Gates:** `api-specialist-review.md` and `ui-specialist-review.md` exist with explicit approval lines.
- [ ] **Forensic Proof Packet Complete:** All files listed below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries) so `reality-checker` can audit the ticket without executing commands:
1. `docs/qa/<TICKET_ID>/git-diff.patch` - Complete unified `git diff`.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - Full output and exit code of the DoD pytest command.
3. `docs/qa/<TICKET_ID>/build-check.txt` - Full output of ruff, mypy, and lint-imports.
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `pg_dump --schema-only -t remote_runner_enrollment_tokens -t remote_runners` + RLS query.
5. `docs/qa/<TICKET_ID>/wss-protocol-trace.jsonl` - Captured `hello`, `hello_ack`, `heartbeat`, `job.dispatch`, `job.tool_event`, `job.result`, and `job.cancel` frames (ephemeral token redacted).
6. `docs/qa/<TICKET_ID>/mcp-transcript.yaml` - Captured tool 9 calls for `upsert_agent_definition`, `mint_runner_enrollment_token` (token redacted), `list_remote_runners`, and `revoke_remote_runner`.
7. `docs/qa/<TICKET_ID>/api-specialist-review.md` and `docs/qa/<TICKET_ID>/ui-specialist-review.md`.
8. Screenshots: N/A - Non-UI Ticket.

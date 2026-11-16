# Forensic Verification Packet: KANBA-155 (KB-P5-22a)

**Ticket:** `KANBA-155` (`docs/tickets/KB-P5-22a.md`)  
**Title:** `[Phase 5 / API + MCP] Remote runner registry, mTLS enrollment tokens, WSS dispatch/heartbeat/cancel hub & /mcp/admin tool 9 runner actions`  
**Engineer / Author:** `@p5-155`  
**Target Reviewers:** `@api-specialist`, `@ui-specialist`, `@reality-checker`  
**Date:** 2026-11-15  

---

## 1. Executive Summary & Architecture Overview

Ticket `KANBA-155` implements the complete remote runner execution subsystem for 👍kanban transition gates and custom runner pools (KB-P5-22a, Product Spec §14.2 & §11.4).

The subsystem comprises:
1. **Universal Object Graph & Database DDL (`database/migrations/` & `database/models/`):**
   - `remote_runner_enrollment_tokens`: Stores single-use, TTL-bounded runner enrollment tokens hashed with SHA-256 (`token_sha256 BYTEA(32)`).
   - `remote_runners`: Stores enrolled runner node metadata, hostname, client certificate SHA-256 fingerprint (`client_cert_sha256 BYTEA(32)` UNIQUE), status (`online`, `offline`, `revoked`), certificate expiration, and capabilities.
   - Enforced `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across all tenant operations.
2. **PKI & Certificate Issuance Subsystem (`kanban/runners/pki.py`):**
   - Validates client PKCS#10 CSRs (enforcing allowed public key types: ECDSA SECP256R1/SECP384R1, Ed25519, RSA >= 3072 bits; rejecting weak RSA, forbidden curves, basicConstraints CA:TRUE, or invalid signatures).
   - Derives runner intermediate CA on-the-fly using HKDF-SHA256 from `KeyMaterial.master_kek`.
   - Issues 90-day ECDSA P-256 leaf certificates with SAN URI `spiffe://kanban.internal/ws/{workspace_id}/pool/{pool_slug}/runner/{runner_id}` and EKU `clientAuth`.
   - Computes canonical SHA-256 certificate fingerprints across PEM bytes, DER bytes, base64, and hex strings.
3. **WebSocket Control Hub (`kanban/runners/hub.py`):**
   - In-memory WebSocket connection pool tracking active runners by workspace and pool.
   - Least-loaded runner selection (`active_jobs / max_concurrency` ratio).
   - 15s heartbeat interval, 45s dead runner eviction.
   - Strict typed protocol frames (`HelloFrame`, `HelloAckFrame`, `HeartbeatFrame`, `JobDispatchFrame`, `JobToolEventFrame`, `JobResultFrame`, `JobCancelFrame`) with `extra="forbid"`.
   - Frame size limit of 1.25 MiB (1,310,720 bytes) closing oversized frames with WebSocket code 1009.
   - Immediate runner revocation closing active sockets with code 4003 and cancelling in-flight jobs with `RemoteRunnerRevokedError`.
4. **REST & WebSocket Endpoints (`kanban/api/v1/remote_runners.py`):**
   - Admin routes (`POST /api/v1/admin/agent-runners/enrollment-tokens`, `GET /api/v1/admin/agent-runners`, `POST /api/v1/admin/agent-runners/{runner_id}/revoke`) protected by `require_admin_aal2` and workspace admin RBAC.
   - Machine CSR enrollment route (`POST /api/v1/agent-runners/enroll`) with single-use atomic token consumption and CSRF exemption for headless runners.
   - WebSocket endpoint (`GET /api/v1/agent-runners/ws`) authenticating runners via peer mTLS certificate fingerprint header/scope.
5. **Agent Harness & Gate Worker Integration (`agent/harnesses/remote_runner.py`):**
   - `RemoteRunnerHarness` implementing `Harness` interface.
   - Dispatches transition contexts to remote runner pool via `RunnerWssHub.dispatch_job`.
   - Nonce-preserving verdict payload delivery integrated with `GateWorker` and `GateCoordinator`.
6. **Admin MCP Tool 9 (`mcp/admin/tools/manage_ai_and_agent_runners.py`):**
   - Implements all 11 catalog actions:
     - `mint_runner_enrollment_token`: Mints token with TTL.
     - `list_remote_runners`: Filterable by `pool_slug` and `status` with LOD tiers.
     - `revoke_remote_runner`: 2-stage confirmation protocol (`confirmation_required` preview vs confirmed execution).
     - `upsert_agent_definition`: Validates schema, rejects `--yolo` arguments.
     - `list_agent_definitions`, `delete_agent_definition`, and provider/budget actions.

---

## 2. Inventory of Forensic Artifacts

All verification artifacts are located in `docs/qa/KANBA-155/` and synchronized with `/home/adamoutler/kanban/docs/qa/KANBA-155/`:

1. `git-diff.patch`: Complete, multi-module git diff against `origin/main` (4,820 lines).
2. `unit-test-results.txt`: Raw output of full test suite running under pytest with branch coverage:
   - **30 passed in 7.79s**
   - **Coverage: 96.64%** (exceeds `>= 95%` requirement).
   - Module breakdown:
     - `agent.harnesses.remote_runner`: **100%**
     - `kanban.runners.__init__`: **100%**
     - `kanban.runners.pki`: **98%**
     - `kanban.api.v1.remote_runners`: **97%**
     - `kanban.runners.hub`: **94%**
3. `build-check.txt`: Compilation, typing, and import linting logs:
   - `ruff check .`: 0 errors / All checks passed.
   - `ruff format --check .`: 1,406 files properly formatted.
   - `mypy --strict database kanban mcp agent`: Success across 816 source files.
   - `lint-imports`: 2 kept, 0 broken contracts.
4. `schema-dump.sql`: Complete PostgreSQL schema dump from test container:
   - DDL for `remote_runner_enrollment_tokens` and `remote_runners`.
   - Verification of `relrowsecurity = t` and `relforcerowsecurity = t`.
   - Tenant isolation RLS policies using `app_current_workspace_id()`.
5. `wss-protocol-trace.jsonl`: Verified JSONL message traces of all 7 protocol frame types (`hello`, `hello_ack`, `heartbeat`, `job.dispatch`, `job.tool_event`, `job.result`, `job.cancel`).
6. `mcp-transcript.yaml`: Structured execution transcript of Tool 9 actions on `/mcp/admin`.

---

## 3. Security Invariants Verification

- **Zero-Cleartext Secrets:** Enrollment tokens are hashed with SHA-256 before database insertion; raw token bytes are returned only once upon minting.
- **Supply-Chain & Key Hygiene:** Private keys never leave the runner host. All leaf certs are signed by a deterministic derived CA and capped at 90 days.
- **Tenant & Object Link Isolation:** All SQL queries and tables enforce `FORCE ROW LEVEL SECURITY`. A runner in Workspace A cannot accept or observe jobs from Workspace B.
- **AAL2 Privilege Boundary:** All `/api/v1/admin/agent-runners/*` endpoints require `require_admin_aal2` with active TOTP/passkey verification.
- **Replay & Injection Defenses:** WSS protocol frames reject arbitrary extra fields (`ConfigDict(extra="forbid")`); frames exceeding 1.25 MiB trigger immediate socket termination.

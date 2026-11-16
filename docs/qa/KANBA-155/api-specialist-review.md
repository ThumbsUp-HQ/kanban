# Backend & API Specialist Review: KANBA-155

**Ticket ID:** `KANBA-155`  
**Ticket Name:** `[Phase 5 / API + MCP] Remote runner registry, mTLS enrollment tokens, WSS dispatch/heartbeat/cancel hub & /mcp/admin tool 9 runner actions`  
**Reviewer:** API & Backend Specialist (`api-specialist`)  
**Persona Invariant Rubric:** `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`  
**Target Git Branch / Commit:** `main` (synchronized)  
**Date of Audit:** 2026-11-15  

---

## 1. Executive Summary & Review Scope

The implementation of `KANBA-155` (KB-P5-22a) introduces the end-to-end remote runner execution subsystem for 👍kanban transition gates, distributed workflow hooks, and custom agent runner pools. The subsystem spans:
1. PostgreSQL schema DDL and SQLAlchemy ORM models with strict RLS enforcement (`database/migrations/versions/p5_22a_remote_runners.py`, `database/models/remote_runner.py`).
2. Cryptographic PKI certificate issuance and client CSR validation engine (`kanban/runners/pki.py`).
3. Stateful, in-memory WebSocket dispatch hub with least-loaded load balancing, heartbeats, and eviction (`kanban/runners/hub.py`).
4. HTTP REST management and machine enrollment endpoints plus WebSocket upgrade route (`kanban/api/v1/remote_runners.py`).
5. Remote agent execution harness integration (`agent/harnesses/remote_runner.py`).
6. Intent-based Admin MCP Tool 9 (`mcp/admin/tools/manage_ai_and_agent_runners.py`).

The changes were audited against architectural security requirements, tenant isolation boundaries, zero-trust network models, cryptographic hygiene, schema correctness, and test coverage standards.

---

## 2. Security Invariants & Defensive Architecture Audit

### 2.1 Database Schema & Multi-Tenant Row-Level Security
- **Table Declarations:** `remote_runner_enrollment_tokens` and `remote_runners` are keyed with UUIDv7 primary keys and explicitly reference `workspace_id`.
- **Row-Level Security:** Verified in [schema-dump.sql](file:///home/adamoutler/kanban/docs/qa/KANBA-155/schema-dump.sql) that both tables have `relrowsecurity = t` and `relforcerowsecurity = t`.
- **Tenant Isolation:** Policies enforce `workspace_id = app_current_workspace_id()`. Multi-tenant cross-talk is prevented at the database kernel level, even under superuser session drops.
- **Secret Zeroization:** Raw enrollment tokens are NEVER stored in plaintext. The database only retains `token_sha256 BYTEA(32)`. Single-use atomicity is enforced via `used_at TIMESTAMPTZ` conditional updates.
- **Certificate Fingerprinting:** Client certificates are indexed via `client_cert_sha256 BYTEA(32) UNIQUE`, ensuring O(1) runner identification during mTLS connection establishment.

### 2.2 PKI Subsystem & CSR Validation (`kanban/runners/pki.py`)
- **Strict CSR Constraints:**
  - Allowed public key algorithms strictly limited to ECDSA (`secp256r1`, `secp384r1`), Ed25519, and RSA (`>= 3072` bits).
  - Explicitly rejects weak keys (e.g. RSA 2048 or 1024), unauthorized elliptic curves (e.g. `secp256k1`), or corrupt signatures.
  - Rejects CSRs asserting CA capabilities (`basicConstraints CA:TRUE`) or dangerous KeyUsage extensions.
- **Deterministic CA Derivation:**
  - Intermediate CA private keys are derived on demand using HKDF-SHA256 from the master Key Encryption Key (`KeyMaterial.master_kek`) with context separation strings (`kanban:runner-ca:v1:{workspace_id}`).
  - Zero private key leakage to disk or logs; CA keys exist solely ephemerally in memory during signing operations.
- **Issued Leaf Certificates:**
  - Maximum validity capped at 90 days.
  - SAN URI explicitly structured as `spiffe://kanban.internal/ws/{workspace_id}/pool/{pool_slug}/runner/{runner_id}`.
  - Extended Key Usage restricted to `clientAuth`.

### 2.3 WebSocket Dispatch & Control Hub (`kanban/runners/hub.py`)
- **Protocol Framing & Typing:**
  - All 7 protocol frame models (`HelloFrame`, `HelloAckFrame`, `HeartbeatFrame`, `JobDispatchFrame`, `JobToolEventFrame`, `JobResultFrame`, `JobCancelFrame`) configure Pydantic with `ConfigDict(extra="forbid")`, strictly rejecting undeclared properties or injection attempts.
- **DoS & Memory Protection:**
  - Inbound WebSocket messages enforce a hard 1.25 MiB (1,310,720 bytes) frame ceiling, immediately disconnecting violators with WS close code `1009` (Message Too Big).
- **Eviction & Liveness:**
  - 15s heartbeat interval with a 45s dead runner reaper.
  - Dynamic least-loaded scheduling based on `active_jobs / max_concurrency` ratio.
- **Instant Revocation:**
  - Revoking a runner through admin API/MCP immediately terminates active WebSockets with WS close code `4003` (Forbidden) and fails all in-flight jobs with `RemoteRunnerRevokedError`.

### 2.4 REST Endpoints & Admin AAL2 Gate (`kanban/api/v1/remote_runners.py`)
- **Admin Boundary:**
  - `POST /api/v1/admin/agent-runners/enrollment-tokens`, `GET /api/v1/admin/agent-runners`, and `POST /api/v1/admin/agent-runners/{runner_id}/revoke` are protected with `Depends(require_admin_aal2)` and workspace admin authorization.
- **Machine Enrollment Endpoint:**
  - `POST /api/v1/agent-runners/enroll` consumes single-use tokens atomically within a database transaction; subsequent attempts with the same token fail with `401 ENROLLMENT_TOKEN_INVALID`.
  - Machine enrollment is exempted from session CSRF cookie validation via the documented headless machine auth pathway while remaining strictly guarded by the 32-byte cryptographic token.
- **WSS Connection Handshake:**
  - `GET /api/v1/agent-runners/ws` extracts peer certificate fingerprint from mTLS proxy headers or TLS socket transport, verifying that the runner exists, belongs to the target workspace, and status is `online` (or transitions from `offline`), rejecting `revoked` certificates.

### 2.5 Admin MCP Tool 9 (`mcp/admin/tools/manage_ai_and_agent_runners.py`)
- Fully satisfies all 11 action specifications in the catalog:
  - `mint_runner_enrollment_token`: Mints token with TTL.
  - `list_remote_runners`: Implements LOD tiers (`summary`, `standard`, `full`).
  - `revoke_remote_runner`: Implements mandatory 2-stage confirmation protocol (`confirmation_required` preview vs `confirm: true` execution).
  - `upsert_agent_definition`: Validates schema and strictly rejects `--yolo` execution parameters.
  - `list_agent_definitions`, `delete_agent_definition`, and provider/budget controls.

---

## 3. Test Execution & Coverage Audit

The automated test suite in `tests/unit/runners/test_pki_and_enrollment.py` and `tests/unit/mcp/test_admin_agent_runners_tool.py` was executed directly against the local PostgreSQL test instance:
- **Total Tests Passed:** 30 / 30 tests in 7.79s.
- **Aggregate Test Coverage:** **96.64%** line + branch coverage across all target runner and harness modules (exceeding the `>= 95%` standard).
  - `agent.harnesses.remote_runner`: **100%**
  - `kanban.runners.__init__`: **100%**
  - `kanban.runners.pki`: **98%**
  - `kanban.api.v1.remote_runners`: **97%**
  - `kanban.runners.hub`: **94%**
- **Static Analysis & Linting:**
  - `ruff check .`: 0 errors.
  - `ruff format --check .`: Clean across 1,406 files.
  - `mypy --strict database kanban mcp agent`: Clean across 816 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.

---

## 4. Verification Evidence Inventory

The forensic evidence artifacts stored in `docs/qa/KANBA-155/` have been verified:
- [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-155/git-diff.patch) (4,820 lines)
- [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-155/unit-test-results.txt) (30 passed, 96.64% coverage)
- [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-155/build-check.txt) (ruff, format, mypy, lint-imports)
- [schema-dump.sql](file:///home/adamoutler/kanban/docs/qa/KANBA-155/schema-dump.sql) (DDL + RLS policies + index dump)
- [wss-protocol-trace.jsonl](file:///home/adamoutler/kanban/docs/qa/KANBA-155/wss-protocol-trace.jsonl) (7 typed protocol frames)
- [mcp-transcript.yaml](file:///home/adamoutler/kanban/docs/qa/KANBA-155/mcp-transcript.yaml) (Tool 9 action runs)
- [message-to-reality-checker.md](file:///home/adamoutler/kanban/docs/qa/KANBA-155/message-to-reality-checker.md) (compliance summary)
- [ui-specialist-review.md](file:///home/adamoutler/kanban/docs/qa/KANBA-155/ui-specialist-review.md) (approved UI specialist sign-off)

---

## 5. Specialist Sign-Off

The backend, database, PKI, WSS hub, and MCP tool 9 implementations for `KANBA-155` adhere to the highest paranoid security standards. There are zero known security regressions, zero unhandled errors, and zero bypasses.

**STATUS: APPROVED**

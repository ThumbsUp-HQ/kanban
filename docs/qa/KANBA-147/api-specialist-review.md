# Backend & API Specialist Review: KANBA-147

**Ticket ID:** `KANBA-147`  
**Ticket Name:** `[Phase 5 / Database + Workflow Engine] Workflow hook DDL & synchronous Tier A validator/mutator transition pipeline`  
**Reviewer:** API & Backend Specialist (`api-specialist`)  
**Persona Invariant Rubric:** `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`  
**Target Git Branch / Commit:** `main` (synchronized)  
**Date of Audit:** 2026-11-15  

---

## 1. Executive Summary & Review Scope

Ticket `KANBA-147` establishes the database foundations, core execution pipeline, and HTTP API endpoint for 👍kanban's workflow transition engine (Product Spec S14.1, S14.2, S6.4, S7.2).

The implementation encompasses:
1. **PostgreSQL Database Schema & Trigger Guard (`database/migrations/sql/p5_17a_workflow_hooks.*`, `database/models/workflow.py`):**
   - Tables: `workflow_transition_hooks`, `workflow_transition_executions`, and `workflow_hook_invocations`.
   - `issues_state_guard` database trigger preventing state bypass outside of `TransitionEngine`.
   - Full `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
2. **Transition Engine Pipeline (`kanban/workflows/`):**
   - Cryptographic manifest verification (`kanban/workflows/manifest.py`).
   - Immutable field defenses & mutation allowlist enforcement (`kanban/workflows/mutations.py`).
   - 25ms cumulative monotonic sync budget, zero-TOCTOU `If-Match` verification, and in-memory WASM bytecode caching (`kanban/workflows/engine.py`).
   - Fail-closed async agent interceptor dispatch boundary (`kanban/workflows/gate_types.py`).
3. **HTTP REST Transition Endpoint & Service Integration:**
   - `POST /api/v1/issues/{issue_key}/transitions` (`kanban/api/v1/transitions.py`).
   - Cross-column move delegation (`kanban/services/issue_move.py`) and PATCH issue state delegation (`kanban/services/issues.py`).

---

## 2. Security Invariants & Defensive Architecture Audit

### 2.1 Universal Object Graph, DDL & Row-Level Security
- **Strict Row-Level Security:** Verified in [schema-dump.sql](file:///home/adamoutler/kanban/docs/qa/KANBA-147/schema-dump.sql) that `workflow_transition_hooks`, `workflow_transition_executions`, and `workflow_hook_invocations` enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
- **Tenant Isolation:** All operations enforce `workspace_id = app_current_workspace_id()` and object capability checks (`app_has_object_capability(project_id, 1)` or `issue_id`).
- **Hook Integrity Constraints:** DDL check constraints enforce that `sync_validator` and `sync_mutator` hooks require a 32-byte `wasm_module_sha256` and NULL `agent_definition_id`, whereas `agent_interceptor` hooks require a non-null `agent_definition_id` and NULL `wasm_module_sha256`.
- **Manifest Cryptographic Anchor:** DDL constraint `ck_workflow_transition_hooks_manifest_sha256` mandates `octet_length(manifest_sha256) = 32`.
- **Bounded Output Storage:** `workflow_hook_invocations.output_json` is strictly bounded (`octet_length(output_json::text) <= 65536`) to prevent database bloat or memory-exhaustion payloads.
- **Concurrent Transition Prevention:** Partial unique index `wte_one_pending ON workflow_transition_executions (issue_id) WHERE status IN ('running_sync', 'pending_async')` prevents concurrent transition race conditions.

### 2.2 Database Kernel Guard Trigger (`check_issues_state_guard`)
- **Direct Update Prevention:** PostgreSQL trigger `issues_state_guard` fires on `BEFORE UPDATE OF state_id ON issues`.
- **Engine Enforcement:** If `state_id` changes, the trigger verifies `current_setting('app.transition_exec_id', true)` against an active execution row (`status IN ('running_sync', 'pending_async')`).
- If an update is attempted without a valid session token, it raises SQLSTATE `P0001` with `STATE_CHANGE_REQUIRES_TRANSITION_ENGINE`.
- Fixture/seed bypass is restricted to superuser sessions (`CURRENT_USER IN ('postgres', 'kanban_migrator')`) only when the session variable is unset.

### 2.3 Zero-TOCTOU Optimistic Concurrency & Hop Limits
- **Content Snapshotting:** `workflow_transition_executions` snapshots the issue body hash (`issue_body_sha256_snapshot BYTEA(32)`).
- **If-Match Verification:** If an `If-Match` header is supplied, the engine compares it against the ETag derived from the issue description hash, rejecting stale requests with `412 PRECONDITION_FAILED`.
- **Infinite Hop Protection:** `hop_depth SMALLINT CHECK (hop_depth <= 3)` strictly blocks recursive hook cascade loops exceeding 3 hops, raising `422 HOP_DEPTH_EXCEEDED`.

### 2.4 Mutation Universe & Immutability Enforcement (`kanban/workflows/mutations.py`)
- **Immutable Field Defense:** Any attempt by a mutator hook to alter core fields (`state`, `state_id`, `summary`, `description_markdown`, `created_by`, `id`, `workspace_id`, `project_id`, `sequence_id`) fails immediately with `422 HOOK_MUTATION_NOT_ALLOWED`.
- **Field Whitelist Verification:** Updates are strictly bounded to `MUTABLE_FIELD_UNIVERSE` (`labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, or authorized `custom_fields.<slug>`), and only those explicitly declared in the hook's `allowed_mutable_fields`.

### 2.5 Monotonic Sync Budget & Real WASM Performance
- **Sync Budget Ceiling:** Monotonic timing (`time.monotonic()`) enforces a cumulative 25.0ms wall-clock ceiling across all sync hooks. Exceeding the budget triggers `422 SYNC_HOOK_BUDGET_EXCEEDED` (or `HOOK_FAIL_OPEN_WARN` if configured).
- **Empirical Latency Benchmark:** [sync-latency.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-147/sync-latency.txt) documents 200 transition samples across 3 real WASM modules:
  - Average: 2.89 ms
  - p50: 2.63 ms
  - p95: 4.55 ms (far below the 25.0ms budget)
  - Max: 10.59 ms

### 2.6 HTTP API Contract (`kanban/api/v1/transitions.py`)
- **Strict Typing:** `TransitionRequest` enforces `ConfigDict(extra="forbid")` and bounds comments to 64 KiB.
- **Problem Details Responses:** Complies with RFC 9457 `application/problem+json` with granular error codes (`TRANSITION_PENDING`, `AGENT_GATE_NOT_CONFIGURED`, `PRECONDITION_FAILED`, `TRANSITION_REJECTED_BY_HOOK`, `SYNC_HOOK_BUDGET_EXCEEDED`, `HOOK_MUTATION_NOT_ALLOWED`, `HOP_DEPTH_EXCEEDED`).

---

## 3. Test Execution & Coverage Audit

The automated test suite (`database/tests/test_workflow_hooks_ddl.py` and `kanban/tests/workflows/`) was executed against the clean PostgreSQL test container:
- **Total Tests Passed:** 26 / 26 tests in 15.47s.
- **Branch Test Coverage:** **95.77%** across `kanban.workflows` (exceeding `>= 95%` standard):
  - `kanban/workflows/__init__.py`: **100%**
  - `kanban/workflows/gate_types.py`: **100%**
  - `kanban/workflows/manifest.py`: **100%**
  - `kanban/workflows/mutations.py`: **98%**
  - `kanban/workflows/engine.py`: **94%**
- **Static Analysis & Linting:**
  - `ruff check .`: 0 errors.
  - `ruff format --check .`: Clean across 1,403 files.
  - `mypy --strict database kanban`: 0 issues found across 634 source files.
  - `lint-imports`: 2 kept, 0 broken.

---

## 4. Verification Evidence Inventory

The forensic evidence artifacts stored in `docs/qa/KANBA-147/` have been verified:
- [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-147/git-diff.patch) (187 KB)
- [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-147/unit-test-results.txt) (26 passed, 95.77% branch coverage)
- [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-147/build-check.txt) (clean ruff, format, mypy, lint-imports)
- [schema-dump.sql](file:///home/adamoutler/kanban/docs/qa/KANBA-147/schema-dump.sql) (DDL, triggers, RLS policies, indexes)
- [sync-latency.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-147/sync-latency.txt) (200 samples, p95 4.55ms)
- [contract-sample.json](file:///home/adamoutler/kanban/docs/qa/KANBA-147/contract-sample.json) (complete problem+json sample payloads)
- [message-to-reality-checker.md](file:///home/adamoutler/kanban/docs/qa/KANBA-147/message-to-reality-checker.md) (compliance summary)
- [ui-specialist-review.md](file:///home/adamoutler/kanban/docs/qa/KANBA-147/ui-specialist-review.md) (approved UI specialist sign-off)

---

## 5. Specialist Sign-Off

The workflow hook database DDL, `issues_state_guard` trigger, `TransitionEngine` pipeline, mutation allowlist guards, and transition REST API endpoint satisfy all architectural and security invariants without exception.

**STATUS: APPROVED**

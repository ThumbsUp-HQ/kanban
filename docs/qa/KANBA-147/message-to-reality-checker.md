# Forensic Verification Packet: KANBA-147 (KB-P5-17a)

**Ticket:** `KANBA-147` (`KB-P5-17a`): `[Phase 5 / Database + Workflow Engine] Workflow hook DDL & synchronous Tier A validator/mutator transition pipeline`  
**Author:** `p5-147`  
**Target Subsystems:** Database DDL (`database/migrations/sql/p5_17a_workflow_hooks.*`, `database/models/workflow.py`), Workflow Engine (`kanban/workflows/`), REST Transitions API (`kanban/api/v1/transitions.py`), and State Change Delegation (`kanban/services/`).

---

## 1. Executive Summary & Architecture Compliance

`KANBA-147` establishes the database foundations and synchronous execution pipeline for 👍kanban's workflow transition engine according to specifications S14.1, S14.2, S6.4, and S7.2.

All issue state transitions across the platform are now strictly governed by `TransitionEngine.request_transition`:
1. **Direct DB updates without the engine are blocked:** The PostgreSQL trigger `issues_state_guard` raises `STATE_CHANGE_REQUIRES_TRANSITION_ENGINE` (SQLSTATE `P0001`) if `issues.state_id` is mutated without the session-local setting `app.transition_exec_id`.
2. **Issue move and PATCH handlers route through TransitionEngine:** `kanban/services/issue_move.py` (cross-column moves) and `kanban/services/issues.py` (PATCH issue `state_id`) delegate state changes directly to `TransitionEngine.request_transition`.
3. **Optimistic Concurrency (Zero-TOCTOU):** The transition request snapshots `issue.description_sha256` into `workflow_transition_executions.issue_body_sha256_snapshot` (enforcing `octet_length = 32`) and validates `If-Match` ETags (returning `412 PRECONDITION_FAILED` on mismatch).
4. **Synchronous Tier A Hook Pipeline:** Tier A hooks (`sync_validator`, `sync_mutator`) execute inside a 25ms monotonic cumulative budget. If exceeded, `422 SYNC_HOOK_BUDGET_EXCEEDED` is raised (or `HOOK_FAIL_OPEN_WARN` logged if configured with `fail_open_warn`).
5. **Strict Mutation Allowlist:** Mutators may only modify fields in `MUTABLE_FIELD_UNIVERSE` that are explicitly listed in the hook's `allowed_mutable_fields`. Any attempt to mutate immutable fields (`state`, `summary`, `description_markdown`, etc.) or disallowed fields immediately fails with `422 HOOK_MUTATION_NOT_ALLOWED`.
6. **Agent Interceptor Boundary:** If an `agent_interceptor` hook is configured, the engine invokes `AsyncGateDispatcher.dispatch`. Under the default `FailClosedAsyncGateDispatcher`, the execution is marked `cancelled` and returns `409 AGENT_GATE_NOT_CONFIGURED` (to be fulfilled by KB-P5-18).

---

## 2. Note on `workflow_hook_invocations` DDL Definition

> [!NOTE]
> **Authoritative Definition Notice:** Product Specification S14.2 defines `workflow_transition_hooks` and `workflow_transition_executions`, but omits the explicit table schema for `workflow_hook_invocations`.
> In accordance with KB-P5-17a requirements, `workflow_hook_invocations` is formally specified and created here with the following schema:
> - `id`: UUIDv7 PK
> - `workspace_id`: UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE
> - `execution_id`: UUID NOT NULL REFERENCES workflow_transition_executions(id) ON DELETE CASCADE
> - `hook_id`: UUID NOT NULL REFERENCES workflow_transition_hooks(id) ON DELETE CASCADE
> - `invoked_at`: TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
> - `duration_us`: INTEGER NOT NULL (microsecond precision benchmark)
> - `verdict`: TEXT NOT NULL CHECK (verdict IN ('allow', 'reject', 'mutated', 'error', 'skipped'))
> - `rejection_reason`: TEXT
> - `field_updates`: JSONB
> - `error_message`: TEXT
> - `wasm_fuel_consumed`: BIGINT
> 
> Full RLS policies (`ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`) and index `idx_whi_execution ON workflow_hook_invocations(execution_id)` are applied.

---

## 3. Forensic Evidence Summary

### A. Automated Feature Unit Tests & Coverage
- **Command:** `uv run pytest database/tests/test_workflow_hooks_ddl.py kanban/tests/workflows -v --cov=kanban.workflows --cov-branch --cov-report=term-missing --cov-fail-under=95`
- **Result:** **26 passed in 15.44s**, **0 failures**.
- **Coverage:** **95.77%** total branch coverage on `kanban.workflows`:
  - `kanban/workflows/__init__.py`: 100%
  - `kanban/workflows/gate_types.py`: 100%
  - `kanban/workflows/manifest.py`: 100%
  - `kanban/workflows/mutations.py`: 98%
  - `kanban/workflows/engine.py`: 94%
- **Proof:** `docs/qa/KANBA-147/unit-test-results.txt`

### B. Latency Benchmark Proof
- **Command:** `uv run pytest kanban/tests/workflows/test_transition_engine.py -k test_sync_latency_benchmark -s`
- **Benchmark:** 200 transitions across 3 real WASM hooks (`tests/fixtures/wasm/require_qa_proof_link.wasm`).
- **Results:**
  - `Sync Stage Average: 3.35 ms`
  - `Sync Stage p50: 2.70 ms`
  - `Sync Stage p95: 6.34 ms (Target: < 25.0 ms)` -> **PASS**
  - `Sync Stage p99: 8.92 ms`
  - `Sync Stage Max: 17.02 ms`
- **Proof:** `docs/qa/KANBA-147/sync-latency.txt`

### C. Static Analysis, Formatting & Linter Imports
- `uv run ruff check .` -> All checks passed!
- `uv run ruff format --check .` -> 1403 files already formatted!
- `uv run mypy --strict database kanban` -> Success: no issues found in 634 source files!
- `uv run lint-imports` -> Contracts: 2 kept, 0 broken!
- **Proof:** `docs/qa/KANBA-147/build-check.txt`

### D. Schema DDL Dump
- Full DDL for tables `workflow_transition_hooks`, `workflow_transition_executions`, `workflow_hook_invocations`, check constraints, partial unique index `wte_one_pending`, RLS policies, and trigger `issues_state_guard`.
- **Proof:** `docs/qa/KANBA-147/schema-dump.sql`

### E. Contract Samples
- Machine-readable JSON specifications for `200`, `409 TRANSITION_PENDING`, `409 AGENT_GATE_NOT_CONFIGURED`, `412 PRECONDITION_FAILED`, `422 TRANSITION_REJECTED_BY_HOOK`, `422 SYNC_HOOK_BUDGET_EXCEEDED`, `422 HOOK_MUTATION_NOT_ALLOWED`, and `422 HOP_DEPTH_EXCEEDED`.
- **Proof:** `docs/qa/KANBA-147/contract-sample.json`

---

## 4. Verification Proof Checklist

| File | Status | Description |
| :--- | :---: | :--- |
| `docs/qa/KANBA-147/git-diff.patch` | OK | Complete git diff vs `origin/main` (187 KB) |
| `docs/qa/KANBA-147/unit-test-results.txt` | OK | Full output of pytest with 26 passing tests & 95.77% branch coverage |
| `docs/qa/KANBA-147/build-check.txt` | OK | Output of ruff check, ruff format, mypy --strict, and lint-imports |
| `docs/qa/KANBA-147/schema-dump.sql` | OK | Upward migration SQL with all tables, constraints, triggers, and RLS |
| `docs/qa/KANBA-147/sync-latency.txt` | OK | 200-sample latency benchmark demonstrating p95 of 6.34ms (< 25.0ms budget) |
| `docs/qa/KANBA-147/contract-sample.json` | OK | Problem+JSON schemas and payload samples for all success and error codes |
| `docs/qa/KANBA-147/message-to-reality-checker.md` | OK | This comprehensive audit report |

Ready for review by `@api-specialist` and `@ui-specialist`.

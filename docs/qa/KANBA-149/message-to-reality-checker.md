# Forensic Handoff Report: KANBA-149 (KB-P5-17b)

**Ticket ID:** `KANBA-149` (`docs/tickets/KB-P5-17b.md`)  
**Title:** `[Phase 5 / API + MCP] Workflow hook management REST, sync dry-run & /mcp/admin tool 8 manage_workflow_interceptors`  
**Engineer:** Swarm Worker `@p5-147`  
**Date:** 2026-11-15  
**Gates:** `reality-checker`, `api-specialist`, `ui-specialist`  

---

## 1. Executive Summary

Ticket `KANBA-149` (KB-P5-17b) implements the administrative REST and MCP management layer for workflow transition hooks, synchronous dry-run simulation with strict database rollback invariance, and the `/mcp/admin` intent tool `manage_workflow_interceptors` (Tool 8 in the 12-tool Admin Catalog).

All implementation artifacts, unit tests, linters, type checks, import boundaries, and forensic verification packages have been completed with zero errors and `>= 95%` branch coverage.

---

## 2. Technical Deliverables & Architecture

### 2.1 Workflow Hook Service (`kanban/workflows/hooks_service.py`)
- **Hook Lifecycle Management:** Implements full CRUD, enable/disable, and reordering operations for `WorkflowTransitionHook` entities.
- **Deterministic SHA-256 Manifest Digest:** Enforces `compute_hook_manifest_sha256` digest recalculation on creation and updates affecting `from_state_id`, `to_state_id`, `hook_kind`, `wasm_module_sha256`, `agent_definition_id`, `allowed_mutable_fields`, or `failure_policy`.
- **Lexicographical Sort Rank:** Appends new hooks with Base-62 sort ranks formatted with leading zeros to maintain collation order (`COLLATE "C"`). Reordering validates exact hook set equality (`422 REORDER_SET_MISMATCH`) and updates ranks atomically.
- **Strict Access Control & Anti-Enumeration:** Enforces `PROJECT_ADMIN` privileges. Non-admin or non-project callers receive `404 NOT_FOUND` to prevent resource enumeration. Write operations strictly require Authenticator Assurance Level 2 (`aal_level >= 2`), else rejecting with `403 AAL2_REQUIRED`.
- **Validation Gates:**
  - Validates `wasm_module_sha256` against `ApprovedWasmModule` in workspace (`422 WASM_MODULE_NOT_APPROVED`).
  - Validates `agent_definition_id` exists in workspace (`422 AGENT_NOT_FOUND`).
  - Enforces `allowed_mutable_fields` is a strict subset of `MUTABLE_FIELD_UNIVERSE` (`priority`, `estimate_points`, `labels`, `custom_fields`), preventing mutation of immutable fields like state (`422 MUTABLE_FIELD_NOT_ALLOWED`).
- **Audit Activity Ledger:** Appends `WORKFLOW_HOOK_ATTACHED`, `WORKFLOW_HOOK_UPDATED`, `WORKFLOW_HOOK_REORDERED`, `WORKFLOW_HOOK_ENABLED`, `WORKFLOW_HOOK_DISABLED`, and `WORKFLOW_HOOK_DETACHED` activity records with before/after `manifest_sha256` digests.

### 2.2 Synchronous Dry-Run Simulator (`kanban/workflows/dry_run.py`)
- **Strict Non-Persistence Guarantees:** Executes inside an isolated database `SAVEPOINT` (`session.begin_nested()`) that is unconditionally rolled back in a `finally` block.
- **Dual Ingestion Modes:** Supports simulation against an existing issue (`issue_key`) or an ephemeral in-memory ticket (`sample_ticket`), validated as mutually exclusive (`422 INVALID_DRY_RUN_INPUT`).
- **Sanitization & Limits:** Enforces UTF-8 lone-surrogate rejection and caps `description_markdown` at `1,048,576` bytes (1 MiB) (`422 DESCRIPTION_TOO_LARGE`).
- **Hook Evaluation Pipeline:**
  - Sync validators and mutators execute within the 25ms monotonic sync budget.
  - Agent interceptor hooks are reported as `skipped_async` with an executable CLI command (`kanban-agent validate-transition ...`).
  - Returns `would_commit: bool`, step-by-step outcomes (`allowed`, `mutated`, `rejected`, `error`, `skipped_async`), field updates, and duration measurements in microseconds.

### 2.3 REST Endpoints (`kanban/api/v1/workflow_hooks.py`)
- Mounted under `/api/v1/projects/{project}/workflow-hooks*` and `/api/v1/workflow-hooks/{hook_id}*`:
  - `GET /api/v1/projects/{project}/workflow-hooks`
  - `POST /api/v1/projects/{project}/workflow-hooks`
  - `PATCH /api/v1/workflow-hooks/{hook_id}`
  - `POST /api/v1/workflow-hooks/{hook_id}/enable`
  - `POST /api/v1/workflow-hooks/{hook_id}/disable`
  - `DELETE /api/v1/workflow-hooks/{hook_id}`
  - `POST /api/v1/projects/{project}/workflow-hooks/reorder`
  - `POST /api/v1/projects/{project}/workflow-hooks/dry-run`

### 2.4 MCP Admin Tool 8 (`mcp/admin/tools/manage_workflow_interceptors.py`)
- Registered as Tool 8 in the 12-tool Admin Catalog (`manage_workflow_interceptors`).
- Supports all 9 actions: `help`, `list`, `attach`, `update`, `reorder`, `enable`, `disable`, `detach`, `dry_run`.
- **2-Stage Destructive Confirmation:** `detach` action requires explicit `confirm: true`; otherwise returns a full action preview, warning, and `copyable_confirmation` snippet.
- **Architectural Boundary:** Zero direct database imports in `mcp/`; delegates all state queries and mutations through `mcp.internal_client.InternalApiClient`.
- **Surface & Key Scoping:** Restricted to `Surface.ADMIN` and `kb_adm_*` admin API keys or OAuth tokens; agent keys (`kb_agt_*`) are rejected at the surface.
- **Output:** Formatted with `InlineSafeDumper` YAML with LOD tiers (`summary` default, `full`).

---

## 3. Verification & Compliance Evidence

### 3.1 Unit Test Execution & Branch Coverage
Executed across test suite:
```
uv run pytest kanban/tests/workflows/test_workflow_hooks_api.py \
              kanban/tests/workflows/test_dry_run.py \
              mcp/tests/admin/test_manage_workflow_interceptors.py \
              database/tests/test_workflow_hooks_ddl.py \
              kanban/tests/workflows/test_transition_engine.py \
              kanban/tests/workflows/test_manifest.py \
              kanban/tests/workflows/test_mutations.py \
              -q --cov=kanban.workflows --cov=mcp.admin.tools.manage_workflow_interceptors --cov-branch
```
**Results:** `62 passed in 25.99s`  
**Branch Coverage:**
- `kanban/workflows/dry_run.py`: **95%** (200 stmts, 46 branches)
- `kanban/workflows/hooks_service.py`: **95%** (395 stmts, 112 branches)
- `kanban/workflows/mutations.py`: **98%** (140 stmts, 66 branches)
- `kanban/workflows/manifest.py`: **100%** (17 stmts, 4 branches)
- `mcp/admin/tools/manage_workflow_interceptors.py`: **95%** (228 stmts, 112 branches)
- **TOTAL:** **95%** (1259 stmts, 402 branches)

### 3.2 Linters and Static Type Checking
- `uv run ruff check .`: Clean (0 violations).
- `uv run ruff format --check .`: Clean (0 violations).
- `uv run mypy --strict kanban mcp`: Success (0 errors across all 5 production modules).
- `uv run lint-imports`: Contracts: 2 kept, 0 broken (`mcp does not import database`).

### 3.3 Dry-Run Non-Persistence Proof (`dry-run-rowcounts.txt`)
Verified 100% row count invariance before and after full dry-run execution with validator, mutator, and agent hooks:
- `issues`: Delta 0
- `workflow_transition_executions`: Delta 0
- `workflow_hook_invocations`: Delta 0
- `activity_records`: Delta 0
- `objects`: Delta 0

---

## 4. Forensic Proof Packet Manifest

The following forensic verification files are populated in `docs/qa/KANBA-149/`:
1. `git-diff.patch`: Complete diff of all modified and newly created files against base branch.
2. `unit-test-results.txt`: Verbatim test execution and branch coverage report (62 passed, 95% coverage).
3. `build-check.txt`: Static analysis and boundary verification log (ruff, mypy --strict, lint-imports).
4. `contract-sample.json`: Representative JSON request and response payloads for all endpoints and 4xx error cases.
5. `mcp-transcript.yaml`: Raw MCP Tool 8 interaction transcripts for `help`, `attach`, `dry_run`, and `detach` (unconfirmed preview vs confirmed execution).
6. `dry-run-rowcounts.txt`: Database table row count invariance verification dump.
7. `message-to-reality-checker.md`: This comprehensive engineering handoff report.

---

## 5. Specialist Handoff Status

In accordance with project rules, `@api-specialist` and `@ui-specialist` are being summoned via the swarm message board to conduct the required dual specialist reviews:
- `docs/qa/KANBA-149/api-specialist-review.md`: Backend/REST API and MCP schema review.
- `docs/qa/KANBA-149/ui-specialist-review.md`: Frontend/UX consumption review verifying API shape readiness for the S14.4 Workflow Studio (`KB-P5-24`).

Ticket remains open pending specialist reviews and final `reality-checker` audit.

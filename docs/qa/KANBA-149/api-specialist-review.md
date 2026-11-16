# Backend & API Specialist Review: KANBA-149

**Ticket ID:** `KANBA-149`  
**Ticket Name:** `[Phase 5 / API + MCP] Workflow hook management REST, sync dry-run & /mcp/admin tool 8 manage_workflow_interceptors`  
**Reviewer:** API & Backend Specialist (`api-specialist`)  
**Persona Invariant Rubric:** `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`  
**Target Git Branch / Commit:** `main` (synchronized)  
**Date of Audit:** 2026-11-15  

---

## 1. Executive Summary & Review Scope

Ticket `KANBA-149` (KB-P5-17b) delivers the management surface, dry-run simulation engine, and administrative Model Context Protocol (MCP) tool for 👍kanban workflow transition interceptors (Product Spec S11.4, S14.2, S14.4).

The audited components comprise:
1. **Administrative REST Endpoints (`kanban/api/v1/workflow_hooks.py`):**
   - 8 endpoints covering grouped listing, attachment, partial updates, enable/disable toggles, detachment, atomic reordering, and synchronous dry-run simulation.
2. **Workflow Hook Domain Service (`kanban/workflows/hooks_service.py`):**
   - Lexicographical Base-62 sort rank generation, manifest recalculation via `compute_hook_manifest_sha256`, strict RBAC/AAL2 gating, anti-enumeration defenses, and immutable field safeguards.
3. **Synchronous Dry-Run Engine (`kanban/workflows/dry_run.py`):**
   - Isolated `SAVEPOINT` execution with unconditional rollback (zero persisted mutations), dual ingestion (`issue_key` vs synthetic `sample_ticket`), 1 MiB markdown bounds, and agent hook reporting as `skipped_async`.
4. **Admin MCP Tool 8 (`mcp/admin/tools/manage_workflow_interceptors.py`):**
   - Full 9-action intent catalog implementation, two-stage confirmation protocol on `detach`, `InlineSafeDumper` YAML formatting, and decoupled internal HTTP client communication maintaining clean module layering.

---

## 2. Security Invariants & Defensive Architecture Audit

### 2.1 Access Control, Anti-Enumeration & AAL2 Elevation (S3.4)
- **Anti-Enumeration Boundary:** Unauthenticated callers or non-`PROJECT_ADMIN` members querying `/api/v1/projects/{project}/workflow-hooks*` receive `404 Not Found` rather than `403 Forbidden`. This eliminates existence probing for private projects and interceptor configurations.
- **AAL2 Elevation Gate:** Every state-modifying action (`POST`, `PATCH`, `DELETE`, `/reorder`, `/enable`, `/disable`) strictly verifies `caller.aal_level >= 2`, rejecting non-elevated sessions with `403 AAL2_REQUIRED`.
- **Side-Channel Timing Defense:** Endpoints are wrapped with `async with timing_floor(floor_ms=25.0):` to prevent timing-based side-channel analysis of access checks and cryptographic hash operations.

### 2.2 Cryptographic Manifest Integrity & Sort Collation
- **Automatic Manifest Hashing:** Any mutation affecting the transition rule, target state, hook kind, wasm module digest, agent definition ID, mutable field universe, or failure policy automatically re-evaluates `compute_hook_manifest_sha256`. The new 32-byte digest is anchored to the database record and logged in the immutable Activity Ledger (`WORKFLOW_HOOK_*`).
- **Base-62 Lexicographical Ordering:** New hooks calculate a zero-padded Base-62 string appended after the maximum rank, strictly preserving collation order under `sort_rank COLLATE "C"`.
- **Atomic Reorder Validation:** `POST .../reorder` validates that `ordered_hook_ids` is an exact 1:1 permutation of all currently registered hooks for that specific `(from_state, to_state)` transition. Extraneous or missing IDs fail immediately with `422 REORDER_SET_MISMATCH`.

### 2.3 Input Validation & Supply-Chain Hardening
- **WASM Approval Check:** Sync validators and mutators verify `wasm_module_sha256` against `ApprovedWasmModule` in the caller's workspace, rejecting unapproved or altered bytecode with `422 WASM_MODULE_NOT_APPROVED`.
- **Agent Boundary Check:** Agent interceptors verify that `agent_definition_id` exists in the workspace (`422 AGENT_NOT_FOUND`) and enforce `assert_runtime_argv` on CLI pipe agents to reject dangerous execution flags (`--yolo`, `CODEX_SANDBOX_OVERRIDE`).
- **Immutability & Mutation Allowlist:** `allowed_mutable_fields` must be a strict subset of `MUTABLE_FIELD_UNIVERSE`. Any attempt to permit mutation of immutable core fields (`state`, `summary`, `description_markdown`, `created_by`, `id`, `workspace_id`, `project_id`) raises `422 MUTABLE_FIELD_NOT_ALLOWED`.

### 2.4 Dry-Run Non-Persistence Proof (`dry-run-rowcounts.txt`)
- **Strict Non-Persistence Guarantee:** `run_dry_run()` executes entirely within an explicit `session.begin_nested()` subtransaction and triggers an unconditional `await sp.rollback()` in the `finally:` block.
- **Verification Evidence:** [dry-run-rowcounts.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-149/dry-run-rowcounts.txt) demonstrates 0 delta across `issues`, `workflow_transition_executions`, `workflow_hook_invocations`, `activity_records`, and `objects`.
- **Hostile Payload Limits:** Synthetic `sample_ticket.description_markdown` is checked against lone UTF-16 surrogates and capped at `1,048,576` bytes (1 MiB), rejecting oversized descriptions with `422 DESCRIPTION_TOO_LARGE`.
- **Dual Mode Mutual Exclusivity:** Supplying both or neither of `issue_key` and `sample_ticket` fails validation with `422 INVALID_DRY_RUN_INPUT`.
- **Agent Hook Reporting:** Agent interceptors report `result: "skipped_async"` accompanied by a copyable CLI validation command (`kanban-agent validate-transition ...`).

### 2.5 MCP Admin Tool 8 (`manage_workflow_interceptors`)
- **Surface & Key Scoping:** Restricted to `Surface.ADMIN` / `kb_adm_*` tokens; explicitly rejects agent tokens (`kb_agt_*`) and ephemeral tokens.
- **Two-Stage Confirmation Protocol:** Detaching a hook without `confirm: true` returns an audit preview and copyable CLI confirmation snippet with `requires_confirmation: true`.
- **Decoupled Architecture:** Employs `mcp.internal_client.InternalApiClient` (ASGI-backed HTTP client) to execute all requests against the REST API. Zero direct database imports exist in `mcp/`, verifying compliance with `lint-imports`.
- **Safe Output Formatting:** YAML payloads serialize through `InlineSafeDumper` to prevent multiline injection attacks and scalar breakout.

---

## 3. Test Execution & Coverage Audit

The automated test suite across `kanban/tests/workflows/test_workflow_hooks_api.py`, `kanban/tests/workflows/test_dry_run.py`, and `mcp/tests/admin/test_manage_workflow_interceptors.py` was executed:
- **Total Tests Passed:** 62 / 62 tests in 25.99s.
- **Branch Test Coverage:** **95%** across all touched modules (meeting the `>= 95%` standard):
  - `kanban/workflows/dry_run.py`: **95%**
  - `kanban/workflows/hooks_service.py`: **95%**
  - `kanban/workflows/mutations.py`: **98%**
  - `kanban/workflows/manifest.py`: **100%**
  - `mcp/admin/tools/manage_workflow_interceptors.py`: **95%**
- **Static Analysis & Linters:**
  - `ruff check .`: 0 errors.
  - `ruff format --check .`: Clean.
  - `mypy --strict`: Clean across all touched source files.
  - `lint-imports`: 2 kept, 0 broken.

---

## 4. Verification Evidence Inventory

The forensic verification bundle in `docs/qa/KANBA-149/` has been verified:
- [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-149/git-diff.patch) (191 KB unified diff)
- [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-149/unit-test-results.txt) (62 passed, 95% branch coverage)
- [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-149/build-check.txt) (clean ruff, format, mypy, lint-imports)
- [dry-run-rowcounts.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-149/dry-run-rowcounts.txt) (verified 0 delta across 5 tables)
- [contract-sample.json](file:///home/adamoutler/kanban/docs/qa/KANBA-149/contract-sample.json) (REST request/response contracts for all status codes)
- [mcp-transcript.yaml](file:///home/adamoutler/kanban/docs/qa/KANBA-149/mcp-transcript.yaml) (raw Tool 8 action executions)
- [message-to-reality-checker.md](file:///home/adamoutler/kanban/docs/qa/KANBA-149/message-to-reality-checker.md) (comprehensive handoff report)

---

## 5. Specialist Sign-Off

The REST management endpoints, domain hook service, zero-mutation dry-run simulator, and Admin MCP tool 8 for `KANBA-149` fulfill all architectural, security, and cryptographic invariants without reservation.

**STATUS: APPROVED**

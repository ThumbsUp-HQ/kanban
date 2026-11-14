# API Specialist Gate Review: KANBA-135 (KB-P4-06)

- **Ticket**: `KANBA-135` (`KB-P4-06`: `[Phase 4 / MCP] /mcp/agent tools: begin_work, transition_ticket & complete_work (pending_agent_gate shape)`)
- **Reviewer**: API Specialist (`arch-reviewer`)
- **Authority**: Architecture \u0026 API Invariants per `AGENTS.md` and Advisory Board Post #902
- **Verdict**: APPROVED

---

## 1. Scope and Architectural Review

The implementation of composite issue workflow endpoints and MCP tools on `/mcp/agent` has been evaluated against the technical requirements defined in `docs/tickets/KB-P4-06.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 11.2, 14.3, 15.2, 7.2).

### A. Atomic Single-Transaction Composite Operations
- `POST /api/v1/issues/{id}/begin-work`:
  - Executes in a single atomic database transaction: resolves issue, verifies `EDIT | TRANSITION` capability, assigns caller principal if not already assigned, moves state to lowest `sort_order` state in `state_group == 'started'`, attaches project active cycle if issue currently has none, and inserts normalized `plan_markdown` as an issue comment.
  - Returns HTTP 409 `NO_STARTED_STATE` if project has no started state.
  - Emits `ASSIGNEE_ADDED`, `ISSUE_STATE_CHANGED`, and `COMMENT_CREATED` activity ledger events.
  - Savepoint transaction rollback verified on invalid inputs or failures.

### B. State Transition Boundaries and Guard Hierarchy
- `POST /api/v1/issues/{id}/transition` and `transition_ticket` MCP tool:
  - Validates intermediate state transitions (e.g. `Backlog` -> `In Progress` -> `In Review`).
  - Enforces `USE_COMPLETE_WORK` guard: if target `to_state` belongs to `completed` group, transition is immediately rejected, requiring caller to invoke `complete_work` with structured verification proof.

### C. Blocker Audit and Anti-Enumeration Redaction
- `POST /api/v1/issues/{id}/complete-work` and `complete_work` MCP tool:
  - Checks for open recursive child issues (via `ancestry_path`) in non-terminal states.
  - Checks for open inbound `BLOCKS` dependencies via `object_links`.
  - Rejects completion with HTTP 409 `OPEN_CHILD_BLOCKERS` listing blocker keys.
  - Enforces Anti-Enumeration Redaction: for foreign project blockers where caller lacks `VIEW` permission, blocker key is redacted as `redacted: N hidden blocker(s)` preventing information leakage.

### D. Reality-Checker QA Gate Verification
- Validates `verification_proof` Pydantic v2 model:
  - Enforces `verdict == 'READY'` and `grade == 'A'`. Returns HTTP 422 `QA_VERDICT_NOT_READY` otherwise.
  - Enforces ticket key matching across `qa_dir`, `report_path`, and `artifacts`.
  - Rejects directory traversal `..` and double slashes `//` with HTTP 422 `VALIDATION_FAILED`.
  - Renders structured proof table markdown into completion comment.
  - Emits `WORK_COMPLETED` event into activity ledger.

### E. Asynchronous 202 Accepted `pending_agent_gate` Contract
- When an active `WorkflowGateHook` holds a transition, endpoints return HTTP 202 Accepted with `{status: "pending_agent_gate", execution_id, active_agent, from_state, to_state}`.
- MCP tools return clean YAML with `isError: false` and informative non-blocking hint:
  `hint: "transition is held; poll read_ticket for the gate verdict"`.

---

## 2. Verification Summary

- **Unit Tests**: 33 passed in 10.08s with **95%** overall coverage across target modules (`kanban/api/v1/issue_workflow.py` 97%, `mcp/surfaces/agent/begin_work.py` 96%, `mcp/surfaces/agent/complete_work.py` 96%, `mcp/surfaces/agent/transition_ticket.py` 95%, `kanban/issues/proof.py` 100%).
- **Static Analysis**: `ruff check` (0 errors), `ruff format --check` (0 issues), `mypy --strict` (0 errors across 417 files), `lint-imports` (2 kept, 0 broken).
- **Typography Standard**: Clean ASCII hyphens `-` only (0 non-ASCII dashes).

Architecture and API integrity certified.

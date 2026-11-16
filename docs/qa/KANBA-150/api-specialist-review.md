# API Specialist Gate Review: KANBA-150 (KB-P5-18)

- **Ticket**: `KANBA-150` (`KB-P5-18`: `[Phase 5 / Workflow Engine] Async agent gate state machine: 202 pending hold, TOCTOU-checked approve, reject snap-back & realtime events`)
- **Reviewer**: API Specialist (`backend-architect`)
- **Authority**: Architecture and API Invariants per `AGENTS.md` and Advisory Board Guidance
- **Verdict**: APPROVED

---

## 1. Scope and Technical Architecture

The implementation of the asynchronous agent transition gate state machine has been evaluated against the technical requirements defined in `docs/tickets/KB-P5-18.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 14.1, 14.2, 14.3, 11.2, 1.3).

### A. HTTP 202 Accepted Transition Hold Dispatch
- `POST /api/v1/issues/{issue_key}/transitions`:
  - When an `agent_interceptor` workflow hook is encountered in the transition pipeline, the transition enters `pending_async` status.
  - Sets `issues.pending_transition_exec_id = execution.id` while leaving `issues.state_id` unchanged.
  - Returns HTTP 202 Accepted with payload:
    `{status: "pending_agent_gate", execution_id, active_agent, hook_name, harness_kind, state}`.
  - Concurrency control: Enforces partial unique constraint `wte_one_pending`. Concurrent transition requests on the same issue return HTTP 409 `TRANSITION_PENDING`.

### B. Two-Phase Decision Recording and TOCTOU Snapshot Protection
- `GateCoordinator.record_decision(execution_id, hook_id, decision)`:
  - Atomic transaction with `SELECT ... FOR UPDATE` row locks on both execution and issue.
  - Rejects out-of-order invocations with `GATE_DECISION_OUT_OF_ORDER`. Duplicate submissions with identical `verdict_sha256` are idempotent no-ops.
  - Validates `decision.field_updates` against `hook.allowed_mutable_fields`. Unauthorized mutations reject with `HOOK_MUTATION_NOT_ALLOWED` under `fail_closed` policy or trigger `HOOK_FAIL_OPEN_WARN` under `fail_open_warn`.
  - TOCTOU verification: On approval of the final hook in the chain, verifies `issues.description_sha256 == execution.issue_body_sha256_snapshot` and `issues.state_id == execution.from_state_id`. On mismatch, cancels execution, clears hold, and records `GATE_ABORTED_STALE`.
  - On approval match: applies `accumulated_updates`, labels, links, sets `state_id` with transaction-local `app.transition_exec_id`, emits `GATE_APPROVED` activity, and records `workflow.gate.approved` outbox event.

### C. Reject Veto and Secret Sanitization
- On `reject` decision:
  - Execution marked `rejected`, hold cleared, and issue state left at `from_state_id`.
  - Posts veto comment authored by agent principal: `🛑🤖 Gate <hook_name> (<harness_label>) vetoed <from> -> <to>`.
  - Reason markdown is normalized (KB-P2-13), stripped of secrets (`sk-live-...`, PEM keys) via `SecretScrubber` (KB-P2-17), and capped at 16,384 bytes.
  - Emits `workflow.gate.rejected` outbox event with scrubbed `reason_preview` (<= 2 lines, <= 280 chars) and zero `verdict_json` exposure.

### D. Timeout Sweeper and Failure Handling
- `GateTimeoutSweeper.run_once(session, now)`:
  - Queries `pending_async` executions exceeding `deadline_at` using `FOR UPDATE SKIP LOCKED` (batch <= 100).
  - Handles `fail_closed` vs `fail_open_warn` policies cleanly.
  - Emits `workflow.gate.timed_out` event and `GATE_TIMED_OUT` activity.

### E. Cancellation Endpoint
- `DELETE /api/v1/transitions/{execution_id}`:
  - Authorized for `invoking_principal_id` or `PROJECT_ADMIN`. Non-authorized callers receive HTTP 404 (anti-enumeration).
  - Marks execution `cancelled`, clears issue hold, and emits `workflow.gate.cancelled`.

### F. Serializer and MCP Surface Alignment
- `kanban/issues/serializers.py`:
  - `pending_gate`: `{execution_id, hook_name, agent_slug, harness_label, started_at, deadline_at} | null`.
  - `latest_gate_verdict`: `{decision, hook_name, completed_at, latency_ms, verdict_sha256} | null`.
- `mcp/surfaces/agent/transition_ticket.py`:
  - Returns `status: "pending_agent_gate"`, `execution_id`, and `active_agent` on HTTP 202.
  - Maps HTTP 409 `TRANSITION_PENDING` to structured error.

---

## 2. Verification Summary

- **Unit Tests**: 24 passed in 19.47s with **95.44%** total branch coverage across target modules (`kanban.workflows.async_gate`: 95%, `kanban.workflows.gate_sweeper`: 100%, `kanban.workflows.gate_types`: 100%).
- **Static Analysis**: `ruff check` (0 errors), `ruff format --check` (15 files already formatted), `mypy --strict` (0 errors across 15 source files), `lint-imports` (Contracts: 2 kept, 0 broken).
- **Typography Standard**: Clean ASCII hyphens `-` only (0 non-ASCII dashes).

Architecture and API integrity certified.

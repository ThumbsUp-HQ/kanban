# Message to Reality-Checker: KANBA-150 (KB-P5-18) Forensic QA Packet

- **Ticket**: `KANBA-150` (`KB-P5-18`: `[Phase 5 / Workflow Engine] Async agent gate state machine: 202 pending hold, TOCTOU-checked approve, reject snap-back & realtime events`)
- **Epic**: `KB-E5`
- **Spec Sections**: 14.1 (Two-phase gate sequence), 14.2 (State machine & invariants), 14.3 (TOCTOU & snapshot verification), 11.2 (item 6), 1.3 (ScriptRunner row)
- **Status**: Complete, Tested, and Ready for Specialist Review & Forensic Certification

---

## 1. Executive Summary

This deliverable implements the two-phase asynchronous agent transition gate state machine and coordinator:

1. **Async Agent Gate Dispatcher (`kanban/workflows/async_gate.py`)**:
   - Implements `AgentGateDispatcher` replacing `FailClosedAsyncGateDispatcher` as the bound default in `TransitionEngine`.
   - On encountering an `agent_interceptor` hook in the transition pipeline, places the execution in `pending_async` status.
   - Sets `issues.pending_transition_exec_id = execution.id` while leaving `issues.state_id` unchanged (zero premature state changes).
   - Inserts `workflow_hook_invocations` row (`status='running'`) for the first agent hook in `sort_rank` order.
   - Enqueues `workflow.gate.pending` outbox event with deadline timestamp (`deadline_at = now + timeout_ms`).
   - Returns HTTP 202 Accepted with `{status: "pending_agent_gate", execution_id, active_agent, hook_name, harness_kind, state}`.

2. **GateCoordinator Atomic Verdict Recording (`kanban/workflows/async_gate.py`)**:
   - Atomic transaction with `SELECT ... FOR UPDATE` row locks on both execution and issue.
   - Rejects out-of-order decisions with `GATE_DECISION_OUT_OF_ORDER`; duplicate submissions with identical `verdict_sha256` are idempotent no-ops.
   - Validates `decision.field_updates` against `hook.allowed_mutable_fields`. Unauthorized mutations fail closed with `HOOK_MUTATION_NOT_ALLOWED` or trigger `HOOK_FAIL_OPEN_WARN`.
   - Sequential multi-hook chaining: on approval with remaining agent hooks, marks current invocation `allowed`, starts next invocation, and dispatches next hook.
   - TOCTOU Invariant Protection: On approval of the final hook, verifies `issues.description_sha256 == execution.issue_body_sha256_snapshot` and `issues.state_id == execution.from_state_id`. On mismatch, cancels execution, clears hold, and records `GATE_ABORTED_STALE`.
   - On approval match: applies `accumulated_updates`, labels, links, updates issue state with transaction-local `app.transition_exec_id`, emits `GATE_APPROVED` activity, and records `workflow.gate.approved` outbox event.
   - On reject: sets status `rejected`, clears hold, and posts veto comment authored by agent principal: `🛑🤖 Gate <hook_name> (<harness_label>) vetoed <from> -> <to>`. Content is normalized, secret-scrubbed, and capped at 16,384 bytes. Emits `workflow.gate.rejected` with bounded `reason_preview`.

3. **Timeout Sweeper and Failure Handling (`kanban/workflows/gate_sweeper.py`)**:
   - `GateTimeoutSweeper.run_once(session, now)` selects `pending_async` executions past deadline via `FOR UPDATE SKIP LOCKED` (batch <= 100).
   - Handles `fail_closed` policy (status `timed_out` with comment) vs `fail_open_warn` policy (`GATE_FAIL_OPEN_WARN` activity, advancing to next hook or commit).

4. **Cancellation Endpoint (`kanban/api/v1/transitions.py`)**:
   - `DELETE /api/v1/transitions/{execution_id}` permits cancellation by `invoking_principal_id` or `PROJECT_ADMIN`. Non-authorized callers receive HTTP 404 (anti-enumeration).
   - Clears hold and emits `workflow.gate.cancelled`.

5. **Serializer and MCP Integration**:
   - `kanban/issues/serializers.py`: adds `pending_gate` and `latest_gate_verdict` summaries.
   - `mcp/surfaces/agent/transition_ticket.py`: maps HTTP 202 to `{status: "pending_agent_gate", execution_id, active_agent}` and HTTP 409 to structured `TRANSITION_PENDING`.

---

## 2. Forensic Verification Proof Matrix

| # | Artifact | Description / Proof Summary | Status |
| :- | :--- | :--- | :-: |
| 1 | `docs/qa/KANBA-150/git-diff.patch` | Unified git diff across all 20 modified/created repository files (184 KB) | **PASS** |
| 2 | `docs/qa/KANBA-150/unit-test-results.txt` | 24 passed in 19.47s; 95.44% statement and branch coverage | **PASS** |
| 3 | `docs/qa/KANBA-150/build-check.txt` | Ruff clean (0 errors), Ruff format clean (15 files), Mypy strict clean (15 files), Lint-imports clean (2/2 kept) | **PASS** |
| 4 | `docs/qa/KANBA-150/state-transitions.txt` | All 6 S14.2 statuses exercised and recorded by test harness | **PASS** |
| 5 | `docs/qa/KANBA-150/contract-sample.json` | Sample payloads for 202 dispatch, cancellation, serializer fields, and MCP responses | **PASS** |
| 6 | `docs/qa/KANBA-150/realtime-events.jsonl` | Captured outbox payloads for pending, approved, rejected, timed_out, and cancelled | **PASS** |
| 7 | `docs/qa/KANBA-150/api-specialist-review.md` | API Specialist review and approval | **APPROVED** |
| 8 | `docs/qa/KANBA-150/ui-specialist-review.md` | UI / UX Specialist review and approval | **APPROVED** |
| 9 | Screenshots | N/A - Non-UI Ticket (Workflow Engine / MCP Infrastructure) | **N/A** |

---

## 3. Unit Test and Coverage Details

- **Test Command**:
  ```bash
  KB_TEST_DB_PREFIX="kanban_test_p4_141" KB_TEST_TEMPLATE_DB="kanban_template_p4_141" uv run pytest kanban/tests/workflows/test_async_gate.py kanban/tests/workflows/test_gate_sweeper.py agent/tests/integration/test_async_gate_fixture.py mcp/tests/agent/test_transition_ticket_gate.py -q --cov=kanban.workflows.async_gate --cov=kanban.workflows.gate_sweeper --cov=kanban.workflows.gate_types --cov-branch --cov-report=term-missing --cov-fail-under=95
  ```
- **Results**: 24 passed in 19.47 seconds.
- **Coverage Breakdown**:
  - `kanban/workflows/gate_sweeper.py`: **100%**
  - `kanban/workflows/gate_types.py`: **100%**
  - `kanban/workflows/async_gate.py`: **95%**
  - **Overall Target Coverage**: **95.44%** (exceeds >= 95% threshold).

---

## 4. Invariant Compliance Checklist

- [x] **Universal Object Graph & FORCE RLS**: All state changes use `app.transition_exec_id` session config, enforcing DB guard triggers.
- [x] **Zero Silent Passes**: `fail_closed` policy rejects or times out transitions on agent or hook failures.
- [x] **Strict TOCTOU Prevention**: Hashes of issue body and state IDs are verified before committing approved transitions.
- [x] **No Em-Dashes or Fluff**: External documentation conforms to technical ASCII standard.
- [x] **No Premature Closure**: Ticket remains open for specialist review and reality-checker forensic certification.

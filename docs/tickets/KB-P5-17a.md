---
id: KB-P5-17a
title: "[Phase 5 / Database + Workflow Engine] Workflow hook DDL & synchronous Tier A validator/mutator transition pipeline"
epic: KB-E5
depends_on: [KB-P5-13, KB-P5-16]
spec_sections: ["14.1", "14.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P5-17` is split into `KB-P5-17a` (this ticket: DDL + engine + transition endpoint) and `KB-P5-17b` (hook management REST, dry-run, `/mcp/admin manage_workflow_interceptors`).

### User Story
As a **Project Admin enforcing ScriptRunner-style workflow rules**, I need **the `workflow_transition_hooks`, `workflow_transition_executions`, and `workflow_hook_invocations` tables plus a transition engine that runs ordered Tier A `sync_validator` / `sync_mutator` hooks inside a `< 25ms` budget before any state change** so that **invalid transitions are rejected with `422` before commit, mutators can only touch whitelisted fields, and no code path can change `issues.state_id` without passing through the engine**.

**Requirement Traceability:** `S14.1` (sequence diagram steps 1-3: sync validators, `422` on reject), `S14.2` (DDL `workflow_transition_hooks`, `workflow_transition_executions`, `allowed_mutable_fields`, `failure_policy`, `manifest_sha256`, `hop_depth <= 3`, `issue_body_sha256_snapshot`) | ScriptRunner row of the traceability matrix | **Dependencies:** `KB-P5-13`, `KB-P5-16`

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/p5_17a_workflow_hooks.py`
   - `database/models/workflow.py` (`WorkflowTransitionHook`, `WorkflowTransitionExecution`, `WorkflowHookInvocation`)
   - `kanban/workflows/manifest.py` (`compute_hook_manifest_sha256()`)
   - `kanban/workflows/engine.py` (`TransitionEngine`, `TransitionOutcome`, `AsyncGateDispatcher` protocol, `FailClosedAsyncGateDispatcher`)
   - `kanban/workflows/mutations.py` (`MUTABLE_FIELD_UNIVERSE`, `apply_field_updates()`)
   - `kanban/api/v1/transitions.py` (`POST /api/v1/issues/{issue_key}/transitions`)
   - Edit: issue `PATCH` handler from `KB-P3-02` and board move handler from `KB-P3-12` delegate any `state` change to `TransitionEngine`.
2. **DDL:** `workflow_transition_hooks` and `workflow_transition_executions` verbatim from S14.2 (lines 968-999). `workflow_hook_invocations` is named in the manifest but not defined in the spec; define it as:
   ```sql
   CREATE TABLE workflow_hook_invocations (
     id            UUID PRIMARY KEY DEFAULT uuidv7(),
     workspace_id  UUID NOT NULL,
     execution_id  UUID NOT NULL REFERENCES workflow_transition_executions(id) ON DELETE CASCADE,
     hook_id       UUID NOT NULL REFERENCES workflow_transition_hooks(id) ON DELETE RESTRICT,
     hook_kind     TEXT NOT NULL CHECK (hook_kind IN ('sync_validator','sync_mutator','agent_interceptor')),
     status        TEXT NOT NULL CHECK (status IN ('running','allowed','rejected','mutated','error','timed_out','skipped')),
     error_code    TEXT,
     output_json   JSONB,                       -- bounded <= 64 KiB, scrubbed
     duration_us   INTEGER CHECK (duration_us >= 0),
     started_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
     completed_at  TIMESTAMPTZ,
     UNIQUE (execution_id, hook_id)
   );
   CREATE INDEX wth_lookup ON workflow_transition_hooks (project_id, to_state_id, sort_rank) WHERE is_enabled;
   CREATE UNIQUE INDEX wte_one_pending ON workflow_transition_executions (issue_id) WHERE status IN ('running_sync','pending_async');
   ```
   - Add CHECKs: `hook_kind IN ('sync_validator','sync_mutator') -> wasm_module_sha256 IS NOT NULL AND agent_definition_id IS NULL`; `hook_kind = 'agent_interceptor' -> agent_definition_id IS NOT NULL AND wasm_module_sha256 IS NULL`; `octet_length(manifest_sha256) = 32`.
   - `ENABLE` + `FORCE ROW LEVEL SECURITY` on all 3 tables; hooks writable only by `PROJECT_ADMIN` (`WITH CHECK`); executions/invocations insertable only via `SECURITY DEFINER`-free engine path under `kanban_app` with workspace context, readable by principals with `VIEW` on the issue.
   - DB guard trigger `issues_state_guard BEFORE UPDATE OF state_id ON issues`: raises `STATE_CHANGE_REQUIRES_TRANSITION_ENGINE` unless `current_setting('app.transition_exec_id', true)` equals the id of a `workflow_transition_executions` row for `NEW.id` with `to_state_id = NEW.state_id` and status `running_sync` or `pending_async`.
3. **Manifest hash (`compute_hook_manifest_sha256`):** `SHA256(hook_kind || 0x00 || hex(wasm_module_sha256 or '') || 0x00 || str(agent_definition_id or '') || 0x00 || ",".join(sorted(allowed_mutable_fields)) || 0x00 || failure_policy || 0x00 || str(from_state_id or '*') || 0x00 || str(to_state_id))`. Engine recomputes per hook at run time; mismatch -> invocation `error`, code `HOOK_MANIFEST_MISMATCH`, always fail-closed regardless of `failure_policy`.
4. **Engine (`TransitionEngine.request_transition(issue_key, to_state, actor, if_match: str | None, parent_execution_id: UUID | None) -> TransitionOutcome`):**
   1. `SELECT ... FOR UPDATE` the issue; `If-Match` vs `description_sha256` ETag -> `412` on mismatch; `pending_transition_exec_id IS NOT NULL` -> `409 TRANSITION_PENDING`; caller lacks `TRANSITION` capability -> `404`.
   2. `hop_depth = parent.hop_depth + 1` when `parent_execution_id` set (else `0`); `> 3` -> `422 HOP_DEPTH_EXCEEDED` before insert.
   3. Insert execution `status='running_sync'`, `issue_body_sha256_snapshot = issues.description_sha256`; `SET LOCAL app.transition_exec_id`.
   4. Load enabled hooks where `project_id` matches, `to_state_id = target`, `from_state_id = current OR from_state_id IS NULL`, ordered `sort_rank COLLATE "C", id`.
   5. Run each `sync_validator` / `sync_mutator` through the Tier A runner from `KB-P5-13` with input JSON `{schema: "kb-sync-hook-input/v1", issue: {key, summary, description_markdown, priority, labels, assignees, custom_fields}, transition: {from_state, to_state, actor}}` and expected output `{decision: "allow"|"reject", reason?: str<=2000, field_updates?: object}`; per-hook deadline = remaining of a single `25ms` monotonic budget for the whole sync stage (Tier A caps of `50M` fuel / `32MiB` still apply).
   6. Validator `reject` -> execution `rejected`, `422 TRANSITION_REJECTED_BY_HOOK` `{hook_name, reason}` (reason plain text, scrubbed, `<= 2000` chars).
   7. Mutator `field_updates`: every key must be in `hook.allowed_mutable_fields` AND in `MUTABLE_FIELD_UNIVERSE = {"labels","priority","assignees","start_date","due_date","cycle"} | {"custom_fields.<slug>"}`; `state`, `summary`, `description_markdown`, `created_by`, `parent` are never mutable (TOCTOU invariant) -> `HOOK_MUTATION_NOT_ALLOWED`.
   8. Hook error / budget overrun (`SYNC_HOOK_BUDGET_EXCEEDED`) / malformed output (`SYNC_HOOK_OUTPUT_INVALID`): `fail_closed` -> `422` with the code; `fail_open_warn` -> invocation `error`, activity `HOOK_FAIL_OPEN_WARN`, continue.
   9. No `agent_interceptor` hooks -> update `state_id`, execution `approved`, `completed_at`, activity `TRANSITIONED`; return `200`.
   10. Any `agent_interceptor` hooks -> call `AsyncGateDispatcher.dispatch(execution, hooks)`. Default bound implementation `FailClosedAsyncGateDispatcher` marks execution `cancelled` and returns `409 AGENT_GATE_NOT_CONFIGURED` (replaced by `KB-P5-18`).
5. **Transition endpoint:** `POST /api/v1/issues/{issue_key}/transitions` body `{"to_state": "<name|uuid>", "comment_markdown"?: str}`, header `If-Match` optional; responses `200 {execution_id, status:"approved", state}`, `202` reserved for `KB-P5-18`, `409`, `412`, `422 {code, hook_name?, reason?}`.

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `database/tests/test_workflow_hooks_ddl.py`
  - `kanban/tests/workflows/test_transition_engine.py` (clean-DB `SAVEPOINT` harness; Tier A runner replaced by a deterministic `FakeWasmRunner` returning scripted outputs and durations, plus 1 test using a real minimal `.wasm` validator fixture from `KB-P5-13` at `tests/fixtures/wasm/require_qa_proof_link.wasm`)
  - `kanban/tests/workflows/test_manifest.py`
- **Required Test Cases:**
  1. Positive: no hooks -> `200`, state changed, execution `approved`; 2 ordered validators allow + 1 mutator sets `labels` (allowed) -> `200`, label applied, invocations recorded in `sort_rank` order with `duration_us`.
  2. Rejection: validator `require-qa-proof-link` rejects description lacking `docs/qa/` -> `422 TRANSITION_REJECTED_BY_HOOK`, state unchanged, execution `rejected`.
  3. Security: mutator returns `field_updates={"state":"Done"}` or `{"description_markdown":"x"}` or `{"priority":"urgent"}` when only `labels` allowed -> `HOOK_MUTATION_NOT_ALLOWED`, `fail_closed` -> `422`.
  4. Security: direct `UPDATE issues SET state_id=...` as `kanban_app` without `app.transition_exec_id` -> raises `STATE_CHANGE_REQUIRES_TRANSITION_ENGINE`; `PATCH /issues/{key}` with `state` routes through engine (validator rejection observed).
  5. Security: tampered `wasm_module_sha256` (manifest mismatch) with `fail_open_warn` still fails closed `HOOK_MANIFEST_MISMATCH`.
  6. Boundary: hooks totaling `26ms` simulated -> `SYNC_HOOK_BUDGET_EXCEEDED`; `fail_open_warn` variant continues with `HOOK_FAIL_OPEN_WARN` activity; wildcard `from_state_id IS NULL` hook applies from any state; disabled hook skipped.
  7. Boundary: `parent_execution_id` chain reaching `hop_depth=4` -> `422 HOP_DEPTH_EXCEEDED`; DB CHECK rejects direct insert with `hop_depth=4`; second concurrent transition while one is `running_sync` -> unique partial index -> `409 TRANSITION_PENDING`.
  8. Agent hook present with default dispatcher -> `409 AGENT_GATE_NOT_CONFIGURED`, execution `cancelled`, state unchanged.
  9. RLS: hooks invisible across workspaces; `MEMBER` insert into hooks rejected by `WITH CHECK`.
- Touched-module coverage `>= 95%` for `kanban.workflows`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** All target files exist; `kanban/workflows/engine.py` defines `TransitionEngine.request_transition`, `AsyncGateDispatcher`, `FailClosedAsyncGateDispatcher`; trigger `issues_state_guard` exists in migration.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest database/tests/test_workflow_hooks_ddl.py kanban/tests/workflows -q --cov=kanban.workflows --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`, `0` failures.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict database kanban && uv run lint-imports` exits `0`.
- [ ] **Schema Proof:** `schema-dump.sql` shows the 3 tables, 2 indexes, CHECKs, `issues_state_guard`, and `relforcerowsecurity = t` for all 3 tables.
- [ ] **Latency Proof:** `sync-latency.txt` shows p95 of the sync stage `< 25ms` over `200` runs with 3 hooks using the real wasm fixture.
- [ ] **Forensic Proof Packet Complete:** All files below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - full output + exit code of the pytest command above.
3. `docs/qa/<TICKET_ID>/build-check.txt` - full output of the ruff/mypy/lint-imports command.
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `pg_dump --schema-only -t workflow_transition_hooks -t workflow_transition_executions -t workflow_hook_invocations` + trigger definition + `pg_class` RLS flags.
5. `docs/qa/<TICKET_ID>/sync-latency.txt` - raw benchmark output (`pytest -k latency_benchmark -s`).
6. `docs/qa/<TICKET_ID>/contract-sample.json` - `200`, `409 TRANSITION_PENDING`, `409 AGENT_GATE_NOT_CONFIGURED`, `412`, `422` samples.
7. `docs/qa/<TICKET_ID>/api-specialist-review.md` and `docs/qa/<TICKET_ID>/ui-specialist-review.md` (UI specialist reviews `422` payload ergonomics for inline card/drawer toasts).
8. `docs/qa/<TICKET_ID>/message-to-reality-checker.md` - notes that `workflow_hook_invocations` columns are defined here because S14.2 omits the table.
- Screenshots: N/A - Non-UI Ticket.

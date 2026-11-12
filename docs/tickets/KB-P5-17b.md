---
id: KB-P5-17b
title: '[Phase 5 / API + MCP] Workflow hook management REST, sync dry-run & /mcp/admin tool 8 manage_workflow_interceptors'
epic: KB-E5
depends_on: [KB-P5-17a, KB-P4-09a, KB-P4-09b]
spec_sections: ['14.1', '14.2', '14.4', '11.4']
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P5-17` (see `KB-P5-17a`).

### User Story
As a **Project Admin or admin MCP client**, I need **REST endpoints and the `/mcp/admin` intent tool `manage_workflow_interceptors` to attach, order, enable/disable, detach, and dry-run hooks on `(from_state -> to_state)` transitions** so that **workflow gates are managed through one audited, AAL2-protected path with a non-committing dry-run against a sample ticket**.

**Requirement Traceability:** `S11.4` tool 8 (`manage_workflow_interceptors`: attach, order, enable/disable, dry-run `sync_validator`, `sync_mutator`, `agent_interceptor`), `S14.2` (`sort_rank COLLATE "C"`, `manifest_sha256`), `S14.4` (`▶ Dry-Run Against Sample Ticket`), `S11.1` (`EntityResolver`, `help`, `InlineSafeDumper`) | Original requirement `#12` | **Dependencies:** `KB-P5-17a`, `KB-P4-09`

### Scoped Technical Actions
1. **Target Files:**
   - `kanban/workflows/hooks_service.py` (`WorkflowHookService`)
   - `kanban/workflows/dry_run.py` (`run_dry_run()`)
   - `kanban/api/v1/workflow_hooks.py`
   - `mcp/admin/tools/manage_workflow_interceptors.py`
   - `mcp/admin/registry.py` (register tool 8; tool count stays within the 12-tool catalog)
2. **REST (all require `PROJECT_ADMIN` on the project; writes additionally require session `aal_level >= 2`, else `403 AAL2_REQUIRED`):**
   - `GET /api/v1/projects/{project}/workflow-hooks` -> list grouped by `(from_state, to_state)` with `active_hook_count`.
   - `POST /api/v1/projects/{project}/workflow-hooks` body `{name, from_state|null, to_state, hook_kind, wasm_module_sha256?, agent?, allowed_mutable_fields[], failure_policy}`; server computes `sort_rank` (Base-62 append after last rank) and `manifest_sha256` via `compute_hook_manifest_sha256` (KB-P5-17a).
   - `PATCH /api/v1/workflow-hooks/{hook_id}` (any manifest-relevant change recomputes `manifest_sha256`), `POST /api/v1/workflow-hooks/{hook_id}/enable|disable`, `DELETE /api/v1/workflow-hooks/{hook_id}`.
   - `POST /api/v1/projects/{project}/workflow-hooks/reorder` body `{transition: {from_state, to_state}, ordered_hook_ids: [...]}` -> rewrites `sort_rank` values; must contain exactly the current hook set for that transition else `422 REORDER_SET_MISMATCH`.
   - Validation: `wasm_module_sha256` must reference an approved Tier A module from `KB-P5-13` (`422 WASM_MODULE_NOT_APPROVED`); `agent` must resolve to an `agent_definitions` row in the same workspace (`422 AGENT_NOT_FOUND`) and pass `assert_runtime_argv` for `cli_pipe` (KB-P5-16); `allowed_mutable_fields` subset of `MUTABLE_FIELD_UNIVERSE` (`422 MUTABLE_FIELD_NOT_ALLOWED`); `from_state`/`to_state` must belong to the project.
   - Every write appends activity `WORKFLOW_HOOK_ATTACHED|UPDATED|REORDERED|ENABLED|DISABLED|DETACHED` with before/after `manifest_sha256`.
3. **Dry-run (`POST /api/v1/projects/{project}/workflow-hooks/dry-run`):** body `{from_state, to_state, issue_key?: str, sample_ticket?: {summary, description_markdown, priority, labels[]}}` (exactly one of `issue_key` / `sample_ticket`). Executes the `KB-P5-17a` sync pipeline inside a `SAVEPOINT` that is always rolled back (zero persisted rows, verified by test), using a synthetic in-memory issue for `sample_ticket` (normalized via `KB-P2-13`, `description_markdown <= 1,048,576` bytes). Returns per hook `{order, name, hook_kind, result: allowed|rejected|mutated|error|skipped_async, reason?, field_updates?, duration_us}` and `would_commit: bool`. `agent_interceptor` hooks are reported `skipped_async` (agent dry-run lives in `kanban-agent validate-transition`, KB-P5-23).
4. **MCP tool 8 (`manage_workflow_interceptors`)** calls the REST API over the internal client (no DB credentials in `mcp/`):
   - Actions: `help`, `list`, `attach`, `update`, `reorder`, `enable`, `disable`, `detach`, `dry_run`.
   - Parameters accept human keys via `EntityResolver`: project `"KAN"`, states `"In Review"` / `"*"`, hook `"require-qa-proof-link"`, agent slug `"forensic-code-check"`, issue `"KAN-142"`.
   - `detach` requires `confirm: true` else returns a preview of the hook and `requires_confirmation: true` without deleting.
   - Output via `InlineSafeDumper` YAML, LOD `summary` default; `help` returns live states, approved wasm modules, agents, and the mutable field universe.
   - Scope: only `kb_adm_*` keys / admin OAuth tokens; `kb_agt_*` and `kb_agt_eph_*` tokens rejected at the surface (inherited from `KB-P4-02`).

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `kanban/tests/workflows/test_workflow_hooks_api.py` (clean-DB `SAVEPOINT` harness)
  - `kanban/tests/workflows/test_dry_run.py`
  - `mcp/tests/admin/test_manage_workflow_interceptors.py` (internal API client faked with recorded responses)
- **Required Test Cases:**
  1. Positive: attach 3 hooks (`require-qa-proof-link` validator, `forensic-code-check` agent, `sec-invariant-scan` agent) -> list shows `active_hook_count=3` in insertion order; reorder swaps them; `manifest_sha256` changes when `failure_policy` changes.
  2. Positive: dry-run with `sample_ticket` lacking `docs/qa/` -> validator `rejected`, agents `skipped_async`, `would_commit=false`; row counts of executions/invocations/issues identical before and after.
  3. Security: `MEMBER` -> `404`; `PROJECT_ADMIN` at `aal_level=1` -> `403 AAL2_REQUIRED`; unapproved wasm hash -> `422 WASM_MODULE_NOT_APPROVED`; agent from another workspace -> `422 AGENT_NOT_FOUND`; `allowed_mutable_fields=["state"]` -> `422 MUTABLE_FIELD_NOT_ALLOWED`.
  4. Security (MCP): `kb_agt_*` key calling tool 8 rejected; `detach` without `confirm` deletes nothing; hostile hook name `"x\n- injected: true"` is emitted as a quoted YAML scalar (round-trip `yaml.safe_load` equals input).
  5. Boundary: reorder with a missing or extra hook id -> `422 REORDER_SET_MISMATCH`; dry-run with both `issue_key` and `sample_ticket` -> `422`; `description_markdown` of `1,048,577` bytes -> `413`/`422`.
  6. `help` action returns states, agents, wasm modules, mutable fields for project `KAN` resolved by key.
- Touched-module coverage `>= 95%` for `kanban.workflows` and `mcp.admin.tools.manage_workflow_interceptors`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** All target files exist; tool `manage_workflow_interceptors` registered on `/mcp/admin` with the 9 actions listed.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/workflows/test_workflow_hooks_api.py kanban/tests/workflows/test_dry_run.py mcp/tests/admin/test_manage_workflow_interceptors.py -q --cov=kanban.workflows --cov=mcp.admin --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict kanban mcp && uv run lint-imports` exits `0`.
- [ ] **Dry-run non-persistence proof:** `dry-run-rowcounts.txt` shows identical row counts before/after for `issues`, `workflow_transition_executions`, `workflow_hook_invocations`, `activity_records`.
- [ ] **Specialist Gates:** `api-specialist-review.md` and `ui-specialist-review.md` exist with approval lines.
- [ ] **Forensic Proof Packet Complete:** All files below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/contract-sample.json` - REST samples for list, attach, reorder, dry-run, each `4xx` code.
5. `docs/qa/<TICKET_ID>/mcp-transcript.yaml` - raw tool 8 request/response for `help`, `attach`, `dry_run`, `detach` (unconfirmed + confirmed).
6. `docs/qa/<TICKET_ID>/dry-run-rowcounts.txt`
7. `docs/qa/<TICKET_ID>/api-specialist-review.md`
8. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - verifies payload shape supports the S14.4 Studio (KB-P5-24).
- Screenshots: N/A - Non-UI Ticket.

# API Specialist Review: KAN-29 (KB-P3-AUDIT-23)

- Ticket: KAN-29
- Title: [KB-P3-AUDIT-23] Add 12-Color Palette + Advanced Color Picker and Pre-Delete Reverse-Audit & Safe Migration for Workflow States & Labels (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan29-92d52807`
- Branch: `feat/KAN-29`
- Commit: `5d3d03eac38c2e1e0038148e3b424f8cc70ec2d8`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-29 on branch `feat/KAN-29` (commit `5d3d03ea`). The ticket implements a 12-color WCAG-contrast preset palette and advanced color picker (`<ColorPresetPicker />`), live colored badge pills and row editing for workflow states and labels, backend reverse-audit impact endpoints (`audit-impact`) for blast-radius calculation, hardened deletion APIs for workflow states and labels with in-flight execution guards and atomic FK migrations, and an accessible pre-delete reverse-audit modal (`<DeleteAuditModal />`).

All API contracts, security invariants, transaction boundaries, and test coverage requirements are verified and approved:
1. Exact endpoint routing and Pydantic schema validation for `GET /api/v1/projects/{ref}/states/{id}/audit-impact` and `GET /api/v1/projects/{ref}/labels/{id}/audit-impact`, protected with `Capability.ADMIN` and constant-time `timing_floor(25.0)`.
2. Hardened `DELETE /api/v1/projects/{ref}/states/{id}`:
   - Fails closed with HTTP 409 `TRANSITION_IN_FLIGHT` when transitions are actively executing (`running_sync` / `pending_async`).
   - Fails closed with HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE` when active workflow hooks reference the target state without a replacement.
   - Prevents self-loop transition creation with HTTP 409 `HOOK_MIGRATION_SELF_LOOP` when reassigning transition hooks.
   - Atomically updates `Issue.state_id`, `WorkflowTransitionHook` (`from_state_id`/`to_state_id`), `WorkflowTransitionExecution` historical FKs, and `View.filters_json['state_ids']` before deleting the state entity.
   - Retains the legacy `migrate_to` query parameter alias alongside `replacement_state_id` for complete backward compatibility.
3. Hardened `DELETE /api/v1/projects/{ref}/labels/{id}`:
   - Supports `replacement_label_id` migration, reassigning `IssueLabel` join rows while respecting label `exclusive_group` rules and preventing PK duplicate collisions.
   - Updates `View.filters_json['label_ids']` across all project saved views.
4. Clean architectural layering: Zero direct `database` runtime imports from disallowed surfaces; all database queries enforce Row-Level Security tenant boundaries.
5. Zero new external dependencies introduced.
6. Test coverage and static gates:
   - 12 Pytest tests passing in 9.38s with 97% overall coverage across touched backend files (`project_config.py` 100%, `schemas/project_config.py` 100%, `services/project_config.py` 96%).
   - 51 Vitest unit tests passing across 3 test suites with 99.14% Statements and 95.27% Branch coverage.
   - `cssTokensAudit.test.ts` passed 4/4 (100% canonical tokens, 0 inline React styles).
   - Strict 0 em-dashes or en-dashes across all code, tests, and documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Reverse-Audit Impact Endpoints (`audit-impact`)
- Endpoints Audited:
  - `GET /api/v1/projects/{project_ref}/states/{state_id}/audit-impact`
  - `GET /api/v1/projects/{project_ref}/labels/{label_id}/audit-impact`
- Security & Permission Verification:
  - Scoped to project and caller via `get_project_or_404`.
  - Enforces `require_capability(session, caller, project.id, Capability.ADMIN)`.
  - Constant-time execution protected by `timing_floor(floor_ms=25.0)`.
- Payload Schema Verification:
  - `StateAuditImpactResponse`:
    * `issues_count` and `sample_issue_keys` (up to 5 recent keys).
    * `workflow_hooks`: list of `WorkflowHookSummary` (`id`, `name`, `hook_kind`, `is_enabled`, `from_state_id`, `to_state_id`).
    * `pending_executions_count`: integer count of executions in `running_sync` or `pending_async`.
    * `historical_executions_count`: integer count of completed/failed executions.
    * `saved_views`: list of `SavedViewSummary` referencing this state in `filters_json['state_ids']`.
    * `is_default`: boolean flag indicating if this is the project default state.
    * `blocking_reasons`: list of human-readable blocking conditions.
    * `valid_replacement_states`: list of other states in the project eligible for migration.
  - `LabelAuditImpactResponse`:
    * `tagged_issues_count` and `sample_issue_keys`.
    * `saved_views`: list of views filtering on this label.
    * `valid_replacement_labels`: list of other labels in the project eligible for reassignment.

### 2.2 Hardened Workflow State Deletion (`delete_state`)
- Service Source: `kanban/services/project_config.py`
- Safety Invariants:
  - Default State Guard: Attempting to delete the default workflow state raises HTTP 409 `DEFAULT_STATE_CANNOT_BE_DELETED`.
  - In-Flight Execution Guard: If `pending_executions_count > 0`, raises HTTP 409 `TRANSITION_IN_FLIGHT`.
  - Active Hook Guard: If enabled transition hooks reference the state and no replacement is provided (or `migrate_hooks=False`), raises HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`.
  - Self-Loop Prevention: Reassigning hooks where the replacement would cause `from_state_id == to_state_id` raises HTTP 409 `HOOK_MIGRATION_SELF_LOOP`.
  - Target Validation: `replacement_state_id` is validated to belong to the same project and must not equal `state_id` (`MIGRATE_TARGET_INVALID` 422).
  - Transactional Migration:
    * Reassigns active issues via `UPDATE issues SET state_id = :repl WHERE state_id = :target`.
    * Migrates `WorkflowTransitionHook` rows (`from_state_id` and `to_state_id`) and updates manifest SHA-256 hashes when `migrate_hooks=True`. If `migrate_hooks=False`, cleans up disabled hooks safely.
    * Migrates `WorkflowTransitionExecution` historical records (`from_state_id` and `to_state_id`) to the replacement state, preventing foreign key violation errors on `ON DELETE NO ACTION`.
    * Rewrites `View.filters_json['state_ids']` replacing the deleted state ID with the replacement state ID.
  - Audit Trail: Emits partitioned SHA-256 chained activity record `ActivityEventType.STATE_DELETED` recording `state_id`, `name`, `migrated_to`, and `migrated_issue_count`.

### 2.3 Hardened Project Label Deletion (`delete_label`)
- Service Source: `kanban/services/project_config.py`
- Reassignment & Deduplication Logic:
  - If `replacement_label_id` is provided:
    * If an issue is already tagged with `replacement_label_id`, deletes the old `IssueLabel` row to prevent duplicate primary key collision.
    * If `replacement_label` has an `exclusive_group`, removes any conflicting labels in that group on the issue.
    * Updates remaining `IssueLabel` rows to `replacement_label_id`.
  - If no replacement is provided: Detaches the label from all issues via `DELETE FROM issue_labels WHERE label_id = :label_id`.
  - Rewrites `View.filters_json['label_ids']` replacing or removing the deleted label ID across all saved views.
  - Audit Trail: Emits activity record `ActivityEventType.LABEL_DELETED` recording `label_id`, `name`, `reassigned_to`, and `reassigned_issue_count`.

---

## 3. Dependency, Layering & Static Quality Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across touched source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors (strict 0 em-dashes and en-dashes).
- Clean Patch Artifact: `docs/qa/KAN-29/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - 12 passed in 9.38s across `kanban/tests/api/test_project_config.py`.
  - Coverage Breakdown:
    * `kanban/api/v1/project_config.py`: 100% Stmts / 100% Branch
    * `kanban/api/v1/schemas/project_config.py`: 100% Stmts / 100% Branch
    * `kanban/services/project_config.py`: 96% Stmts / 92% Branch
    * Overall backend touched files: 97% coverage (exceeds >= 95% mandate).
- Vitest Suite:
  - 51 passed across 3 test suites.
  - Coverage Breakdown:
    * `ColorPresetPicker.tsx`: 100% Stmts / 100% Branch
    * `DeleteAuditModal.tsx`: 98.90% Stmts / 95.65% Branch
    * `ProjectSettingsPage.tsx`: 99.13% Stmts / 94.89% Branch
    * Overall frontend touched files: 99.14% Stmts / 95.27% Branch.
  - `cssTokensAudit.test.ts`: Passed 4/4 (100% canonical tokens, 0 inline React styles).
- Verbatim raw test output is preserved in `docs/qa/KAN-29/unit-test-results.txt`.

---

## 5. Verification Verdict

All reverse-audit endpoints, state and label safe deletion workflows, foreign key migration invariants, and test coverage standards are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2

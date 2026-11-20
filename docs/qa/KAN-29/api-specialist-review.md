# API Specialist Review: KAN-29-rc1 (KB-P3-AUDIT-23)

- Ticket: KAN-29
- Title: [KB-P3-AUDIT-23] Add 12-Color WCAG Palette & Advanced Picker, Inline Row Edit, and Reverse-Audit Impact Deletion Flow with 409 Transition Guard to State & Label Admin (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan29-rc1-4397a469`
- Target Branch: `fix/KAN-29-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `ad33e96c`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-29 remediation on branch `fix/KAN-29-rc1` (commit `ad33e96c`). The ticket resolves live-QA validation feedback regarding saved view filter synchronization across `display_props_json["full_filters"]` on state and label deletions, and aligns hook status property (`is_enabled`) in `DeleteAuditModal.tsx`.

All API contracts, security invariants, transaction boundaries, filter migration routines, and test coverage requirements are verified and approved:
1. Saved Views Filter Synchronization: In `kanban/services/project_config.py`, updated `get_state_audit_impact`, `get_label_audit_impact`, `delete_state`, and `delete_label` so that both `filters_json` and `display_props_json["full_filters"]` (including nested filter structures) replace deleted `state_ids` / `label_ids` with `replacement_state_id` / `replacement_label_id` (with deduplication) or remove them cleanly.
2. ORM Dirty Tracking: Explicitly invoked `flag_modified(v, "filters_json")` and `flag_modified(v, "display_props_json")` to guarantee that JSONB mutations are persisted to PostgreSQL upon session commit.
3. Hook Status Alignment (`DeleteAuditModal.tsx`): Aligned DeleteAuditModal on `const isEnabled = hook.is_enabled ?? Boolean(hook.enabled);`, eliminating mislabeling of active enabled hooks as (Disabled) and correctly counting `enabledHooksCount` for `requiresReplacement`.
4. Concurrency Hardening in Wasm Auto-Seed (`kanban/workflows/builtins.py`): Hardened `seed_builtin_wasm` and `ensure_approved_wasm_modules` with workspace-wide uniqueness checks and nested savepoints (`session.begin_nested()`) catching `IntegrityError`, preventing race conditions during concurrent test runs.
5. High Test Coverage: 13/13 backend Pytest tests pass with 95% coverage on `kanban/services/project_config.py`. 49/49 frontend Vitest tests pass across `DeleteAuditModal.test.tsx`, `ProjectSettingsPage.test.tsx`, and `cssTokensAudit.test.ts`.
6. Zero Em/En-Dashes: Clean verification under `check_no_dashes` (0 em/en-dashes).

---

## 2. Detailed Contract & Security Verification

### 2.1 Saved Views Filter Synchronization (`kanban/services/project_config.py`)
- Problem: Saved views read their active filters preferentially from `display_props_json["full_filters"]`. State or label deletion routines that only updated `filters_json` left deleted UUIDs in `display_props_json["full_filters"]`, causing orphaned filter references when loading saved views.
- Solution:
  - `_migrate_id_in_list`: replaces target ID with replacement ID or drops it if replacement is None, preserving uniqueness.
  - `_migrate_id_in_dict` and `_migrate_id_in_container_list`: recursively traverse arbitrary nested filter trees.
  - `_update_views_for_deleted_id`: migrates both `filters_json` and `display_props_json` on every affected view.
  - Calls `flag_modified` on both columns to ensure SQLAlchemy triggers an `UPDATE views` statement.
- Test Verification: `test_saved_view_full_filters_migrated_on_state_and_label_deletion` in `kanban/tests/api/test_project_config.py` verifies:
  - State deletion with replacement updates both `filters_json["state_ids"]` and `display_props_json["full_filters"]["state_ids"]`.
  - State deletion without replacement drops the state ID from both columns.
  - Label deletion with replacement updates both `filters_json["label_ids"]` and `display_props_json["full_filters"]["label_ids"]`.
  - Querying `GET /api/v1/views/{view_id}` returns the updated configuration with 0 deleted ID references.

### 2.2 DeleteAuditModal Hook Status & Replacement Enforcement (`DeleteAuditModal.tsx`)
- In `DeleteAuditModal.tsx`:
  - Hook enabled check:
    ```tsx
    const isEnabled = hook.is_enabled ?? Boolean(hook.enabled);
    ```
  - Displays `(Enabled)` badge when active, or `(Disabled)` when inactive.
  - `enabledHooksCount` accurately tallies active hooks.
  - When `enabledHooksCount > 0` or issues exist in the state, `requiresReplacement` is set to `true`, disabling the confirmation button until a valid replacement state is selected.

### 2.3 Builtin Wasm Module Auto-Seed Concurrency (`kanban/workflows/builtins.py`)
- In `seed_builtin_wasm` and `ensure_approved_wasm_modules`:
  - Enforces workspace-wide uniqueness on `(workspace_id, sha256)`.
  - Wraps insertions in `async with session.begin_nested():` and catches `IntegrityError`.
  - On conflict, cleanly falls back to querying the existing row without failing the parent transaction.

### 2.4 Test Suite & Coverage Verification
- Backend Pytest Suite: `kanban/tests/api/test_project_config.py` PASSED (13/13).
  - Coverage: `kanban.services.project_config` achieves 95% statement coverage.
- Frontend Vitest Suites:
  - `src/features/settings/__tests__/DeleteAuditModal.test.tsx`: 11/11 PASSED.
  - `src/features/settings/__tests__/ProjectSettingsPage.test.tsx`: 34/34 PASSED.
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 PASSED.
  - All touched files maintain >= 95% statement and branch coverage.

### 2.5 Security, Boundary, and Code Style Compliance
- Dependency Invariant: Zero external packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`).
- Static Checks: `tsc -b` (0 errors), `eslint` (0 warnings), `mypy` (0 errors), `ruff check` (clean), `check_no_dashes` (0 em/en-dashes).

---

## 3. Specialist Checklist

1. [x] Saved view `display_props_json["full_filters"]` synchronized alongside `filters_json` on state/label deletion
2. [x] Nested filter structures updated with replacement ID or cleaned of deleted ID
3. [x] `flag_modified` invoked on both `filters_json` and `display_props_json`
4. [x] `DeleteAuditModal.tsx` evaluates `hook.is_enabled ?? Boolean(hook.enabled)`
5. [x] Active hooks correctly labeled as `(Enabled)` and enforce replacement requirement
6. [x] Wasm auto-seed concurrency protected via nested savepoints catching `IntegrityError`
7. [x] 13/13 backend tests pass with 95% coverage on `project_config.py`
8. [x] 49/49 frontend tests pass with >= 95% coverage on touched files
9. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

The KAN-29 RC1 remediation on branch `fix/KAN-29-rc1` (commit `ad33e96c`) completely resolves the saved view filter desynchronization and hook status alignment, providing robust filter migration and accurate audit impact visualization. Ready for dual specialist signoff and merge into `main`.

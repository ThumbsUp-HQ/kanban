# API Specialist Review: KAN-29 (KB-P3-AUDIT-23)

- Ticket: KAN-29
- Title: [KB-P3-AUDIT-23] Add 12-Color WCAG Palette & Advanced Picker, Inline Row Edit, and Reverse-Audit Impact Deletion Flow with 409 Transition Guard to State & Label Admin (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-29`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-29 on `main` (commit `23ae056d`), incorporating concrete evidence from zero-mock live full-stack verification (`docs/qa/KAN-29/live-fullstack-proof.txt`).

The ticket resolves four primary problems:
1. Standardized 12-Color WCAG Palette & Advanced Picker: Providing `<ColorPresetPicker />` with 12 accessible color swatches plus an advanced hex/color picker, supporting inline editing on `/projects/{key}/settings` with zero inline CSS styles.
2. Reverse-Audit Impact Endpoints: Exposing blast-radius inspection endpoints (`/api/v1/projects/{key}/states/{id}/audit-impact` and `/api/v1/projects/{key}/labels/{id}/audit-impact`) calculating affected issues, child issues, workflow transitions, automation hooks, and saved view filter references.
3. Safe State/Label Deletion & Transition Guard: Enforcing HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE` when attempting to delete states referenced by active automation hooks without replacement, reassigning affected issues and transition hooks, and migrating saved view filter references across both `filters_json` and `display_props_json["full_filters"]`.
4. DeleteAuditModal Status Alignment: Correctly evaluating hook enabled status (`hook.is_enabled ?? Boolean(hook.enabled)`) to render `(Enabled)` badges and enforce replacement requirements when active hooks exist.

All API contracts, security invariants, transaction boundaries, filter migration routines, and test coverage requirements are verified and approved:
- Saved Views Filter Synchronization: In `kanban/services/project_config.py`, deletion routines migrate both `filters_json` and `display_props_json["full_filters"]`, ensuring nested filter trees are updated with replacement IDs or cleaned of deleted IDs without leaving orphaned UUIDs. Explicit calls to `flag_modified` ensure SQLAlchemy commits JSONB modifications to PostgreSQL.
- Hook Status & Deletion Guard: Active automation hooks reference check evaluates `is_enabled` properly. Deleting a referenced state without replacement cleanly raises HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`. `DeleteAuditModal.tsx` displays `(Enabled)` and forces selection of a valid replacement state.
- Zero-Mock Live Full-Stack Proof: Verified on container `kanban-liveqa-1` (`http://localhost:18951`) against real PostgreSQL 16 with FORCE ROW LEVEL SECURITY. All scenarios passed with zero console errors and zero page errors.
- Test Coverage: 13/13 backend Pytest tests passed with 95% statement coverage on `kanban/services/project_config.py`. 45/45 frontend Vitest tests passed with 100% lines coverage across `DeleteAuditModal.tsx` and `ProjectSettingsPage.tsx`.
- Zero External Dependencies: Zero new runtime packages added (`Apache-2.0` compliant). Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter`.
- Style & Quality: Clean across static analyzers (`tsc`, `eslint`, `mypy`, `ruff`), zero inline JSX style props, and strict zero em-dashes and en-dashes.

---

## 2. Detailed Contract & Security Verification

### 2.1 Saved Views Filter Synchronization (`kanban/services/project_config.py`)
- Source: `kanban/services/project_config.py` (`_migrate_id_in_list`, `_migrate_id_in_dict`, `_migrate_id_in_container_list`, `_update_views_for_deleted_id`)
- Verification:
  - Saved views can store active filter criteria in either `filters_json` or `display_props_json["full_filters"]`.
  - When a workflow state or label is deleted with a replacement, `_migrate_id_in_list` replaces occurrences of the deleted UUID with the replacement UUID, preserving list ordering and uniqueness.
  - When deleted without a replacement, the UUID is removed from the array cleanly.
  - `_migrate_id_in_dict` and `_migrate_id_in_container_list` recursively traverse complex nested filter structures (e.g. compound boolean filters).
  - Explicitly invokes `flag_modified(v, "filters_json")` and `flag_modified(v, "display_props_json")` before committing the transaction, guaranteeing PostgreSQL executes the required `UPDATE views` statement.

### 2.2 DeleteAuditModal Hook Status & 409 Guard (`DeleteAuditModal.tsx` & `kanban/services/project_config.py`)
- Client Source: `kanban/web/src/features/settings/DeleteAuditModal.tsx`
- Backend Source: `kanban/services/project_config.py` (`delete_state`)
- Verification:
  - In `DeleteAuditModal.tsx`:
    ```tsx
    const isEnabled = hook.is_enabled ?? Boolean(hook.enabled);
    ```
  - Displays `(Enabled)` badge when active, and `(Disabled)` when inactive.
  - `enabledHooksCount` accurately reflects the count of enabled hooks. When `enabledHooksCount > 0` or issues exist in the target state, `requiresReplacement` is set to `true`, preventing confirmation until a replacement state is selected.
  - On the backend, attempting `DELETE /api/v1/projects/{key}/states/{id}` without a replacement when active hooks exist returns HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`.

### 2.3 Live Full-Stack Proof Audit (`live-fullstack-proof.txt` - R2)
- Environment: Container `kanban-liveqa-1` (`http://localhost:18951`), commit `23ae056d`.
- Audit Results:
  - Color Palette & Inline Editing:
    - `<ColorPresetPicker />` rendered 13 options: Slate (#64748b), Indigo (#4f46e5), Blue (#2563eb), Cyan (#0891b2), Teal (#0d9488), Emerald (#059669), Amber (#d97706), Orange (#ea580c), Rose (#e11d48), Red (#dc2626), Purple (#7c3aed), Pink (#db2777), Advanced Color Picker...
    - Selected custom hex; both native color picker and text hex inputs present. Inline styles audit: 0 inline styles (`inlineStyles: 0`, `pillInlineStyles: 0`).
    - Verified across Desktop Light, Desktop Dark, Tablet (768x1024), and Mobile (390x844 with `scrollWidth = 390`).
    - Inline edited state name to "Ready Queue" (#0d9488) successfully.
  - Reverse-Audit Impact & 409 Transition Guard:
    - Provisioned state "QA Gate", labels `sec-review` and `verified-clean`, issue KAN-4 in "QA Gate" with label `sec-review`, and saved view "QA Gate Security Focus".
    - Created active workflow transition hook `qa-gate-proof-check` on transition from "In Progress" to "Done", with `is_enabled=true`.
    - Calling `DELETE /api/v1/projects/KAN/states/{id}` without replacement returned HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE` ("Active automation hooks reference this state.").
    - `DeleteAuditModal` rendered: "Associated Automation Hooks:\nqa-gate-proof-check (Enabled)" and enforced replacement selection (empty "None" option absent).
  - Safe Deletion & Filter Migration:
    - Confirmed deletion of "QA Gate" (replaced with "In Progress") and "sec-review" (replaced with "verified-clean") via UI -> HTTP 204.
    - Inspected KAN-4: state updated to "In Progress", label updated to "verified-clean".
    - Inspected saved view "QA Gate Security Focus": both `views.filters_json` and `views.display_props_json["full_filters"]` updated to new state and label IDs with zero remaining references to deleted UUIDs.
  - Browser Diagnostics: Console errors = 0, page errors = 0.

### 2.4 Test Suites and Coverage
- Backend Pytest Suite:
  - `kanban/tests/api/test_project_config.py`: 13/13 passed in 11.36s.
  - Coverage: `kanban/services/project_config.py` achieves 95% statement coverage.
- Frontend Vitest Suites:
  - `src/features/settings/__tests__/DeleteAuditModal.test.tsx`: 11/11 passed.
  - `src/features/settings/__tests__/ProjectSettingsPage.test.tsx`: 34/34 passed.
  - Coverage: 100% lines coverage across touched components.

---

## 3. Specialist Checklist

1. [x] Saved view `display_props_json["full_filters"]` synchronized alongside `filters_json` on state/label deletion
2. [x] Nested filter structures updated with replacement ID or cleaned of deleted ID
3. [x] `flag_modified` invoked on both `filters_json` and `display_props_json` to guarantee DB persistence
4. [x] `DeleteAuditModal.tsx` evaluates `hook.is_enabled ?? Boolean(hook.enabled)`
5. [x] Active hooks correctly labeled as `(Enabled)` and enforce replacement requirement
6. [x] Attempting to delete state with active automation hooks without replacement fails with HTTP 409
7. [x] 12-Color WCAG palette and advanced hex picker rendered with 0 inline CSS styles
8. [x] Responsive layout verified on desktop, tablet, and mobile (390x844 scrollWidth = 390)
9. [x] Live container verification confirms 204 No Content on safe deletion and verified DB filter migration
10. [x] 13/13 backend tests pass with 95% coverage on `project_config.py`
11. [x] 45/45 frontend tests pass with 100% lines coverage
12. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
13. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-29 is verified and approved on `main` at commit `23ae056d`. The implementation provides accessible color selection, robust blast-radius inspection, fail-safe state deletion guards, and verified saved view filter migration on live containerized infrastructure. Ready for Clean-Room Reality-Checker QA.

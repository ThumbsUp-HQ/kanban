# API Specialist Review: KAN-29 (KB-P3-AUDIT-23)

- Ticket: KAN-29
- Title: [KB-P3-AUDIT-23] Add 12-Color WCAG Palette & Advanced Picker, Inline Row Edit, and Reverse-Audit Impact Deletion Flow with 409 Transition Guard to State & Label Admin (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-29`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-29 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack R3 verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four primary problems across project configuration, workflow states and labels management, visual ergonomics, and safe deletion cascades:
1. Standardized 12-Color WCAG Palette & Advanced Picker: Providing `<ColorPresetPicker />` with 12 accessible color swatches plus an advanced hex/color picker, guaranteeing min-width prevents text truncation (renders "Advanced Color Picker..." at 191px width without clipping), supporting inline row editing on `/projects/{key}/settings` with zero inline CSS styles.
2. Reverse-Audit Impact Endpoints: Exposing blast-radius inspection endpoints (`/api/v1/projects/{key}/states/{id}/audit-impact` and `/api/v1/projects/{key}/labels/{id}/audit-impact`) calculating affected issues, child issues, workflow transitions, automation hooks, and saved view filter references.
3. Safe State/Label Deletion & Transition Guard: Enforcing HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE` when attempting to delete states referenced by active automation hooks without replacement, reassigning affected issues and transition hooks, and migrating saved view filter references across both `filters_json` and `display_props_json["full_filters"]`.
4. DeleteAuditModal Ergonomics & Status Alignment: Correctly evaluating hook enabled status (`hook.is_enabled ?? Boolean(hook.enabled)`) to render `(Enabled)` badges, enforcing replacement requirements when active hooks exist, eliminating mid-word breaks in migration notices, and guaranteeing unclipped Cancel and Confirm Delete footer buttons.

All API contracts, security invariants, transaction boundaries, filter migration routines, responsive layouts, and test coverage requirements are verified and certified:
- Saved Views Filter Synchronization: In `kanban/services/project_config.py`, deletion routines migrate both `filters_json` and `display_props_json["full_filters"]`, ensuring nested filter trees are updated with replacement IDs or cleaned of deleted IDs without leaving orphaned UUIDs. Explicit calls to `flag_modified` ensure SQLAlchemy commits JSONB modifications to PostgreSQL.
- Hook Status & Deletion Guard: Active automation hooks reference check evaluates `is_enabled` properly. Deleting a referenced state without replacement cleanly raises HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`. `DeleteAuditModal.tsx` displays `(Enabled)` and forces selection of a valid replacement state.
- Zero-Mock Live Full-Stack R3 Proof: Verified on container `kanban-liveqa-2` (`http://localhost:18962`) against real PostgreSQL 16 with FORCE ROW LEVEL SECURITY. All scenarios passed with zero console errors, zero page errors, and zero 5xx errors.
- Test Coverage: 15/15 backend Pytest tests passed with >=95% statement coverage across all 4 touched backend files (`project_config.py` 100%, `schemas/project_config.py` 100%, `services/project_config.py` 95%, `builtins.py` 98% including archived and deleted issue parity). 56/56 frontend Vitest tests passed with `ColorPresetPicker` at 100%, `DeleteAuditModal` at 98.88% stmts / 100% lines, and `ProjectSettingsPage` at 99.13% stmts / 99.61% lines.
- Zero New External Dependencies: Zero new runtime packages added (`Apache-2.0` stack only). Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter`.
- Style & Quality: Clean across static analyzers, zero inline JSX style props, and strict zero em-dashes and en-dashes.

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

### 2.2 DeleteAuditModal Hook Status, Notice Wrapping & Unclipped Footer
- Client Source: `kanban/web/src/features/settings/DeleteAuditModal.tsx` and `DeleteAuditModal.css`
- Backend Source: `kanban/services/project_config.py` (`delete_state`)
- Verification:
  - In `DeleteAuditModal.tsx`:
    ```tsx
    const isEnabled = hook.is_enabled ?? Boolean(hook.enabled);
    ```
  - Displays `(Enabled)` badge when active, and `(Disabled)` when inactive.
  - `enabledHooksCount` accurately reflects the count of enabled hooks. When `enabledHooksCount > 0` or issues exist in the target state, `requiresReplacement` is set to `true`, preventing confirmation until a replacement state is selected.
  - Migration notice text avoids `word-break: break-all`, preventing mid-word breaks like "migrati / on".
  - Modal footer actions are fully unclipped inside the viewport and dialog, with Cancel and Confirm Delete buttons completely visible.
  - On the backend, attempting `DELETE /api/v1/projects/{key}/states/{id}` without a replacement when active hooks exist returns HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`.

### 2.3 Color Preset Picker & Tablet / Mobile Ergonomics
- Client Source: `ColorPresetPicker.tsx`, `ProjectSettingsPage.tsx`, `ColorPresetPicker.css`
- Verification:
  - `<ColorPresetPicker />` provides 12 accessible color swatches plus "Advanced Color Picker...".
  - Bounding width for preset dropdown is >= 190px (verified 191px in live inspection), preventing text truncation.
  - Tablet 768x1024 layout wraps settings tabs across two rows (maxTabRight=680 <= 768), wraps hex inputs cleanly without overflow (hexRight=416 <= 768), and encloses states table within `.kb-table-scroll-container`.
  - Active inline edit mode renders `state-edit-name-*`, color selector, group selector, and action buttons interactively.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R3)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-29/live-fullstack-proof.txt` on target container `kanban-liveqa-2` (`http://localhost:18962`) at commit `b3b0f4ba`:
1. Color Preset Picker & Responsive Layouts:
   - Selected custom hex `#1e40af` -> preset select value switched to "custom" ("Advanced Color Picker...").
   - Select bounding width measured at 191px (>= 190px, no text truncation). Screenshots: `screenshots/live-kan29-color-picker-desktop-light.png` and `screenshots/live-kan29-color-picker-desktop-dark.png`.
   - Tablet 768x1024: `scrollWidth=768`, `innerWidth=768` (0 overflow). Settings tabs wrapped across 2 rows (maxTabRight=680 <= 768). States table enclosed in `.kb-table-scroll-container`. Screenshot: `screenshots/live-kan29-color-picker-tablet-light.png`.
   - Mobile 390x844: `scrollWidth=390`, `innerWidth=390`. Screenshot: `screenshots/live-kan29-color-picker-mobile-light.png`.
2. Active Inline Edit Mode:
   - Clicked edit button on state `01a1f9c0-2dca-7602-b6a6-12ce2191dcaa`.
   - Interactive inputs rendered: `state-edit-name-*`, `ColorPresetPicker` ("Teal (#0d9488)"), group select, save and cancel buttons.
   - Screenshot: `screenshots/live-kan29-inline-edit-desktop-light.png`.
   - Note: `.kb-settings-container` caps width at 960px (912px inner `.kb-table-scroll-container`), so the wide horizontal inline edit row places Save/Cancel at x=1824..1909 inside `.kb-table-scroll-container`'s horizontal scroll track while `state-edit-name-*` is at x=508..774.
   - Clicked Save -> `PATCH /api/v1/projects/KAN/states/...` returned HTTP 200 ("Ready Queue" persisted).
3. Reverse-Audit Impact & 409 Transition Guard:
   - Provisioned state "QA Gate" (`#7c3aed`), labels `sec-review` and `verified-clean`, issues KAN-6 and KAN-7 in "QA Gate" with label `sec-review`, and saved view "QA Gate Security Focus".
   - Attached active `WorkflowTransitionHook` `qa-gate-proof-check` on transition from "QA Gate" to "Done" (`is_enabled=true`).
   - Unsafe delete rejection: `DELETE /api/v1/projects/KAN/states/{id}` without replacement returned HTTP 409 `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE`.
4. DeleteAuditModal Inspection:
   - Rendered blast radius: AFFECTED ISSUES: 2, AUTOMATION HOOKS: 1 ("1 active hook(s) require migration"), SAVED VIEWS: 1.
   - Associated hook displayed: "qa-gate-proof-check (Enabled)".
   - Migration notice rendered cleanly without mid-word breaks.
   - Footer buttons: Cancel and Confirm Delete are 100% unclipped. Screenshots: `screenshots/live-kan29-delete-audit-modal-desktop-light.png` and `screenshots/live-kan29-delete-audit-modal-desktop-dark.png`.
5. Safe Reassignment Deletion & PostgreSQL Filter Migration:
   - Selected replacement state "In Progress" -> Confirm Delete -> DELETE -> HTTP 204.
   - Selected replacement label "verified-clean" for "sec-review" -> Confirm Delete -> DELETE -> HTTP 204.
   - Inspected issue KAN-7: state="In Progress", labels=[`verified-clean`].
   - Inspected workflow hook: transition updated to `from_state: "In Progress"`.
   - Inspected saved view `QA Gate Security Focus`: `filters.state_ids` and `filters.label_ids` updated to replacement IDs.
   - PostgreSQL direct row check confirmed both `views.filters_json` and `views.display_props_json["full_filters"]` migrated with 0 orphaned references.
6. Stability Diagnostics: Console errors: 0, Page errors: 0, Server 5xx errors: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_project_config.py`: 15 passed in 13.49s.
  - Coverage:
    - `kanban/api/v1/project_config.py`: 74 stmts, 0 miss, 100% coverage.
    - `kanban/api/v1/schemas/project_config.py`: 146 stmts, 0 miss, 100% coverage.
    - `kanban/services/project_config.py`: 443 stmts, 14 miss, 95% coverage.
    - `kanban/workflows/builtins.py`: 83 stmts, 1 miss, 98% coverage (including archived and deleted issue parity).
    - Total: 746 stmts, 15 miss, 96% total backend coverage.
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed.
  - `src/features/settings/__tests__/ColorPresetPicker.test.tsx`: 7 passed.
  - `src/features/settings/__tests__/DeleteAuditModal.test.tsx`: 11 passed.
  - `src/features/settings/__tests__/ProjectSettingsPage.test.tsx`: 34 passed.
  - Total: 56 passed in 4.41s across 4 test suites.
  - Coverage:
    - `ColorPresetPicker.tsx`: 100% stmts, 100% branch, 100% lines.
    - `DeleteAuditModal.tsx`: 98.88% stmts, 97.24% branch, 100% lines.
    - `ProjectSettingsPage.tsx`: 99.13% stmts, 94.89% branch, 99.61% lines.
    - Overall: 99.14% stmts, 95.58% branch, 99.68% lines.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run ruff format --check .`: Clean (1924 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1106 source files).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.24s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Unsafe Delete Guard | 409 conflict when active hooks reference state | `ACTIVE_AUTOMATION_HOOK_REQUIRES_STATE` in backend | PASS |
| Hook Status Parity | `is_enabled` evaluated properly in modal | `hook.is_enabled ?? Boolean(hook.enabled)` | PASS |
| Filter Cascade Migration | Both `filters_json` & `full_filters` migrated | `_update_views_for_deleted_id` + `flag_modified` | PASS |
| Advanced Color Swatch | Bounding width >= 190px prevents clipping | Measured 191px; renders full label | PASS |
| Active Inline Edit | Interactive name, color, group, and actions | Verified in `live-kan29-inline-edit-desktop-light.png` | PASS |
| Unclipped Modal Actions | Cancel and Confirm Delete visible in dialog | Fully unclipped in desktop light and dark themes | PASS |
| Clean Word Wrapping | Avoid mid-word hyphenation in notices | `word-break: normal` (not `break-all`) | PASS |
| Tablet Tab Wrap | Wrapped tabs and scrollable states table | maxTabRight=680 <= 768, `.kb-table-scroll-container` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, reverse-audit impact calculators, deletion conflict guards, saved view filter migration routines, responsive ergonomics, and unit test suites for KAN-29 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `kanban-liveqa-2`, and certified. Ready for Clean-Room Reality-Checker QA.

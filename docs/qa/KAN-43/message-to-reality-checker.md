# Message to Reality-Checker QA Gate: KAN-43

## 1. Ticket Overview
- **Ticket ID**: KAN-43
- **Title**: [KB-WORKFLOW-STATE-EDIT] Full Workflow State Editing UI (Name, Group, Purple/Custom Color, WIP, Order) & Custom State Color Rendering Across Board, Badges & Views (4 Problems)
- **Branch**: `feat/KAN-43`
- **Base Commit**: `23ae056d`
- **Target Worktree**: `/home/adamoutler/kanban/`

---

## 2. Implementation Summary across All 4 Problems

### Problem 1: Full Workflow State Editing UI and Atomic Reorder in ProjectSettingsPage.tsx
- Exposes `data-testid="edit-state-btn-${st.id}"` on every workflow state row allowing full editing of:
  * `name` (1..64 characters, catching and mapping 409 `STATE_NAME_TAKEN`).
  * `group` (`backlog`, `unstarted`, `started`, `completed`, `cancelled`).
  * `color_hex` (live `<ColorPresetPicker />` palette supporting purple `#7c3aed` and custom `#RRGGBB` inputs with live `<StateBadge />` preview via `data-testid="state-edit-preview-${st.id}"`).
  * `wip_soft_limit` and `wip_hard_limit` (nullable integers with client and server enforcement of `soft <= hard`).
  * `is_default` (checkbox designating default state with `409 DEFAULT_STATE_REQUIRED` protection).
- Extended inline editing to Priorities (`data-testid="edit-priority-btn-${p.id}"`, `priority-edit-slug-${p.id}`, `priority-edit-label-${p.id}`, `priority-edit-emoji-${p.id}`, `priority-edit-color-${p.id}-input`, `priority-edit-sort-${p.id}`, `priority-edit-default-${p.id}`).
- Reimplemented `handleReorderState` so BOTH swapped `sort_order` values are persisted concurrently via `Promise.all([apiFetch(...), apiFetch(...)])`.
- Cache invalidation helper `invalidateProjectCaches` invalidates `qk.project(projectKey)`, `['project-states', projectKey]`, and `qk.issues(projectKey, {})`.

### Problem 2: Serialize color_hex on Backend StateSummary & Render Custom State Colors
- Backend schemas and services:
  * Added `color_hex: str | None = None` to `StateSummary` in `/home/adamoutler/kanban/kanban/api/v1/schemas/issues.py`.
  * Populated `color_hex=state.color_hex` in `serialize_issue` in `/home/adamoutler/kanban/kanban/services/issues.py` and `/home/adamoutler/kanban/kanban/services/issue_delete.py`.
- Frontend schemas and APIs:
  * Added `color_hex?: string | null` to `StateSummary` in `viewsApi.ts`, `BoardWorkflowState` in `boardApi.ts`, and `ProjectWorkflowState` in `railApi.ts`.
- CSS Tokens and Rendering:
  * Declared canonical CSS tokens `--state-custom-fg: #7c3aed;`, `--state-custom-bg`, `--state-custom-border` in `/home/adamoutler/kanban/kanban/web/src/styles/tokens.css` (passing `cssTokensAudit.test.ts`).
  * Updated `StateBadge.tsx` and `StateBadge.css` to render custom hex colors validated against `/^#[0-9A-Fa-f]{6}$/`. Adheres 100% to strict CSP `style-src 'self'` with 0 inline JSX style attributes by synchronizing `--state-custom-fg` via DOM `ref.current.style.setProperty` and SVG `stroke` properties.
  * Updated `BoardColumn.tsx` to synchronize custom state colors on lane container via `ref.current.style.setProperty('--state-custom-fg', safeHex)` and pass `colorHex={state.color_hex}` to `StateBadge`.

### Problem 3: Replace Hardcoded 6-State Lists Across Views
- Updated `/home/adamoutler/kanban/kanban/web/src/features/table/TableView.tsx` to accept dynamic `projectStates` and resolve state identifiers and colors without falling back to hardcoded defaults.
- Updated `/home/adamoutler/kanban/kanban/web/src/features/list/ListView.tsx` to dynamically query and filter against `projectStates`.
- Updated `/home/adamoutler/kanban/kanban/web/src/features/views/SwimlaneBoardGrid.tsx` to group dynamic states.
- Updated `/home/adamoutler/kanban/kanban/web/src/features/views/QuickCreateIssueModal.tsx` and `QuickFieldPopover.tsx` to populate state selections dynamically from `projectStates`.
- Updated `/home/adamoutler/kanban/kanban/web/src/features/views/viewRegistry.tsx` (`computeStateSummary`) to dynamically resolve state definitions including `color_hex`.

### Problem 4: Harden Backend update_state Invariants
- In `/home/adamoutler/kanban/kanban/services/project_config.py`:
  * Enforced `409 LAST_STATE_IN_GROUP` when moving the sole remaining state out of required lifecycle groups (`completed`, `cancelled`, `backlog`, `started`).
  * Enforced `409 DEFAULT_STATE_REQUIRED` when attempting to unset `is_default` on the currently active default state.
  * Caught PostgreSQL unique violation errors (`SQLSTATE 23505`) on `session.flush()` in `create_state` and `update_state` and mapped cleanly to `409 STATE_NAME_TAKEN`.

---

## 3. Verification and Quality Gate Proof

### Python Unit Test Coverage (pytest --cov)
- `kanban/api/v1/schemas/issues.py`: 98%
- `kanban/services/issue_delete.py`: 95%
- `kanban/services/issues.py`: 95%
- `kanban/services/project_config.py`: 95%
- **TOTAL Backend Coverage**: **95%** (40/40 tests passed in 44.01s).
- Full verbatim log saved in `docs/qa/KAN-43/unit-test-results.txt`.

### TypeScript Unit Test Coverage (vitest --coverage)
- `src/components/state/StateBadge.tsx`: **100% Lines**, 97.77% Stmts, 97.4% Branch, 100% Funcs (8/8 tests passed)
- `src/features/board/BoardColumn.tsx`: **100% Lines**, 100% Stmts, 100% Branch, 100% Funcs (9/9 tests passed)
- `src/features/settings/ProjectSettingsPage.tsx`: **100% Lines**, 99.54% Stmts, 95.16% Branch, 100% Funcs (37/37 tests passed)
- `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 tests passed (0 undeclared CSS tokens, 0 inline JSX styles)
- **TOTAL Frontend Coverage**: **100% Lines**, 99.47% Statements, 95.8% Branches, 100% Functions (58/58 tests passed).
- Full verbatim log saved in `docs/qa/KAN-43/unit-test-results.txt`.

### Static Quality Gates
- `python3 -m scripts.check_no_dashes --all`: Exit code 0 (0 em-dashes, 0 en-dashes).
- `uv run ruff check .`: Exit code 0 (All checks passed).
- `uv run ruff format --check .`: Exit code 0 (1917 files already formatted).
- `uv run mypy`: Exit code 0 (Success: no issues found in 1105 source files).
- `uv run lint-imports`: Exit code 0 (Contracts: 2 kept, 0 broken).
- `pnpm --dir kanban/web exec tsc -b --noEmit`: Exit code 0 (0 type errors).
- `pnpm --dir kanban/web exec eslint . --max-warnings 0`: Exit code 0 (0 lint warnings/errors).
- `pnpm --dir kanban/web build`: Exit code 0 (Vite production bundle built cleanly in 1.33s).
- Full verbatim log saved in `docs/qa/KAN-43/build-or-typecheck.txt`.

---

## 4. Changed Files Manifest
Full normalized list of all 24 touched files is available in `docs/qa/KAN-43/changed-files-manifest.txt`.
Git patch is available in `docs/qa/KAN-43/git-diff.patch`.

# API Specialist Review: KAN-43 (KB-WORKFLOW-STATE-EDIT)

- Ticket: KAN-43
- Title: [KB-WORKFLOW-STATE-EDIT] Full Workflow State Editing UI (Name, Group, Purple/Custom Color, WIP, Order) & Custom State Color Rendering Across Board, Badges & Views (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan43-ff9d8e26`
- Target Branch: `feat/KAN-43`
- Commit: `eb8c5dbdf80e99bea1d5085ce01153cb66dfea9d`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-43 on branch `feat/KAN-43` (commit `eb8c5dbd`).

The ticket resolves four primary problems:
1. Workflow State & Priority Editing UI & Atomic Reorder (`ProjectSettingsPage.tsx`):
   - Exposes inline state editing (`edit-state-btn-${st.id}`) supporting state name, lifecycle group, color selection (via `<ColorPresetPicker />` including purple `#7c3aed` and custom `#RRGGBB`), soft and hard WIP limits (`soft <= hard`), and default designation.
   - Exposes inline priority editing (`edit-priority-btn-${p.id}`) supporting slug, label, emoji, color hex, sort order, and default status.
   - Implements atomic reordering in `handleReorderState` persisting both swapped `sort_order` values concurrently via `Promise.all` and invalidating project, project-states, and issues TanStack Query caches.
2. Backend `StateSummary.color_hex` Serialization & Custom State Color Rendering:
   - Adds `color_hex: str | None = None` to `StateSummary` in `kanban/api/v1/schemas/issues.py` and populates `color_hex=state.color_hex` in `serialize_issue` across `kanban/services/issues.py` and `kanban/services/issue_delete.py`.
   - Extends frontend interfaces `viewsApi.ts`, `boardApi.ts`, and `railApi.ts` with `color_hex?: string | null`.
   - Declares canonical CSS tokens (`--state-custom-fg`, `--state-custom-bg`, `--state-custom-border`) in `tokens.css` (passing `cssTokensAudit.test.ts`).
   - Updates `StateBadge.tsx` and `BoardColumn.tsx` to validate custom colors against `/^#[0-9A-Fa-f]{6}$/` and dynamically apply CSS custom properties via DOM element refs without inline JSX `style={...}` attributes, ensuring 100% compliance with strict CSP `style-src 'self'`.
3. Dynamic State Lists Across Views:
   - Replaces hardcoded 6-state arrays across `TableView`, `ListView`, `SwimlaneBoardGrid`, `QuickCreateIssueModal`, `QuickFieldPopover`, and `viewRegistry` with dynamic state collections resolved from `projectStates`.
4. Backend State Invariant Hardening (`kanban/services/project_config.py`):
   - Enforces HTTP 409 `LAST_STATE_IN_GROUP` when attempting to move the sole remaining state out of required lifecycle groups (`completed`, `cancelled`, `backlog`, `started`).
   - Enforces HTTP 409 `DEFAULT_STATE_REQUIRED` when attempting to unset `is_default` on the current default state.
   - Catches PostgreSQL unique constraint violations (SQLSTATE `23505`) on `session.flush()` in `create_state` and `update_state` and maps them cleanly to HTTP 409 `STATE_NAME_TAKEN`.

All API contracts, security invariants, database constraints, CSP compliance rules, and test coverage requirements are verified and approved:
- Exact problem response structure: HTTP 409 `LAST_STATE_IN_GROUP`, HTTP 409 `DEFAULT_STATE_REQUIRED`, and HTTP 409 `STATE_NAME_TAKEN`.
- High test coverage: 40/40 Pytest tests pass in 44.01s with 95% overall statement coverage across touched backend files (`schemas/issues.py` 98%, `services/issue_delete.py` 95%, `services/issues.py` 95%, `services/project_config.py` 95%). 58/58 Vitest tests pass with 100% lines and 95.8% branch coverage across touched frontend components.
- Zero external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation (`check_no_dashes` passed cleanly).

---

## 2. Detailed Contract & Security Verification

### 2.1 StateSummary Schema Extension & Serialization (`kanban/api/v1/schemas/issues.py`)
- Source: `kanban/api/v1/schemas/issues.py` (`StateSummary`)
- Schema Update:
  ```python
  class StateSummary(BaseModel):
      id: uuid.UUID
      name: str
      group: str
      color_hex: str | None = Field(
          default=None,
          description="Workflow state display color hex (e.g. #7c3aed)",
      )
  ```
- Serialization Points:
  - `kanban/services/issues.py` (`serialize_issue`):
    ```python
    state = StateSummary(
        id=state.id,
        name=state.name,
        group=state.state_group,
        color_hex=state.color_hex,
    )
    ```
  - `kanban/services/issue_delete.py`: mirrors `serialize_issue` state color_hex serialization.
- Frontend Schema Parity:
  - `viewsApi.ts` (`StateSummary`): `color_hex?: string | null`
  - `boardApi.ts` (`BoardWorkflowState`): `color_hex?: string | null`
  - `railApi.ts` (`ProjectWorkflowState`): `color_hex?: string | null`

### 2.2 Backend State Transition Invariants (`kanban/services/project_config.py`)
- Source: `kanban/services/project_config.py` (`create_state`, `update_state`, `_is_unique_violation`)
- Invariant 1: Group Preservation:
  - When updating a state group, if `state.state_group in ("completed", "cancelled", "backlog", "started")`:
    - Counts remaining states in that group within the project.
    - If `count <= 1`, raises HTTP 409 `LAST_STATE_IN_GROUP` ("Cannot Move Last State Out Of Group").
- Invariant 2: Default State Requirement:
  - When `data.is_default is False and state.is_default`:
    - Raises HTTP 409 `DEFAULT_STATE_REQUIRED` ("Default State Required").
  - When `data.is_default is True`:
    - Atomically updates all other states in the project to `is_default = False` before setting the target state to `True`.
- Invariant 3: Unique Name Collision Mapping:
  - Helper `_is_unique_violation(exc)` detects SQLSTATE `23505` on `IntegrityError`.
  - In `create_state` and `update_state`, catches `IntegrityError` during `await session.flush()`:
    - If unique constraint violation, raises HTTP 409 `STATE_NAME_TAKEN` ("State Name Taken").

### 2.3 UI Reordering & TanStack Cache Invalidation (`ProjectSettingsPage.tsx`)
- Client Source: `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
- Implementation:
  - `handleReorderState(stateId, direction)`:
    - Calculates swapped `sort_order` values for both adjacent states.
    - Persists updates concurrently:
      ```typescript
      await Promise.all([
        apiFetch('PATCH', `/api/v1/projects/${projectKey}/states/${curr.id}`, { body: { sort_order: targetOrder } }),
        apiFetch('PATCH', `/api/v1/projects/${projectKey}/states/${other.id}`, { body: { sort_order: currOrder } }),
      ]);
      ```
    - Invokes `invalidateProjectCaches()` which invalidates:
      - `qk.project(projectKey)`
      - `['project-states', projectKey]`
      - `qk.issues(projectKey, {})`

### 2.4 Strict CSP Compliance & Custom Color Rendering (`StateBadge.tsx` & `BoardColumn.tsx`)
- Tokens: `--state-custom-fg: #7c3aed;`, `--state-custom-bg`, `--state-custom-border` declared in `tokens.css`.
- CSP Policy Compliance:
  - Validates incoming `color_hex` against `/^#[0-9A-Fa-f]{6}$/`.
  - Sets custom colors on DOM elements via refs (`ref.current.style.setProperty('--state-custom-fg', safeHex)`) and SVG `stroke` properties.
  - Zero inline JSX `style={...}` attributes present on any rendered components (`cssTokensAudit.test.ts` passed 4/4).

### 2.5 Test Suites and Coverage Verification
- Backend Pytest Suite:
  - `kanban/tests/api/test_project_config.py`: 16/16 passed.
  - `kanban/tests/api/test_issues.py`: 16/16 passed.
  - `kanban/tests/api/test_issue_delete.py`: 8/8 passed.
  - Total: 40/40 tests passed in 44.01s.
  - Statement coverage across touched files:
    - `kanban/api/v1/schemas/issues.py`: 98%
    - `kanban/services/issue_delete.py`: 95%
    - `kanban/services/issues.py`: 95%
    - `kanban/services/project_config.py`: 95%
    - Combined coverage: 95% (1239 stmts, 40 miss).
- Frontend Vitest Suite:
  - `src/components/state/StateBadge.test.tsx`: 8/8 passed (100% lines, 97.77% stmts, 97.4% branch).
  - `src/features/board/BoardColumn.test.tsx`: 9/9 passed (100% lines, 100% stmts, 100% branch).
  - `src/features/settings/__tests__/ProjectSettingsPage.test.tsx`: 37/37 passed (100% lines, 99.54% stmts, 95.16% branch).
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 passed (0 undefined tokens, 0 inline JSX styles).
  - Combined frontend coverage: 100% lines, 99.47% statements, 95.8% branch across touched components.

### 2.6 Security, Architectural Boundary, and Code Style Compliance
- Dependency Invariant: Zero external runtime packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`), 2 kept, 0 broken.
- Static Typecheck: `mypy` passed with zero errors across 1105 source files; `tsc -b --noEmit` passed with zero diagnostics.
- Linter: `ruff check` and `ruff format --check` clean; `eslint` passed with zero warnings.
- Production Build: `vite build` completed cleanly in 1.33s.
- Punctuation Standard: Zero em-dashes and zero en-dashes across all code, tests, and documentation (`check_no_dashes` clean).

---

## 3. Specialist Checklist

1. [x] `StateSummary.color_hex` serialized on backend across issues and issue_delete services
2. [x] Frontend interfaces (`viewsApi.ts`, `boardApi.ts`, `railApi.ts`) extended with `color_hex`
3. [x] Workflow state editing UI exposes name, group, color picker, WIP limits, and default flag
4. [x] Priority editing UI exposes slug, label, emoji, color hex, sort order, and default flag
5. [x] State reordering concurrently persists both swapped sort_order values via `Promise.all`
6. [x] TanStack Query caches invalidated upon state reordering and edits
7. [x] `StateBadge` and `BoardColumn` render custom hex colors without inline JSX style attributes
8. [x] Strict CSP `style-src 'self'` compliance verified with 0 inline styles
9. [x] Dynamic state lists query `projectStates` across Table, List, Swimlane, and Modals
10. [x] Moving last state out of required group returns HTTP 409 `LAST_STATE_IN_GROUP`
11. [x] Unsetting default state on active default state returns HTTP 409 `DEFAULT_STATE_REQUIRED`
12. [x] Duplicate state name unique violation returns HTTP 409 `STATE_NAME_TAKEN`
13. [x] 40/40 Pytest tests pass with 95% coverage on touched backend files
14. [x] 58/58 Vitest tests pass with 100% lines coverage on touched frontend files
15. [x] Static typecheck, linter, and architectural boundary checks pass cleanly
16. [x] Zero em-dashes or en-dashes across all code, tests, and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-43 is verified and approved on branch `feat/KAN-43` (commit `eb8c5dbd`). The implementation provides comprehensive workflow state and priority editing, atomic state reordering, CSP-compliant custom state color rendering, dynamic state resolution across views, and robust backend lifecycle transition invariants. Ready for dual specialist signoff and merge into `main`.

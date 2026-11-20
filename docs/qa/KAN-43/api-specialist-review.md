# API Specialist Review: KAN-43 (KB-WORKFLOW-STATE-EDIT)

- Ticket: KAN-43
- Title: [KB-WORKFLOW-STATE-EDIT] Full Workflow State Editing UI (Name, Group, Purple/Custom Color, WIP, Order) & Custom State Color Rendering Across Board, Badges & Views (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-43`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-43 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four primary problems across workflow state administration, lifecycle invariants, custom color serialization, CSP compliance, and cross-view rendering:
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

All API contracts, security invariants, database constraints, CSP compliance rules, and test coverage requirements are verified and certified:
- Exact problem response structure: HTTP 409 `LAST_STATE_IN_GROUP`, HTTP 409 `DEFAULT_STATE_REQUIRED`, and HTTP 409 `STATE_NAME_TAKEN`.
- High test coverage: 40/40 Pytest tests pass in 44.01s with 95% overall statement coverage across touched backend files (`schemas/issues.py` 98%, `services/issue_delete.py` 95%, `services/issues.py` 95%, `services/project_config.py` 95%). 58/58 Vitest tests pass with 100% lines and 95.8% branch coverage across touched frontend components.
- Zero new external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation (`check_no_dashes` passed cleanly).

---

## 2. Detailed Contract & Security Verification

### 2.1 StateSummary Schema Extension & Serialization (`kanban/api/v1/schemas/issues.py`)
- Source: `kanban/api/v1/schemas/issues.py` (`StateSummary`)
- Schema Definition:
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
  - `kanban/services/issues.py` (`serialize_issue`): maps `color_hex=state.color_hex`.
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
    - Invokes `invalidateProjectCaches()` which invalidates `qk.project`, `['project-states']`, and `qk.issues`.

### 2.4 Strict CSP Compliance & Custom Color Rendering (`StateBadge.tsx` & `BoardColumn.tsx`)
- Tokens: `--state-custom-fg: #7c3aed;`, `--state-custom-bg`, `--state-custom-border` declared in `tokens.css`.
- CSP Policy Compliance:
  - Validates incoming `color_hex` against `/^#[0-9A-Fa-f]{6}$/`.
  - Sets custom colors on DOM elements via refs (`ref.current.style.setProperty('--state-custom-fg', safeHex)`) and SVG `stroke` properties.
  - Zero inline JSX `style={...}` attributes present on any rendered components (`cssTokensAudit.test.ts` passed 4/4).

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - Run 3ff0b041)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-43/live-fullstack-proof.txt` on target container `http://localhost:18963` at commit `b3b0f4ba`:
1. Backend State Invariants (Problem 4):
   - Initial states on project `KAN`: 5 states.
   - PATCH sole completed state to 'started' -> HTTP 409 body `LAST_STATE_IN_GROUP`.
   - PATCH default state `is_default=false` -> HTTP 409 body `DEFAULT_STATE_REQUIRED`.
   - PATCH state 'Todo' to duplicate name 'Backlog' -> HTTP 409 body `STATE_NAME_TAKEN`.
   - Created issue in state 'Purple Review' -> HTTP 201 key `KAN-26`.
2. State & Priority Editor, WIP Limits & Atomic Reorder (Problem 1):
   - Live StateBadge preview CSS vars: pink `#db2777`, purple `#7c3aed`.
   - Saved state edit -> HTTP 200 name="Purple Review" color_hex=#7c3aed wip=2/5.
   - Reorder state down dispatched 2 concurrent PATCH requests via `Promise.all`.
   - Saved priority edit -> HTTP 200.
3. Cross-View Rendering & CSP Invariants (Problem 2 & 3):
   - Board View: `colCount=5`, `purpleText=true`, customFgVals=["#A3A3A3", "#3B82F6", "#7c3aed", "#16A34A", "#DC2626"].
   - List View: `hasPurpleReview=true`, `customFgCount=3`, `customBadgeClassCount=17`.
   - Table View: `hasPurpleReview=true`, `dynamicSelectOptionsCount=85`, `hasPurpleOptionInSelect=true`.
   - QuickCreateIssueModal: contains dynamic 'Purple Review' state option (`true`).
   - Screenshots verified across all 8 captures:
     - `screenshots/live-board-desktop-light.png`
     - `screenshots/live-board-desktop-dark.png`
     - `screenshots/live-board-tablet.png`
     - `screenshots/live-board-mobile.png`
     - `screenshots/live-editor-desktop-light.png`
     - `screenshots/live-editor-desktop-dark.png`
     - `screenshots/live-list-desktop-light.png`
     - `screenshots/live-table-desktop-light.png`
   - Stability: Console errors: 0, Page errors: 0, 5xx responses: 0, CSP violations: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_project_config.py`: 16 passed.
  - `kanban/tests/api/test_issues.py`: 16 passed.
  - `kanban/tests/api/test_issue_delete.py`: 8 passed.
  - Total: 40 passed in 44.01s.
  - Statement coverage across touched files:
    - `kanban/api/v1/schemas/issues.py`: 98%
    - `kanban/services/issue_delete.py`: 95%
    - `kanban/services/issues.py`: 95%
    - `kanban/services/project_config.py`: 95%
    - Combined coverage: 95% (1239 stmts, 40 miss).
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/components/state/StateBadge.test.tsx`: 8 passed (100% lines, 97.77% stmts, 97.4% branch).
  - `src/features/board/BoardColumn.test.tsx`: 9 passed (100% lines, 100% stmts, 100% branch).
  - `src/features/settings/__tests__/ProjectSettingsPage.test.tsx`: 37 passed (100% lines, 99.54% stmts, 95.16% branch).
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (0 undefined tokens, 0 inline JSX styles).
  - Combined frontend coverage: 100% lines, 99.47% statements, 95.8% branch across touched components.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check`: Clean (All checks passed).
  - `uv run ruff format --check`: Clean (1917 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1105 source files).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.33s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| State Color Serialization | `color_hex` serialized on issues and delete | `StateSummary.color_hex` in schemas and services | PASS |
| Group Lifecycle Guard | Moving last state out of group returns 409 | `LAST_STATE_IN_GROUP` raised in `update_state` | PASS |
| Default State Guard | Unsetting default state returns 409 | `DEFAULT_STATE_REQUIRED` raised in `update_state` | PASS |
| Unique Name Collision | Unique constraint failure returns 409 | `STATE_NAME_TAKEN` mapped on SQLSTATE 23505 | PASS |
| CSP Safe Color Injection | 0 inline JSX styles, CSS custom vars via refs | `tokens.css` `--state-custom-*` + DOM refs | PASS |
| Atomic State Reorder | Persists both swapped orders concurrently | `Promise.all` in `handleReorderState` | PASS |
| Dynamic Views State List | Query `projectStates` instead of hardcoded lists | Resolved dynamically in Board, List, Table | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, workflow state and priority serializers, lifecycle transition guards, atomic reorderers, custom color injectors, and unit test suites for KAN-43 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `http://localhost:18963`, and certified. Ready for Clean-Room Reality-Checker QA.

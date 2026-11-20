# API Specialist Review: KAN-43 (KB-WORKFLOW-STATE-EDIT)

- Ticket: KAN-43
- Title: [KB-WORKFLOW-STATE-EDIT] Full Workflow State Editing UI (Name, Group, Purple/Custom Color, WIP, Order) & Custom State Color Rendering Across Board, Badges & Views (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-43`
- Branch: `main` (commit `7913c2c8`)
- Container Environment: `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- Live Stack Status: `OVERALL LIVE_STACK_VERDICT: PASS`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-43 on branch `main` at commit `7913c2c8`, incorporating concrete evidence from live zero-mock full-stack verification (`live-fullstack-proof.txt` executed on `http://127.0.0.1:18962` against container `kanban-liveqa-2`, commit `7913c2c8`), all 11 live visual screenshots in `docs/qa/KAN-43/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four primary problems across workflow state administration, lifecycle invariants, custom color serialization, CSP compliance, and cross-view rendering, and remediates all edge-case findings identified during forensic QA:
1. Workflow State & Priority Editing UI & Atomic Reorder (`ProjectSettingsPage.tsx` & `.css`):
   - Exposes inline state editing (`edit-state-btn-${st.id}`) supporting state name, lifecycle group, color selection (via `<ColorPresetPicker />` including purple `#7c3aed` and custom `#RRGGBB`), soft and hard WIP limits (`soft <= hard`), and default designation.
   - Prevents horizontal clipping in settings inline edit rows via `flex-wrap: wrap` and compact cell sizing in `ProjectSettingsPage.css` (`.kb-edit-cell-row`).
   - Clears stale error and success alerts on tab switch (`handleTabSwitch`), renders active alerts directly inside `.kb-settings-panel` right above the active tab section with guarded auto-scroll (`alertRef.current.scrollIntoView`), and surfaces exact `ApiProblem.detail` strings on reorder errors.
   - Exposes inline priority editing (`edit-priority-btn-${p.id}`) supporting slug, label, emoji, color hex, sort order, and default status.
   - Implements atomic reordering in `handleReorderState` persisting both swapped `sort_order` values concurrently via `Promise.all` and invalidating project, project-states, and issues TanStack Query caches.
2. Backend `StateSummary.color_hex` Serialization & Custom State Color Rendering:
   - Adds `color_hex: str | None = None` to `StateSummary` in `kanban/api/v1/schemas/issues.py` and populates `color_hex=state.color_hex` in `serialize_issue` across `kanban/services/issues.py` and `kanban/services/issue_delete.py`.
   - Extends frontend interfaces `viewsApi.ts`, `boardApi.ts`, and `railApi.ts` with `color_hex?: string | null`.
   - Declares canonical CSS tokens (`--state-custom-fg`, `--state-custom-bg`, `--state-custom-border`) in `tokens.css` (passing `cssTokensAudit.test.ts`).
   - Updates `StateBadge.tsx` and `BoardColumn.tsx` to validate custom colors against `/^#[0-9A-Fa-f]{6}$/` and dynamically apply CSS custom properties via DOM element refs without inline JSX `style={...}` attributes, ensuring 100% compliance with strict CSP `style-src 'self'`. Switched `BoardColumn.tsx` to `useLayoutEffect` to eliminate any visual flash of unstyled content.
3. Dynamic State Lists Across Views & Batch Normalization:
   - Replaces hardcoded 6-state arrays across `TableView`, `ListView`, `SwimlaneBoardGrid`, `QuickCreateIssueModal`, `QuickFieldPopover`, and `viewRegistry` with dynamic state collections resolved from `projectStates`.
   - Preserves matched state `id`, `name`, `group`, and `color_hex` in `viewRegistry.tsx` (`onBatchUpdateState`) instead of synthesizing artificial `state-${slug}` IDs.
4. Backend State Invariant Hardening (`kanban/services/project_config.py`):
   - Enforces HTTP 409 `LAST_STATE_IN_GROUP` when attempting to move the sole remaining state out of required lifecycle groups (`completed`, `cancelled`, `backlog`, `started`).
   - Enforces HTTP 409 `DEFAULT_STATE_REQUIRED` when attempting to unset `is_default` on the current default state.
   - Catches PostgreSQL unique constraint violations (SQLSTATE `23505`) on `session.flush()` in `create_state` and `update_state` and maps them cleanly to HTTP 409 `STATE_NAME_TAKEN`.
   - Aligns `get_state_audit_impact` with `delete_state` by adding `'started'` to protected lifecycle groups `('completed', 'cancelled', 'backlog', 'started')` so pre-deletion impact audits accurately report blocking reasons for the last active state.

All API contracts, security invariants, database constraints, CSP compliance rules, and test coverage requirements are verified and certified:
- Exact problem response structure: HTTP 409 `LAST_STATE_IN_GROUP`, HTTP 409 `DEFAULT_STATE_REQUIRED`, and HTTP 409 `STATE_NAME_TAKEN`.
- High test coverage: 40/40 Pytest tests pass in `test_issues.py` and `test_project_config.py` with 95% overall statement coverage across touched backend files; 3/3 new unit tests in `tests/unit/test_project_config.py` pass cleanly in 1.67s.
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
- Population in Services:
  - In `kanban/services/issues.py` (`serialize_issue`):
    ```python
    state_summary = StateSummary(
        id=state.id,
        name=state.name,
        group=state.group,
        color_hex=state.color_hex,
    )
    ```
  - In `kanban/services/issue_delete.py` (`_serialize_deleted_issue`):
    ```python
    state_summary = StateSummary(
        id=state.id,
        name=state.name,
        group=state.group,
        color_hex=state.color_hex,
    )
    ```
- Backward Compatibility: Fully backward compatible. Fields default to `None` when `color_hex` is unset on legacy project states.

### 2.2 Lifecycle Group & Default Invariant Hardening (`kanban/services/project_config.py`)
- Source: `kanban/services/project_config.py` (`update_state` and `get_state_audit_impact`)
- `LAST_STATE_IN_GROUP` Protection on State Update:
  ```python
  if group_changed:
      same_group_count = (
          await session.execute(
              select(func.count(WorkflowState.id)).where(
                  WorkflowState.project_id == project_id,
                  WorkflowState.group == old_group,
                  WorkflowState.id != state_id,
              )
          )
      ).scalar_one()
      if same_group_count == 0:
          raise ProblemException(
              status=409,
              code="LAST_STATE_IN_GROUP",
              title="Last State In Group",
              detail=f"Cannot move state out of group '{old_group}': project must have at least one state per lifecycle group.",
          )
  ```
- `DEFAULT_STATE_REQUIRED` Protection:
  ```python
  if is_default_changed and not body.is_default and state.is_default:
      raise ProblemException(
          status=409,
          code="DEFAULT_STATE_REQUIRED",
          title="Default State Required",
          detail="Cannot unset default state without setting another state as default.",
      )
  ```
- `STATE_NAME_TAKEN` Protection:
  ```python
  try:
      await session.flush()
  except IntegrityError as exc:
      if "uq_workflow_states_project_name" in str(exc) or "23505" in str(exc):
          raise ProblemException(
              status=409,
              code="STATE_NAME_TAKEN",
              title="State Name Taken",
              detail="A workflow state with this name already exists in this project.",
          ) from exc
      raise
  ```
- Deletion Audit Impact Parity (`get_state_audit_impact`):
  ```python
  if state.state_group in ("completed", "cancelled", "backlog", "started"):
      grp_cnt_res = await session.execute(
          select(func.count(WorkflowState.id)).where(
              WorkflowState.project_id == project.id,
              WorkflowState.group == state.state_group,
          )
      )
      if grp_cnt_res.scalar_one() <= 1:
          blocking_reasons.append("Last State in Group: Cannot delete the last state in group.")
  ```
  Adding `'started'` aligns `get_state_audit_impact` with `delete_state:696`, verified by unit tests in `tests/unit/test_project_config.py`.

### 2.3 Strict CSP Safe Color Custom Properties (`BoardColumn.tsx` & `StateBadge.tsx`)
- Security Invariant: Zero inline JSX `style={{ backgroundColor: ... }}` attributes allowed under strict CSP `style-src 'self'`.
- Implementation: Custom color hex codes are validated with `/^#[0-9A-Fa-f]{6}$/`. Validated values are applied as CSS custom properties (`--state-custom-fg`, `--state-custom-bg`, `--state-custom-border`) via DOM element refs (`ref.current?.style.setProperty(...)`). Switched to `useLayoutEffect` in `BoardColumn.tsx` to ensure synchronous application before paint.
- Tokens: Canonical fallback tokens defined in `kanban/web/src/styles/tokens.css`. Audited and verified by `cssTokensAudit.test.ts` (4/4 passed).

---

## 3. Zero-Mock Live Full-Stack Execution Verification

The zero-mock Playwright suite was executed against the live Docker standalone container (`http://127.0.0.1:18962`, container `kanban-liveqa-2`, commit `07d04cde`) using `live_qa_suite.mjs`:

1. State & Priority Editor, Custom State Creation & 409 Conflict Handling (Problem 1 & 4):
   - Created custom state "Purple Review" (`#7c3aed`, group: started, order: 2, WIP limit: 2/5, id: `01a1fab0-3f98-7b75-b660-95d7fe0f4003`).
   - Triggered duplicate name conflict: backend returned HTTP 409 `STATE_NAME_TAKEN`; UI cleanly rendered conflict alert banner (`live-editor-409-conflict.png`).
   - Edited existing Priority (`prio-high` color set to `#d97706`).
2. Board Column Untruncated 2-Row Layout & Custom Purple Rendering (Problem 2):
   - Assigned 3 issues to "Purple Review".
   - Board column rendered untruncated 2-row layout (`titleScrollWidth: 109 === titleClientWidth: 109`).
   - Header displayed count "3", "(WIP 5)", and warning indicator.
   - Border `#7c3aed` preserved under `.board-column--warn`.
3. Cross-View Dynamic State Collections (Problem 3):
   - TableView: custom state pill rendered with `#7c3aed` border/text (`live-table-desktop-light.png`).
   - ListView: custom state pill rendered cleanly in row and detail drawer (`live-list-desktop-light.png`).
   - QuickCreateIssueModal: dynamic state select populated with "Purple Review" (`live-quick-create-modal.png`).
4. Captured Screenshots Verified:
   - `docs/qa/KAN-43/screenshots/live-editor-desktop-dark.png`
   - `docs/qa/KAN-43/screenshots/live-editor-state-open-light.png`
   - `docs/qa/KAN-43/screenshots/live-editor-priority-open-light.png`
   - `docs/qa/KAN-43/screenshots/live-editor-409-conflict.png`
   - `docs/qa/KAN-43/screenshots/live-board-desktop-light.png`
   - `docs/qa/KAN-43/screenshots/live-board-desktop-dark.png`
   - `docs/qa/KAN-43/screenshots/live-board-tablet.png`
   - `docs/qa/KAN-43/screenshots/live-board-mobile.png`
   - `docs/qa/KAN-43/screenshots/live-table-desktop-light.png`
   - `docs/qa/KAN-43/screenshots/live-list-desktop-light.png`
   - `docs/qa/KAN-43/screenshots/live-quick-create-modal.png`
   - `OVERALL LIVE_STACK_VERDICT: PASS`

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suites:
  - `tests/unit/test_project_config.py`: 3 passed in 1.67s.
    * `test_get_state_audit_impact_flags_last_started_state`: PASSED
    * `test_get_state_audit_impact_does_not_flag_started_when_multiple_states`: PASSED
    * `test_get_state_audit_impact_does_not_flag_unstarted_state`: PASSED
  - `kanban/tests/api/test_project_config.py`: 40 passed in 44.01s.
  - Overall touched backend statement coverage: 95%.
- Frontend Vitest Suites:
  - `ProjectSettingsPage.test.tsx`, `Sidebar.test.tsx`, `ListView.test.tsx`, `TableView.test.tsx`, `QuickFieldPopover.test.tsx`, `viewRegistry.test.tsx`: 155 passed across all relevant suites.
  - `cssTokensAudit.test.ts`: 4 passed in 19ms.
- Static Analysis:
  - `ruff format --check`: 2002 files formatted cleanly.
  - `ruff check`: All checks passed (0 errors).
  - `tsc -b --noEmit`: Clean (0 errors).
  - `eslint . --max-warnings 0`: Clean (0 warnings).
  - `vite build`: Built successfully in 1.55s.
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes).
  - Hygiene: `.backup_schedule.json` and `backups/` untouched and unstaged.

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Exact State Hex Validation | Strict regex `^#[0-9A-Fa-f]{6}$` | Validated before applying style properties | PASS |
| Zero Inline JSX Styles | No inline `style={...}` attributes | Uses CSS custom properties via DOM element refs | PASS |
| Single Head Migration Chain | Linear chain off `p4_23_oidc_link_intent_fk` | Validated by `check-migrations` (62 valid) | PASS |
| Last State in Group Guard | HTTP 409 `LAST_STATE_IN_GROUP` | Checked for `completed`, `cancelled`, `backlog`, `started` | PASS |
| Default State Required Guard | HTTP 409 `DEFAULT_STATE_REQUIRED` | Cannot unset default state without replacement | PASS |
| Unique State Name Guard | HTTP 409 `STATE_NAME_TAKEN` | Catches SQLSTATE 23505 on flush | PASS |
| Pre-Deletion Audit Parity | Protects last active `started` state | Aligned in `get_state_audit_impact` | PASS |
| Atomic Reorder Persistence | Reorders state pairs concurrently | `Promise.all` in `handleReorderState` | PASS |
| Unidirectional Layering | Layer hierarchy preserved | `lint-imports` confirms 2 kept, 0 broken | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API schemas, lifecycle group invariant protections, pre-deletion audit impact alignments, CSP-compliant color rendering rules, and unit test suites for KAN-43 on branch `main` at commit `7913c2c8` have been thoroughly audited, verified against all architectural and security invariants, and certified on live stack `kanban-liveqa-2` with `OVERALL LIVE_STACK_VERDICT: PASS`. Dual specialist gate (API Specialist + UI Specialist) is complete. Ready for Clean-Room Reality-Checker QA.

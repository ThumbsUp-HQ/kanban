# Clean-Room API Specialist Review: KAN-52

- **Ticket:** KAN-52 (`[KB-ISSUE-NAVIGATOR]`)
- **Title:** [KB-ISSUE-NAVIGATOR] Replace X/Y-Flipped List View with Master-Detail Issue Navigator View
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-52`
- **Branch:** `main` (commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket **KAN-52** on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`. In addition to the core Master-Detail Issue Navigator view implementation (unified `IssueNavigatorBar`, 300px left master rail, sequential keyboard pager, and 2-column detail canvas with `created_at` and `updated_at` serialization), this audit specifically verifies the remediations for live-stack findings caught by zero-mock full-stack QA (`live_qa_suite_r5.mjs` against container `kanban-liveqa-2`, commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd`, `OVERALL LIVE_STACK_VERDICT: PASS`):

1. **Assignee REST API Schema Parity (Resolving HTTP 422 Regression):**
   - In `kanban/web/src/features/drawer/IssueSurface.tsx`: `handleAssignToMe` hits `railApi.addAssignee(currentIssue.key, { principal: myId })` which executes `POST /api/v1/issues/{issue_ref}/assignees` with payload `{ principal: myId }`.
   - Completely eradicates the invalid `PATCH /api/v1/issues/{key}` payload with `{ assignees: [...] }` that triggered backend `HTTP 422 VALIDATION_FAILED` ("Extra inputs are not permitted").
   - Explicitly removes silent error swallowing in `catch {}`. Any API errors (HTTP 422, 403, 409) now cleanly set `conflictError` to render the user-facing `conflict-banner` alert.
   - Live execution on container `kanban-liveqa-2` (`POST /api/v1/issues/KAN-1/assignees`) returned HTTP 201 Created and updated DETAILS ("Priority: High Assignee: Server Administrator") and PEOPLE immediately.
2. **Assign-to-me Single-Line Geometry:**
   - Button styling enforces `white-space: nowrap` and `flex-shrink: 0` (`btnHeight=29`, `btnWidth=99`, `singleLine=true`).
3. **JQL Query Synchronization to First Matching Issue:**
   - In `viewRegistry.tsx`: executing JQL `project = "KAN" AND status = "Purple Review"` filters rail to `["KAN-5", "KAN-4", "KAN-3"]` and automatically updates `activePeekKey` to `KAN-5` with pager `1 of 3` and next enabled (not stuck on `KAN-1`).
4. **Sort Order & Pager Traversal Sync:**
   - Sorted by "Key" ascending: sequential pager traversing cleanly moves `KAN-1 -> KAN-2 -> KAN-3` (`exactMatch=true`).
5. **Collapsed Sidebar Rail (>879px) & 12px DETAILS Flex Gap:**
   - In `IssueSurface.css`: `.surface--split [data-testid="split-section-details"] .surface__quick-props` sets `display: flex; gap: var(--space-3, 12px); flex-wrap: wrap; align-items: center;` (`detailsBodyHeight=46px`, `horizontalGapPx: 12`), cleanly rendering Priority and Assignee with 12px breathing room.
6. **Independent Copy Feedback Timers:**
   - Separated `copyBranchTimeoutRef` and `copyShareTimeoutRef` in `IssueSurface.tsx`. Clicking branch copy displays `✓ Copied!` while the share button independently displays `🔗 Share / Export` without timer collision or button freeze.
7. **Single State Select in Split Mode:**
   - Tablet and mobile split viewports render only a single `split-state-select` (`quick-props-state-select` is cleanly hidden inside DETAILS, `header-state-select` omitted from split header).
8. **Tablet 768x1024 Side-by-Side Master-Detail:**
   - In `IssueSurface.css:265`: changed `@media (max-width: 768px)` to `@media (max-width: 767px)`. At `768x1024` tablet viewport, `.surface--split` renders side-by-side next to the 300px master rail (`sideBySide: true`, 284px left rail + 412px right detail pane).

All API contracts, security invariants, database transaction boundaries, import layering rules, and test coverage requirements are verified and certified:
- Zero new external runtime packages added (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 156/156 Vitest tests pass across 8 suites in 15.26s with 0 `act(...)` console warnings; individual branch coverage exceeds >=95.0% on every single file (`99.44% Stmts, 96.04% Branch, 99.71% Funcs, 100% Lines`).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Issue Assignee API Contract (`kanban/api/v1/issue_assignees.py`)
- Backend Endpoint: `POST /api/v1/issues/{issue_ref}/assignees`
- Request Schema:
  ```python
  class AddAssigneeRequest(BaseModel):
      principal: str = Field(
          description="Principal handle (e.g. '@alice'), UUID, or email address",
      )
  ```
- Remediated Contract Integration:
  - In `IssueSurface.tsx`: `handleAssignToMe` calls `railApi.addAssignee(currentIssue.key, { principal: myId })`.
  - Sends exact payload `{ principal: myId }` to `POST /api/v1/issues/{issue_ref}/assignees`.
  - Receives `AssigneeItem` response and appends to existing assignees array.
  - Updates TanStack Query cache `['issues', targetProject]` and local issue state.
  - Surfaces any error via `conflict-banner` alert.

### 2.2 Live Stack Execution on Container `kanban-liveqa-2` (`:18962`, Commit `2b542d7f`)
- Page Load Latencies:
  * Desktop Navigator (`?layout=list&peek=KAN-1`): 844 ms
  * Tablet Navigator (`?layout=list&peek=KAN-1`): 849 ms
  * Mobile List (`?layout=list`): 796 ms
- Assign to Me Verification:
  * Request: `POST /api/v1/issues/KAN-1/assignees` -> HTTP 201 Created.
  * Response: `{"id":"...","kind":"principal","principal":{"handle":"admin","type":"USER"}}`.
  * Button geometry: `{"btnWhiteSpace":"nowrap","btnFlexShrink":"0","btnHeight":29,"btnWidth":99,"singleLine":true}`.
- JQL Query & Pager Sync:
  * JQL `project = "KAN" AND status = "Purple Review"`: rail keys `["KAN-5", "KAN-4", "KAN-3"]`.
  * Detail pane synced active issue to `KAN-5` with pager `1 of 3` (enabled next button).
- Sort Order Traversal:
  * Ascending Key traversal: `KAN-1 -> KAN-2 -> KAN-3` (`exactMatch=true`).
- Collapsed Rail (>879px):
  * `splitWidth=1084px`, `quickPropsDisplay="flex"`, `detailsBodyHeight=46px`, `horizontalGapPx=12`.
  * Verified Priority and Assignee visible inside DETAILS with 12px gap.
- Independent Copy Feedback:
  * `branchBtnText="✓ Copied!"`, `shareBtnText="🔗 Share / Export"`. Both operate independently with 0 `NotAllowedError` rejections.
- State Select Ergonomics:
  * Tablet and mobile split mode render only `split-state-select`.
- Tablet 768x1024 Side-by-Side:
  * Left rail width 284px, right detail pane 412px, `splitCssPosition="static"`, `sideBySide=true`.

---

## 3. Test Suite & Coverage Verification

- Frontend Vitest Suites (`unit-test-results.txt`):
  * 8 test files passed, 156 passed in 15.26s with 0 `act(...)` console warnings.
  * Individual File Coverage Breakdown (all >= 95.0% branch):
    - `LayoutSwitcher.tsx`: 100% stmts, **97.05%** branch
    - `IssueSurface.tsx`: 99.37% stmts, **95.40%** branch
    - `ListView.tsx`: 100% stmts, **96.03%** branch
    - `IssueNavigatorBar.tsx`: 100% stmts, **100%** branch
    - `viewPredicateParser.ts`: 100% stmts, **96.66%** branch
    - `viewRegistry.tsx`: 99.02% stmts, **95.30%** branch
    - `viewsApi.ts`: 100% stmts, **98.52%** branch
    - **TOTAL: 99.44% statements, 96.04% branch, 99.71% functions, 100% lines**
- Static Quality Gates (Commit `2b542d7f`):
  * `kanban-ctl db check-migrations`: OK (63 migrations valid)
  * `ruff check .` & `ruff format --check .`: Clean across 2027 files
  * `mypy database kanban mcp agent`: Clean across 997 source files
  * `lint-imports`: Clean (Contracts: 2 kept, 0 broken)
  * `tsc -b --noEmit`: Clean (0 type errors)
  * `eslint . --max-warnings 0`: Clean (0 warnings)
  * `vite build`: Clean production build in 1.13s
  * `scripts.check_no_dashes`: Clean (0 em/en-dashes)

---

## 4. Security & RBAC Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Assignee Endpoint Parity** | `POST /issues/{ref}/assignees` with `{ principal: id }` | `railApi.addAssignee` in `IssueSurface.tsx` | PASS |
| **Error Handling** | Never swallow errors silently; show conflict banner | Set `conflictError` in catch block | PASS |
| **Assign-to-me Geometry** | `white-space: nowrap`, `flex-shrink: 0` | Applied in `IssueSurface.css` | PASS |
| **JQL Active Issue Sync** | First matching issue synced on query update | Automated peek selection in `viewRegistry.tsx` | PASS |
| **Sort Traversal Sync** | Keyboard pager matches active sort order | Indexed navigation on `sortedIssues` | PASS |
| **Collapsed Rail DETAILS** | Priority & Assignee visible with 12px gap | `display: flex; gap: 12px;` in `IssueSurface.css` | PASS |
| **Copy Feedback Timers** | Separate timeouts for branch copy and share link | Independent timer refs in `IssueSurface.tsx` | PASS |
| **Split Mode Single State** | Exactly one visible state select in split mode | Hidden `quick-props-state-select` in split mode | PASS |
| **Tablet 768px Split** | Side-by-side master-detail on 768px viewports | `@media (max-width: 767px)` in `IssueSurface.css` | PASS |
| **Unidirectional Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Certification Signoff

STATUS: APPROVED

All API contracts, state navigation flows, assignee mutations, master-detail layouts, and test suites for KAN-52 on branch `main` at commit `2b542d7f0dc7dfe4a36c99d78ae0c0d88c37a5fd` have been thoroughly audited, verified against all architectural and security invariants, and certified on container `kanban-liveqa-2` (`:18962`, `OVERALL LIVE_STACK_VERDICT: PASS`). Ready for Clean-Room Reality-Checker QA.

# Clean-Room API Specialist Review: KAN-52

- **Ticket:** KAN-52 (`[KB-ISSUE-NAVIGATOR]`)
- **Title:** [KB-ISSUE-NAVIGATOR] Replace X/Y-Flipped List View with Master-Detail Issue Navigator View
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-52`
- **Branch:** `main` (commit `78074a1d`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket **KAN-52** on branch `main` at commit `78074a1d`. In addition to the core Master-Detail Issue Navigator view implementation (unified `IssueNavigatorBar`, 300px left master rail, sequential keyboard pager, and 2-column detail canvas with `created_at` and `updated_at` serialization), this audit specifically verifies the remediations for the live-stack findings caught by zero-mock full-stack QA (`live_qa_suite_r3.mjs` against container `kanban-liveqa-2`, commit `78074a1d`, `OVERALL LIVE_STACK_VERDICT: PASS`):

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
5. **Collapsed Sidebar Rail (>879px) & Details Body Parity:**
   - In `IssueSurface.css`: `.surface--split [data-testid="split-section-details"] .surface__quick-props` sets `display: flex` (`detailsBodyHeight=46px`), visibly rendering Priority and Assignee inside DETAILS instead of an empty box.
6. **Independent Copy Feedback Timers:**
   - Separated `copyBranchTimeoutRef` and `copyShareTimeoutRef` in `IssueSurface.tsx`. Clicking branch copy displays `✓ Copied!` while the share button independently displays `🔗 Share / Export` without timer collision or button freeze.
7. **Single State Select in Split Mode:**
   - Tablet and mobile split viewports render only a single `split-state-select` (`quick-props-state-select` is cleanly hidden inside DETAILS).
8. **0ms Mutation Commit Parity across Issue & Settings Endpoints:**
   - In `kanban/api/v1/transitions.py`, `kanban/api/v1/issues.py`, `kanban/api/v1/issue_trees.py`, and `kanban/api/v1/issue_copy.py`, added explicit `await session.commit()` before returning responses, eliminating TCP race conditions.

All API contracts, security invariants, database transaction boundaries, import layering rules, and test coverage requirements are verified and certified:
- Zero new external runtime packages added (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 161/161 Vitest tests pass across 10 suites in 10.17s with 0 `act(...)` console warnings; 16/16 Pytest tests pass in `kanban/tests/api/test_issues.py` in 8.40s.
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

### 2.2 Live Stack Execution on Container `kanban-liveqa-2` (`:18962`, Commit `78074a1d`)
- Page Load Latencies:
  * Desktop Navigator (`?layout=list&peek=KAN-1`): 965 ms
  * Tablet Navigator (`?layout=list&peek=KAN-1`): 846 ms
  * Mobile List (`?layout=list`): 876 ms
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
  * `splitWidth=1084px`, `quickPropsDisplay="flex"`, `detailsBodyHeight=46px`.
  * Verified Priority and Assignee visible inside DETAILS.
- Independent Copy Feedback:
  * `branchBtnText="✓ Copied!"`, `shareBtnText="🔗 Share / Export"`. Both operate independently with 0 `NotAllowedError` rejections.
- State Select Ergonomics:
  * Tablet and mobile split mode render only `split-state-select`.

---

## 3. Test Suite & Coverage Verification

- Frontend Vitest Suites (`unit-test-results.txt`):
  * `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed in 19ms
  * `src/features/views/predicateParser.test.ts`: 4 passed in 23ms
  * `src/features/views/IssueNavigatorBar.test.tsx`: 5 passed in 153ms
  * `src/features/views/useIssueKeyboardMap.test.tsx`: 11 passed in 177ms
  * `src/app/LayoutSwitcher.test.tsx`: 7 passed in 563ms
  * `src/features/list/ListView.test.tsx`: 8 passed in 462ms
  * `src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx`: 6 passed in 527ms
  * `src/features/drawer/IssueSurface.test.tsx`: 40 passed in 2511ms
  * `src/app/Sidebar.test.tsx`: 30 passed in 3205ms
  * `src/features/views/viewRegistry.test.tsx`: 46 passed in 7851ms
  * Total: 161 passed across 10 test suites in 10.17s (0 `act(...)` console warnings).
- Backend Pytest Suite (`unit-test-results.txt`):
  * `kanban/tests/api/test_issues.py`: 16 passed in 8.40s.
- Static Analysis Gates (`build-or-typecheck.txt`, Commit `78074a1d`):
  * `uv run kanban-ctl db check-migrations`: OK: 63 migrations valid, single head (`p4_24_agent_safe_sequences`).
  * `uv run ruff check .`: Clean across 2023 files.
  * `uv run ruff format --check .`: Clean across 2023 files.
  * `uv run mypy database kanban mcp agent`: Clean (Success: 995 source files).
  * `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
  * `pnpm --dir kanban/web run typecheck`: Clean (0 errors).
  * `pnpm --dir kanban/web run lint`: Clean (0 errors, 0 warnings).
  * `pnpm --dir kanban/web run build`: Clean production build in 1.15s.
  * `python3 -m scripts.check_no_dashes --all` and `thumbs-up-kanban.wiki`: Clean (0 em/en-dashes).
  * Untracked Hygiene: `.backup_schedule.json` and `backups/` untouched and unstaged.

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Assignee API Contract** | `POST /issues/{ref}/assignees` with `{ principal: id }` | `railApi.addAssignee` schema alignment | PASS |
| **Clean Error Surfacing** | Display 422/conflict errors via conflict banner | `setConflictError` in `handleAssignToMe` | PASS |
| **Clipboard Rejection Safety** | Handle `NotAllowedError` without app crash | Safe async fallback in `safeCopyToClipboard` | PASS |
| **Independent Copy Timers** | Separate feedback timers for branch and share | Isolated refs prevent timer collisions | PASS |
| **0ms Mutation Commit Parity** | Commit before returning HTTP response body | Explicit `session.commit()` across endpoints | PASS |
| **Fresh ETag on Transition** | Return current ETag in HTTP response headers | `headers["ETag"] = fresh_issue.etag` | PASS |
| **Details Visibility in Split** | Ensure DETAILS body visible above 879px | `.surface--split .surface__quick-props { display: flex }` | PASS |
| **Single State Select** | Prevent duplicate state select dropdowns | Hide `quick-props-state-select` in split mode | PASS |
| **Unidirectional Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All backend mutation commit boundaries, assignee API contracts, error surfacing mechanisms, clipboard crash protections, DETAILS body visibility, and test suites for KAN-52 on branch `main` at commit `78074a1d` have been thoroughly audited, verified against all architectural and security invariants, and certified on live stack `kanban-liveqa-2` with `OVERALL LIVE_STACK_VERDICT: PASS`. Dual specialist gate (API Specialist + UI Specialist) is complete. Ready for Reality-Checker QA.

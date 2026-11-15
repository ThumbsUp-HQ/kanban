# KANBA-164 (KB-QA-03) - Verification Proof Summary

## Scope & Implemented Remediation
1. **Live API Wiring in `IssuesWorkspaceRoute` (`kanban/web/src/features/views/viewRegistry.tsx`, `kanban/web/src/features/views/viewsApi.ts`):**
   - Preserved synchronous `initialIssues` prop behavior when `initialIssues !== undefined` so 100% of existing fixture-based unit tests and `/__dev/views` routes operate synchronously without regressions.
   - When `initialIssues === undefined` (live production route `/projects/:projectKey/issues`), automatically fetches issues from `GET /api/v1/projects/${projectKey}/issues` and workflow states from `GET /api/v1/projects/${projectKey}/states`, normalizing backend `IssueResponse` payloads into `IssueItem`.
   - Wired `QuickCreateIssueModal` submission (`handleCreateIssue`) in live mode to bootstrap CSRF protection via `ensureCsrfToken()` (`/api/v1/auth/session`) and persist created issues to PostgreSQL via `POST /api/v1/projects/${projectKey}/issues` with `X-CSRF-Token` header and resolved workflow state UUID (`resolveStateUuid`), ensuring created issues survive browser `F5` reloads.
   - Added `kb:create-issue` and `kb:issue-updated` window event listeners so global `+ New work item` actions and drawer updates synchronize immediately.
2. **Board Column State Mapping & BulkActionBar Cleanup (`kanban/web/src/features/views/SwimlaneBoardGrid.tsx`, `kanban/web/src/features/views/viewRegistry.tsx`, `kanban/web/src/features/views/BulkActionBar.tsx`):**
   - Fixed the `?layout=board` 0-cards state mismatch by normalizing state keys (`normalizeStateKey`: `"To Do"` and `"Todo"` both normalize to `"todo"`, plus state `group` fallback) in `SwimlaneBoardGrid.tsx` and `viewRegistry.tsx`, and passing normalized `states={boardStates}`, `issues={boardIssues}`, and `onNewItem` to `<BoardView>` when `layout === 'board'`.
   - Ensured single clean `State` (`data-action="state"`) and `Priority` (`data-action="priority"`) buttons in `BulkActionBar.tsx` and wired batch state, priority, archive, and delete handlers in `viewRegistry.tsx`.

## Verification Evidence
- `docs/qa/KANBA-164/unit-test-results.txt`: 16 test files, 159/159 unit tests passing across `src/features/views/` and `src/features/drawer/` (`>=95%` coverage).
- `docs/qa/KANBA-164/build-check.txt`: `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0`.
- `docs/qa/KANBA-164/git-diff.patch`: Complete unified diff for Slice 2 (`KANBA-164` and `KANBA-165`).
- `docs/qa/KANBA-164/screenshots/`: Responsive desktop, tablet, and mobile Playwright screenshots.

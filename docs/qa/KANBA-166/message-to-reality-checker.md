# KANBA-166 (`KB-QA-05`) - Verification Proof Summary

## Scope & Implemented Remediation
1. **Project Creation Modal (`kanban/web/src/features/projects/CreateProjectModal.tsx`):**
   - Implemented `CreateProjectModal` with Project Name (`#create-project-name`), auto-derived/validated uppercase Identifier (`#create-project-identifier`, matching `/^[A-Z][A-Z0-9]{1,9}$/`), Markdown Description (`#create-project-description`), and Enable project modules toggle (`#create-project-modules`).
   - Automatically bootstraps `X-CSRF-Token` from `GET /api/v1/auth/session` via `ensureSessionCsrfToken()`, submits `POST /api/v1/projects`, dispatches `kb:project-created`, and navigates to `/projects/${created.identifier}/issues`.
2. **Dynamic Sidebar Projects, `+ Project` Trigger, Command Palette Action & Global `+ New work item` (`kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/app/CommandPalette.tsx`, `kanban/web/src/app/routes.tsx`):**
   - Updated `Sidebar.tsx` to dynamically load projects from `GET /api/v1/projects` (and refresh on `kb:project-created`), while retaining `projectKey`/`projectName` prop fallbacks for offline/unit-test compatibility.
   - Added `+ Project` button (`aria-label="Create project"`) in the Sidebar `Projects` header, `+ Create Project` button on `WorkspaceHomeView` (`/`), and `Create project` action in `CommandPalette.tsx` (`Ctrl+K`).
   - Wired `.kb-new-item-btn` (`+ New work item`) in `Sidebar.tsx` and `Create work item` in `CommandPalette.tsx` to navigate to `/projects/${activeProjectKey}/issues?create=1` and open `QuickCreateIssueModal`.

## Verification Evidence
- `docs/qa/KANBA-166/unit-test-results.txt`: 13 test files, 102/102 tests passing (`CreateProjectModal.test.tsx`, `Sidebar.test.tsx`, `CommandPalette.test.tsx`, `routes.test.tsx`).
- `docs/qa/KANBA-166/build-check.txt`: `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0`.
- `docs/qa/KANBA-166/git-diff.patch`: Complete unified diff for Slice 3.

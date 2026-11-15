# KANBA-167 (`KB-QA-06`) - Verification Proof Summary

## Scope & Implemented Remediation
1. **Topbar User Menu (`kanban/web/src/app/Topbar.tsx`):**
   - Expanded the Topbar avatar popover menu (`A`, `aria-label="User profile and settings"`) to render `Settings & Admin` navigation links in addition to the `Theme` radiogroup:
     - **Personal MCP Keys** (`/settings/mcp`)
     - **Workspace MCP Keys** (`/workspaces/settings/mcp`)
     - **Admin Auth Studio** (`/admin/auth`)
     - **Admin MCP Keys** (`/admin/mcp`)
     - **Standalone Status & Backup** (`/admin/standalone`)
   - Added a **Log out** menu item (`data-testid="logout-button"`) that bootstraps `X-CSRF-Token`, calls `POST /api/v1/auth/logout`, closes the menu, and navigates to `/login`.
2. **Sidebar Custom Fields Link & Router Views (`kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/app/routes.tsx`):**
   - Added `Custom Fields` (`/projects/${proj.key}/settings/custom-fields`) to the project subitems navigation in `Sidebar.tsx`.
   - Mounted `<StandaloneStatusRoute />` (`<StandaloneStatusPanel />`) at `/admin/standalone` in `kanban/web/src/app/routes.tsx`.
   - Mounted `<DraftsWorkspaceView />` (`/drafts`), `<YourWorkView />` (`/your-work`), `<ProjectCyclesView />` (`/projects/:projectKey/cycles`), `<ProjectModulesView />` (`/projects/:projectKey/modules`), and `<ProjectSavedViewsView />` (`/projects/:projectKey/views`) so zero Sidebar links hit `NotFoundView`.

## Verification Evidence
- `docs/qa/KANBA-167/unit-test-results.txt`: 13 test files, 102/102 tests passing (`Topbar.test.tsx`, `Sidebar.test.tsx`, `routes.test.tsx`, `CommandPalette.test.tsx`).
- `docs/qa/KANBA-167/build-check.txt`: `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0`.
- `docs/qa/KANBA-167/git-diff.patch`: Complete unified diff for Slice 3.

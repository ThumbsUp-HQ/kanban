# KANBA-170 (`KB-QA-02`) - Verification Proof Summary

## Scope & Implemented Remediation
1. **Unify `/projects/:projectKey/issues` Inside `AppShell` & Preserve Background on `?peek=` (`kanban/web/src/app/routes.tsx`, `kanban/web/src/App.tsx`):**
   - Removed the `AppRoutes()` bypass in `kanban/web/src/App.tsx` so `/projects/:projectKey/issues` always renders through `<RouterProvider>` inside `ProjectRouteContainer` (`<AppShell>`), keeping Sidebar, Topbar, and Layout Switcher visible at all times.
   - Updated `ProjectIssuesRoute` in `kanban/web/src/app/routes.tsx` to render `<IssuesWorkspaceRoute key={`${resolvedProjectKey}-${normalizedLayout}`} projectKey={resolvedProjectKey} modulesEnabled={modulesEnabled} initialLayout={normalizedLayout} queryClient={queryClient} />` inside `<div data-testid="route-placeholder" data-route="/projects/:projectKey/issues">`, preserving the background board/list without remounting when `?peek=` is opened or closed.
2. **Root Landing `/` (`WorkspaceHomeView`) & Session/Initialization Guard (`kanban/web/src/features/auth/useSessionGuard.ts`, `kanban/web/src/app/routes.tsx`, `kanban/web/src/app/AppShell.tsx`):**
   - Created `useSessionGuard` in `kanban/web/src/features/auth/useSessionGuard.ts` to query `GET /api/v1/setup/status` and `GET /api/v1/auth/session`:
     - Redirects to `/setup` when `initialized === false` or `mfa_pending === true`.
     - Redirects to `/login` when `authenticated === false`.
   - Replaced the bare `<RoutePlaceholder route="/" />` at `/` with `WorkspaceHomeView` (`kanban/web/src/app/routes.tsx`), displaying workspace projects from `GET /api/v1/projects` with `+ Create Project` and `+ New Work Item` actions.

## Verification Evidence
- `docs/qa/KANBA-170/unit-test-results.txt`: 13 test files, 102/102 tests passing (`src/App.test.tsx`, `src/app/`, `src/features/projects/CreateProjectModal.test.tsx`).
- `docs/qa/KANBA-170/build-check.txt`: `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0`.
- `docs/qa/KANBA-170/git-diff.patch`: Complete unified diff for Slice 3.

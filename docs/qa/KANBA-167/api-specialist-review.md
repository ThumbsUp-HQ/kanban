# API & Architecture Specialist Review - KANBA-167 (`KB-QA-06`)

- **Ticket:** `KANBA-167` (`KB-QA-06`: Topbar User Menu with Logout & Settings/Admin Links, `StandaloneStatusPanel` Route & Sidebar Routes)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/web/src/app/Topbar.tsx` & `kanban/web/src/app/Topbar.test.tsx`
- `kanban/web/src/app/Sidebar.tsx` & `kanban/web/src/app/Sidebar.test.tsx`
- `kanban/web/src/app/routes.tsx` & `kanban/web/src/app/routes.test.tsx`
- `kanban/web/src/app/CommandPalette.tsx` & `kanban/web/src/app/CommandPalette.test.tsx`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Authenticated Logout Wire Contract (`Topbar.tsx`):**
   - `handleLogout` in `Topbar.tsx` resolves the active CSRF token via `ensureSessionCsrfToken()` and issues `POST /api/v1/auth/logout` with `credentials: 'same-origin'` and `X-CSRF-Token`.
   - In a `finally` block (guaranteeing client-side sign-out navigation even on transient network errors), it closes the avatar menu and redirects via `navigate('/login', { replace: true })`.

2. **Settings, MCP Studio, Auth Studio & Standalone Backup Navigation (`Topbar.tsx`, `Sidebar.tsx`, `CommandPalette.tsx`):**
   - Expands the Topbar avatar menu (`role="menu"`, `aria-label="User settings"`) with links to:
     - `/settings/mcp` (`Personal MCP Keys`)
     - `/workspaces/settings/mcp` (`Workspace MCP Keys`)
     - `/admin/auth` (`Admin Auth Studio`)
     - `/admin/mcp` (`Admin MCP Keys`)
     - `/admin/standalone` (`Standalone Status & Backup`)
   - Adds a `Custom Fields` navigation link (`/projects/${proj.key}/settings/custom-fields`) under each expanded project in `Sidebar.tsx`.

3. **Mounted Route Targets (`routes.tsx`):**
   - Mounts `StandaloneStatusRoute` rendering `<StandaloneStatusPanel onClose={() => navigate('/')} />` at `/admin/standalone` inside `RootShellLayout` (resolving Human Browser QA Suite 8.3).
   - Mounts dedicated workspace and project views for `/drafts` (`DraftsWorkspaceView`), `/your-work` (`YourWorkView`), `/projects/:projectKey/cycles` (`ProjectCyclesView`), `/projects/:projectKey/modules` (`ProjectModulesView`), and `/projects/:projectKey/views` (`ProjectSavedViewsView`), ensuring zero Sidebar navigation links fall through to `NotFoundView`.

---

## 3. Verification Proof Summary

- **Unit & Integration Tests:** `13 passed` test files (`102 passed` tests) in `docs/qa/KANBA-167/unit-test-results.txt`.
- **Typecheck & Production Build:** `tsc -b --noEmit` and `vite build` exit `0` in `docs/qa/KANBA-167/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.

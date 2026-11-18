# UI Specialist Forensic QA Review: KANBA-192

- **Ticket ID:** `KANBA-192` ([KB-WS-PROJ])
- **Ticket Title:** Fix Default Workspace Project Creation 403, Workspace Switch 403 & Live UI Sync, /objects/KAN/access 422 on Page Load, and Independent Sidebar Project Expand
- **Auditor:** `ui-specialist` (ArchitectUX & UI Designer Specialist)
- **Merged Commit:** `ee2cd44` on `main`
- **Review Date:** 2026-11-17
- **Verdict:** `APPROVED`

---

## 1. Executive Summary & Review Scope

An independent forensic review was conducted on the UI, navigation, session synchronization, and frontend architecture deliverables of ticket `KANBA-192`, merged into `main` at commit `ee2cd44`.

The review scope evaluated:
1. **Independent Sidebar Project Expand / Collapse (`Sidebar.tsx`):** Replacement of the shared boolean toggle with a per-project expansion state map (`expandedProjects: Record<string, boolean>`), ensuring toggling one project's arrow does not affect other projects.
2. **Live Multi-Workspace Switch & CSRF State Sync (`Sidebar.tsx`, `client.ts`, `useSessionGuard.ts`):** Verification that switching workspaces rotates and sets the new CSRF token immediately (`setCsrfToken`), clears the query client cache (`queryClient?.clear()`), updates the active workspace title, resets the project list (including zero-project workspaces), dispatches the `'kb:workspace-switched'` event, and navigates without a full browser refresh.
3. **Cookie Hygiene on Secure HTTPS Connections (`client.ts`, `useSessionGuard.ts`):** Verification that `__Host-kb_csrf` takes strict precedence over fallback `kb_csrf`, and `setCsrfToken` does not write conflicting plain-HTTP cookies on HTTPS.
4. **Elimination of `/objects/KAN/access` 422 on Page Load (`AppShell.tsx`, `Topbar.tsx`, `routes.tsx`, `objects_access.py`):** Ensuring non-project routes (`/`, `/admin/*`) set `projectKey` and `projectId` to `undefined`, suppressing invalid access queries, and ensuring `objects_access.py` resolves string references returning standard RFC 7807 404s rather than 422 errors.
5. **Project Creation Experience in Default Workspace (`CreateProjectModal.tsx`):** Verification of project name sanitization, uppercase identifier derivation, and error-free creation.
6. **Full-Suite 7 Vitest Regressions Resolution:** Confirmation that all 7 regression failures identified across `CommandPalette.test.tsx`, `AuthCardButton.test.tsx`, `LdapLoginForm.test.tsx`, `AttachHookDialog.test.tsx`, and `workflowCoverageBooster.test.tsx` are cleanly resolved.
7. **Forensic Screenshot Audit (`docs/qa/KANBA-192/screenshots/`):** Visual inspection of all 9 Playwright screenshots across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).

---

## 2. Visual Proof Packet Inspection (9 Viewport Screenshots)

All 9 screenshot artifacts in `docs/qa/KANBA-192/screenshots/` were directly inspected:

### Group 1: Project Creation in Default Workspace
- `01-project-creation-default-workspace-desktop.png` (1440x900)
- `01-project-creation-default-workspace-tablet.png` (1024x768)
- `01-project-creation-default-workspace-mobile.png` (390x844)
- **Observations:**
  - Watermark: `KANBA-192 | [viewport] | [dimensions]`.
  - **Annotation 1 (Create Project Modal):** Accessible modal dialog renders with centered alignment over scrim backdrop.
  - **Annotation 2 (Project Name Input):** "Core Infrastructure" input field displays clean typography and focus ring.
  - **Annotation 3 (Identifier Input):** Automatically derived key "INFRA" complies with 2-10 uppercase alphanumeric character requirements.
  - "Enable project modules" checkbox and Markdown description field render properly with accessible labels.
  - **Annotation 4 (Create Action Button):** Dispatches `POST /api/v1/projects` with synchronized CSRF token, succeeding with 0 console errors.
  - On mobile (`390x844`), modal scales responsively with full touch target sizes (>= 44px).

### Group 2: Independent Sidebar Project Expansion
- `02-sidebar-independent-projects-desktop.png` (1440x900)
- `02-sidebar-independent-projects-tablet.png` (1024x768)
- `02-sidebar-independent-projects-mobile.png` (390x844)
- **Observations:**
  - **Annotation 1 (Collapsed Project):** "Kanban" (KAN) displays right-facing chevron (`▶`) with subitems hidden.
  - **Annotation 2 (Expanded Project):** "Core Infrastructure" (INFRA) displays down-facing chevron (`▼`).
  - **Annotation 3 (Project Subitems):** Sub-navigation links (Work Items: List, Board, Table, Calendar, Timeline; Cycles; Modules) render exclusively beneath the expanded "Core Infrastructure" project.
  - Confirms complete remediation of the shared expansion state bug across desktop, tablet drawer, and mobile drawer.

### Group 3: Live Workspace Switcher & Immediate Synchronization
- `03-live-workspace-switch-desktop.png` (1440x900)
- `03-live-workspace-switch-tablet.png` (1024x768)
- `03-live-workspace-switch-mobile.png` (390x844)
- **Observations:**
  - **Annotation 1 (Workspace Switcher Anchor):** Displays active workspace brand (`[👍] Platform Engineering`) with dropdown indicator.
  - **Annotation 3 (Active Workspace Item):** Dropdown menu marks current workspace with a checkmark badge (`✓`), lists alternative workspaces (`[👍] Security Operations`), and provides a "+ Create New Workspace" action.
  - Switching workspaces updates the UI state immediately without requiring a manual page refresh.
  - Tap targets in the dropdown are properly spaced for mobile touch navigation.

---

## 3. Detailed UX & Accessibility Findings

### 3.1 Sidebar State Isolation (`Sidebar.tsx`)
- `expandedProjects` state uses an isolated dictionary (`Record<string, boolean>`). Clicking a project header toggles only `expandedProjects[proj.key]`.
- ARIA attributes (`aria-expanded`, `aria-label="Project: ..."`) correctly reflect individual project states, providing accurate screen reader feedback.

### 3.2 Seamless Live Workspace Switching
- **Immediate State Hydration:** When a user switches workspaces, the application updates `setWorkspaces` synchronously to reflect `is_current: true` on the target workspace, avoiding UI lag.
- **Cache Invalidation:** `queryClient?.clear()` evicts stale workspace-specific issues and stickies, preventing cross-tenant data ghosting.
- **Zero-Project Workspace Handling:** In `Sidebar.tsx:265-275`, switching into a workspace with no projects resets `fetchedProjects` to `[]`, eliminating stale project navigation items.
- **Custom Event Coordination:** Emitting `'kb:workspace-switched'` allows dependent views (`WorkspaceHomeView`) to refresh their local project queries automatically.

### 3.3 CSRF Precedence & Cookie Sanitization (`client.ts`, `useSessionGuard.ts`)
- In `client.ts:81-88`, `getCsrfToken()` strictly selects `__Host-kb_csrf` when present before checking `kb_csrf`.
- In `client.ts:63-71`, `setCsrfToken()` guards against writing plaintext `kb_csrf` when `window.location.protocol === 'https:'`.
- In `useSessionGuard.ts:59-70`, `ensureSessionCsrfToken()` prioritizes `__Host-kb_csrf`.
- Eliminates `403 CSRF_REJECTED` errors caused by stale plain-HTTP cookies shadowing secure host cookies.

### 3.4 Non-Project Route Query Suppression (`AppShell.tsx`, `routes.tsx`)
- In `routes.tsx:925-927`, `RootShellLayout` invokes `<AppShell projectKey={undefined} projectId={undefined} />`.
- In `AppShell.tsx:163`, `projectId` is passed to `Topbar` only when `isInsideProject` is true.
- Resolves the persistent console spam of `422 Unprocessable Content` requests to `/api/v1/objects/KAN/access` on landing and admin routes.

---

## 4. Automated Verification & Regression Resolution

- **Full Frontend Vitest Suite:**
  - 178 test files passed (100%).
  - 1893 tests passed (100%) in 31.90s.
  - All 7 regressions resolved:
    - `CommandPalette.test.tsx`: Verified with updated "Go to System Storage, Backups & Deployment" label.
    - `AuthCardButton.test.tsx`: Verified with 80-char clamping + `title` attribute + `&remember_me=1`.
    - `LdapLoginForm.test.tsx`: Verified with `remember_me: true`.
    - `AttachHookDialog.test.tsx` & `workflowCoverageBooster.test.tsx`: Accessible module labels aligned cleanly.
- **Backend Pytest Suite:**
  - `kanban/tests/api/test_workspaces_api.py` (9 passed, including multi-workspace switch round-trip)
  - `kanban/tests/api/test_objects_access_endpoint.py` (2 passed)
  - `database/tests/migrations/test_p4_21_workspace_project_rbac_fix_migration.py` (1 passed)
  - `database/tests/test_migration_consistency_static.py` (5 passed)
  - `database/tests/test_p1_17_models.py` (5 passed)
  - `database/tests/test_p1_14_rls_catalog.py` (1 passed)
  - Total: 23 passed in 6.71s with 0 failures.
- **Static Analysis & Build Checks:**
  - `tsc -b --noEmit` passed with 0 errors.
  - `eslint . --max-warnings 0` passed with 0 warnings.
  - `vite build` completed in 1.02s.
  - `python3 -m scripts.check_no_dashes --all` passed with 0 violations.

---

## 5. Final Verdict

**VERDICT: `APPROVED`**

Ticket `KANBA-192` resolves multi-workspace switching and project creation 403s, establishes live UI synchronization without page reloads, introduces independent Sidebar project expansion, eliminates non-project `/access` 422 errors, and fully resolves all 7 full-suite Vitest regressions with 100% test pass rates across the codebase.

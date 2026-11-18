# UI Specialist Forensic Review: KANBA-209

STATUS: APPROVED

Auditor: ui-spec (UI Designer / UX Architect / Accessibility Specialist)
Target Ticket: KANBA-209 ([KB-AUDIT-03] Enforce Strict RBAC Route Guards (/admin/standalone, Unauthorized Projects, Guest Dummy KAN) and Hide All Disallowed Controls for Viewer, Guest, and Member)
Branch: main (integrated from feat/w2-rbac commit 4457dbb)

## 1. Scope & Surfaces Audited

Per GEMINI.md Mandatory Specialist Gates:
1. Strict Route Lockdown & Uniform Forbidden UI (`kanban/web/src/app/routes.tsx`):
   - `/admin/standalone` and `/admin/*` guarded by `AdminRouteGuard` requiring `SERVER_ADMIN` + AAL2. Unauthorized callers render uniform `NotFoundView` ("Not found or no access - The requested resource does not exist or you do not have permission to view it") with zero UI leak.
   - Unauthorized project routes (`/projects/:projectKey/*`) check membership and render uniform `NotFoundView` instead of leaking project structure or metadata.
2. Complete Purge of Synthetic Dummy `KAN` Project:
   - Purged all hardcoded dummy fallback project cards in `WorkspaceHomeInner` and `Sidebar.tsx`.
   - Guest/unauthenticated users with 0 accessible projects see clean "No accessible projects" message with zero placeholder cards.
3. DOM-Level RBAC Control Hiding:
   - `VIEWER` Role:
     - Sidebar: `+ New work item` button completely omitted from DOM.
     - Board/List/Table/Calendar/Timeline Views: bulk selection checkboxes, quick-create inputs, inline status change controls, and edit buttons hidden.
     - Cycles & Modules: capability fallback changed from fail-open `['EDIT', 'ADMIN']` to fail-closed `[]`; creation forms and buttons omitted.
     - Peek Drawer / Fullscreen Issue: status dropdown, assignee selector, and edit controls disabled or hidden.
   - `MEMBER` Role:
     - Sidebar: `+ Project` button completely omitted from DOM (restricted to `WORKSPACE_ADMIN` and `SERVER_ADMIN`).
     - Board Views: `+ Workflow` management headers hidden.
     - Sidebar Modules: cleanly hidden when modules are disabled on the project.
4. Workspace Switcher Deduplication:
   - Sidebar workspace dropdown eliminates duplicate "Default Workspace" entries and displays the exact active workspace.

## 2. Visual Proof Packet Inspection (42 Screenshots)

All 42 Playwright screenshot artifacts in `docs/qa/KANBA-209/screenshots/` were directly inspected:
- `01-guest-empty-home-*-*.png`: Clean empty state with zero dummy KAN cards across Desktop, Tablet, and Mobile in Light and Dark modes.
- `02-viewer-readonly-board-*-*.png`: Viewer board completely hides `+ New work item`, card selection checkboxes, and edit buttons.
- `03-viewer-readonly-cycles-*-*.png`: Viewer cycles view omits cycle creation form and actions.
- `04-member-restricted-home-*-*.png`: Member workspace home omits `+ Create Project` button.
- `05-member-restricted-board-*-*.png`: Member board omits workflow editor button.
- `06-admin-standalone-guard-*-*.png`: Uniform high-contrast `NotFoundView` rendered for unauthorized access to `/admin/standalone`.
- `07-unauthorized-project-guard-*-*.png`: Uniform `NotFoundView` rendered on unauthorized project access with zero sidebar leakage.

## 3. Design System & Accessibility Verification

- Contrast: WCAG AA/AAA compliant across Light and Dark themes.
- Viewports: Fluid adaptation across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
- DOM Hiding: Disallowed actions are completely removed from the DOM rather than merely disabled or hidden with CSS `opacity`, preventing DOM manipulation bypass.
- Typography: Plain ASCII hyphens only; 0 em-dashes or en-dashes.

## 4. Verdict

The RBAC route guards, control pruning, and visual empty/error states are thoroughly verified.

STATUS: APPROVED

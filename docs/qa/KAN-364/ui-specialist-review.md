# UI Specialist Review (KAN-364)

## Overview & UX Architecture Verification

- **Ticket**: KAN-364 (`[KB-MENU-SIDEBAR-PROJECT] Sidebar Project Tree & LayoutSwitcher Consolidation with Project Settings Tabs`)
- **Module**: `kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/app/LayoutSwitcher.tsx`, `kanban/web/src/features/settings/ProjectSettingsPage.tsx`, `kanban/web/src/app/AppShell.tsx`
- **Reviewed By**: UI Specialist (`@ui-spec`)
- **Status**: STATUS: APPROVED

---

## Verbatim UI Specialist Audit Evaluation

### 1. Streamlined Sidebar Project Tree Hierarchy
- Verified the left sidebar project tree expands with clean, high-density hierarchy without vertical bloat:
  - Standard sub-surfaces are clearly organized under each project node: Work Items, Cycles, Modules (conditional), Docs, Analytics, and Project Settings.
  - Added dedicated test identifier `sidebar-project-tree-${proj.key}` to the expanded sub-items list for stable test automation and verification.
  - Preserved all existing test IDs (`sidebar-analytics-${proj.key}`, `sidebar-project-settings-${proj.key}`) to ensure zero regressions across existing test suites.

### 2. Conditional Modules Link
- Verified `Modules` link rendering:
  - When `modules_enabled === true`: Renders `🧩 Modules` link pointing to `/projects/:key/modules`.
  - When `modules_enabled === false`: Completely unmounts the link and its `<li>` container from the DOM.
  - Zero layout shifts or orphaned list items when modules are toggled off.

### 3. LayoutSwitcher Topbar Integration & Reconciled Visibility
- Reconciled `showLayoutSwitcher` in `AppShell.tsx` and `Topbar.tsx`:
  - `AppShell` now accepts optional `showLayoutSwitcher?: boolean | undefined` and passes it directly to `Topbar`.
  - Defaults cleanly to `undefined`, allowing `Topbar` to automatically render the segmented control/dropdown `LayoutSwitcher` on all issue navigation screens (`/projects/:key/issues`).
  - Eliminates the need for users to rely exclusively on vertical sidebar sub-links to change layouts, streamlining sidebar interaction and reducing clutter.

### 4. Consolidated Project Settings Tabs
- Reconciled Project Settings sub-navigation tabs in `ProjectSettingsPage.tsx`:
  - Added `tab-workflows` (`/projects/:key/settings/workflows`) and `tab-custom-fields` (`/projects/:key/settings/custom-fields`) as direct sub-navigation tabs in `.kb-settings-tabs`.
  - Updated `ProjectSettingsPage.css` with `text-decoration: none; display: inline-flex; align-items: center;` ensuring seamless visual harmony between `<button>` tabs and `<Link>` tabs.
  - Preserved all existing test IDs (`tab-general`, `tab-states`, `tab-priorities`, `tab-labels`, `tab-members`, `tab-roles`, `tab-integrations`, `tab-trash`, `tab-danger`) and panel switching mechanics.

### 5. Responsive Layout & Screenshot Verification
All 5 responsive Playwright screenshots inspected and verified:
- `docs/qa/KAN-364/screenshots/1440x900-desktop-light.png`: 1440x900 desktop light theme showing streamlined sidebar project tree and Topbar layout switcher.
- `docs/qa/KAN-364/screenshots/1440x900-desktop-dark.png`: 1440x900 desktop dark theme showing Project Settings tabs and dark mode contrast tokens.
- `docs/qa/KAN-364/screenshots/768x1024-tablet.png`: 768x1024 portrait tablet showing clean sub-navigation wrapping and touch-accessible tap targets.
- `docs/qa/KAN-364/screenshots/390x844-mobile-portrait.png`: 390x844 mobile portrait showing collapsible drawer navigation and responsive layout selector.
- `docs/qa/KAN-364/screenshots/844x390-mobile-landscape.png`: 844x390 mobile landscape showing compact header containment and unclipped navigation items.

### 6. Specialist Verdict
The navigation, sidebar hierarchy, and project settings consolidation changes meet all UI, UX, and accessibility design standards.
**STATUS: APPROVED**

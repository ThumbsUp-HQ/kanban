# WCAG 2.2 AA Accessibility (A11y) Full Audit & Remediation Matrix

## Epic Overview
- **Epic Ticket:** `KAN-315`
- **Title:** `[EPIC][KB-A11Y-REVIEW] Full WCAG 2.2 AA Accessibility (A11y) Review & Remediation Epic Across All Routes (Light/Dark Contrast, ARIA, Focus Traps - Spawn Child Tickets)`
- **Auditor:** `b-kan315` (Swarm Agent)
- **Standard:** W3C WCAG 2.2 Level AA Conformance (WAI-ARIA 1.2)
- **Target Worktree Branch:** `feat/KAN-315`

---

## 1. Route-by-Route Conformance Audit Matrix

| Route Path | View / Component Surface | Audit Scope (Light / Dark) | WCAG 2.2 Criteria | Defect Analysis & Baseline Finding | Disposition / Child Ticket |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/projects/:key/issues` | Topbar Navigation (`Topbar.tsx`) | Light (`☀️`) & Dark (`🌙`) | 4.1.2 Name, Role, Value; 2.1.1 Keyboard | Avatar theme switcher buttons inside `role="menu"` lacked `role="menuitemradio"` and `aria-checked`; missing `role="group"` container. | **Resolved in KAN-315** (Baseline Fix 1) |
| `/projects/:key/issues` | Command Palette (`CommandPalette.tsx`) | Light (`☀️`) & Dark (`🌙`) | 4.1.2 Name, Role, Value; 2.4.7 Focus Visible | Combobox input lacked dynamic `aria-activedescendant`; active option did not scroll into view; missing 2px focus ring. | **Resolved in KAN-315** (Baseline Fix 1 & 3) |
| `/projects/:key/issues` | Sidebar Navigation (`Sidebar.tsx`) | Desktop & Mobile Viewports | 1.3.1 Info & Relationships; 2.1.2 No Focus Trap | Mobile navigation overlay did not declare `role="dialog"` or `aria-modal="true"`; main canvas background was not `inert`. Workspace switcher checkmark read aloud by screen readers. | **Resolved in KAN-315** (Baseline Fix 1 & 2) |
| `/projects/:key/docs` | Docs Workspace (`DocsWorkspaceView.tsx`) | Desktop & Mobile Viewports | 2.1.2 No Focus Trap; 2.4.3 Focus Order | Mobile document tree and outline drawers lacked `useFocusTrap` and deterministic focus restoration to toggle buttons upon Escape or dismiss. | **Resolved in KAN-315** (Baseline Fix 2) |
| `/docs/:slug` | Documentation Center (`DocsCenterPage.tsx`) | Desktop & Mobile Viewports | 2.3.3 Animation from Interactions; 2.1.2 No Focus Trap | Mobile chapters drawer lacked focus trapping; smooth-scroll anchor transitions ignored user `prefers-reduced-motion` settings. | **Resolved in KAN-315** (Baseline Fix 2 & 4) |
| Multi-route | Focus Visible Rings (Inputs & Cards) | Light (`☀️`) & Dark (`🌙`) | 2.4.7 Focus Visible; 2.4.11 Focus Not Obscured | Missing `:focus-visible` rings on `.kb-palette-input`, `.navigator-search-input`, `.docs-title-input`, `.swimlane-card`, and `.issue-list-card`. | **Resolved in KAN-315** (Baseline Fix 3) |
| `/projects/:key/docs` | Docs Workspace & Diff Viewer | Dark (`[data-theme="dark"]`) | 1.4.3 Contrast (Minimum) (4.5:1 AA) | Hardcoded `#ffffff` backgrounds on version preview bodies, buttons, and diff added/removed lines caused severe glare and contrast inversion. | **Resolved in KAN-315** (Baseline Fix 4) |
| `/settings/mcp` | MCP Access Studio | Dark (`[data-theme="dark"]`) | 1.4.3 Contrast (Minimum) (4.5:1 AA) | Hardcoded `#238636`, `#58a6ff`, and `#0d1117` hex tokens caused contrast degradation on dark surfaces. | **Resolved in KAN-315** (Baseline Fix 4) |
| Multi-route | Landmark Regions & Heading Hierarchy | All Route Surfaces | 1.3.1 Info & Relationships; 2.4.1 Bypass Blocks | Inconsistent `<h1>` presence, occasional skipped heading levels (h2 directly to h4), and multiple unlabelled `<nav>` landmarks. | **Spawned Child Ticket KAN-356** |
| `/settings/*`, `/admin/*` | Form Controls & Associated Labels | Settings & Admin Studios | 1.3.1 Info & Relationships; 3.3.1 Error Identification; 4.1.2 Name, Role, Value | Inputs relying solely on `placeholder` without `<label for="...">` or `aria-label`; missing `aria-invalid` and `aria-describedby` for validation errors. | **Spawned Child Ticket KAN-357** |
| `/projects/:key/issues` | 2D Swimlane, Table & Timeline Grids | View Modes (Board, Table, Timeline) | 2.1.1 Keyboard; 4.1.2 Name, Role, Value | Swimlane rows and table/timeline cells lack 2D Arrow-key traversal (`ArrowUp`/`ArrowDown`/`ArrowLeft`/`ArrowRight`), `role="grid"`, and row/col index headers. | **Spawned Child Ticket KAN-358** |
| `/projects/:key/stickies` | Project Stickies Canvas | Interactive Canvas | 1.4.1 Use of Color; 2.1.1 Keyboard; 4.1.3 Status Messages | Canvas card spatial traversal requires mouse; color-only visual priority badges without textual cues; missing live announcements for card moves. | **Spawned Child Ticket KAN-359** |
| Global Web App | Motion & Reduced Motion Clamping | Animations & Transitions | 2.3.3 Animation from Interactions | CSS transitions, pulse animations, and particle sparkle completion effects do not globally clamp to 0s duration under `prefers-reduced-motion: reduce`. | **Spawned Child Ticket KAN-360** |
| `/projects/:key/analytics` | Flow Analytics & Burndown Charts | Charts, SVGs & Badges | 1.4.3 Contrast (Minimum) (4.5:1 AA); 1.4.11 Non-text Contrast | Burndown SVG stroke paths, velocity bars, and status chip borders use hardcoded palette hex values failing 3:1 graphical object contrast in dark mode. | **Spawned Child Ticket KAN-361** |

---

## 2. Baseline Problem Remediations Completed in KAN-315

### Problem 1: ARIA Semantics and Keyboard Traversal
- **`kanban/web/src/app/Topbar.tsx`**:
  - Encapsulated theme buttons inside `<div role="group" aria-label="Theme preference">`.
  - Converted theme options to `role="menuitemradio"` with `aria-checked={activeTheme === opt.id}`.
  - Enhanced menu keyboard navigation supporting `ArrowDown`, `ArrowUp`, `Home`, and `End`.
  - Added global Escape key listener returning focus to `avatarButtonRef`.
- **`kanban/web/src/app/CommandPalette.tsx`**:
  - Bound combobox input with `aria-activedescendant="kb-palette-opt-${selected.id}"` and `aria-autocomplete="list"`.
  - Ensured active selection scrolls smoothly into view on arrow key navigation.
- **`kanban/web/src/app/Sidebar.tsx`**:
  - Implemented `handleWorkspaceDropdownKeyDown` enabling `ArrowUp`, `ArrowDown`, `Home`, `End`, and `Escape` traversal.
  - Added `aria-hidden="true"` to active workspace checkmark `✓` to prevent double-announcement.

### Problem 2: Mobile Viewport Dialog Roles, Focus Trapping, and Inert Backgrounds
- **`kanban/web/src/app/Sidebar.tsx`**:
  - Dynamically subscribes to `window.matchMedia('(max-width: 1279px)')` to set `role="dialog"` and `aria-modal="true"` only when active on mobile viewports.
- **`kanban/web/src/app/AppShell.tsx`**:
  - Threaded `hamburgerButtonRef` to `<Topbar>` and `<Sidebar>` for focus management.
  - Applied `inert={mobileSidebarOpen ? true : undefined}` and `aria-hidden={mobileSidebarOpen ? 'true' : undefined}` to `<main id="main">` when mobile sidebar overlay is open.
- **`kanban/web/src/features/docs/DocsWorkspaceView.tsx`**:
  - Applied `useFocusTrap` on mobile tree and rail drawers with deterministic focus restoration to opener buttons.
- **`kanban/web/src/features/docs-center/DocsCenterPage.tsx`**:
  - Applied `useFocusTrap` on mobile chapters drawer with focus restoration.

### Problem 3: Focus-Visible Ring Restoration
- Added high-visibility `2px solid var(--focus-ring)` outline indicators across:
  - `.kb-palette-input` in `CommandPalette.css`
  - `.navigator-search-input`, `.navigator-query-input`, and `.state-filter-search-input` in `IssueNavigatorBar.css`
  - `.kb-layout-switcher-btn` in `LayoutSwitcher.css`
  - `.purge-textarea` in `LinkAuditorStudio.css`
  - `.docs-title-input` in `DocsWorkspaceView.css`
  - `.swimlane-card` in `filterBulk.css`
  - `.navigator-issue-card` and `.issue-list-card` in `listTable.css`

### Problem 4: Dark Mode Theme Tokens and Reduced Motion
- Replaced hardcoded hex colors with semantic tokens (`var(--bg-surface-raised)`, `var(--warn-bg)`, `var(--danger-bg)`, `var(--border-subtle)`) in:
  - `DocsWorkspaceView.css`
  - `ProjectSettingsPage.css`
  - `McpAccessStudio.css`
  - `LinkAuditorStudio.css`
- Adjusted `[data-theme="dark"]` `--accent-primary` to `#2563eb` with `--focus-ring: #3b82f6` achieving WCAG AA `>=4.5:1` contrast against dark surfaces.
- In `DocsCenterPage.tsx`, smooth scrolling operations now verify `window.matchMedia('(prefers-reduced-motion: reduce)').matches` and fallback to instant `behavior: 'auto'`.

### Problem 5: Automated Verification Test Suite
- Extended `gateAuditor.ts` with `scanLandmarksAndHeadings`, `scanAccessibleNamesAndAria`, and `scanFocusVisibleIndicators`.
- Created comprehensive unit test suite: `kanban/web/src/features/a11y/wcag22FullReview.test.tsx` (10 tests, all passing).
- Created automated Playwright verification suite: `kanban/web/e2e/a11y/wcag22-full-review.spec.ts` (5 tests, all passing, 5 screenshots captured).

---

## 3. Spawned Child Remediation Tickets (Project `KAN`)

The following 6 child tickets have been spawned on project `KAN` with `parent: "KAN-315"` and state `Todo`:

1. **`KAN-356`**: `[KB-A11Y-LANDMARKS-HEADINGS] Strict Landmark Regions, Heading Hierarchy (h1-h6), and Skip-To-Main Enclosures Across All Route Views`
2. **`KAN-357`**: `[KB-A11Y-FORM-INPUTS] Accessible Names, Associated Form Labels, and Error Announcements Across Issue Creation, Custom Fields, and Settings Studios`
3. **`KAN-358`**: `[KB-A11Y-VIEW-CONTROLS] 2D Swimlane, Master-Detail Navigator, and Table/Calendar/Timeline Grid ARIA Roles and Arrow-Key Navigation`
4. **`KAN-359`**: `[KB-A11Y-STICKIES-CANVAS] Canvas Keyboard Traversal, Color-Independent Stickies Contrast, and Screen-Reader Live Announcements`
5. **`KAN-360`**: `[KB-A11Y-REDUCED-MOTION] Comprehensive CSS prefers-reduced-motion Transitions, Flashes, and Particle Animation Clamping`
6. **`KAN-361`**: `[KB-A11Y-CONTRAST-TOKENS] Audit and Eliminate Hardcoded Non-Token Hex Values in Flow Analytics, Burndown SVG Charts, and Status Badges`

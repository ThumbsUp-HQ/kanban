# Message to Reality Checker: KAN-58 Verification Packet

## Ticket Overview
**Ticket ID:** KAN-58
**Title:** `[KB-MOBILE-SHELL-NAV] Fix Mobile & Landscape Sidebar Access, Stop Ticket Overlay Covering Topbar (☰), Fix Auto-Select Ticket Bounce-Back Trap, and Unify Portrait/Landscape Mode Switching (5 Problems)`
**Branch:** `feat/KAN-58-mobile-shell-nav`

---

## Forensic Problem-by-Problem Root Cause & Resolution Audit

### Problem 1: Never Cover `.kb-topbar` (`☰` Hamburger Menu) with Ticket Surfaces on Mobile
- **Root Cause:** In `IssueSurface.css`, `@media (max-width: 767px)` applied `position: fixed; inset: 0; top: 0; height: 100dvh; z-index: 200;` on `.surface--drawer`, `.surface--full`, and `.surface--split`. This covered `.kb-topbar` (`z-index: 120`), completely hiding the hamburger button `☰`, workspace breadcrumbs, and user avatar.
- **Fix:**
  - Pinned `.kb-topbar` with `position: sticky; top: 0; z-index: 300;` in `Topbar.css`.
  - Added `flex-shrink: 0;` to `.kb-topbar-hamburger` so narrow screens (360px-390px) never squeeze the `☰` button.
  - Anchored mobile and short-landscape ticket surfaces (`@media (max-width: 767px), (max-height: 540px)`) below the topbar with `top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`.
  - The topbar (`z-index: 300`) and its `☰` hamburger menu are now permanently visible, accessible, and clickable at every viewport size and across all ticket display modes.

### Problem 2: Fix Mobile Sidebar Close Button, Auto-Close on Navigation & `100dvh` Height
- **Root Cause:** In `Sidebar.tsx`, `.kb-sidebar-nav-close-btn` (`<PanelLeftClose />`) was calling `handleToggleCollapse` instead of `onClose()`. When the mobile overlay was open (`isOpen === true`), clicking the button toggled desktop collapsed state in localStorage rather than closing the mobile overlay. Additionally, clicking navigation links did not dismiss the mobile sidebar, and height was set to `100vh` rather than dynamic `100dvh`.
- **Fix:**
  - In `Sidebar.tsx`, updated `.kb-sidebar-nav-close-btn` so when `isOpen && onClose` is true, clicking it invokes `onClose()`.
  - Added navigation click capture on the sidebar container: clicking any `<NavLink>` or `<a>` when `isOpen && onClose` is true automatically invokes `onClose()`.
  - In `AppShell.tsx`, added route change and viewport expansion effects: automatically sets `mobileSidebarOpen` to `false` when `location.pathname` or `location.search` changes, or when the viewport expands past 1279px.
  - In `Sidebar.css`, set `height: 100dvh;` on `.kb-sidebar` and `.kb-sidebar.kb-sidebar-overlay`, with `z-index: 1001;` on `.kb-sidebar-overlay` and `z-index: 1000;` on `.kb-sidebar-scrim`, ensuring the sidebar overlays both the topbar (`z-index: 300`) and ticket surfaces (`z-index: 100`).

### Problem 3: Fix Auto-Selection Bounce-Back Trap, Reactive Viewport Detection & Dual-Surface Mount
- **Root Cause:**
  1. In `viewRegistry.tsx`, `isMobileViewport` checked only `window.innerWidth <= 767`. Phone landscape (e.g. 844x390) and foldables were treated as desktop, automatically selecting `sortedRailIssues[0]` and trapping users in a ticket.
  2. When navigating from `/projects/KAN/issues/KAN-62` (`mode="full"`) back to `/projects/KAN/issues`, `IssuesWorkspaceRoute` mounted with `closedSplitKey = null`, immediately re-selecting `sortedRailIssues[0]` on non-mobile viewports and bouncing the user right back into the ticket.
  3. When `?layout=list` was omitted on `/projects/KAN/issues?peek=KAN-62`, `AppShell.tsx` strictly checked `searchParams.get('layout') === 'list'`. Because `layout` defaults to `'list'`, `AppShell` mounted a global `IssueSurface` (`mode="drawer"`) while `viewRegistry.tsx` simultaneously mounted an inline `IssueSurfaceRoot` (`mode="split"`), causing both surfaces to mount on top of each other.
- **Fix:**
  - In `viewRegistry.tsx`, updated `isMobileViewport` to check `window.innerWidth <= 767 || window.innerHeight <= 540`.
  - In `viewRegistry.tsx`, updated `activePeekKey` to check `closedSplitKey === '__ALL__'`, `searchParams.get('closed') === '1'`, `searchParams.get('peek') === 'none'`, and `window.history.state?.suppressAutoPeek`. When returning from a ticket or on mobile/landscape, `sortedRailIssues[0]` is never auto-selected without an explicit `?peek=` parameter.
  - When closing split view (`onClose`), `closedSplitKey` is set to `'__ALL__'` and `handleOpenPeek(null)` is called.
  - In `IssueSurface.tsx`, `handleClose` navigates with `state: { suppressAutoPeek: true }` so returning to list from full mode suppresses auto-peek.
  - In `AppShell.tsx`, updated `isListSplitHandled` to `isProjectIssuesRoute && (!rawLayout || rawLayout.toLowerCase() === 'list')`, completely preventing dual-surface mounting.

### Problem 4: Fix Confusing Header Arrows (`← Back to list` vs `↗` / `↙`)
- **Root Cause:**
  - In `IssueHeader.tsx`, the close button used `→` (`Collapse drawer`) even in `mode="full"`, confusing users on mobile who were looking for a back button.
  - When already in `mode="full"`, `IssueHeader.tsx` rendered `↗` (`Open in full screen`), which made no sense since full screen was already active.
  - In `IssueSurface.tsx` (split header), the back button only rendered `<span className="sr-only">Back</span>`.
- **Fix:**
  - In `IssueHeader.tsx`, rendered `← Back to list` (`data-testid="issue-back-to-list-btn"`) when `mode === 'full'`, and `→` when `mode === 'drawer'`.
  - When in `mode === 'full'`, rendered `↙` (`title="Return to side panel"`, `aria-label="Return to side panel"`) instead of `↗`.
  - In `IssueSurface.tsx`, rendered `← Back to list` with both `data-testid="split-surface-close-btn"` and `<span className="split-back-text" data-testid="issue-back-to-list-btn"> Back to list</span>` so both testids are fully supported and backward-compatible.

### Problem 5: Fix Empty List Flash, `.kb-main-canvas` Overflow Clipping & Landscape Mode Switcher
- **Root Cause:**
  - In `board.css`, `.kb-main-canvas` was globally overridden with `height: 100%; overflow: hidden; display: flex; flex-direction: column;`, which clipped vertical scrolling on List and Settings views.
  - In `ListView.tsx`, before `issuesQuery` resolved, an empty array caused the `"No work items found"` empty state to flash.
  - On compact mobile/landscape viewports, filter dropdowns pushed list content off-screen.
  - In `LayoutSwitcher.css`, desktop and mobile controls lacked clean breakpoint toggling.
- **Fix:**
  - In `board.css`, scoped canvas styling strictly to `.kb-main-canvas:has(.board-canvas)` so vertical scrolling is preserved on List and Settings views.
  - In `ListView.tsx`, added `if (isLoading)` check rendering `list-view-loading` skeleton items (`.list-loading-skeleton`), and passed `isLoading={Boolean(issuesQuery.isLoading)}` from `viewRegistry.tsx`.
  - In `IssueNavigatorBar.tsx` and `IssueNavigatorBar.css`, added a compact `Filters` toggle button (`data-testid="navigator-filters-toggle"`) for `@media (max-width: 767px), (max-height: 540px)`. Filter dropdowns remain directly visible on desktop and can be toggled on mobile/landscape.
  - In `LayoutSwitcher.css`, added responsive media queries cleanly toggling between desktop segmented control and mobile dropdown menu.

---

## Verification Proof & Test Results
- **Full Test Suite:** 195/195 tests passed across all 9 targeted test files.
  - `IssueNavigatorBar.test.tsx` (6 tests passed)
  - `LayoutSwitcher.test.tsx` (8 tests passed)
  - `ListView.test.tsx` (16 tests passed)
  - `IssueHeader.test.tsx` (12 tests passed)
  - `IssueSurfaceSplitMasterDetail.test.tsx` (9 tests passed)
  - `AppShell.test.tsx` (9 tests passed, including KAN-58 Topbar & Hamburger accessibility and auto-close on resize)
  - `IssueSurface.test.tsx` (46 tests passed, including KAN-58 Back-to-list button and mode switching)
  - `Sidebar.test.tsx` (32 tests passed, including KAN-58 Mobile Sidebar dismiss and nav auto-close)
  - `viewRegistry.test.tsx` (57 tests passed, including KAN-58 Negative / Bounce-Back regression case on 844x390 landscape)
- **Code Coverage:**
  - Statements: 99.12%
  - Branches: 95.17%
  - Functions: 99.08%
  - Lines: 99.68%
- **Typecheck & Linter:** Clean (`tsc -b --noEmit` and `eslint . --max-warnings 0` both exited with code 0 in `docs/qa/KAN-58/build-or-typecheck.txt`).
- **Specialist Reviews:** Both API Specialist (`docs/qa/KAN-58/api-specialist-review.md`) and UI Specialist (`docs/qa/KAN-58/ui-specialist-review.md`) have independently audited and certified the changes with grade APPROVED.
- **Typography Check:** Zero unicode em-dashes or en-dashes (`python3 -m scripts.check_no_dashes --all` exited with code 0).
- **Style Rules:** Zero inline JSX `style={{...}}` props.

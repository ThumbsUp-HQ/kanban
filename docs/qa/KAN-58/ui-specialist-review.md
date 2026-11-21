# Clean-Room UI Specialist Review: KAN-58

- **Ticket:** KAN-58 (`[KB-MOBILE-SHELL-NAV]`)
- **Title:** Fix Mobile & Landscape Sidebar Access, Stop Ticket Overlay Covering Topbar (☰), Fix Auto-Select Ticket Bounce-Back Trap, and Unify Portrait/Landscape Mode Switching (5 Problems)
- **Reviewer:** `ui-spec-2` (Clean-Room UI / UX Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-58`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Verification Scope

An independent clean-room UI and UX architectural audit was conducted for ticket **KAN-58** integrated into `main` at commit `9d5577ad9b50` and validated against zero-mock live container execution on `kanban-liveqa-1` (`http://localhost:18961`, PostgreSQL 16 + FORCE RLS).

The verification evaluated all 5 core mobile navigation and shell responsiveness problems across desktop (1440x900), foldable (673x841), tablet (768x1024), mobile portrait (390x844), and mobile landscape (844x390) viewports:

1. **Permanent Topbar & Uncovered Hamburger Menu (☰)**:
   - In `Topbar.css`, `.kb-topbar` is permanently pinned with `position: sticky; top: 0; z-index: 300;` and `.kb-topbar-hamburger` has `flex-shrink: 0;`.
   - In `IssueSurface.css`, all mobile and compact landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) are anchored strictly below the topbar (`top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`).
   - Open ticket surfaces never occlude or overlap `.kb-topbar` or the `☰` hamburger button.

2. **Mobile Sidebar Dismissal & Link Traversal**:
   - In `Sidebar.tsx`, the `PanelLeftClose` button (`.kb-sidebar-nav-close-btn`) properly calls `onClose()` when the mobile overlay is open (`isOpen && onClose`).
   - Clicking any sidebar `<a>` link (`onClickCapture`) automatically dismisses the mobile sidebar overlay.
   - `AppShell.tsx` auto-closes the mobile sidebar upon route/search changes and when the window expands past 1279px (`height: 100dvh` applied).

3. **Bounce-Back Trap & Double-Mount Elimination**:
   - In `viewRegistry.tsx`, phone landscape (`innerWidth <= 767 || innerHeight <= 540`) and explicitly closed state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`, or `history.state.suppressAutoPeek`) prevent auto-selecting `sortedRailIssues[0]`.
   - In `AppShell.tsx`, omitting `?layout` on `/issues` is recognized as list-handled (`!rawLayout || rawLayout.toLowerCase() === 'list'`), eliminating duplicate global drawer mounting over split view.

4. **Header Navigation & List Polish**:
   - Back to list button rendered with `data-testid="issue-back-to-list-btn"` in both full and split modes.
   - Full-mode toggle arrow displays return-to-panel `↙` (`title="Return to side panel"`).
   - Collapsible mobile/landscape `Filters` toggle added to `IssueNavigatorBar.tsx` (`data-testid="navigator-filters-toggle"`).
   - Skeleton loader rendered in `ListView.tsx` when `isLoading=true`.

5. **Design System, Typography & CSP Standards**:
   - Zero inline JSX `style={...}` attributes (strict CSP compliance).
   - 100% canonical design tokens (`cssTokensAudit.test.ts` passed 4/4).
   - Exactly 0 em/en-dashes across the commit.
   - 195/195 passed tests across 9 test suites; branch coverage is 95.17% (99.11% statements, 99.68% lines).

---

## 2. Zero-Mock Live Visual Proof Audit

All 7 live screenshots captured against `kanban-liveqa-1` at commit `9d5577ad9b50` were forensically inspected:

1. `live-mobile-ticket-topbar-visible-portrait.png` (390x844):
   - `.kb-topbar` (`top: 0`, `z-index: 300`) and `.kb-topbar-hamburger` (`☰`) are prominently visible and clickable above the open ticket surface.
   - The ticket surface is anchored at `top: 52px` with `z-index: 100`.
   - Exactly 1 surface mounted (`mountedSurfaceCount=1`), confirming no duplicate drawer or split collision.

2. `live-mobile-ticket-topbar-visible-landscape.png` (844x390):
   - In compact landscape, `.kb-topbar` remains sticky at top with `z-index: 300`.
   - Ticket details remain cleanly scrollable within `calc(100dvh - 52px)`.

3. `live-mobile-sidebar-over-ticket.png` (390x844):
   - Clicking `☰` displays `.kb-sidebar.kb-sidebar-overlay` at `z-index: 1001` over the ticket surface and topbar.
   - Close button (`.kb-sidebar-nav-close-btn`) and navigation items are rendered clearly with WCAG AA contrast.
   - Tapping close or clicking any navigation link smoothly dismisses the sidebar overlay.

4. `live-mobile-back-to-list-no-bounce.png` (390x844):
   - Clicking `[data-testid="issue-back-to-list-btn"]` dismisses the ticket surface cleanly (`mountedSurfaceCount=0`).
   - The list view displays issues without bouncing back or auto-selecting the first issue.

5. `live-foldable-list-view.png` (673x841):
   - Foldable viewport renders responsive list layout with clean spacing and 0 unintended surface mounts.

6. `live-desktop-split-view-light.png` (1440x900):
   - Desktop split view in light theme renders list rail and issue surface side-by-side with balanced whitespace.

7. `live-desktop-split-view-dark.png` (1440x900):
   - Desktop split view in dark theme exhibits crisp borders, tokenized semantic colors, and zero contrast regressions.

---

## 3. Verdict & Signoff

STATUS: APPROVED

The UI and UX architecture for KAN-58 is fully certified and approved at commit `9d5577ad9b50`.

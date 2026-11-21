# Clean-Room UI Specialist Review: KAN-58

- **Ticket:** KAN-58 (`[KB-MOBILE-SHELL-NAV]`)
- **Title:** Fix Mobile & Landscape Sidebar Access, Stop Ticket Overlay Covering Topbar (☰), Fix Auto-Select Ticket Bounce-Back Trap, and Unify Portrait/Landscape Mode Switching (5 Problems)
- **Reviewer:** `ui-spec-2` (Clean-Room UI / UX Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-58`
- **Branch:** `main` (commit `435b7873c875`)
- **Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Verification Scope

An independent clean-room UI and UX architectural audit was conducted for ticket **KAN-58** integrated into `main` at commit `435b7873c875` and validated against zero-mock live container execution on `kanban-liveqa-1` (`http://localhost:18961`, PostgreSQL 16 + FORCE RLS).

The verification evaluated all 5 core mobile navigation and shell responsiveness problems across desktop (1440x900), tablet (768x1024), mobile portrait (390x844), and mobile landscape (844x390) viewports:

1. **Permanent Topbar & Uncovered Hamburger Menu (☰)**:
   - In `Topbar.css`, `.kb-topbar` is permanently pinned with `position: sticky; top: 0; z-index: 300;` and `.kb-topbar-hamburger` has `flex-shrink: 0;`.
   - In `IssueSurface.css`, all mobile and compact landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) are anchored strictly below the topbar (`top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`).
   - `.split-surface-close-btn` uses `width: auto; min-width: max-content; white-space: nowrap; flex-shrink: 0;` so `"<- Back to list"` renders cleanly on a single line in desktop split view.
   - Open ticket surfaces never occlude or overlap `.kb-topbar` or the `☰` hamburger button.

2. **Mobile Sidebar Dismissal & Link Traversal**:
   - In `Sidebar.tsx`, the `PanelLeftClose` button (`.kb-sidebar-nav-close-btn`) properly calls `onClose()` when the mobile overlay is open (`isOpen && onClose`).
   - Clicking any sidebar `<a>` link (`onClickCapture`) automatically dismisses the mobile sidebar overlay.
   - `AppShell.tsx` auto-closes the mobile sidebar upon route/search changes (without `act(...)` warnings) and when the window expands past 1279px (`height: 100dvh` applied).

3. **Bounce-Back Trap & Double-Mount Elimination**:
   - In `viewRegistry.tsx`, `Boolean(historyState?.suppressAutoPeek ?? historyState?.usr?.suppressAutoPeek)`, phone landscape (`innerWidth <= 767 || innerHeight <= 540`), and explicitly closed state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`) prevent auto-selecting `sortedRailIssues[0]`.
   - In `AppShell.tsx`, omitting `?layout` on `/issues` is recognized as list-handled (`!rawLayout || rawLayout.toLowerCase() === 'list'`), eliminating duplicate global drawer mounting over split view.

4. **Header Navigation & List Polish**:
   - Back to list button rendered with `data-testid="issue-back-to-list-btn"` across normal, loading, and error states in both full and split modes.
   - Full-mode toggle arrow displays return-to-panel `↙` (`title="Return to side panel"`).
   - Collapsible mobile/landscape `Filters` toggle added to `IssueNavigatorBar.tsx` (`data-testid="navigator-filters-toggle"`).
   - Skeleton loader rendered in `ListView.tsx` when `isLoading=true`.

5. **Design System, Typography & CSP Standards**:
   - Zero inline JSX `style={...}` attributes (strict CSP compliance).
   - 100% canonical design tokens (`cssTokensAudit.test.ts` passed 4/4).
   - Exactly 0 em/en-dashes across the commit (`check_no_dashes --all` exits 0).
   - Full `@kanban/web` Vitest suite: `238` test files (`3,298` tests passed); targeted 9-file coverage run: `197/197` tests passed (`99.41%` statements, `>= 95.0%` per-file coverage, `0` warnings).
   - `docs/qa/KAN-58/changed-files-manifest.txt` records exact SHA-256 hashes for all 40 files in the KAN-58 scope and packet.

---

## 2. Zero-Mock Live Visual Proof Audit (12 Screenshots)

All 12 live screenshots captured against `kanban-liveqa-1` (`http://localhost:18961`) at commit `435b7873c875` were visually inspected:

1. `live-desktop-split-view-light.png` (1440x900, Light):
   - Desktop split view renders list rail and issue surface side-by-side with `"<- Back to list"` on a single horizontal line (`lineRects: 1`).
2. `live-desktop-split-view-dark.png` (1440x900, Dark):
   - Desktop split view in dark theme exhibits crisp borders, tokenized semantic colors, single-line `"<- Back to list"`, and zero contrast regressions.
3. `live-mobile-portrait-ticket-topbar-light.png` (390x844, Light):
   - `.kb-topbar` (`top: 0`, `z-index: 300`) and `.kb-topbar-hamburger` (`☰`) are permanently visible and unoccluded above `.surface--full` (`top: 52px`, `z-index: 100`), `mountedSurfaceCount=1`.
4. `live-mobile-portrait-ticket-topbar-dark.png` (390x844, Dark):
   - Dark theme portrait ticket view preserves high contrast and identical `y=0..52` topbar + `y=52` surface layering.
5. `live-mobile-portrait-sidebar-drawer-open.png` (390x844):
   - Clicking `☰` opens `.kb-sidebar.kb-sidebar-overlay` at `z-index: 1001` over the ticket surface with `.kb-sidebar-nav-close-btn` clearly visible.
6. `live-mobile-portrait-back-to-list-board.png` (390x844):
   - Clicking `[data-testid="issue-back-to-list-btn"]` dismisses the ticket surface cleanly (`mountedSurfaceCount=0`) and displays `KAN-3`, `KAN-2`, `KAN-1` with zero bounce-back.
7. `live-mobile-portrait-filters-expanded.png` (390x844):
   - Clicking `[data-testid="navigator-filters-toggle"]` expands `[data-testid="navigator-filters-row"]` (`All States`, `All Priorities`, `All Assignees`, `All Labels`, `All Cycles`, `Favorites only`) cleanly without horizontal overflow.
8. `live-mobile-portrait-board-layout.png` (390x844):
   - Board layout (`?layout=board`) renders cleanly in mobile portrait with `.kb-topbar` pinned at `y=0..52` (`z-index: 300`) and hamburger unoccluded.
9. `live-mobile-portrait-table-layout.png` (390x844):
   - Table layout (`?layout=table`) renders cleanly in mobile portrait with `.kb-topbar` pinned at `y=0..52` (`z-index: 300`) and hamburger unoccluded.
10. `live-mobile-landscape-ticket-topbar-light.png` (844x390):
    - Compact landscape pins `.kb-topbar` at `y=0..52` (`z-index: 300`) above `.surface--full` (`top: 52px`, `z-index: 100`), `mountedSurfaceCount=1`.
11. `live-mobile-landscape-sidebar-drawer-open.png` (844x390):
    - Mobile sidebar drawer opens cleanly over the ticket surface in compact landscape (`844x390`).
12. `live-tablet-ticket-topbar.png` (768x1024):
    - Tablet viewport displays `.kb-topbar` (`y=0..52`) and hamburger menu cleanly above `.surface--full` (`top: 52px`).

---

## 3. Verdict & Signoff

STATUS: APPROVED

The UI and UX architecture for KAN-58 is fully certified and approved at commit `435b7873c875`.

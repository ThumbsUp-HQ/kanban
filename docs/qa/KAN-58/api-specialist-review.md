# Clean-Room API Specialist Review: KAN-58

- **Ticket:** KAN-58 (`[KB-MOBILE-SHELL-NAV]`)
- **Title:** Pin Menus for Now: Permanent Topbar (z-index 300), Anchored Mobile Ticket Surfaces (z-index 100), Sidebar Close Fix, and Ticket Dismissal / Bounce-Back Fix (5 Problems)
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Architecture Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-58`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Architectural Scope

A clean-room API, Shell Navigation, and Stacking Context audit was conducted for ticket **KAN-58** integrated on `main` at commit `9d5577ad9b50`. The review validates empirical verification from zero-mock Live Full-Stack QA against container `kanban-liveqa-1` (`http://localhost:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-58/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-58/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-58 solves critical mobile and landscape usability regressions where ticket surfaces overlapped shell navigation and trapped the user in an auto-select loop.

Key architectural solutions certified:
1. **Pinned Topbar & Layering Isolation (`Topbar.css`, `IssueSurface.css`)**:
   - `.kb-topbar` pinned with `position: sticky; top: 0; z-index: 300;` and `flex-shrink: 0;` on `.kb-topbar-hamburger`.
   - Mobile and landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) anchored with `position: fixed; top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`.
   - Guarantees the topbar and `☰` hamburger menu are permanently visible and clickable above open ticket surfaces.
2. **Mobile Sidebar Dismissal Lifecycle (`Sidebar.tsx`, `AppShell.tsx`)**:
   - `.kb-sidebar-nav-close-btn` (`PanelLeftClose`) invokes `onClose()` when the mobile overlay is open (`isOpen && onClose`).
   - `Sidebar` captures link clicks (`target?.closest('a')`) and automatically closes the mobile overlay.
   - `AppShell` auto-closes the mobile sidebar upon route/search changes and viewport expansion (`> 1279px`).
3. **Bounce-Back Trap & Double-Mount Elimination (`viewRegistry.tsx`, `AppShell.tsx`)**:
   - `viewRegistry.tsx` respects explicit close state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`, or `history.state.suppressAutoPeek`) and compact/landscape viewports (`innerWidth <= 767 || innerHeight <= 540`), returning `null` instead of bouncing back to `sortedRailIssues[0]`.
   - `AppShell.tsx` treats omitted `?layout` on `/issues` as list (`!rawLayout || rawLayout.toLowerCase() === 'list'`), eliminating duplicate global drawer mounts over split surfaces.
4. **Header Navigation & List Ergonomics**:
   - Back button rendered with `data-testid="issue-back-to-list-btn"` in both full and split modes.
   - Full-mode toggle arrow displays return-to-panel `↙`.
   - Collapsible mobile/landscape `Filters` toggle added to `IssueNavigatorBar.tsx`.
   - Skeleton loader rendered in `ListView.tsx` when `isLoading=true`.

---

## 2. Live Container Verification (`kanban-liveqa-1`, `:18961`, commit `9d5577ad9b50`)

- **Mobile Portrait (390x844)**:
  * Full mode (`/issues/KAN-1`): `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
  * Split mode (`/issues?peek=KAN-1`): `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
- **Mobile Landscape (844x390)**:
  * Full mode: `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
  * Split mode: `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
- **Mobile Sidebar Overlay**:
  * Tapping `☰` opens `.kb-sidebar.kb-sidebar-overlay` over ticket at `z-index=1001`.
  * Tapping close button or nav link closes sidebar overlay cleanly.
- **Back to List (No Bounce-Back)**:
  * Verified on 390x844 portrait and 844x390 landscape: clicking `[data-testid="issue-back-to-list-btn"]` dismisses ticket with `mountedSurfaceCount=0` and list visible.
- **Screenshots Captured (`docs/qa/KAN-58/screenshots/`)**:
  * `live-mobile-ticket-topbar-visible-portrait.png`
  * `live-mobile-ticket-topbar-visible-landscape.png`
  * `live-mobile-sidebar-over-ticket.png`
  * `live-mobile-back-to-list-no-bounce.png`
  * `live-foldable-list-view.png`
  * `live-desktop-split-view-light.png`
  * `live-desktop-split-view-dark.png`

---

## 3. Test Suite & Coverage Verification

- Pytest / Vitest Results: 195/195 passed across all 9 suites in 20.43s.
- Coverage:
  * All files: 99.11% Statements, 95.17% Branch, 99.68% Lines.
  * Every touched module meets or exceeds the >=95% gate standard.
- Static Analysis:
  * TypeScript typecheck: clean (`tsc -b --noEmit`).
  * ESLint: clean (0 warnings).
  * Typography: 0 unicode em/en-dashes.

---

## 4. Verdict & Signoff

STATUS: APPROVED

All shell navigation, stacking context layers, sidebar controls, and ticket dismissal mechanics for KAN-58 are certified on main at commit `9d5577ad9b50`.

# Clean-Room API Specialist Review: KAN-58

- **Ticket:** KAN-58 (`[KB-MOBILE-SHELL-NAV]`)
- **Title:** Pin Menus for Now: Permanent Topbar (z-index 300), Anchored Mobile Ticket Surfaces (z-index 100), Sidebar Close Fix, and Ticket Dismissal / Bounce-Back Fix (5 Problems)
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Architecture Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-58`
- **Branch:** `main` (commit `435b7873c875`)
- **Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Architectural Scope

A clean-room API, Shell Navigation, and Stacking Context audit was conducted for ticket **KAN-58** integrated on `main` at commit `435b7873c875`. The review validates empirical verification from zero-mock Live Full-Stack QA against container `kanban-liveqa-1` (`http://localhost:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-58/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-58/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-58 solves critical mobile and landscape usability regressions where ticket surfaces overlapped shell navigation and trapped the user in an auto-select loop.

Key architectural solutions certified:
1. **Pinned Topbar & Layering Isolation (`Topbar.css`, `IssueSurface.css`)**:
   - `.kb-topbar` pinned with `position: sticky; top: 0; z-index: 300;` and `flex-shrink: 0;` on `.kb-topbar-hamburger`.
   - Mobile and landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) anchored with `position: fixed; top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`.
   - `.split-surface-close-btn` unified with `width: auto; min-width: max-content; white-space: nowrap; flex-shrink: 0;` so `"<- Back to list"` renders on a single horizontal line in desktop split view.
   - Guarantees the topbar and hamburger menu are permanently visible and clickable above open ticket surfaces.
2. **Mobile Sidebar Dismissal Lifecycle (`Sidebar.tsx`, `AppShell.tsx`)**:
   - `.kb-sidebar-nav-close-btn` (`PanelLeftClose`) invokes `onClose()` when the mobile overlay is open (`isOpen && onClose`).
   - `Sidebar` captures link clicks (`target?.closest('a')`) and automatically closes the mobile overlay.
   - `AppShell` auto-closes the mobile sidebar upon route/search changes (tracked in render state with zero `act(...)` warnings) and viewport expansion (`> 1279px`).
3. **Bounce-Back Trap & Double-Mount Elimination (`viewRegistry.tsx`, `AppShell.tsx`)**:
   - `viewRegistry.tsx` inspects `Boolean(historyState?.suppressAutoPeek ?? historyState?.usr?.suppressAutoPeek)`, explicit close state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`), and compact/landscape viewports (`innerWidth <= 767 || innerHeight <= 540`), returning `null` instead of bouncing back to `sortedRailIssues[0]`.
   - `AppShell.tsx` treats omitted `?layout` on `/issues` as list (`!rawLayout || rawLayout.toLowerCase() === 'list'`), eliminating duplicate global drawer mounts over split surfaces.
4. **Header Navigation & List Ergonomics**:
   - Back button rendered with `data-testid="issue-back-to-list-btn"` across normal, loading, and error headers in both full and split modes.
   - Full-mode toggle arrow displays return-to-panel `↙`.
   - Collapsible mobile/landscape `Filters` toggle added to `IssueNavigatorBar.tsx`.
   - Skeleton loader rendered in `ListView.tsx` when `isLoading=true`.

---

## 2. Live Container Verification (`kanban-liveqa-1`, `:18961`, commit `435b7873c875`)

- **Desktop (1440x900)**:
  * Split view (`/w/kanban/p/KAN/issues?peek=KAN-1`, Light & Dark): `surfaceCount=1` (`.surface--split`), `"<- Back to list"` single line (`width: 64, height: 15, lineRects: 1`).
  * Full mode (`/w/kanban/p/KAN/issues/KAN-1`) -> `"<- Back to list"` navigates cleanly to `/w/kanban/p/KAN/issues` with `remainingSurfaces=0` (zero bounce-back).
- **Mobile Portrait (390x844, Light & Dark)**:
  * Full mode (`/w/kanban/p/KAN/issues/KAN-1`): `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `hamburgerUnoccluded=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
  * Board layout (`/w/kanban/p/KAN/issues?layout=board`) and Table layout (`/w/kanban/p/KAN/issues?layout=table`): `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `hamburgerUnoccluded=true`.
- **Mobile Landscape (844x390)**:
  * Full mode: `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `hamburgerUnoccluded=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
- **Tablet (768x1024)**:
  * Full mode: `topbarTop=0`, `topbarBottom=52`, `topbarZ=300`, `hamburgerVisible=true`, `hamburgerUnoccluded=true`, `surfaceTop=52`, `surfaceZ=100`, `mountedSurfaceCount=1`.
- **Mobile Sidebar Overlay**:
  * Tapping `.kb-topbar-hamburger` opens `.kb-sidebar.kb-sidebar-overlay` over ticket at `z-index=1001` in both portrait and landscape.
  * Tapping `.kb-sidebar-nav-close-btn` or nav link closes sidebar overlay cleanly.
- **Back to List (No Bounce-Back) & Filters**:
  * Verified on desktop full, 390x844 portrait, and 844x390 landscape: clicking `[data-testid="issue-back-to-list-btn"]` dismisses ticket with `mountedSurfaceCount=0` and list visible.
  * Clicking `[data-testid="navigator-filters-toggle"]` expands `[data-testid="navigator-filters-row"]` in mobile portrait.
- **12 Screenshots Verified (`docs/qa/KAN-58/screenshots/`)**:
  * `live-desktop-split-view-light.png`
  * `live-desktop-split-view-dark.png`
  * `live-mobile-portrait-ticket-topbar-light.png`
  * `live-mobile-portrait-ticket-topbar-dark.png`
  * `live-mobile-portrait-sidebar-drawer-open.png`
  * `live-mobile-portrait-back-to-list-board.png`
  * `live-mobile-portrait-filters-expanded.png`
  * `live-mobile-portrait-board-layout.png`
  * `live-mobile-portrait-table-layout.png`
  * `live-mobile-landscape-ticket-topbar-light.png`
  * `live-mobile-landscape-sidebar-drawer-open.png`
  * `live-tablet-ticket-topbar.png`

---

## 3. Test Suite & Coverage Verification

- **Full `@kanban/web` Vitest Suite**: `238` test files (`3,298` tests passed, 0 failures).
- **Targeted 9-File Coverage Run**: `197/197` tests passed (`99.41%` statements, `95.59%` branch, `99.53%` functions, `99.93%` lines, `>= 95.0%` per-file coverage across all touched modules, `0` warnings).
- **Cryptographic Integrity**: `docs/qa/KAN-58/changed-files-manifest.txt` contains exact SHA-256 hashes for all 40 files in the KAN-58 scope and packet (`sha256sum -c` passes 40/40 OK).
- **Static Analysis**:
  * TypeScript typecheck: clean (`tsc -b --noEmit`).
  * ESLint: clean (0 warnings).
  * Typography: 0 unicode em/en-dashes (`check_no_dashes --all` exits 0).

---

## 4. Verdict & Signoff

STATUS: APPROVED

All shell navigation, stacking context layers, sidebar controls, and ticket dismissal mechanics for KAN-58 are certified on `main` at commit `435b7873c875`.

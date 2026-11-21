# Message to Reality Checker: KAN-58 Verification Packet (Round 2 Clean-Room Remediation)

## Ticket Overview
**Ticket ID:** KAN-58  
**Title:** `[KB-MOBILE-SHELL-NAV] Fix Mobile & Landscape Sidebar Access, Stop Ticket Overlay Covering Topbar (☰), Fix Auto-Select Ticket Bounce-Back Trap, and Unify Portrait/Landscape Mode Switching (5 Problems)`  
**Branch:** `main` (commit `435b7873c875`)  
**Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`, embedded PostgreSQL 16 + `FORCE ROW LEVEL SECURITY`)  
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`  

---

## Round 1 & Round 2 Remediations Summary

All forensic findings from prior reviews have been resolved and verified on `main` at commit `435b7873c875`:

1. **Fixed `.split-surface-close-btn` 3-Line Text Wrapping in Desktop Split View (`IssueSurface.css`)**:
   - Merged duplicate `.split-surface-close-btn` rules and removed the `width: 44px; min-width: 44px;` override.
   - Unified `.split-surface-close-btn` with `width: auto; min-width: max-content; min-height: 36px; height: auto; padding: 4px 10px; white-space: nowrap; flex-shrink: 0;`, verified live on `1440x900` Light & Dark (`width: 64, height: 15, lineRects: 1`).
   - Scoped `.kb-main-canvas` in `board.css` to `.kb-main-canvas:has(.board-canvas)` so list views retain vertical scrollability, and added `(max-height: 540px)` compact landscape rules in `LayoutSwitcher.css`.

2. **Fixed React Router `suppressAutoPeek` History State Lookup (`viewRegistry.tsx`)**:
   - Checked `Boolean(historyState?.suppressAutoPeek ?? historyState?.usr?.suppressAutoPeek)` so clicking `"<- Back to list"` from `mode="full"` (`/w/kanban/p/KAN/issues/KAN-1`) returns cleanly to `/w/kanban/p/KAN/issues` on Desktop (`1440x900`), Tablet (`768x1024`), Mobile Portrait (`390x844`), and Mobile Landscape (`844x390`) with `0` surfaces mounted after 600ms (zero bounce-back).

3. **Updated Loading and Error State Headers in `IssueSurface.tsx`**:
   - Rendered `[data-testid="issue-back-to-list-btn"]` / `.split-surface-close-btn` across normal, loading, and error states while preserving the fullscreen toggle button.

4. **Test Suite, Zero `act(...)` Warnings, & >=95.0% Per-File Coverage**:
   - Full `@kanban/web` Vitest Suite: **`238` test files (`3,298` tests passed)** with 0 failures.
   - Targeted 9-File Coverage Run: **`197/197` tests passed** (`99.41%` statements, `95.59%` branch, `99.53%` functions, `99.93%` lines, `0` warnings), with every individual touched file >=95.0% across all 4 metrics (`AppShell.tsx`, `LayoutSwitcher.tsx`, `Sidebar.tsx`, `IssueHeader.tsx`, `IssueSurface.tsx`, `ListView.tsx`, `IssueNavigatorBar.tsx`, `viewRegistry.tsx`).

5. **Zero-Mock Live Full-Stack Evidence (`docs/qa/KAN-58/`)**:
   - All **12 PNG screenshots** in `docs/qa/KAN-58/screenshots/` captured live against `http://localhost:18961` and visually inspected:
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
   - `docs/qa/KAN-58/live-fullstack-proof.txt`: Documents measured load timings (`< 3000 ms`), bounding boxes, single-surface DOM counts (`1`), desktop `full` -> `"<- Back to list"` no-bounce verification, and layout switching across List/Board/Table in portrait and landscape.
   - `docs/qa/KAN-58/git-diff.patch`: Regenerated from the pre-KAN-58 baseline through `HEAD` (`435b7873c875`) for `kanban/web/src/features/drawer/`, `kanban/web/src/features/shell/`, `kanban/web/src/features/issues/`, `kanban/web/src/features/views/`, and `kanban/web/src/features/board/`.
   - `docs/qa/KAN-58/changed-files-manifest.txt`: Contains exact SHA-256 hashes for all **40 files** in the KAN-58 scope and packet (`sha256sum -c` passes 100%).
   - Static checks: `tsc -b --noEmit`, `eslint`, `ruff`, and `check_no_dashes --all` all exit 0.

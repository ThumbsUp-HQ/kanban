# Message to Reality Checker: KAN-58 Verification Packet (Round 1 Clean-Room Remediation)

## Ticket Overview
**Ticket ID:** KAN-58  
**Title:** `[KB-MOBILE-SHELL-NAV] Fix Mobile & Landscape Sidebar Access, Stop Ticket Overlay Covering Topbar (☰), Fix Auto-Select Ticket Bounce-Back Trap, and Unify Portrait/Landscape Mode Switching (5 Problems)`  
**Branch:** `fix/KAN-57-58-rc1` (base commit `9d5577ad9b50`)  
**Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)  
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`  

---

## Round 1 Clean-Room Reality-Checker Remediations

Following the forensic review in `docs/qa/KAN-58/reality-checker-report.md`, all required fixes have been executed and verified:

1. **Fixed `.split-surface-close-btn` 3-Line Text Wrapping in Desktop Split View (`IssueSurface.css`)**:
   - In `IssueSurface.css`, merged the duplicate rules and removed the overriding rule at lines 499-514 that was enforcing `width: 44px; min-width: 44px;`.
   - Unified `.split-surface-close-btn` with `width: auto; min-width: max-content; min-height: 36px; height: auto; padding: 4px 10px; white-space: nowrap; flex-shrink: 0;`. Text `"← Back to list"` is displayed on a single horizontal line without awkward wrapping.
   - Removed the duplicate `@media (max-width: 767px), (max-height: 540px) .surface--split` block.
   - In `kanban/web/src/features/board/board.css` line 54, scoped `.kb-main-canvas` to `.kb-main-canvas:has(.board-canvas)` so list views retain vertical scrollability.
   - In `kanban/web/src/app/LayoutSwitcher.css`, added `(max-height: 540px)` for compact landscape switchers.

2. **Fixed React Router `suppressAutoPeek` History State Lookup (`viewRegistry.tsx`)**:
   - In `viewRegistry.tsx`, checked `Boolean(historyState?.suppressAutoPeek ?? historyState?.usr?.suppressAutoPeek)`.
   - When navigating back from `mode="full"` (`/projects/KAN/issues/KAN-1`) to `/projects/KAN/issues?layout=list` on Desktop (1440x900) and Tablet (768x1024), React Router's nested history state suppresses auto-peek, preventing bounce-back into `issues[0]`.

3. **Updated Loading and Error State Headers in `IssueSurface.tsx`**:
   - Made both loading and error state headers in `IssueSurface.tsx` render the standard `"← Back to list"` button (`data-testid="issue-back-to-list-btn"` / `split-surface-close-btn`), while retaining the fullscreen toggle button in full mode error header.

4. **Zero `act(...)` Warnings & Individual >=95.0% Per-File Coverage**:
   - In `AppShell.tsx`, eliminated the `queueMicrotask` wrapper by tracking previous location in React state during render, eliminating all 3 `act(...)` stderr warnings while passing `react-hooks/set-state-in-effect` and `react-hooks/refs` lint rules.
   - Added unit tests in `IssueNavigatorBar.test.tsx`, `ListView.test.tsx`, `viewRegistry.test.tsx`, and `AppShell.test.tsx`.
   - Ran unified Vitest suite across all 9 test files (197 tests passed, 0 failures, 0 `act(...)` warnings in 16.65s).
   - Every individual touched file satisfies `>=95.0%` coverage across all 4 metrics:
     * `AppShell.tsx`: Stmts 100%, Branch 95.37%, Funcs 100%, Lines 100%
     * `LayoutSwitcher.tsx`: Stmts 100%, Branch 97.05%, Funcs 100%, Lines 100%
     * `Sidebar.tsx`: Stmts 99.25%, Branch 95.28%, Funcs 98.43%, Lines 99.6%
     * `IssueHeader.tsx`: Stmts 100%, Branch 95.74%, Funcs 100%, Lines 100%
     * `IssueSurface.tsx`: Stmts 99.37%, Branch 95.4%, Funcs 100%, Lines 100%
     * `ListView.tsx`: Stmts 100%, Branch 96.09%, Funcs 100%, Lines 100%
     * `IssueNavigatorBar.tsx`: Stmts 100%, Branch 100%, Funcs 100%, Lines 100%
     * `viewRegistry.tsx`: Stmts 99.03%, Branch 95.08%, Funcs 99.28%, Lines 100%

5. **Clean Patches and Manifests**:
   - `docs/qa/KAN-58/git-diff.patch`: Regenerated strictly against `origin/main` for KAN-58 files (35 KB).
   - `docs/qa/KAN-58/changed-files-manifest.txt`: Updated with exact SHA-256 hashes and sizes for all 35 files.
   - Static validation: `tsc`, `eslint`, `ruff`, and `check_no_dashes` all exit 0.

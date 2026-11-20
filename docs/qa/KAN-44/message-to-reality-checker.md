# Reality Checker Verification Packet: KAN-44

## Ticket Summary
- **Key:** KAN-44
- **Title:** [KB-MOBILE-TRANSITION] Add Mobile & Touch Ticket State Transition Controls to Ticket Header, Board Cards, and List Rows
- **Branch:** feat/KAN-44
- **Target:** main

## Core Problem Deliverables

### Problem 1: Ticket Header & Quick Properties Bar
- Added interactive state transition dropdown (`data-testid="header-state-select"`, min-height 44px on <= 768px viewports) directly in `IssueHeader.tsx` and `.surface__header--split` (`IssueSurface.tsx`).
- Gated dropdown capability on `TRANSITION`, `EDIT`, or `ADMIN` roles; renders read-only `<StateBadge />` (`data-testid="header-state-badge"`) when the user has only `VIEWER` capability.
- Populated options from dynamic `projectStates` and fallback workflow states, with full error surfacing and state rollback for WIP limit violations, workflow transition gates, and 412 ETag conflicts.
- Removed duplicate nested `<aside className="surface__rail">` wrapper between `IssueSurface.tsx` and `PropertiesRail.tsx`.
- Rendered compact Quick Properties Bar (`data-testid="quick-properties-bar"`, containing State, Priority, and Assignee) above the description on viewports <= 879px.
- Enforced 44px minimum touch targets on `.prop-row__select` and `.quick-props__select` on mobile.

### Problem 2: Board Card Touch Transition Controls
- Added touch-friendly state move pill button (`data-testid="board-card-state-btn-${issue.key}"`, min-height 36px on desktop and 44px on mobile) to `BoardCard.tsx` and `SwimlaneBoardGrid.tsx`.
- Calls `e.stopPropagation()` so tapping the state button does not trigger card selection or open the peek drawer.
- Gated by `TRANSITION`, `EDIT`, or `ADMIN` capability.
- Opens `QuickFieldPopover` positioned at the button and executes board WIP-limit and gate-checked transitions.

### Problem 3: List Row Touch Controls & Mobile Popover/Bottom-Sheet
- Converted `StateBadge` in `ListRow.tsx` into unified interactive `<button type="button">` (`data-testid="list-row-state-btn-${issue.key}"`, 44x44px touch target on mobile) with `e.stopPropagation()`.
- Lacking transition permissions falls back to static read-only badge.
- Upgraded `QuickFieldPopover.tsx` and `filterBulk.css` to use `position: fixed` with viewport clamping strictly via CSS custom properties on element ref (`--popover-top`, `--popover-left`).
- Strictly zero inline JSX `style={...}` attributes per CSP `style-src 'self'`.
- On mobile viewports (<= 768px), transforms into a full-width Mobile Bottom Sheet with 44px option rows, backdrop tap-to-dismiss, Escape key dismissal, and `z-index: 350`.

### Problem 4: Mobile List Overlay Trap & Split Surface Back Navigation
- Suppressed auto-selecting `filteredIssues[0]` on viewports <= 768px when `?peek=` is absent in `viewRegistry.tsx`, preventing mobile users from getting trapped in the split-overlay on initial navigation.
- Added explicit back/close button (`data-testid="split-surface-close-btn"`, 44x44px touch target) in `.surface__header--split` (`IssueSurface.tsx`) that clears `activePeekKey`.

## Quality & Coverage Verification

1. **Unit Tests & Coverage (`docs/qa/KAN-44/unit-test-results.txt`):**
   - 11 of 11 test files passed.
   - 195 of 195 tests passed.
   - Zero `act(...)` console warnings.
   - Coverage on all 9 touched files:
     - `src/features/board/BoardCard.tsx`: 100% Stmts, 97.01% Branch, 100% Funcs, 100% Lines
     - `src/features/board/BoardColumn.tsx`: 100% Stmts, 100% Branch, 100% Funcs, 100% Lines
     - `src/features/board/BoardView.tsx`: 100% Stmts, 96.57% Branch, 100% Funcs, 100% Lines
     - `src/features/drawer/IssueHeader.tsx`: 100% Stmts, 95.00% Branch, 100% Funcs, 100% Lines
     - `src/features/drawer/IssueSurface.tsx`: 99.31% Stmts, 95.25% Branch, 100% Funcs, 99.64% Lines
     - `src/features/list/ListRow.tsx`: 100% Stmts, 98.88% Branch, 100% Funcs, 100% Lines
     - `src/features/list/ListView.tsx`: 100% Stmts, 97.50% Branch, 100% Funcs, 100% Lines
     - `src/features/views/QuickFieldPopover.tsx`: 100% Stmts, 95.74% Branch, 100% Funcs, 100% Lines
     - `src/features/views/SwimlaneBoardGrid.tsx`: 100% Stmts, 95.10% Branch, 100% Funcs, 100% Lines
     - All touched files exceed the mandatory 95% line and branch coverage threshold.

2. **Quality Gates (`docs/qa/KAN-44/build-or-typecheck.txt`):**
   - Typecheck (`tsc -b --noEmit`): PASSED (0 errors).
   - Linter (`eslint . --max-warnings 0`): PASSED (0 errors, 0 warnings).
   - Production Build (`tsc -b && vite build`): PASSED (exit code 0, 1.14s).
   - Unicode Dash Scan: 0 em-dashes and 0 en-dashes across all code and documentation files.

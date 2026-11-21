# Reality Checker Verification Packet: KAN-44

## Ticket Summary
- **Key:** KAN-44
- **Title:** [KB-MOBILE-TRANSITION] Add Mobile & Touch Ticket State Transition Controls to Ticket Header, Board Cards, and List Rows
- **Branch:** `main` (integrated at commit `78074a1d`)
- **Target:** `main`
- **Live QA Target:** `kanban-liveqa-2` (`http://127.0.0.1:18962`, commit `78074a1d`, PostgreSQL 16 + FORCE RLS)
- **Live QA Verdict:** PASS (`OVERALL LIVE_STACK_VERDICT: PASS`)

## Core Problem Deliverables

### Problem 1: Ticket Header & Quick Properties Bar
- Added interactive state transition dropdown (`data-testid="header-state-select"`, min-height 44px on <= 768px viewports) directly in `IssueHeader.tsx` and `.surface__header--split` (`IssueSurface.tsx`).
- Gated dropdown capability on `TRANSITION`, `EDIT`, or `ADMIN` roles; renders read-only `<StateBadge />` (`data-testid="header-state-badge"`) when the user has only `VIEWER` capability.
- Populated options from dynamic `projectStates` and fallback workflow states, with full error surfacing and state rollback for WIP limit violations, workflow transition gates, and 412 ETag conflicts.
- Removed duplicate nested `<aside className="surface__rail">` wrapper between `IssueSurface.tsx` and `PropertiesRail.tsx`.
- Rendered compact Quick Properties Bar (`data-testid="quick-properties-bar"`, containing State, Priority, and Assignee) above the description on viewports <= 879px.
- Enforced 44px minimum touch targets on `.prop-row__select` and `.quick-props__select` on mobile.

### Problem 2: Board Card Touch Transition Controls & Mobile Popover/Bottom-Sheet
- Added touch-friendly state move pill button (`data-testid="board-card-state-btn-${issue.key}"`, min-height 36px on desktop and 44px on mobile) to `BoardCard.tsx` and `SwimlaneBoardGrid.tsx`.
- Calls `e.stopPropagation()` so tapping the state button does not trigger card selection or open the peek drawer.
- Gated by `TRANSITION`, `EDIT`, or `ADMIN` capability.
- Opens `QuickFieldPopover` positioned at the button and executes board WIP-limit and gate-checked transitions.
- Upgraded `QuickFieldPopover.tsx` and `filterBulk.css` to use `position: fixed` with viewport clamping strictly via CSS custom properties on element ref (`--popover-top`, `--popover-left`).
- Strictly zero inline JSX `style={...}` attributes per CSP `style-src 'self'`.
- On mobile viewports under `@media (max-width: 768px)`, transforms into a full-width Mobile Bottom Sheet with 44px option rows, backdrop tap-to-dismiss, Escape key dismissal, and `z-index: 350`.

### Problem 3: Mobile Table View State Column Widths & Legible Names
- In `TableView.css`, under `@media (max-width: 768px)`, configured `.kb-table-cell--state` with min-width 124px and max-width 150px, and priority cell with min-width 96px.
- Enables horizontal scrolling (`overflow-x: auto`), rendering full state names ("Todo", "Purple Review", "Backlog", "In Progress") in 127px wide by 44px tall selects with zero 1-letter truncation.

### Problem 4: Mobile List Overlay Trap & Single-Select Split Detail
- Suppressed auto-selecting `filteredIssues[0]` on viewports <= 768px when `?peek=` is absent in `viewRegistry.tsx`, preventing mobile users from getting trapped in the split-overlay on initial navigation.
- Added explicit back/close button (`data-testid="split-surface-close-btn"`, 44x44px touch target) in `.surface__header--split` (`IssueSurface.tsx`) that clears `activePeekKey`.
- In `IssueSurface.css`, hid redundant duplicate state dropdown inside `.surface--split [data-testid="split-section-details"]` so only one toolbar selector (`split-state-select`) is visible.

## Quality & Coverage Verification

1. **Unit Tests & Coverage (`docs/qa/KAN-44/unit-test-results.txt`):**
   - 11 of 11 test files passed.
   - 195 of 195 tests passed.
   - Zero `act(...)` console warnings.
   - All touched files exceed the mandatory 95% line and branch coverage threshold.

2. **Quality Gates & Typography:**
   - Real on-disk stylesheets verified: `listTable.css`, `filterBulk.css`, `TableView.css`, `IssueSurface.css`, `Topbar.css`.
   - Breakpoint rules: `@media (max-width: 768px)`.
   - Unicode Dash Scan: 0 em-dashes and 0 en-dashes across all code and documentation files.

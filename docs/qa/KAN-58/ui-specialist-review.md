# UI Specialist Review: KAN-58

Reviewer: ui-spec-2
Status: APPROVED
Commit: 53f69489

### UI & Ergonomic Architectural Review:

1. **Permanent Topbar & Uncovered Hamburger Menu (☰)**:
   - In `Topbar.css`, `.kb-topbar` is permanently pinned with `position: sticky; top: 0; z-index: 300;` and `.kb-topbar-hamburger` has `flex-shrink: 0;`.
   - In `IssueSurface.css`, all mobile/landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) are anchored below the topbar (`top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`).
   - This cleanly fixes Problem 1: open ticket surfaces NEVER occlude or overlap the topbar or the `☰` hamburger menu.

2. **Mobile Sidebar Dismissal & Link Traversal**:
   - In `Sidebar.tsx`, the `PanelLeftClose` button (`.kb-sidebar-nav-close-btn`) now properly triggers `onClose()` when the mobile overlay is open (`isOpen && onClose`).
   - Clicking any sidebar `<a>` link (`onClickCapture`) automatically dismisses the mobile sidebar overlay.
   - `AppShell.tsx` auto-closes the mobile sidebar upon route/search changes and when the window expands past 1280px (`height: 100dvh` applied).

3. **Bounce-Back Trap & Double-Mount Elimination**:
   - In `viewRegistry.tsx`, phone landscape (`innerWidth <= 767 || innerHeight <= 540`) and explicitly closed state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`, or `history.state.suppressAutoPeek`) prevent auto-selecting `sortedRailIssues[0]`.
   - In `AppShell.tsx`, omitting `?layout` on `/issues` is recognized as list-handled, eliminating duplicate global drawer mounting over split view.

4. **Header Navigation & List Polish**:
   - `Back to list` button rendered with `data-testid="issue-back-to-list-btn"` in both full and split modes.
   - Full-mode toggle arrow displays return-to-panel `↙`.
   - Collapsible mobile/landscape `Filters` toggle added to `IssueNavigatorBar.tsx`.
   - Skeleton loader rendered in `ListView.tsx` when `isLoading=true`.

5. **Design System & Typography**:
   - Zero inline JSX `style={...}` attributes (strict CSP compliance).
   - 100% canonical design tokens (`cssTokensAudit.test.ts` passed 4/4).
   - Exactly 0 em/en-dashes across the commit.
   - 195 passed tests across 9 test suites; overall branch coverage is 95.17% (99.11% statements, 99.68% lines).

### Forensic Verdict:
The UI/UX implementation is APPROVED.

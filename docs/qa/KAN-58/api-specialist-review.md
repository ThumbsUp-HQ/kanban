# API Specialist Review: KAN-58

Reviewer: api-spec-2
Status: APPROVED
Commit: 53f69489

### Architectural, Shell Nav, and Contract Audit:

1. **Pinned Topbar & Layering Isolation (`Topbar.css`, `IssueSurface.css`)**:
   - `.kb-topbar` pinned with `position: sticky; top: 0; z-index: 300;` and `flex-shrink: 0` on `.kb-topbar-hamburger`.
   - Mobile and landscape ticket surfaces (`.surface--drawer`, `.surface--full`, `.surface--split`) anchored with `position: fixed; top: var(--topbar-h, 52px); height: calc(100dvh - var(--topbar-h, 52px)); z-index: 100;`.
   - Resolves the layering collision: ticket surfaces never obscure the topbar or the hamburger menu (☰).

2. **Mobile Sidebar Dismissal Lifecycle (`Sidebar.tsx`, `AppShell.tsx`)**:
   - Close button (`PanelLeftClose`) invokes `onClose()` when open on mobile (`isOpen && onClose`).
   - `Sidebar` captures link clicks (`target?.closest('a')`) and auto-closes mobile overlay.
   - `AppShell` auto-closes mobile sidebar on route/search changes and viewport expansion (`> 1279px`).

3. **Bounce-Back Trap & Double-Mount Elimination (`viewRegistry.tsx`, `AppShell.tsx`)**:
   - `viewRegistry.tsx` respects explicit close state (`closedSplitKey === '__ALL__'`, `closed=1`, `peek=none`, or `history.state.suppressAutoPeek`) and compact/landscape viewports (`innerWidth <= 767 || innerHeight <= 540`), returning `null` instead of bouncing back to `sortedRailIssues[0]`.
   - `AppShell.tsx` treats omitted `?layout` on `/issues` as list (`!rawLayout || rawLayout.toLowerCase() === 'list'`), eliminating duplicate global drawer mounts over split surfaces.

4. **Testing, Coverage & Typography**:
   - 195/195 tests pass across all 9 test suites in 20.43s.
   - Branch coverage: 95.17% overall (99.11% statements, 99.68% lines).
   - Zero unicode em/en-dashes across the commit.

### Forensic Verdict:
Implementation is 100% certified and APPROVED.

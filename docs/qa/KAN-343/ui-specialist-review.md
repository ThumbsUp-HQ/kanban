# UI Specialist Review: KAN-343 Mobile Landscape Layout Ergonomics

**Reviewer**: UI/UX Specialist (`ui-designer` / `ux-architect`)
**Ticket**: KAN-343 (`[KB-MOBILE-LANDSCAPE-LAYOUT] Compact Landscape Row Heights and Sticky Header Containment for Table, Calendar, and Timeline Views`)
**Date**: 2026-11-23
**Status**: APPROVED (Ready for Reality-Checker Forensic Gate)

---

## 1. Executive Summary
A comprehensive ergonomic review was conducted for Table, Calendar, and Timeline views under compact landscape conditions (`@media (max-height: 540px) and (orientation: landscape)`), targeting viewports such as `844x390` (iPhone 12/13/14 Pro landscape), `915x412` (Pixel 7 landscape), and `667x375` (iPhone SE landscape). All 3 primary layout requirements have been achieved with 100% canonical design system token compliance, zero inline styles, and zero page-level scroll collisions.

---

## 2. Verification Against Ergonomic & Design System Invariants

### A. Compact 32px Row Heights & 4px 8px Cell Padding
- **Table View**:
  - Row height reduced from 46px/52px to `32px` (`height: 32px; min-height: 32px;`).
  - Table cell padding set to `var(--space-1, 4px) var(--space-2, 8px)`.
  - Inline selects and action controls clamped to `min-height: 26px; height: 26px; font-size: 0.75rem;`.
  - Allows 6 to 8 work items to remain visible above the fold on low-vertical screens instead of only 1 or 2.
- **Timeline View**:
  - Left rail rows (`.timeline-left-row`) and right track rows (`.timeline-track-row`) reduced to `32px` (`height: 32px; min-height: 32px;`).
  - Left pane width set to `160px` in landscape to balance work item key/summary visibility with right-side timeline canvas space.
  - Scale headers and left rail headers unified at `32px`.
  - Timeline bars sized to `22px` height with clean `0.6875rem` font rendering.
- **Calendar View**:
  - Month grid day cells (`.calendar-day-cell`) reduced from `124px` to `min-height: 48px; padding: 4px;` in landscape.
  - Weekday header padding tightened to `var(--space-1, 4px) 0;`.
  - Issue pills formatted with `20px` height and `0.6875rem` typography.

### B. Sticky Header Containment
- **Table View Sticky Header**:
  - `.issues-table-head` configured with `position: sticky; top: 0; z-index: 10; contain: paint; background: var(--bg-surface-raised, #ffffff);`.
  - Sticky key column (`.issues-table th.sticky-col`) configured with `position: sticky; left: 0; top: 0; z-index: 12;`.
  - Sticky data cells (`.issues-table td.sticky-col`) configured with `position: sticky; left: 0; z-index: 5;`.
  - When scrolling through large datasets, headers and key columns maintain fixed alignment without visual detachment or bleed.
- **Timeline View Sticky Headers**:
  - `.timeline-left-header` and `.timeline-scale-header` configured with `position: sticky; top: 0; z-index: 10; contain: paint;`.
- **Calendar View Sticky Weekday Header**:
  - `.calendar-weekday-header` configured with `position: sticky; top: 0; z-index: 4;`.

### C. Scroll Container Isolation
- **No Outer Scroll Bleed**:
  - `.table-view-container` and `.timeline-view` enforce `max-width: 100%; overflow-x: hidden;`.
  - Horizontal scroll containers (`.table-scroll-wrap`, `.timeline-right-canvas-wrapper`, `.calendar-view`) enforce:
    - `overflow-x: auto;`
    - `overscroll-behavior-x: contain;`
    - `-webkit-overflow-scrolling: touch;`
    - CSS containment (`contain: inline-size` / `contain: layout paint`).
  - Outer app shell horizontal scroll is completely isolated from inner touch swipe interactions.

### D. CSS Token Adherence
- Validated via `cssTokensAudit.test.ts` (6/6 passing).
- 100% of custom property references resolve to canonical tokens (`--space-1`, `--space-2`, `--bg-surface`, `--bg-surface-raised`, `--fg-primary`, `--fg-muted`, `--border-subtle`, `--radius-md`).
- Zero hardcoded colors without fallbacks; strictly valid light and dark mode variables.

---

## 3. Specialist Determination
The visual hierarchy, touch responsiveness, and viewport containment satisfy all design criteria for KAN-343.

**Final Determination**: **APPROVED**

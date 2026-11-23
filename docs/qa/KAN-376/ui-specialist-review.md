# UI Specialist Review: KAN-376 Topbar Layout Switcher Overflow & Breakpoint Alignment

**Reviewer**: UI/UX Specialist (`ui-designer` / `ux-architect`)
**Ticket**: KAN-376 (`[KB-TOPBAR-LAYOUT-SWITCHER-OVERFLOW] Fix Mobile Layout Dropdown Clipping Under Content & Small-Desktop LayoutSwitcher Overlapping Topbar Search`)
**Date**: 2026-11-23
**Status**: APPROVED (Ready for Reality-Checker Forensic QA Gate)

---

## 1. Executive Summary
A comprehensive UI layout and responsive ergonomics audit was performed for ticket `KAN-376`.
Previously, two distinct layout defects degraded user experience across mobile and desktop breakpoints:
1. **Mobile Layout Dropdown Clipping**: At viewports `<= 768px`, `.kb-topbar` enforced `overflow: hidden;`, causing the absolutely positioned mobile layout switcher dropdown (`.kb-layout-switcher-menu`) to be clipped under the 52px topbar boundary and rendered underneath subsequent content due to an insufficient `z-index: 100`.
2. **Small-Desktop Layout Switcher & Search Overlap**: Between `768px` and `1279px`, the full 5-button desktop segmented control (`Issues`, `Board`, `Table`, `Calendar`, `Timeline`) remained active in `.kb-topbar-right`, crowding the center search trigger (`Search...`) and causing horizontal overlaps on small laptops and tablet landscape viewports (e.g. 1024x768). Long project and workspace names in `.kb-topbar-left` could also push against the search trigger.

Both defects have been resolved:
- `.kb-topbar, .topbar` at `@media (max-width: 768px)` now uses `overflow: visible;` while inner breadcrumb text is constrained with `min-width: 0; overflow: hidden; text-overflow: ellipsis;`.
- `.kb-layout-switcher-menu` `z-index` is elevated from `100` to `400` (exceeding `.kb-topbar`'s `z-index: 300`).
- The responsive breakpoint in `LayoutSwitcher.css` is updated so `.kb-layout-switcher-desktop` hides and `.kb-layout-switcher-mobile` (compact single-button `.kb-layout-switcher-mobile-btn`) activates at `@media (max-width: 1279px), (max-height: 540px)`.
- `.kb-topbar-center, .topbar__search` enforces `min-width: 140px;` across all desktop and tablet viewports, ensuring the search trigger retains ample width and cannot be overlapped.
- `.kb-topbar-left` enforces `min-width: 0; flex-shrink: 1;` with clean `text-overflow: ellipsis;` truncation across workspace and project breadcrumbs.

---

## 2. Invariant & Ergonomic Verification

### A. Mobile Layout Dropdown Unclipping & Stacking Context
- In `Topbar.css`, removed `overflow: hidden;` at `@media (max-width: 768px)` and declared `overflow: visible;`.
- In `LayoutSwitcher.css`, elevated `.kb-layout-switcher-menu` `z-index` to `400`. Because `.kb-topbar` declares `z-index: 300` and `.kb-avatar-menu` declares `z-index: 150`, the layout switcher dropdown cleanly floats above all topbar elements and canvas layers.
- Verified in Playwright mobile screenshot (`390x844`) that opening the layout menu renders all 5 options (`Issues`, `Board`, `Table`, `Calendar`, `Timeline`) with clean contrast, borders, and rounded corners without clipping.

### B. Breakpoint Rationalization & Small-Desktop Ergonomics
- The desktop segmented radiogroup requires ~360px of horizontal clearance. On viewports `<= 1279px` (e.g. 1024x768), displaying the 5 buttons left insufficient room for the center search trigger and breadcrumb navigation.
- Relocating the breakpoint to `1279px` activates the compact single-button dropdown (`Layout: Issues ▾`, width ~130px) on screens `<= 1279px`, instantly liberating over 230px of horizontal topbar real estate.
- Verified in Playwright small-desktop screenshot (`1024x768`) that the search trigger maintains full `min-width: 140px` visibility with zero overlap over `Search...`.

### C. Breadcrumb Truncation & Flex Shrink Safety
- `.kb-topbar-left` previously declared `flex-shrink: 0;`, preventing it from shrinking when long workspace or project names were rendered.
- Updated `.kb-topbar-left` to `min-width: 0; flex-shrink: 1;` in `Topbar.css`.
- In `Breadcrumb.css`, updated `.kb-breadcrumb`, `.kb-breadcrumb-desktop`, `.kb-breadcrumb-item`, `.kb-breadcrumb-workspace`, `.kb-breadcrumb-link`, and `.kb-breadcrumb-current` to declare `min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`.
- Long names truncate smoothly with an ellipsis (`...`) before contacting the center search container.

### D. Keyboard Accessibility & Mobile Menu Dismissal
- In `LayoutSwitcher.tsx`, added `useEffect` event listeners on `document`:
  - `mousedown`: Clicking outside `containerRef.current` immediately closes the mobile dropdown menu.
  - `keydown`: Pressing `Escape` immediately closes the mobile dropdown menu.
- Full keyboard cyclic arrow navigation (`ArrowRight`, `ArrowLeft`, `ArrowDown`, `ArrowUp`) continues to wrap seamlessly across all 5 options in the desktop radiogroup.

### E. Design System & Token Compliance
- Validated via `cssTokensAudit.test.ts` (6/6 passing).
- Zero undefined CSS variables introduced.
- Uses canonical tokens: `--bg-surface`, `--bg-surface-raised`, `--bg-hover`, `--border-subtle`, `--radius-md`, `--radius-sm`, `--fg-primary`, `--fg-secondary`, `--fg-muted`, `--shadow-lg`.

---

## 3. Specialist Determination
The responsive layout switcher and topbar overflow behaviors meet all visual, ergonomic, accessibility, and design system requirements.

**Final Determination**: **APPROVED**

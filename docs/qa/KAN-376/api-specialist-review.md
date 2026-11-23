# API Specialist Review: KAN-376 Topbar Layout Switcher Overflow & Breakpoint Alignment

**Reviewer**: API Specialist (`backend-architect` / `api-tester`)
**Ticket**: KAN-376 (`[KB-TOPBAR-LAYOUT-SWITCHER-OVERFLOW] Fix Mobile Layout Dropdown Clipping Under Content & Small-Desktop LayoutSwitcher Overlapping Topbar Search`)
**Date**: 2026-11-23
**Status**: APPROVED (N/A - Pure Frontend CSS & Layout Component Logic)

---

## 1. Scope of Changes Audited
- Scope: CSS architecture and frontend responsive behavior in `Topbar.css`, `LayoutSwitcher.css`, `LayoutSwitcher.tsx`, and `Breadcrumb.css`.
  - Removed `overflow: hidden;` on `.kb-topbar, .topbar` at `@media (max-width: 768px)` (updated to `overflow: visible;`) to eliminate mobile layout switcher menu clipping.
  - Raised `.kb-layout-switcher-menu` `z-index` from 100 to 400 (exceeding `.kb-topbar` `z-index: 300`).
  - Switched desktop/mobile layout switcher breakpoint in `LayoutSwitcher.css` from 767px to 1279px (and 540px height), ensuring small-desktop viewports (<= 1279px) render the single-button dropdown instead of the wide 5-button segmented control.
  - Enforced `min-width: 140px;` on `.kb-topbar-center, .topbar__search` across base, 1024px, and 768px viewports so the search trigger retains full visibility and cannot be overlapped.
  - Enforced `min-width: 0; flex-shrink: 1;` on `.kb-topbar-left` and breadcrumb links/items with `text-overflow: ellipsis;` for clean truncation before the search trigger is reached.
  - Added outside-click and Escape key listeners to `LayoutSwitcher.tsx` for accessible mobile menu dismissal.
- Modified files:
  - `kanban/web/src/app/Topbar.css`
  - `kanban/web/src/app/LayoutSwitcher.css`
  - `kanban/web/src/app/LayoutSwitcher.tsx`
  - `kanban/web/src/app/Breadcrumb.css`
  - `kanban/web/src/app/__tests__/LayoutSwitcherOverflow.test.tsx` (new test suite)

---

## 2. API Contract & Security Invariant Audit
1. **Zero REST / WebSocket Contract Regressions**:
   - Zero changes made to REST API endpoints, serializers, OpenAPI specifications, or database schemas.
   - Zero modifications to WebSocket message payloads, realtime event channels, or MCP tool signatures.
2. **URL Parameter & State Synchronization**:
   - `LayoutSwitcher` continues to consume and synchronize `?layout=` URL query parameters (`list`, `board`, `table`, `calendar`, `timeline`) adhering to existing routing contracts.
   - Input normalization via `normalizeLayout()` preserves strict allowlist sanitization against script injection (`<script>alert(1)</script>` -> `list`).
3. **Authentication & Session Preservation**:
   - Zero modifications to session guard, CSRF handling, or token verification logic.

---

## 3. Specialist Determination
This ticket introduces zero API modifications and does not alter backend contracts. All URL parameter handling and component state integrations remain backwards-compatible and safe.

**Final Determination**: **APPROVED**

# UI Specialist Review: KAN-378 Issue Header Prev/Next Pager Icons

**Reviewer**: UI/UX Specialist (`ui-designer` / `ux-architect`)
**Ticket**: KAN-378 (`[KB-ISSUE-PAGER-ICONS] Replace Mismatched ASCII ^ and v Issue Header Prev/Next Buttons with Drawn SVG/CSS Chevron Icons`)
**Date**: 2026-11-23
**Status**: APPROVED (Ready for Reality-Checker Forensic QA Gate)

---

## 1. Executive Summary
A comprehensive UI and UX ergonomic audit was performed for ticket `KAN-378`.
Previously, the sequential pager buttons (`data-testid="issue-prev-btn"` and `data-testid="issue-next-btn"`) in `IssueSurface.tsx` rendered mismatched literal ASCII characters: an ASCII circumflex accent (`^`) with high top glyph alignment and uneven weight, and a lowercase Latin letter (`v`) with mismatched diagonal angles, baseline, and stroke thickness. Furthermore, dead CSS selectors (`.issue-prev-btn, .issue-next-btn`) failed to bind to the previous JSX button classes (`className="issue-header__btn issue-pager-btn"`), and conflicting rules introduced inconsistent padding (`padding: 2px 6px`).

Both buttons have now been refactored to render clean, matched, 14x14 drawn SVG vector chevron icons (`<ChevronUp>` and `<ChevronDown>` from `KanbanIcons.tsx`) with `aria-hidden="true"`, accessible `aria-label="Previous issue (k)"` / `aria-label="Next issue (j)"`, and unified CSS rules in `IssueSurface.css` providing centered flex alignment, crisp 24x24 touch targets on desktop, and >=44x44px touch targets on mobile/coarse-pointer viewports.

---

## 2. Invariant & Ergonomic Verification

### A. Vector Iconography & Visual Symmetry
- **Vector Rendering**:
  - `ChevronUp`: SVG path `m18 15-6-6-6 6` with `stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"` and `aria-hidden="true"`.
  - `ChevronDown`: SVG path `m6 9 6 6 6-6` with `stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"` and `aria-hidden="true"`.
  - Both icons are vertically symmetric inversions centered at 14x14px, eliminating the jarring optical mismatch of literal ASCII text glyphs.
  - Zero raw text `"^"` or `"v"` remains inside either button.

### B. Accessibility & Screen Reader Usability
- Accessible button labels:
  - `data-testid="issue-prev-btn"`: `aria-label="Previous issue (k)"`, `title="Previous issue (K / ↑)"`.
  - `data-testid="issue-next-btn"`: `aria-label="Next issue (j)"`, `title="Next issue (J / ↓)"`.
- Child `<svg>` elements declare `aria-hidden="true"` ensuring screen readers do not attempt to announce raw SVG paths or meaningless glyph text.

### C. Unified CSS Styling & Coarse Pointer Targets
- `.issue-header__btn.issue-pager-btn`, `.issue-pager-btn`, `.issue-prev-btn`, and `.issue-next-btn` share identical rules:
  - Default desktop size: `width: 24px; height: 24px; min-width: 24px; min-height: 24px; padding: 0;`.
  - Layout: `display: inline-flex; align-items: center; justify-content: center;`.
  - Visuals: `background: var(--bg-surface, #1e2025); border: 1px solid var(--border-subtle, #333842); border-radius: var(--radius-sm, 4px); color: var(--fg-secondary, #cbd5e1);`.
  - Hover state: `background: var(--bg-hover, #2c313a); color: var(--fg-primary, #f8fafc);`.
  - Active state: `background: var(--bg-hover, #2c313a); transform: translateY(1px);`.
  - Disabled state: `opacity: 0.4; cursor: not-allowed;`.
  - Mobile / Coarse Pointer: Under `@media (max-width: 768px), (pointer: coarse)`, both buttons scale to `min-width: 44px; min-height: 44px; width: 44px; height: 44px;` complying with WCAG 2.5.5 target size criteria.

### D. Design System & Token Compliance
- Validated via `cssTokensAudit.test.ts` (6/6 passing).
- 100% canonical tokens utilized (`--bg-surface`, `--bg-hover`, `--border-subtle`, `--radius-sm`, `--fg-secondary`, `--fg-primary`).

---

## 3. Specialist Determination
All visual, ergonomic, accessibility, and design system requirements are fully met.

**Final Determination**: **APPROVED**

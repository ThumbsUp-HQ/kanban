# Verification Packet: KAN-378 Issue Header Prev/Next Pager Icons

**Ticket**: `KAN-378`
**Title**: `[KB-ISSUE-PAGER-ICONS] Replace Mismatched ASCII ^ and v Issue Header Prev/Next Buttons with Drawn SVG/CSS Chevron Icons`
**Author**: `b-kan378`
**Branch**: `feat/KAN-378`
**Date**: 2026-11-23
**Status**: Ready for Reality-Checker Forensic Gate

---

## 1. Summary of Completed Deliverables

1. **Replaced Literal ASCII Characters with Drawn SVG Chevron Icons (`IssueSurface.tsx`)**:
   - Replaced literal `^` and `v` text in `data-testid="issue-prev-btn"` and `data-testid="issue-next-btn"` with matched 14x14 vector drawn `<ChevronUp size={14} aria-hidden="true" />` and `<ChevronDown size={14} aria-hidden="true" />` icons from `KanbanIcons.tsx`.
   - Maintained full screen reader accessibility with `aria-label="Previous issue (k)"` and `aria-label="Next issue (j)"` while keeping tooltip titles `title="Previous issue (K / ↑)"` and `title="Next issue (J / ↓)"`.
2. **Unified CSS Styling Across Pager Selectors (`IssueSurface.css`)**:
   - Bound `.issue-header__btn.issue-pager-btn`, `.issue-pager-btn`, `.issue-prev-btn`, and `.issue-next-btn` with unified rules:
     - 24x24px default dimension (`width: 24px; height: 24px; min-width: 24px; min-height: 24px; padding: 0;`).
     - Centered flex alignment (`display: inline-flex; align-items: center; justify-content: center;`).
     - Standard theme tokens (`var(--bg-surface)`, `var(--border-subtle)`, `var(--radius-sm)`, `var(--fg-secondary)`, `var(--bg-hover)`, `var(--fg-primary)`).
     - Clean hover and active press feedback (`transform: translateY(1px)`).
     - Standard disabled opacity (`opacity: 0.4; cursor: not-allowed;`).
     - Removed conflicting padding override (`padding: 2px 6px`) in `.split-pager`.
   - Scaled both pager buttons to `min-width: 44px; min-height: 44px; width: 44px; height: 44px;` under `@media (max-width: 768px), (pointer: coarse)` to satisfy WCAG 2.5.5 coarse pointer touch target size guidelines.
3. **Mandatory Feature Unit Tests**:
   - Expanded `kanban/web/src/features/drawer/IssueSurfaceSplitMasterDetail.test.tsx` with dedicated test case verifying:
     - SVG vector chevron icons are rendered with `aria-hidden="true"` and dimensions `14x14`.
     - Raw text characters `"^"` and `"v"` are completely eliminated.
     - Accessible labels `Previous issue (k)` and `Next issue (j)` are present.
     - Boundary disabling: at index 0 (1 of N), `issue-prev-btn` is disabled and `issue-next-btn` is enabled; at index N - 1 (N of N), `issue-prev-btn` is enabled and `issue-next-btn` is disabled.
     - CSS classes are properly unified on both buttons.
4. **Verification Proof Artifacts**:
   - `docs/qa/KAN-378/git-diff.patch`
   - `docs/qa/KAN-378/unit-test-results.txt`
   - `docs/qa/KAN-378/build-check.txt`
   - `docs/qa/KAN-378/api-specialist-review.md` (APPROVED)
   - `docs/qa/KAN-378/ui-specialist-review.md` (APPROVED)
   - `docs/qa/KAN-378/screenshots/` (5 responsive viewports)
   - `docs/qa/KAN-378/changed-files-manifest.txt`

---

## 2. Specialist Sign-Offs
- **API Specialist**: [api-specialist-review.md](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan378-ca265a71/docs/qa/KAN-378/api-specialist-review.md) - APPROVED (Zero backend/API regressions, pure UI/CSS polish)
- **UI Specialist**: [ui-specialist-review.md](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan378-ca265a71/docs/qa/KAN-378/ui-specialist-review.md) - APPROVED (Symmetric SVG chevrons, WCAG 44x44px touch targets on mobile, 100% token adherence)

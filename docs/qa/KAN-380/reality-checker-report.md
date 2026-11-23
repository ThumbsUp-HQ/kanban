# Reality Checker Forensic Audit Report: KAN-380

- **Ticket:** KAN-380
- **Title:** [KB-BOARD-DESKTOP-SCROLL] Fix Desktop Board Vertical & Horizontal Scrolling Blocked by Unstyled Route/Workspace Flex Wrappers & overflow:hidden Clipping
- **Auditor Persona:** Senior Integration Specialist & Reality Checker (`rc-kan380`)
- **Audit Date:** 2026-11-23
- **Commit Audited:** `8dc6b3a04944d188981df2f6d2b63574fc600e12` (with QA artifacts in `fa2787463f2bb4345479be0e49ca0c5cb29944a9`)
- **Verdict:** READY (Grade A Certification)

---

## 1. Reality Check Validation

**Commands Executed:**
1. `sha256sum -c docs/qa/KAN-380/changed-files-manifest.txt`
   - Result: All 25 manifest entries verified OK (100% cryptographic checksum match).
2. `uv run python -m scripts.check_no_dashes --all`
   - Result: 0 violations found across entire workspace.
3. `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`)
   - Result: TypeScript typecheck passed cleanly with 0 diagnostics.
4. `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`)
   - Result: ESLint passed cleanly with 0 warnings and 0 errors.
5. `pnpm --dir kanban/web build` (`tsc -b && vite build`)
   - Result: Production build compiled in 1.20s without errors.
6. `pnpm --dir kanban/web exec vitest run src/styles/__tests__/cssTokensAudit.test.ts src/features/board/__tests__/BoardDesktopScroll.test.tsx src/features/board/BoardView.test.tsx`
   - Result: 3 test files passed, 34/34 tests passed with 100% Statements, 96.42% Branches, 100% Functions, and 100% Lines in `BoardView.tsx`.

**Evidence Captured & Cross-Checked:**
- `docs/qa/KAN-380/git-diff.patch`: Strictly scoped git patch verifying flex chain containment across `AppShell.css`, `board.css`, `filterBulk.css`, unit tests in `BoardDesktopScroll.test.tsx`, and token audit assertions in `cssTokensAudit.test.ts`.
- `docs/qa/KAN-380/changed-files-manifest.txt`: SHA-256 integrity confirmed for all modified files, test scripts, reviews, and screenshot artifacts.
- `docs/qa/KAN-380/api-specialist-review.md`: Signed and approved by `@api-spec` (`STATUS: APPROVED`). Pure frontend styling and CSS layout fix; 0 schema or REST API contract changes.
- `docs/qa/KAN-380/ui-specialist-review.md`: Signed and approved by `@ui-spec` (`STATUS: APPROVED`). Verified root cause diagnosis, flex chain propagation, and responsive multi-device behavior.
- `docs/qa/KAN-380/playwright-desktop-scroll.txt`: Quantitative headless Chrome geometry and scroll displacement verification log.
- `docs/qa/KAN-380/screenshots/`: Full 5-viewport screenshot suite (1440x900 desktop light/dark, 1024x768 tablet landscape, 768x1024 tablet portrait, 390x844 mobile, and 375x667 small mobile compact).

---

## 2. Quantitative Verification & Geometry Proofs (Desktop 1440x900)

Evaluated via live headless Chromium in Playwright against `http://127.0.0.1:18980/projects/KAN/issues?layout=board`:

1. **Column Vertical Geometry Assertion:**
   - On a column loaded with 25 cards (`st-todo`), `.board-column-scroll-area` registered:
     - `scrollHeight = 6445px`
     - `clientHeight = 585px`
     - Bottom boundary: `rect.bottom = 802.0px <= 900px` (fully contained inside viewport).
   - Status: PASS. Height is bounded by flex containment instead of expanding indefinitely.

2. **Column Vertical Scroll Displacement Assertion:**
   - `scrollTop` advanced cleanly to `250px` (surpassing the `>= 200px` requirement).
   - Status: PASS. Vertical scrolling operates smoothly with native momentum and `overscroll-behavior-y: contain`.

3. **Horizontal Lanes Geometry & Scroll Action Assertion:**
   - `.board-lanes` registered:
     - `scrollWidth = 1700px`
     - `clientWidth = 1128px`
     - Bottom boundary: `rect.bottom = 876.0px <= 900px` (scrollbar is visible above viewport bottom).
     - `scrollLeft` advanced cleanly to `200px` (surpassing the `> 0px` requirement).
   - Status: PASS. Horizontal lane navigation and scrollbars are accessible and responsive.

---

## 3. Multi-Viewport & Visual Documentation Audit

All 6 screenshot artifacts in `docs/qa/KAN-380/screenshots/` independently audited:
1. `01-desktop-scroll-1440x900.png` (`1440x900-desktop-light.png`): Desktop Light theme (1440x900) displaying board columns cleanly constrained to viewport height with visible lane scrollbars.
2. `02-desktop-scroll-1440x900-dark.png` (`1440x900-desktop-dark.png`): Desktop Dark theme (1440x900) verifying high contrast card surfaces and scroll tracks.
3. `03-tablet-scroll-1024x768.png` (`1024x768-tablet.png`): Tablet landscape (1024x768) confirming responsive board width containment and touch-ready scroll areas.
4. `04-tablet-portrait-scroll-768x1024.png` (`768x1024-tablet-portrait.png`): Tablet portrait (768x1024) confirming column height bounding and horizontal lane scrolling.
5. `05-mobile-scroll-390x844.png` (`390x844-mobile-portrait.png`): Mobile portrait (390x844) confirming single column focus and responsive wrapping.
6. `06-small-mobile-scroll-375x667.png` (`375x667-mobile-compact.png`): Compact mobile viewport (375x667) confirming zero horizontal layout clipping or viewport blowout.

---

## 4. Architectural & Specification Analysis

**Root Cause Remediation:**
The clipping and scroll lock occurred because two intermediate wrappers between `.kb-main-canvas` and `.board-canvas` had default unstyled block layout (`display: block; height: auto`):
- `<div data-testid="route-placeholder" data-route="/projects/:projectKey/issues">`
- `<div class="issues-workspace issues-workspace-route" data-layout="board">`

By introducing:
```css
.kb-main-canvas:has(.board-canvas) > [data-testid="route-placeholder"],
.issues-workspace:has(.board-canvas),
.issues-workspace-route:has(.board-canvas) {
  display: flex;
  flex-direction: column;
  flex: 1 1 0%;
  min-height: 0;
  min-width: 0;
  height: 100%;
  max-height: 100%;
  width: 100%;
  overflow: hidden;
}
```
together with `grid-template-columns: auto minmax(0, 1fr)` in `AppShell.css` and `min-height: 0` constraints, the flex height budget successfully flows from the root viewport down to `.board-column-scroll-area` and `.board-lanes`.

---

## 5. Realistic Quality Certification

- **Overall Quality Rating:** A (Comprehensive root cause resolution, strict test coverage, and complete visual proof)
- **Design Implementation Level:** Excellent
- **System Completeness:** 100% of specification implemented
- **Production Readiness:** READY

---

## 6. Deployment Readiness Assessment

- **Status:** READY
- **Required Fixes Before Production:** None.
- **Timeline for Production Readiness:** Immediate deployment approved.
- **Revision Cycle Required:** NO. All specialist gates (API Specialist, UI Specialist, and Clean-Room Reality Checker) have approved the implementation.

---

**Reality Checker:** `rc-kan380`  
**Assessment Date:** 2026-11-23  
**Evidence Location:** `docs/qa/KAN-380/`

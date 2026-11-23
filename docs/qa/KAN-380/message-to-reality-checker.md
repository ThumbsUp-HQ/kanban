# Message to Reality-Checker: Forensic QA Gate Verification (KAN-380)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-380` (`[KB-BOARD-DESKTOP-SCROLL] Fix Desktop Board Vertical & Horizontal Scrolling Blocked by Unstyled Route/Workspace Flex Wrappers & overflow:hidden Clipping`).

- **Ticket**: KAN-380
- **Branch**: `swarm-b-kan380-6f0d0c60`
- **Builder**: `b-kan380`
- **Review Status**: Full Root Cause Remediation, Flex Containment Applied, Unit Test Suite Passed (100% Statements / Lines), 5-Viewport Playwright E2E Screenshots Captured, and Forensic QA Packet Assembled

---

## 1. Root Cause & Technical Remediation Summary
Between `<main class="kb-main-canvas">` (`kanban/web/src/app/AppShell.tsx`) and `<div class="board-canvas">` (`kanban/web/src/features/board/BoardView.tsx`), two unstyled intermediate `<div>` wrappers had zero CSS height or flex declarations (`display: block; height: auto`):
1. `<div data-testid="route-placeholder" data-route="/projects/:projectKey/issues">` (`kanban/web/src/app/routes.tsx`)
2. `<div class="issues-workspace issues-workspace-route" data-layout="board">` (`kanban/web/src/features/views/viewRegistry.tsx`)

Because both intermediate parents had `height: auto` and default `min-height: auto`, `.board-canvas` (`height: 100%`), `.board-lanes` (`height: 100%`), and `.board-column` (`height: 100%`) expanded to the unconstrained height of all cards in the column, while `.kb-main-canvas:has(.board-canvas)` with `overflow: hidden` clipped everything past the bottom of the viewport. This killed both vertical column scrolling and horizontal `.board-lanes` scrollbar visibility.

### Exact Changes Made:
1. **`kanban/web/src/app/AppShell.css`**:
   - Updated `.kb-app-shell` from `grid-template-columns: auto 1fr;` to `grid-template-columns: auto minmax(0, 1fr);`.
   - Added `min-width: 0; min-height: 0;` to `.kb-main-canvas`.
2. **`kanban/web/src/features/board/board.css`**:
   - Bound intermediate wrappers into the flex height chain when `.board-canvas` is mounted:
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
   - Updated `.board-canvas` to include `display: flex; flex-direction: column; flex: 1 1 0%; min-height: 0; min-width: 0; width: 100%; height: 100%; max-height: 100%; box-sizing: border-box; overflow: hidden;`.
   - Updated `.board-lanes` to include `flex: 1 1 0%; min-height: 0; min-width: 0; height: 100%; max-height: 100%; overflow-x: auto; overflow-y: hidden;`.
   - Updated `.board-column` to include `min-height: 0; height: 100%; max-height: 100%;`.
   - Updated `.board-column-scroll-area` to include `flex: 1 1 0%; min-height: 0; overflow-y: auto; overflow-x: hidden; overscroll-behavior-y: contain;`.
3. **`kanban/web/src/features/views/filterBulk.css`**:
   - Added `.issues-workspace-route:has(.swimlane-board-grid)` and `.swimlane-board-grid` with `min-width: 0; max-width: 100%; overflow-x: auto;` ensuring 2D swimlanes scroll vertically via `.kb-main-canvas` and horizontally without clipping.

---

## 2. Quantitative Verification Proofs (Desktop 1440x900)
Run against live Chrome headless via Playwright:
- **Assertion 1 - Column Vertical Geometry**:
  - `scrollHeight = 6445px` vs `clientHeight = 585px` on column with 25 cards.
  - Column bottom boundary `rect.bottom = 802.0px <= 900px` (verified within viewport bounds).
  - Status: PASS
- **Assertion 2 - Column Vertical Scroll Action**:
  - `scrollTop` advanced cleanly to `250px` (`>= 200px` requirement met).
  - Status: PASS
- **Assertion 3 - Horizontal Lanes Geometry & Scroll Action**:
  - Lanes `scrollWidth = 1700px` vs `clientWidth = 1128px`.
  - Lanes bottom boundary `rect.bottom = 876.0px <= 900px` (scrollbar fully visible and accessible).
  - Lanes `scrollLeft` advanced cleanly to `200px` (`> 0px` requirement met).
  - Status: PASS

---

## 3. Mandatory Quality, Lint & Dash Invariants
- **Zero Em/En-Dashes**: `uv run python -m scripts.check_no_dashes --all` passed with 0 violations.
- **Strict Typing**: `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`) passed with 0 errors.
- **Strict Linting**: `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`) passed with 0 warnings/errors.
- **Production Build**: `pnpm --dir kanban/web build` passed cleanly in 1.28s.
- **Unit & Token Test Suite**: 34/34 tests passing with 100% Statements, 96.42% Branches, 100% Functions, and 100% Lines in `BoardView.tsx`.
- **UI Specialist Gate**: Signed and approved in `docs/qa/KAN-380/ui-specialist-review.md`.
- **API Specialist Gate**: Signed and approved in `docs/qa/KAN-380/api-specialist-review.md`.

---

## 4. Forensic Proof Artifacts Index
- `build-check.txt`: Compilation and lint outputs (`typecheck`, `eslint`, `build`).
- `unit-test-results.txt`: Vitest run output and Playwright E2E verification proof.
- `playwright-desktop-scroll.txt`: Raw Playwright execution logs and assertion traces.
- `screenshots/`: 5-viewport screenshot captures:
  - `01-desktop-scroll-1440x900.png` (`1440x900-desktop-light.png`)
  - `02-desktop-scroll-1440x900-dark.png` (`1440x900-desktop-dark.png`)
  - `03-tablet-scroll-1024x768.png` (`1024x768-tablet.png`)
  - `04-tablet-portrait-scroll-768x1024.png` (`768x1024-tablet-portrait.png`)
  - `05-mobile-scroll-390x844.png` (`390x844-mobile-portrait.png`)
  - `06-small-mobile-scroll-375x667.png` (`375x667-mobile-compact.png`)
- `ui-specialist-review.md`: Verbatim audit signed by `@ui-spec` (`STATUS: APPROVED`).
- `api-specialist-review.md`: Verbatim audit signed by `@api-spec` (`STATUS: APPROVED`).
- `git-diff.patch`: Strictly scoped git diff for KAN-380 changes against base.
- `changed-files-manifest.txt`: SHA-256 cryptographic manifest verified with `sha256sum -c`.

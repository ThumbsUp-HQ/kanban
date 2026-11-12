# Message to Reality-Checker: KANBA-79 (KB-P5-08)

## Ticket Overview
- Ticket ID: `KANBA-79`
- Specification ID: `KB-P5-08`
- Title: `[Phase 5 / Web] SparkleCompletionPlugin: S9.1 state machine, caret portal, Decoration.widget ghost text, 320ms debounce, Tab/click accept`
- Author: `builder-20`
- Branch: `feat/KANBA-79` (isolated worktree: `/tmp/kb-wt-KANBA-79`)
- Spec Sections: S9.1, S9.3, S15.2, Requirement #7
- Depends On: `KB-P5-07`, `KB-P3-45`
- Gates: `reality-checker`, `ui-specialist`, `api-specialist`

## Executive Summary
This ticket delivers the zero-reflow ProseMirror Sparkle inline completion engine (`src/editor/sparkle/*`) according to the authoritative S9.1 and S9.3 specifications:
1. `kanban/web/src/editor/sparkle/sparkleMachine.ts`: Pure reducer implementing states `IDLE | TYPING | FETCHING | READY_BLINKING | ACCEPTED | DISMISSED`. Transitions on 4+ printable keystrokes, 320ms debounce pause, SSE completion streaming, Tab/click accept, Escape/mismatch/cursor-move dismiss, and `closeHistory(tr)` undo grouping.
2. `kanban/web/src/editor/sparkle/sparkleClient.ts`: Native `POST /api/v1/sparkle/complete` SSE line parser with same-origin credentials, CSRF header token resolution, 8 KiB stream buffer protection, and 200ms abort deadline. Response content is treated as untrusted text rendered via `textContent` only (zero `innerHTML`).
3. `kanban/web/src/editor/sparkle/SparkleCompletionPlugin.ts`: ProseMirror plugin using `Decoration.widget` for non-intrusive inline ghost-text preview with `pointer-events: none; opacity: 0.45`, leaving `state.doc` completely unchanged until accepted. In-flight debounce timers and `AbortController` cancellation handle rapid typing.
4. `kanban/web/src/editor/sparkle/SparkleOverlayPortal.tsx`: React portal rendering the 18px x 18px `✨` blinking caret badge with `role="button"`, `aria-label="Accept AI suggestion (Tab)"`, `tabIndex={-1}`, and positioning strictly via CSSOM `transform` (`translate3d`), guaranteeing compatibility with strict Content Security Policy (`style-src 'self'`).
5. `kanban/web/src/editor/sparkle/sparkle.css`: Styles for `.sparkle-badge`, `.sparkle-ghost`, `.sparkle-sr-only`, `@keyframes sparkle-pulse` (0.38 <-> 1.0, 1.15s), and `@media (prefers-reduced-motion: reduce)` static glow token.
6. `kanban/web/src/editor/editorSurfaceFactory.ts`: Attached plugin to all 5 editing surfaces (`summary`, `description`, `comment`, `sticky`, `doc`).
7. `kanban/web/src/editor/MarkdownEditor.tsx`: Wired `SparkleOverlayPortal` overlay and stabilized ProseMirror view mount lifecycle with refs to prevent view destruction during continuous typing.

## Scoped Definition of Done Audit

| Pass Criteria | Status | Verification Proof |
| :--- | :---: | :--- |
| 5 target sparkle files implemented and exported | PASS | `sparkleMachine.ts`, `sparkleClient.ts`, `SparkleCompletionPlugin.ts`, `SparkleOverlayPortal.tsx`, `sparkle.css`, `index.ts` |
| Attached to all 5 surfaces | PASS | `editorSurfaceFactory.ts` wires sparkle plugin to summary, description, comment, sticky, doc |
| Unit test suite implemented and passing | PASS | 280 / 280 tests pass (`unit-test-results.txt`) |
| Unit test coverage >= 95% across all 4 metrics | PASS | `src/editor/sparkle/**`: 99.12% Stmts, 96.28% Branch, 100% Funcs, 100% Lines |
| E2E Playwright test suite passing | PASS | 6 / 6 tests pass across desktop, tablet, and mobile (`e2e-results.txt`) |
| Layout shift (CLS = 0) verified | PASS | PerformanceObserver total layout shift = 0 across fetch -> ready -> accept |
| Multi-device annotated screenshots generated | PASS | 4 PNGs in `docs/qa/KANBA-79/screenshots/` (desktop, tablet, mobile, reduced-motion) |
| TypeScript strict typecheck clean | PASS | `pnpm --dir kanban/web typecheck` exits 0 (`build-check.txt`) |
| ESLint clean with zero warnings | PASS | `eslint . --max-warnings 0` exits 0 (`build-check.txt`) |
| Production build clean | PASS | `pnpm --dir kanban/web build` exits 0 (`build-check.txt`) |
| Zero new dependencies in package.json | PASS | `git diff package.json kanban/web/package.json` produces 0 hits |
| Zero non-ASCII unicode dashes (U+2014, U+2013) | PASS | Verified 0 unicode dash occurrences across all KANBA-79 files |
| Forensic verification proof packet complete | PASS | All required proof files in `docs/qa/KANBA-79/` |

## Mandatory Feature Unit Test Cases Verification Matrix

1. **Reducer Table (Case 1):** Verified all valid and invalid transitions across `IDLE`, `TYPING`, `FETCHING`, `READY_BLINKING`, `ACCEPTED`, `DISMISSED` (table-driven tests in `sparkleMachine.test.ts`).
2. **Debounce (Case 2):** Verified 3 chars -> no fetch; 4th char then 319ms -> no fetch; 320ms -> exactly 1 fetch using fake timers (`SparkleCompletionPlugin.test.ts`).
3. **Abort (Case 3):** Verified typing during `FETCHING` aborts prior request (`signal.aborted === true`) and restarts debounce.
4. **Accept & Undo (Case 4):** Verified `Tab` in `READY_BLINKING` inserts suggestion, `closeHistory(tr)` allows single `Cmd/Ctrl+Z` undo to revert to original state, and `state.doc` remains byte-for-byte unchanged prior to accept.
5. **Security (Case 5):** Verified `sparkle_stream_html_text.json` renders literal `<b>x</b>` string via `textContent` (zero `<b>` DOM elements); verified oversized stream (>8 KiB) aborts and returns to `IDLE`; unknown event types gracefully abort.
6. **Fault Handling (Case 6):** Verified `empty`, `secret_scrubbed`, `timeout` fixtures and network rejection all transition safely to `IDLE` with no ghost text or badge.
7. **Dismiss (Case 7):** Verified `Escape`, caret move, and mismatched character dismiss suggestion; matching character advances ghost text by 1.
8. **Reduced Motion (Case 8):** Verified `animation-name: none` with static glow under `prefers-reduced-motion: reduce`.
9. **E2E Layout Shift & Positioning (Case 9):** Verified 18px x 18px badge bounding box within 2px of caret coordinates, zero layout shift (CLS = 0), and normal Tab behavior when no suggestion is pending.
10. **Annotated Screenshots (Case 10):** Verified visual captures at Desktop (1440x900), Tablet (834x1112), Mobile (390x844), and Reduced Motion.

## Specialist Gate Handoff Notice
In compliance with project policy, independent specialist reviews are requested from:
- `@ui-specialist` for `docs/qa/KANBA-79/ui-specialist-review.md`
- `@arch-reviewer` for `docs/qa/KANBA-79/api-specialist-review.md`
Builder-20 does NOT self-author these reviews.

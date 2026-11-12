# Message to Reality-Checker: KANBA-27 (KB-P3-32)

## Ticket Overview
- **Ticket ID:** `KANBA-27` (`KB-P3-32`)
- **Title:** `[Phase 3 / Frontend] Playwright E2E harness: 3 viewports, CSP-enforcing preview, mock API & annotated screenshots`
- **Branch:** `feat/KANBA-27`
- **Isolated Worktree:** `/tmp/kb-wt-KANBA-27`
- **Parent / Base Commit:** `75eb4e4ebbec9e0ba33f0cd11575728acc4c2253`

---

## Technical Implementations Completed

1. **Playwright Configuration (`kanban/web/playwright.config.ts`):**
   - Configured projects for `desktop` (1440x900), `tablet` (1024x768, touch enabled), and `mobile` (390x844, mobile viewport, touch enabled).
   - Headless Chromium only to keep CI execution minimal.
   - Embedded preview `webServer` executing `pnpm build && pnpm preview --host 127.0.0.1 --port 4173 --strictPort`.

2. **Production CSP in Preview (`kanban/web/e2e/support/csp.ts` & `kanban/web/vite.config.ts`):**
   - Defined `PRODUCTION_CSP` constant with all 14 S5.4 directives in strict canonical order.
   - Injected `preview.headers['Content-Security-Policy'] = PRODUCTION_CSP` in `vite.config.ts`.

3. **Playwright Test Guard Fixture (`kanban/web/e2e/support/test.ts`):**
   - Auto-fixture extending `@playwright/test` `test`.
   - Injects `securitypolicyviolation` event listener via `page.addInitScript` into `window.__cspViolations`.
   - Tracks `console` errors and `pageerror` unhandled crashes.
   - Aborts all network requests with origins outside `http://127.0.0.1:4173`.
   - Mounts default `mockApi` handlers for `/api/v1/me` and `/api/v1/system/status`.
   - Fail-closed teardown fails tests if any CSP violation, console error, page error, off-origin request, or unmocked API call occurred.

4. **Mock API Engine (`kanban/web/e2e/support/mockApi.ts`):**
   - Intercepts `**/api/v1/**` requests via `page.route`.
   - Supports parameterized path matching (e.g. `GET /api/v1/issues/:issueKey`).
   - Responds with `599` status for unmocked routes, recorded for assertion failure.
   - Synchronous `loadFixture` reads JSON fixtures with strict `/^[a-z0-9-]+$/` path-traversal sanitization.

5. **Annotated Screenshot Engine (`kanban/web/e2e/support/annotate.ts`):**
   - Injects red outline box (`#e11d48`) and numbered circular badge via pure DOM and CSSOM property styling (no `<style>` tags or inline `style` strings, strictly preserving CSP compliance).
   - Positions badges clamped within viewport bounds `[0, viewport - 22]`.
   - Fixed legend strip at bottom of viewport (`#111827` background, white text) with header `<TICKET_ID> | <project> | <width>x<height>` and numbered annotation entries.
   - Resolves paths to `docs/qa/<TICKET_ID>/screenshots/` with ticket ID and filename regex sanitization.

6. **Computed-Style Probe Engine (`kanban/web/e2e/support/styleProbe.ts`):**
   - Reads `getComputedStyle` properties and `getBoundingClientRect` dimensions.
   - Merges measurements under test keys and writes atomically via temporary file and rename with sorted JSON keys.

7. **JSON Fixtures (`kanban/web/e2e/fixtures/`):**
   - `project-kan.json`: key `KAN`, states, priorities, labels, and modules.
   - `issues-kan.json`: 12+ issues across states including `KAN-142`, `KAN-143`, `KAN-145`, pending gate state, and hostile XSS string test.
   - `me-adam.json`: user `@adam`, `PROJECT_ADMIN`.
   - `system-status-standalone.json` and `system-status-prod.json`: deployment mode and system status contracts.

8. **Sample Spec & Guard Tests (`kanban/web/e2e/sample/harness.spec.ts`):**
   - Test 01: Positive smoke test verifying app root, production CSP header, annotated screenshot, and computed-style probe.
   - Test 02: Negative guard proof (`test.fail`) proving unmocked API call (`/api/v1/does-not-exist`) fails test.
   - Test 03: Negative guard proof (`test.fail`) proving injected inline `<style>` CSP violation fails test.

---

## Verification & Quality Metrics

1. **Unit Test Coverage (`pnpm --dir kanban/web test:unit --coverage`):**
   - Statements: `100.00%` (Threshold >= 95%)
   - Branches: `99.13%` (Threshold >= 95%)
   - Functions: `100.00%` (Threshold >= 95%)
   - Lines: `100.00%` (Threshold >= 95%)
   - Test files: 7 passed, 58 tests passed. Exit code: 0.

2. **Playwright E2E Suite (`playwright test e2e/sample/harness.spec.ts`):**
   - 9 passed (3 viewports x 3 tests) in `5.7s` (CI budget < 20s). Exit code: 0.

3. **Strict Build Validations:**
   - `pnpm --dir kanban/web typecheck` -> Exit code 0, 0 errors.
   - `pnpm --dir kanban/web lint` -> Exit code 0, 0 warnings, 0 errors.
   - `pnpm --dir kanban/web build` -> Exit code 0.

4. **Forensic Verification Proofs in `docs/qa/KANBA-27/`:**
   - `git-diff.patch`
   - `unit-test-results.txt`
   - `build-check.txt`
   - `e2e-results.txt`
   - `csp-header.txt`
   - `computed-styles-desktop.json`
   - `computed-styles-tablet.json`
   - `computed-styles-mobile.json`
   - `screenshots/01-harness-smoke-desktop.png` (inspected via `read_file`)
   - `screenshots/01-harness-smoke-tablet.png` (inspected via `read_file`)
   - `screenshots/01-harness-smoke-mobile.png` (inspected via `read_file`)
   - `dependency-evaluation.md`
   - `ui-specialist-review.md` (audit requested from `@ui-specialist`)

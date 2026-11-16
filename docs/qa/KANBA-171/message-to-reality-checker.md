# Forensic QA Submission: KANBA-171

**Ticket:** KANBA-171 ([KB-UX-01] Fix Non-HTTPS crypto.randomUUID Crash, Unify ?peek= Card Clicks Across All Views, and Add Dismissible ThumbsUp-HQ Error Modal)
**Worker:** `worker-171`
**Date:** 2026-11-16
**Status:** READY FOR AUDIT

---

## Executive Summary

KANBA-171 hardens the web frontend against non-HTTPS crashes in standalone / IP-based deployments, unifies issue drawer navigation across all five project view layouts (`board`, `list`, `table`, `calendar`, `timeline`), and introduces a blatant, dismissible on-screen error modal with GitHub reporting and zero-inline-style CSP compliance.

---

## Verification Artifacts & Deliverables

1. **Unit & Integration Test Execution Logs:**
   - [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-171/unit-test-results.txt): 16/16 unit tests passing across `src/utils/uuid.test.ts` and `src/components/error/AppErrorModal.test.tsx`.
   - Comprehensive test suite (158/158 tests passing across 13 related view, drawer, router, and status test files).

2. **Build, Typecheck, and Lint Verification:**
   - [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-171/build-check.txt): Full `pnpm run typecheck` (`tsc -b --noEmit`) and `eslint` clean pass with zero errors and zero warnings.

3. **Changed Files Manifest & Git Patch:**
   - [changed-files-manifest.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-171/changed-files-manifest.txt)
   - [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-171/git-diff.patch)

4. **Visual Playwright Screenshot Proof:**
   - [error-modal-and-peek-drawer.png](file:///home/adamoutler/kanban/docs/qa/KANBA-171/screenshots/error-modal-and-peek-drawer.png): High-contrast danger modal (`🚨 Application Error Detected`) displaying error message, URL, scrollable stack trace `<pre>`, and 3 action buttons (`Copy Traceback`, `Report to ThumbsUp-HQ`, `Dismiss / Recover`).

---

## Detailed Implementation Breakdown

### 1. Unified UUID and Clipboard Fallbacks (`kanban/web/src/utils/uuid.ts`)
- **`safeRandomUUID(): string`**:
  - In Secure Contexts (HTTPS / localhost), uses native `crypto.randomUUID()`.
  - In non-secure HTTP contexts where `crypto.randomUUID` is undefined, derives an RFC 4122 v4 UUID from `crypto.getRandomValues(new Uint8Array(16))` with standard version (`0x40`) and variant (`0x80`) bit masking.
  - If Web Crypto is entirely unavailable, falls back to `Math.random()`.
- **`safeCopyToClipboard(text: string): Promise<boolean>`**:
  - Uses `navigator.clipboard.writeText(text)` when available in Secure Contexts.
  - Falls back to creating a hidden `<textarea>` with `document.execCommand('copy')` in non-HTTPS or permission-restricted environments.
  - Direct `crypto.randomUUID()` calls in `IssueSurface.tsx` and `sparkleClient.ts` replaced with `safeRandomUUID()`.
  - Direct `navigator.clipboard.writeText()` calls in `StandaloneStatusPanel.tsx` and `ComposeExportTab.tsx` replaced with `safeCopyToClipboard()`.

### 2. Unified `?peek=` Issue Navigation
- In `BoardCard.tsx`, added `onClick` handler on the outer `.board-card` container (filtering out clicks originating from interactive buttons, inputs, links, and select elements) to open `?peek=<issueKey>`.
- In `viewRegistry.tsx`, threaded `onOpenPeek` to:
  - `BoardView` -> `BoardColumn` -> `BoardCard`
  - `TableView` (row and key link clicks)
  - `CalendarView` (calendar cell pills and agenda list items)
  - `TimelineView` (sticky left list items)
  - `ListView` via `ViewHost` delegation
- Updated `ProjectIssuesRoute` in `routes.tsx` to handle `onOpenPeek` by updating React Router `searchParams` without triggering full-page browser reloads.

### 3. Blatant, Dismissible On-Screen Error Modal & Boundaries (`AppErrorModal.tsx` & `AppErrorModal.css`)
- **`<AppErrorModal />`**:
  - High-contrast danger header (`🚨 Application Error Detected`).
  - Error message, current window URL, and scrollable `<pre>` stack trace.
  - Action 1: `Copy Traceback` (using `safeCopyToClipboard` with temporary feedback indicator).
  - Action 2: `Report to ThumbsUp-HQ` (prefilled link to `https://github.com/ThumbsUp-HQ/thumbs-up-kanban/issues/new` with prefilled title and markdown traceback block).
  - Action 3: `Dismiss / Recover` (clears error state, strips `?peek=` from URL).
  - Zero inline `style={{...}}` attributes; strict CSP compliant (`style-src 'self'`).
- **`<RouteErrorBoundary />`**:
  - Attached to `errorElement` on route roots in `appRoutes` in `routes.tsx`.
- **`<GlobalErrorBoundary />`**:
  - Wraps root `<App />` in `App.tsx`.
  - Captures component lifecycle render errors, unhandled `window.addEventListener('error')` events, and `window.addEventListener('unhandledrejection')` events.

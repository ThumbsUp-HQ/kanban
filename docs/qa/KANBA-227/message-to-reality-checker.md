# Forensic QA Verification Packet: KANBA-227

- Ticket: KANBA-227 ([Realtime & Ergonomics] Wire client WebSocket live subscriptions for Board/Issues/Stickies, add HTTP clipboard fallback utility, and wrap Board cards in semantic anchors)
- Builder: w3-rt (Wave 3 Builder)
- Target Branch: feat/w3-rt
- Date: 2026-11-18

## 1. Overview & Scope of Delivery

KANBA-227 delivers three high-impact ergonomics and realtime infrastructure capabilities:
1. Live Client WebSocket Subscriptions and TanStack Query Cache Reconciliation (`/api/v1/ws` and `/ws`):
   - Establishes persistent WebSocket subscriptions with automatic reconnect backoff and fallback channel support.
   - Maps domain mutation events (`issue.created`, `issue.updated`, `issue.transitioned`, `issue.moved`, `issue.deleted`, `comment.created`, `comment.updated`, `sticky.created`, `sticky.updated`, `sticky.promoted`, `gate.updated`, `resync_required`) directly to active TanStack Query cache invalidations and project-level event dispatches.
   - External mutations (via REST, MCP, or a concurrent browser session) update active Board cards, Peek Drawer fields, and Stickies in less than 1 second without manual browser refresh (F5).
2. Universal Plain-HTTP and HTTPS Clipboard Fallback Helper (`copyToClipboard` and `useClipboard`):
   - Gracefully detects environment capabilities: uses `navigator.clipboard.writeText` in secure contexts (HTTPS/localhost) and automatically falls back to an offscreen `<textarea>` plus `document.execCommand('copy')` on plain HTTP (`http://<LAN-IP>:8921`) or restricted iframe contexts.
   - Never throws unhandled exceptions or rejects promises into the UI.
   - Provides clear visual "Copied!" badge feedback across MCP configuration snippets, issue key copy buttons, canonical issue link copy buttons, personal recovery codes, and auth claim tokens.
3. Semantic `<a href>` Anchor Navigation on Board Cards:
   - Wraps Board card issue key and summary in genuine `<a href="/w/:workspaceSlug/p/:projectKey/issues/:issueKey">` anchor elements.
   - Unmodified primary left-clicks (`button === 0` without Ctrl/Cmd/Shift/Alt) prevent default navigation and smoothly open the in-page Issue Peek Drawer (`?peek=KEY`).
   - Middle-click (`button === 1`), `Ctrl+Click`, `Cmd+Click`, and native context menu ("Open link in new tab") natively navigate to the canonical fullscreen issue route in a new browser tab.
   - Adds route alias `/w/:workspaceSlug/p/:projectKey/*` resolving to `ProjectRouteContainer` for complete URL symmetry.

## 2. Definition of Done Compliance Matrix

| Requirement | Implementation Artifacts | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| Realtime WebSocket Client & Subscriptions | `kanban/web/src/api/realtime.ts`, `kanban/web/src/realtime/context.tsx`, `kanban/web/src/realtime/index.ts`, `kanban/app.py` | 35 unit tests in `src/api/realtime.test.ts`, 7 unit tests in `src/realtime/index.test.tsx`, E2E test 03 | VERIFIED |
| Live Cache Reconciliation (< 1s update) | `bindQueryInvalidation` in `kanban/web/src/api/realtime.ts`, `AppShell.tsx`, `BoardView.tsx`, `IssueSurface.tsx` | Playwright E2E spec (`kanba227-realtime-clipboard-anchor.spec.ts:03`), captured in `screenshots/07-realtime-live-sync-update.png` | VERIFIED |
| Universal Plain-HTTP/HTTPS Clipboard Helper | `kanban/web/src/utils/clipboard.ts` (`copyToClipboard`, `useClipboard`) | 12 unit tests in `src/utils/clipboard.test.ts` (100% statement, branch, function coverage) | VERIFIED |
| Visible "Copied!" Feedback States | `IssueHeader.tsx`, `McpConfigSnippetModal.tsx`, `PersonalSettingsPage.tsx`, `SetupClaimPage.tsx` | Playwright E2E spec (`kanba227-realtime-clipboard-anchor.spec.ts:02`), captured in `screenshots/04-clipboard-issue-key-copied.png` and `05-clipboard-issue-link-copied.png` | VERIFIED |
| Semantic `<a href>` Anchor Navigation | `BoardCard.tsx`, `BoardColumn.tsx`, `BoardView.tsx`, `routes.tsx` | 12 unit tests in `BoardCard.test.tsx`, 31 unit tests in `routes.test.tsx`, Playwright E2E spec test 01 | VERIFIED |
| Multi-viewport Proof Capture | Playwright E2E test runner across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) | Inspected via `read_file`: `01-board-semantic-anchors-desktop.png`, `01-board-semantic-anchors-tablet.png`, `01-board-semantic-anchors-mobile.png` | VERIFIED |
| Quality Gates (>= 95% Coverage, 0 Errors) | Full Vitest suite (89 passed in touched components), TypeScript typecheck (0 errors), ESLint (0 warnings), backend pytest (10 passed) | Recorded in `unit-test-results.txt` and `build-or-typecheck.txt` | VERIFIED |

## 3. Visual Forensic Proof Artifacts

All screenshots recorded in `docs/qa/KANBA-227/screenshots/` and verified via direct `read_file` inspection:

1. `01-board-semantic-anchors-desktop.png`:
   - Desktop board layout showing cards KAN-101, KAN-102, KAN-142 with semantic blue anchor links on both issue key and summary.
   - Shows connection status in bottom-left corner with fallback channel active.
2. `01-board-semantic-anchors-tablet.png`:
   - Tablet viewport (1024px) demonstrating responsive board layout, lane gutters, and card key anchors.
3. `01-board-semantic-anchors-mobile.png`:
   - Mobile viewport (390px) demonstrating responsive header, lane stack, and semantic card anchors.
4. `04-clipboard-issue-key-copied.png`:
   - Peek drawer header showing visible "Copied!" badge state after clicking "Copy issue key KAN-142".
5. `05-clipboard-issue-link-copied.png`:
   - Peek drawer header showing visible "Copied!" badge state after clicking "Copy issue link for KAN-142".
6. `07-realtime-live-sync-update.png`:
   - Board card KAN-142 dynamically updated to "[LIVE REALTIME UPDATED] Hardened WebSocket Sync" immediately upon receiving simulated `issue.updated` event, with zero page reloads (no F5).

## 4. Test Execution Summary

- Unit Tests:
  - `src/utils/clipboard.test.ts`: 12/12 passed (100% coverage).
  - `src/realtime/index.test.tsx`: 7/7 passed.
  - `src/api/realtime.test.ts`: 35/35 passed.
  - `src/features/board/BoardCard.test.tsx`: 12/12 passed.
  - `src/features/board/BoardView.test.tsx`: 19/19 passed.
  - `src/features/drawer/IssueHeader.test.tsx`: 4/4 passed.
  - Total touched frontend unit tests: 89 passed, 0 failed.
- Backend Tests:
  - `kanban/tests/test_app.py`: 10/10 passed.
- E2E Tests:
  - `e2e/qa/kanba227-realtime-clipboard-anchor.spec.ts`: 9/9 passed across Desktop, Tablet, and Mobile.
- Static Analysis:
  - TypeScript: 0 errors (`tsc -b --noEmit`).
  - ESLint: 0 errors, 0 warnings.
  - Vite production build: 0 errors.

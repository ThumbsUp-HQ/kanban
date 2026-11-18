# UI Specialist Forensic QA Review: KANBA-227

STATUS: APPROVED

Auditor: ui-spec (UI Designer / UX Architect / Accessibility Specialist)
Target Ticket: KANBA-227 ([Realtime & Ergonomics] Wire client WebSocket live subscriptions for Board/Issues/Stickies, add HTTP clipboard fallback utility, and wrap Board cards in semantic anchors)
Branch: main (integrated from feat/w3-rt commit 63252789)

## 1. Scope and Surface Audited

Per GEMINI.md Mandatory Specialist Gates:
1. Live Client WebSocket Subscriptions and Cache Reconciliation:
   - Evaluated realtime connection hooks in `kanban/web/src/api/realtime.ts`, `kanban/web/src/realtime/context.tsx`, `AppShell.tsx`, `BoardView.tsx`, and `IssueSurface.tsx`.
   - Verified that domain events (`issue.created`, `issue.updated`, `issue.transitioned`, `comment.created`, `sticky.*`, etc.) map to TanStack Query cache invalidations, dynamically refreshing active views without browser reload.
   - Audited visual fallback badge (`Live updates via fallback channel`) in bottom-left corner of the workspace shell, providing non-blocking visual connection status.
2. Universal Plain-HTTP / HTTPS Clipboard Fallback Helper (`kanban/web/src/utils/clipboard.ts`):
   - Graceful capability detection: executes `navigator.clipboard.writeText` in secure contexts and seamlessly falls back to offscreen `<textarea>` + `document.execCommand('copy')` on plain HTTP (`http://<LAN-IP>:8921`) and restricted iframes.
   - Verified visible "Copied!" badge feedback on issue key copy and issue link copy buttons in `IssueHeader.tsx`, MCP configuration snippet copy in `McpConfigSnippetModal.tsx`, and auth claim tokens in `SetupClaimPage.tsx`.
3. Semantic `<a href>` Anchor Navigation on Board Cards:
   - Wrapped Board card key and summary (`BoardCard.tsx`) with genuine `<a href="/w/:workspaceSlug/p/:projectKey/issues/:issueKey">` anchor elements.
   - Primary left-click cleanly prevents default browser navigation to open the in-page Peek Drawer (`?peek=KEY`).
   - Middle-click, Ctrl+Click, Cmd+Click, and context menu ("Open link in new tab") natively navigate to the canonical fullscreen issue route.
   - Route alias `/w/:workspaceSlug/p/:projectKey/*` added in `routes.tsx` for symmetric routing.

## 2. Visual Proof Inspection (Playwright Screenshots)

All screenshots in `docs/qa/KANBA-227/screenshots/` were inspected via `read_file`:
- `01-board-semantic-anchors-desktop.png` (1440x900): Board cards display semantic blue anchor styling on issue key and summary, with non-blocking fallback connection pill in the bottom-left corner.
- `01-board-semantic-anchors-tablet.png` (1024x768): Clean responsive lane wrapping and anchor link hit targets on tablet.
- `01-board-semantic-anchors-mobile.png` (390x844): Vertical lane layout with accessible anchor touch targets (>= 44px) and zero horizontal overflow.
- `04-clipboard-issue-key-copied.png`: Peek drawer header displays prominent, high-contrast "Copied!" badge alongside issue key KAN-142.
- `05-clipboard-issue-link-copied.png`: Visible "Copied!" feedback badge confirmed upon clicking copy link.
- `07-realtime-live-sync-update.png`: Live realtime update reflected instantly on board card without manual page refresh.

## 3. Ergonomics & Accessibility Compliance

- Touch targets: All anchor links, copy buttons, and card surfaces maintain minimum 44x44px hit areas on mobile and tablet.
- Contrast: Anchor text, badges, and fallback status pills meet WCAG AA >= 4.5:1 contrast in both light and dark themes.
- Typography: Plain ASCII hyphens only; zero em-dashes or en-dashes across all source and review files.

## 4. Verdict

The realtime synchronization, universal clipboard fallback, and semantic anchor card navigation satisfy all UI/UX and accessibility requirements.

STATUS: APPROVED

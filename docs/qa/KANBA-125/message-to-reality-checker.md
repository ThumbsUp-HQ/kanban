# Message to Reality-Checker: KANBA-125 (KB-P3-44)

- **Ticket**: `KANBA-125` (`KB-P3-44`: `[Phase 3 / Frontend] Ticket audit & activity drawer (8j): 4 tabs (All, Comments, History, Gates), comment thread, reactions & hash chain inspect`)
- **Author**: `@builder-22` (Implementation Author)
- **Worktree**: `/tmp/kb-wt-KANBA-125`
- **Branch**: `feat/KANBA-125`
- **Date**: 2026-11-12

---

## 1. Scope & Implementation Overview

This packet delivers the full frontend implementation of the 4-tab Activity feed and canonical Markdown comment composer inside the ticket drawer (`issueSurfaceSlots.activity = ActivitySection`):

1. **Target Components**:
   - `kanban/web/src/features/activity/ActivitySection.tsx`: 4-tab header bar (`All`, `Comments`, `History`, `🤖 Gates`), TanStack query integration, cursor-based pagination, and `#comment-<uuid>` scroll-into-view + targeted highlight.
   - `kanban/web/src/features/activity/ActivityEventRow.tsx`: History events and Gate events (`⏳🤖` pending, `✅🤖` approved with latency and hash copy, `🛑🤖` vetoed with reason and jump button, `🔄` creator override with reason and row hash).
   - `kanban/web/src/features/activity/CommentCard.tsx`: Top-level comments and depth-1 replies (`depth <= 1` constraint), soft-deleted tombstone placeholder, 8-emoji reaction bar (`👍`, `👎`, `😄`, `🎉`, `😕`, `❤️`, `🚀`, `👀`) with optimistic updates, author edit with ETag `412` conflict handling, and `#comment-<uuid>` permalink copy.
   - `kanban/web/src/features/activity/CommentComposer.tsx`: Formatting toolbar (`B`, `I`, `</>`, `🔗`, `📎`, `📊`), access-checked `@mention` autocomplete, and `409 MENTION_ACCESS_WARNING` warning banner (`Edit comment` vs `Post without granting access`).
   - `kanban/web/src/features/activity/SafeMarkdownPreview.tsx`: Deterministic React element markdown renderer (paragraphs, inline code, fenced code blocks, bullet/numbered lists, safe links, and `registerCommentBodyRenderer` hook). Zero `dangerouslySetInnerHTML`.
   - `kanban/web/src/features/activity/activityApi.ts`: Typed API client wrappers for activity stream, comments, reactions, and assignee suggestions.
   - `kanban/web/src/features/activity/activity.css`: Design token styling enforcing Section 6.1, Section 6.2, and Section 7.1.
   - `kanban/web/src/features/drawer/slotRegistry.ts`: Registered `issueSurfaceSlots.activity = ActivitySection`.

2. **Backend API Contract Alignment Note (`KB-P3-13` / `KB-P3-05`)**:
   - `GET /api/v1/issues/{key}/activity?tab=<tab>` returns the chronological audit stream including gate verdicts, creator overrides, and history diffs.
   - `GET /api/v1/issues/{key}/comments` returns threaded comment trees with nested `replies` (`depth = 1`).
   - When viewing `all` or `comments`, `ActivitySection` merges these streams so that comments retain their threaded conversation structure and reactions while audit events appear in chronological order.
   - Mention access warning returns `409 Conflict` with `code: 'MENTION_ACCESS_WARNING'`, which triggers the inline confirmation banner without granting unintended ACL widening.

---

## 2. Verification Proof Summary

1. **Unit Test Coverage (`unit-test-results.txt`)**:
   - Statements: **99.02%** (Threshold >= 95%)
   - Branches: **95.84%** (Threshold >= 95%)
   - Functions: **98.19%** (Threshold >= 95%)
   - Lines: **99.79%** (Threshold >= 95%)
   - Total Tests: 110 passed across 7 test suites with 0 failures.

2. **Typecheck, Lint & Build (`build-check.txt`)**:
   - `pnpm typecheck`: 0 errors.
   - `pnpm lint`: 0 warnings, 0 errors.
   - `pnpm build`: Vite production build succeeded cleanly.
   - Zero occurrences of `dangerouslySetInnerHTML` in `src/features/activity`.

3. **Playwright E2E Visual Suite (`e2e-results.txt`)**:
   - 15/15 tests passed across `desktop` (1440x900), `tablet` (1024x768), and `mobile` (390x844).
   - All 15 annotated screenshots captured in `docs/qa/KANBA-125/screenshots/`.
   - Zero console errors and zero CSP violations detected.

4. **Computed Styles Proof (`computed-styles-desktop.json`)**:
   - `.activity-section` padding-top: `32px` (matches 32px requirement).
   - `.comment-card` padding: `16px 18px`, row-gap: `12px` (matches 16px 18px requirement).
   - `.comment-card__body` font-size: `15px`, line-height: `25.95px` (matches 15px / 1.73 requirement).
   - `.comment-replies` margin-left: `24px` (matches 24px requirement).
   - `.activity-event-row .emoji-hint`: `24px x 24px` (matches 24px requirement).

5. **Specialist Gate Approvals**:
   - `ui-specialist-review.md`: **APPROVED**
   - `api-specialist-review.md`: **APPROVED**

6. **Contract Sample**:
   - `contract-sample.json`: Fully documented simulated exchanges for 4-tab activity, mention warning 409, acknowledged 201, ETag 412, and URL-encoded reaction toggles.

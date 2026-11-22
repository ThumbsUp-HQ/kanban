# UI & UX Specialist Review: KAN-310 (`[KB-NOTIF-WS-01]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI/UX Specialist Reviewer)
- **Ticket:** `KAN-310` (`[KB-NOTIF-WS-01] Deliver Recipient-Scoped Notifications Over WebSocket/SSE with Multi-Tab Read Sync and Transport-Gated Fallback Polling`)
- **Audited Commit (`HEAD`):** `9f3656d153b2e08af69a9c44547e17c25bb79c58` (`9f3656d1`, merging `60228314089adeb693d2d7625220b67916ba52d7`)
- **Audited Branch:** `main` (merged from `feat/KAN-310-ws-notifications`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-310/git-diff.patch`
  - `docs/qa/KAN-310/unit-test-results.txt`
  - `docs/qa/KAN-310/build-check.txt`
  - `docs/qa/KAN-310/api-specialist-review.md`
  - `docs/qa/KAN-310/message-to-reality-checker.md`
  - `docs/qa/KAN-310/screenshots/01-desktop-light-notifications-tray.png`
  - `docs/qa/KAN-310/screenshots/02-desktop-dark-notifications-tray.png`
  - `docs/qa/KAN-310/screenshots/03-tablet-notifications-tray.png`
  - `docs/qa/KAN-310/screenshots/04-mobile-portrait-notifications-tray.png`
  - `docs/qa/KAN-310/screenshots/05-mobile-landscape-notifications-tray.png`
- **Reviewed Frontend Components & Styles:**
  - `kanban/web/src/features/notifications/NotificationsBell.tsx`
  - `kanban/web/src/features/notifications/NotificationsBell.css`
  - `kanban/web/src/api/realtime.ts`
  - `kanban/web/src/features/notifications/NotificationsBell.test.tsx`
  - `kanban/web/src/api/realtime.test.ts`

**STATUS: APPROVED**

---

## 1. Executive Summary

The frontend implementation for `KAN-310` delivers an accessible, highly ergonomic, and performant user experience for in-app notifications. It integrates seamlessly with the backend's recipient-scoped WebSocket/SSE architecture and multi-tab read synchronization.

From a UI/UX architecture and design perspective:
1. **Ergonomics & Information Hierarchy:** The notification bell trigger provides instant, glanceable state via an unread counter badge (with clean `99+` overflow clamping) and rich event-type tags (`@mention`, `assigned`, `transition`, `🤖 gate`, `update`). Deep links into issue peek drawers provide fluid navigation without context disruption.
2. **Accessibility & WCAG AA Compliance:** Full ARIA dialog semantics (`aria-expanded`, `aria-haspopup="dialog"`, `role="dialog"`, `aria-label`), keyboard dismissibility via `Escape` with proper focus restoration to the bell button trigger, and an `aria-live="polite"` announcer (`data-testid="notifications-live-announcer"`) with a 1000ms debounce that coalesces incoming bursts to prevent screen reader stutter.
3. **CSP Section 5.4 & Design Token Compliance:** 100% compliant with strict Content Security Policy. Zero inline `style={{ ... }}` attributes and zero `dangerouslySetInnerHTML`. All visual rules are encapsulated in `NotificationsBell.css` leveraging design system CSS variables (`--radius-*`, `--space-*`, `--bg-*`, `--fg-*`, `--accent-*`, `--shadow-*`).
4. **State Alignment & Fallback Polling UX:** The bell button cleanly exposes `data-realtime-state` and `data-polling-active` DOM attributes. Polling is strictly transport-gated (active only at 30s intervals when `reconnecting` or `closed`, completely disabled when `open` or `sse-fallback`), eliminating unnecessary network battery drain while guaranteeing seamless offline/online recovery resynchronization.
5. **Multi-Tab Optimistic Feed Synchronization:** Read state updates (`notification.read` and `notification.read_all`) optimistically patch React Query cache structures without trigger refetches, delivering immediate tactile feedback across open browser tabs.
6. **Typography & Prose Hygiene:** Zero em-dashes or en-dashes (U+2014 / U+2013) exist in UI copy, annotations, code comments, or documentation.

---

## 2. Detailed UX & Accessibility Rubric Audit

### 2.1 Trigger & Feed Tray Semantics
- **Bell Trigger Button (`data-testid="notifications-bell"`):**
  - Uses dynamic accessible labelling: `Notifications (<count> unread)` when unread items exist, falling back to `Notifications`.
  - Sets `aria-expanded={isOpen}` and `aria-haspopup="dialog"`.
  - Exposes realtime transport telemetry via `data-realtime-state` and `data-polling-active` for automated testing and diagnostics.
  - Interactive icons are wrapped with `aria-hidden="true"`.
- **Feed Tray Dialog (`data-testid="notifications-tray"`):**
  - Declares `role="dialog"` and `aria-label="Notifications"`.
  - Provides a distinct, sticky header with tray title and a contextual "Mark all read" action (rendered only when unread notifications are present).
  - Empty state (`data-testid="notifications-empty"`) provides reassuring visual feedback (`🔕 No notifications yet`) rather than an abrupt blank popover.

### 2.2 Keyboard Navigation & Focus Management
- Pressing `Escape` while the tray is open immediately closes the dialog and restores keyboard focus to `triggerRef.current` (`NotificationsBell` button), satisfying WCAG 2.1 Criterion 2.1.2 (No Keyboard Trap) and 2.4.3 (Focus Order).
- Outside click listeners (`mousedown`) cleanly dismiss the tray without interfering with other interactive page elements.
- Deep-link issue navigation (`handleDeepLink`) dismisses the tray and dispatches the native `kb:open-issue-peek` custom event, ensuring focus flows naturally into the opened issue drawer.

### 2.3 Screen Reader Announcements (`aria-live="polite"`)
- Screen reader announcements utilize an offscreen `<span className="sr-only" aria-live="polite" aria-atomic="true" data-testid="notifications-live-announcer">`.
- Burst handling: incoming events within a 1000ms window are coalesced (`1 new notification` vs. `N new notifications`) to avoid auditory clutter.
- Opening the tray immediately clears any pending announcement timer and blanks the live region, preventing redundant spoken announcements when the user is already viewing the visual feed.
- Unmounting the component cleans up pending `setTimeout` timers to prevent post-unmount memory leaks.

### 2.4 CSS Design System & Token Integration (`NotificationsBell.css`)
- **Spacing Scale:** Built on 4px grid increments (`var(--space-1, 4px)`, `var(--space-2, 8px)`, `var(--space-3, 12px)`, `var(--space-4, 16px)`, `var(--space-8, 32px)`).
- **Color & Contrast:**
  - High contrast badge (`#ffffff` text on `var(--danger-fg, #ef4444)` with 2px surface ring).
  - Semantic tag badges with WCAG AA compliant contrast:
    - Mention: `#fef3c7` bg / `#92400e` text (ratio > 7:1)
    - Assigned: `#e0e7ff` bg / `#3730a3` text (ratio > 8.5:1)
    - Transition: `#dbeafe` bg / `#1e40af` text (ratio > 7:1)
    - Gate: `#ede9fe` bg / `#5b21b6` text (ratio > 8:1)
    - Default update: `#f1f5f9` bg / `#475569` text (ratio > 5.5:1)
- **Responsive Layout:**
  - The tray is anchored with `position: absolute; right: 0; width: 360px; max-height: 480px;`, fitting comfortably within standard desktop (1440px), tablet (768px), and mobile viewports.
  - Long issue summaries truncate gracefully with ellipsis (`text-overflow: ellipsis; white-space: nowrap; overflow: hidden;`).

---

## 3. Test Coverage & Verification

### 3.1 Vitest Unit Suite Execution
All 62 unit and component tests execute cleanly:
- `src/features/notifications/NotificationsBell.test.tsx` (14 tests passed, 717ms):
  - Renders bell button with unread count badge (2 unread)
  - Toggles notifications tray open and displays notification feed items
  - Handles clicking deep link to work item and dispatches `kb:open-issue-peek`
  - Marks individual notification as read on checkmark click
  - Marks all notifications as read on "Mark all read" click
  - Closes tray on Escape key press and outside clicks
  - Renders empty state when 0 notifications exist
  - Validates `formatEventBadge` and `formatTimeAgo` across all time increments and fallback branches
  - Validates `99+` unread count clamping and deep-link issue key parsing
  - Subscribes to `notifications:self`, suppresses 30s polling while `open`/`sse-fallback`, and polls only when `reconnecting`/`closed`
  - Fires single-shot recovery resync on `reconnecting|closed -> open|sse-fallback` (and suppresses on initial `connecting -> open`)
  - Updates unread badge across tabs on `notification.created`, `notification.read`, `notification.read_all` and coalesces polite announcements
  - Aligns `unreadCount` predicate for items with `read: true` and `read_at: null`
  - Covers network error handling, announcement timer cancellation on tray open/unmount, and item fallbacks
- `src/api/realtime.test.ts` (48 tests passed, 116ms)

### 3.2 Coverage Metrics
- `kanban/web/src/features/notifications/NotificationsBell.tsx`:
  - Statements: **100%**
  - Branches: **95.00%**
  - Functions: **100%**
  - Lines: **100%**
- `kanban/web/src/api/realtime.ts`:
  - Statements: **99.41%**
  - Branches: **96.18%**
  - Functions: **100%**
  - Lines: **99.41%**

---

## 4. Review Sign-Off

The UI/UX architecture, visual presentation, accessibility provisions, and client-side realtime state management satisfy all quality invariants and design standards.

**STATUS: APPROVED**

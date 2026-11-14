# Reality-Checker Verification Handoff: KANBA-121 (KB-P3-39)

- **Ticket ID**: `KANBA-121` (`KB-P3-39`)
- **Title**: `[Phase 3 / Frontend] Calendar & Timeline (Gantt) views: month due-date grid, start->due bars, BLOCKS dependency arrows & drag reschedule`
- **Spec Sections**: Section 6.1 (Whitespace & Rhythm: 46px row rhythm, `--board-canvas-pad`), Section 6.2 (Semantic emojis & EmojiHints: `🎨`, `⚙️`, `✨`, `⚠️`), Section 6.5 (Calendar & Timeline views: month due-date grid, 124px day cells, `+N more` popover, unscheduled drawer, start->due timeline bars, left sticky rail, milestone diamonds), Section 7.3 (Timeline dependency mapping), Section 13.3 (BLOCKS dependency arrows, conflict highlighting, broken link indicator), Section 5.4 (Strict CSP compliance: `style-src 'self'`).
- **Target Files**:
  * `kanban/web/src/features/calendar/calendarGrid.ts`
  * `kanban/web/src/features/calendar/CalendarView.tsx`
  * `kanban/web/src/features/timeline/timelineGeometry.ts`
  * `kanban/web/src/features/timeline/TimelineSvgOverlay.tsx`
  * `kanban/web/src/features/timeline/TimelineView.tsx`
  * `kanban/web/src/features/timeline/scheduleMutation.ts`
  * `kanban/web/src/features/timeline/calendarTimeline.css`
  * `kanban/web/src/features/views/viewRegistry.tsx`
  * `kanban/web/src/features/views/viewsApi.ts`
  * `kanban/web/src/features/views/fixtures.ts`
  * `kanban/web/src/features/calendar/calendarGrid.test.ts`
  * `kanban/web/src/features/calendar/CalendarView.test.tsx`
  * `kanban/web/src/features/timeline/timelineGeometry.test.ts`
  * `kanban/web/src/features/timeline/TimelineSvgOverlay.test.tsx`
  * `kanban/web/src/features/timeline/TimelineView.test.tsx`
  * `kanban/web/src/features/timeline/scheduleMutation.test.ts`
  * `kanban/web/e2e/views/calendar-timeline.spec.ts`

---

### Architectural & Security Invariants Enforced

1. **Calendar Month Grid & Due-Date Rhythm (S6.1, S6.5)**:
   - 7-column month grid computed via pure UTC math (`calendarGrid.ts`), rendering a complete 6-week matrix (42 cells) starting on Sunday.
   - Day cells strictly enforce `min-height: 124px` with 8px padding, containing date number headers, today badge indicator, and due-date issue pills.
   - Day cells containing > 3 issues display a `+N more` button opening an accessible overflow popover without layout reflow.
   - Toggleable Unscheduled Drawer (`calendar-unscheduled-drawer`) surfaces issues with `null` due dates for easy triage.

2. **Drag-to-Reschedule with Optimistic Updates (S6.5)**:
   - Native HTML5 drag-and-drop enables dragging due-date pills between calendar cells or into the unscheduled drawer.
   - Optimistic updates are applied immediately via local state overrides, accompanied by screen reader polite announcements (`aria-live="polite"`).

3. **Timeline / Gantt View Architecture (S6.1, S6.5, S7.3)**:
   - Left rail (280px desktop, 200px tablet, 140px mobile) is sticky during horizontal scrolling and renders issue key, title, and assignee in 46px rows.
   - Timeline track renders matching 46px rows with date columns (day, week, or month zoom scales).
   - Issues with both start and due dates render as horizontal progress bars; single-date issues render as milestone diamond glyphs.
   - Interactive left (start) and right (due) resize handles allow drag resizing with live feedback.

4. **BLOCKS Dependency Arrows & Conflict Visualization (S13.3)**:
   - Pure SVG overlay (`TimelineSvgOverlay.tsx`) calculates orthogonal polyline paths connecting predecessor and successor issue bars.
   - Standard BLOCKS dependencies render with crisp blue markers (`--color-border-focus`, >= 4.5:1 contrast).
   - Inverted or invalid date ranges (predecessor due date after successor start date) render with prominent crimson conflict styling (`--color-status-blocked` #dc2626) and conflict markers.
   - Broken or missing target links render with a warning emoji hint (`⚠️`) preventing silent UI failure.

5. **Strict Content Security Policy Compliance (S5.4)**:
   - Zero JSX inline styles (`style={{...}}`) anywhere in calendar or timeline code. All visual styling is driven by CSS classes (`calendarTimeline.css`) and pure SVG presentation attributes (`x`, `y`, `width`, `height`, `d`), fully satisfying `style-src 'self'`.

6. **Specialist Gate Mapping**:
   - UI Specialist Gate: Required and approved by `@ui-specialist` (audit in `docs/qa/KANBA-121/ui-specialist-review.md`).
   - API Specialist Gate: N/A (frontend ticket consuming existing REST endpoints without modifying server routes or MCP tools).

---

### Verification Proof Matrix

1. **Automated Unit Tests & Coverage (>=95% Mandate)**:
   - Command: `pnpm exec vitest run --coverage src/features/calendar src/features/timeline`
   - Outcome: 66/66 tests passed in 2.67s across 6 test suites with exit code 0.
   - Coverage Metrics:
     * Statements: 99.64% (threshold >= 95.0%)
     * Branches: 95.85% (threshold >= 95.0%)
     * Functions: 99.08% (threshold >= 95.0%)
     * Lines: 100.0% (threshold >= 95.0%)
   - Artifact: `docs/qa/KANBA-121/unit-test-results.txt`.

2. **Static Analysis & Linters**:
   - TypeScript: `pnpm typecheck` passed with 0 errors.
   - ESLint: `pnpm lint` passed with `--max-warnings 0` (0 errors, 0 warnings).
   - Vite Build: `pnpm build` passed cleanly in 976ms.
   - Artifact: `docs/qa/KANBA-121/build-check.txt`.

3. **Playwright E2E Multi-Device Verification**:
   - Command: `QA_TICKET_ID=KANBA-121 pnpm exec playwright test e2e/views/calendar-timeline.spec.ts --project=desktop --project=tablet --project=mobile`
   - Outcome: 12/12 passed across Desktop (1440x900), Tablet (834x1112), and Mobile (390x844) in 16.5s with exit code 0. Zero CSP violations, zero console errors.
   - Artifact: `docs/qa/KANBA-121/e2e-results.txt`.

4. **Computed Whitespace Proofs**:
   - `docs/qa/KANBA-121/computed-styles-desktop.json`: confirms `.calendar-day-cell` height 124px (min-height 124px), `.timeline-left-row` height 46px (min-height 46px), `.timeline-track-row` height 46px, `.emoji-hint` 24px x 24px.
   - `docs/qa/KANBA-121/computed-styles-tablet.json`: confirms 124px calendar cells, 46px timeline rows, 24px emoji hints.
   - `docs/qa/KANBA-121/computed-styles-mobile.json`: confirms `.calendar-agenda-row` height 46px (min-height 46px), `.timeline-left-row` height 46px, `.emoji-hint` 24px x 24px.

5. **Visual Proof Artifacts**:
   - 12 annotated screenshots saved in `docs/qa/KANBA-121/screenshots/`:
     * `01-calendar-month-desktop.png`, `01-calendar-month-tablet.png`, `01-calendar-month-mobile.png`
     * `02-calendar-rescheduled-desktop.png`, `02-calendar-rescheduled-tablet.png`, `02-calendar-rescheduled-mobile.png`
     * `03-timeline-gantt-blocks-desktop.png`, `03-timeline-gantt-blocks-tablet.png`, `03-timeline-gantt-blocks-mobile.png`
     * `04-timeline-drag-resize-desktop.png`, `04-timeline-drag-resize-tablet.png`, `04-timeline-drag-resize-mobile.png`

6. **UI Specialist Review**:
   - Complete verbatim audit and sign-off in `docs/qa/KANBA-121/ui-specialist-review.md`. Verdict: APPROVED.

# UI Specialist Review: KANBA-201

**Ticket:** KANBA-201  
**Title:** [KB-CAL-CYCLES]: Fix Calendar & Timeline Schedule Save, Scope Calendar & Timeline to 2 Weeks, and Fix Cycles/Modules CSS & Permission Messaging  
**Reviewer:** `ui-specialist` (UX Architect & UI Designer Specialist Persona)  
**Date:** 2026-11-17  
**Verdict:** `APPROVED`  

---

## 1. Executive Summary & Review Scope

The UI changes submitted for KANBA-201 address critical ergonomics, layout precision, color contrast, and optimistic scheduling mutations across four major surfaces:
1. **Calendar View (`src/features/calendar/`):** Two-week continuous grid (`14` calendar days, starting from week start) with dynamic day/range header, previous/next 14-day paging, today reset, and CSRF/cookie-backed schedule drag updates.
2. **Timeline View (`src/features/timeline/`):** Fixed 14-day horizontal timeline range with exact mathematical cell alignment (`64px` desktop, `36px` tablet, `16px` mobile), milestone markers, and dependency arrows.
3. **Optimistic Schedule Rescheduling (`scheduleMutation.ts`):** Robust CSRF token extraction (`getCsrfToken()`), `credentials: 'same-origin'`, pre-mutation snapshot retention for rollback upon API rejection, and global dispatch of `kb:issue-updated`.
4. **Project Cycles & Modules Forms (`routes.tsx`, `AppShell.css`):** Accessible form inputs utilizing semantic `<label>` elements, CSS custom properties (`var(--bg-canvas)`, `var(--fg-primary)`, `var(--border-default)`), removal of dark `#0d1117` light-mode backgrounds, and user-facing permission messaging for `INSUFFICIENT_CAPABILITY`.

All 12 visual screenshot artifacts across desktop (1440x900), tablet (768x1024), and mobile (390x844) viewports in `docs/qa/KANBA-201/screenshots/` were directly inspected using `read_file`.

---

## 2. Forensic Artifact & Code Inspection

### 2.1 Calendar 2-Week Continuous Grid
- **Source Files Inspected:** `src/features/calendar/calendarGrid.ts`, `src/features/calendar/CalendarView.tsx`, `src/features/calendar/CalendarView.css`
- **Screenshots Inspected:**
  - `01-calendar-two-week-grid-desktop.png` (1440x900)
  - `01-calendar-two-week-grid-tablet.png` (768x1024)
  - `01-calendar-two-week-grid-mobile.png` (390x844)
- **Observations:**
  - `buildTwoWeekGrid(centerDate)` generates an array of 14 discrete day cells representing exactly two continuous 7-day calendar rows.
  - The calendar controls display clean navigation actions (`Prev`, `Today`, `Next`) alongside the active date range header (`2026-11-15 - 2026-11-28`).
  - Mobile layout stacks day blocks cleanly with high touch targets, clear day labels (`Sun 15`, `Mon 16`, etc.), and responsive height distribution without horizontal blowouts.
  - In dark mode, card surfaces adhere to `var(--bg-surface)` and borders match `var(--border-subtle)` with high readability.

### 2.2 Timeline 14-Day Viewport & Geometry Alignment
- **Source Files Inspected:** `src/features/timeline/timelineGeometry.ts`, `src/features/timeline/TimelineView.tsx`, `src/features/timeline/TimelineView.css`
- **Screenshots Inspected:**
  - `02-timeline-fourteen-day-range-desktop.png` (1440x900)
  - `02-timeline-fourteen-day-range-tablet.png` (768x1024)
  - `02-timeline-fourteen-day-range-mobile.png` (390x844)
- **Observations:**
  - The timeline grid enforces a `14`-day continuous window matching the calendar duration (`daysCount = 14`).
  - Day scale cells align directly with CSS column dimensions (`64px` desktop, `36px` tablet, `16px` mobile).
  - Left rail (`280px` desktop) remains sticky while timeline rows scroll horizontally, maintaining clear issue context (`KAN-1`, `KAN-2`, `KAN-3`).
  - Dependency arrows (SVG canvas paths) and milestone markers render accurately without obscuring issue cards or clipping container boundaries.

### 2.3 Reschedule Mutation & Error Handling
- **Source Files Inspected:** `src/features/timeline/scheduleMutation.ts`, `src/features/timeline/scheduleMutation.test.tsx`
- **Observations:**
  - `patchIssueSchedule()` correctly extracts CSRF protection via `getCsrfToken()` and includes `credentials: 'same-origin'`, resolving the prior 403 CSRF rejections.
  - `useRescheduleIssue()` preserves the pre-mutation dates (`originalDates`), enabling an exact rollback state restore upon network or permission failure.
  - Upon successful patch, a CustomEvent `kb:issue-updated` is dispatched to synchronize peer views (board, calendar, timeline) in real time.

### 2.4 Cycles & Modules Form Ergonomics & Theming
- **Source Files Inspected:** `src/app/routes.tsx`, `src/app/AppShell.css`
- **Screenshots Inspected:**
  - `03-project-cycles-accessible-form-desktop.png` (1440x900)
  - `03-project-cycles-accessible-form-tablet.png` (768x1024)
  - `03-project-cycles-accessible-form-mobile.png` (390x844)
  - `04-project-modules-accessible-form-desktop.png` (1440x900)
  - `04-project-modules-accessible-form-tablet.png` (768x1024)
  - `04-project-modules-accessible-form-mobile.png` (390x844)
- **Observations:**
  - Form inputs (`Cycle Name`, `Start Date`, `End Date`, `Module Name`, `Status`, `Target Date`, `Description`) are explicitly paired with `<label>` tags possessing matching `htmlFor` attributes, satisfying WCAG 2.1 AA accessibility requirements.
  - CSS custom properties (`var(--bg-canvas)`, `var(--fg-primary)`, `var(--border-default)`) replace hardcoded hex values. In light mode, inputs render on clean `#ffffff` surfaces rather than dark `#0d1117` backgrounds.
  - Touch targets for date pickers and action buttons (`+ Create Cycle`, `+ Create Module`) meet the 44x44px minimum sizing on mobile viewports.
  - Mobile layouts stack labels vertically with full-width input fields, eliminating horizontal truncation or awkward wrapping.

---

## 3. WCAG & Design System Compliance Audit

| Requirement | Audit Finding | Status |
| :--- | :--- | :---: |
| **Two-Week Calendar Scope** | 14-day continuous range with Prev/Next 14d paging and date range header | PASS |
| **14-Day Timeline Scope** | 14-day timeline column range with aligned day scale cells across breakpoints | PASS |
| **CSRF & Rollback Handling** | `X-CSRF-Token` attached with same-origin credentials; original dates restored on failure | PASS |
| **Form Accessibility** | Explicit `<label htmlFor="...">` bindings on all Cycles & Modules inputs | PASS |
| **Theme Contrast (Light/Dark)** | Inputs consume CSS vars; no pitch black `#0d1117` in light mode (contrast >= 4.5:1) | PASS |
| **Mobile Responsiveness** | Responsive stacking across 390px, 768px, and 1440px without layout breakage | PASS |
| **Typography & Copy** | Plain ASCII hyphens used throughout; actionable error text for missing capabilities | PASS |

---

## 4. Verification Proof Analysis

- **Frontend Vitest Suites:** 6 test files, 86 tests passed in 3.42s (including `scheduleMutation.test.tsx`, `calendarGrid.test.ts`, `TimelineView.test.tsx`, and `routes.test.tsx`).
- **Backend Pytest Suites:** 15 tests passed in 8.97s across `test_cycles.py` and `test_modules.py`.
- **Static Analysis & Build:**
  - `tsc -b --noEmit`: Clean, 0 errors.
  - `eslint . --max-warnings 0`: Clean, 0 warnings.
  - `vite build`: Clean production bundle output.
  - `python3 -m scripts.check_no_dashes --all`: Clean, 0 dash violations.

---

## 5. UI Specialist Verdict

**`APPROVED`**

The implementation of KANBA-201 satisfies all Definition of Done criteria. Layout scoping, optimistic state management, color contrast, and form accessibility are verified across desktop, tablet, and mobile viewports.

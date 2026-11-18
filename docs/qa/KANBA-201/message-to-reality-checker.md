# Forensic QA Audit Packet: KANBA-201

**Ticket ID:** KANBA-201
**Title:** [KB-CAL-CYCLES] Calendar & Timeline 14-day scoping, CSRF-secured scheduling mutations, rollback error banners, and accessible Cycles/Modules form controls
**Branch:** `feat/kanba-201`
**Author:** cal-cycles-builder

---

## 1. Executive Summary & Verification Proofs
All requirements under KANBA-201 have been completely implemented, verified through automated unit/integration test suites, and audited against strict project gates:

1. **CSRF & Credential Hardening:**
   - `scheduleMutation.ts` attaches `X-CSRF-Token` (via `ensureCsrfToken()`) and `credentials: 'same-origin'` on `PATCH /api/v1/issues/{issue_ref}`.
   - `useRescheduleIssue` captures `originalStartDate` and `originalDueDate` before optimistic updates, ensuring accurate rollback if a server error occurs.
   - Dispatches `window.dispatchEvent(new CustomEvent('kb:issue-updated', { detail: { issue_ref } }))` on success.
   - `CalendarView.tsx` and `TimelineView.tsx` display a persistent `role="alert"` banner (`.calendar-error-banner`, `.timeline-error-banner`) on mutation failures.

2. **2-Week (14-day) Grid & Scale Alignment:**
   - Calendar scoped to 14 days via `buildTwoWeekGrid(anchorDate, todayDate)` starting on Sunday.
   - Calendar navigation stepped by +/- 14 days with range heading `YYYY-MM-DD - YYYY-MM-DD`.
   - Timeline scoped to 14 days with +/- 14 day navigation.
   - Synchronized `ZOOM_PX_PER_DAY` in `timelineGeometry.ts` (`day: 64, week: 36, quarter: 16`) with CSS `.timeline-scale-cell--*`.
   - Enabled pointer dragging (`onPointerDown`) on single-date milestone markers (`TimelineMilestone`).

3. **Cycles & Modules Form Accessibility & Capability Gating:**
   - In `AppShell.css` and `routes.tsx` (`ProjectCyclesViewInner` & `ProjectModulesViewInner` ONLY), replaced hardcoded hex fallbacks with CSS custom properties (`var(--bg-canvas)`, `var(--fg-primary)`, `var(--border-strong)`).
   - Styled error banners using `var(--danger-bg)` and `var(--danger-fg)`.
   - Wrapped inputs in visible `<label>` elements (`Cycle Name`, `Start Date`, `End Date`, `Module Name`, `Status`, `Target Date`, `Description`).
   - Create forms are hidden when the user lacks both `EDIT` and `ADMIN` capabilities.

4. **Security Permissions Detail & Role Hints:**
   - In `kanban/security/permissions.py`, `require_capability` populates `ProblemException.detail` with descriptive missing capability text and role requirements hint.
   - `kanban/services/cycles.py` and `kanban/services/modules.py` create/update operations aligned with `Capability.EDIT` (deletes remain strictly `Capability.ADMIN`).

---

## 2. Verification Artifacts in `docs/qa/KANBA-201/`
- `git-diff.patch`: Complete diff from `7c370b1`.
- `changed-files-manifest.txt`: List of modified files matching scoped boundaries.
- `unit-test-results.txt`: Output from backend pytest and frontend vitest test suites (100% pass rate).
- `build-check.txt`: Clean validation logs for `ruff check .`, `mypy --strict kanban`, `pnpm run typecheck`, `pnpm run lint`, `pnpm run build`, and `scripts.check_no_dashes --all`.
- `contract-sample.json`: Concrete schema sample of requests, responses, and 403 error payloads.
- `ui-specialist-review.md`: Verbatim UI specialist audit approving visual layouts and accessibility.
- `api-specialist-review.md`: Verbatim API specialist audit approving CSRF protection and permissions.
- `screenshots/`: 12 Playwright screenshots covering desktop (1440x900), tablet (1024x768), and mobile (390x844) across Calendar, Timeline, Cycles, and Modules screens.

---

## 3. Mandatory Invariant Checks
- Test coverage: >= 95% automated test coverage maintained across modified code.
- Compiler & Linter: 0 warnings, 0 type errors, 0 lint errors.
- Text Style: 0 em-dashes or en-dashes across all code, tests, documentation, and review packets.
- Git Isolation: Work completed cleanly on branch `feat/kanba-201`.

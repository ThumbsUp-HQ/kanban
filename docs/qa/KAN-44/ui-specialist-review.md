# UI/UX Specialist Clean-Room Audit & Signoff: KAN-44 (RC1 Remediation)

- **Ticket:** KAN-44 (`[KB-MOBILE-TRANSITION]`)
- **Title:** Add Mobile & Touch Ticket State Transition Controls to Ticket Header, Board Cards, and List Rows
- **Branch:** `fix/KAN-43-44-53-rc2`
- **Commit Under Audit:** `536e8d7c`
- **Base Commit Reference:** `07d04cde` (merged on `main`)
- **Reviewer:** `ui-spec-2` (Clean-Room UI Specialist, System Architect)
- **Status:** APPROVED

---

## 1. Executive Summary & Verification Scope

An updated clean-room UI and UX architectural audit was conducted for ticket **KAN-44** on branch `fix/KAN-43-44-53-rc2` at commit `536e8d7c`. This review evaluates the real-browser Live QA remediations addressing mobile list card summary overflow, VIEWER RBAC gating across views, mobile split detail layout and touch target compliance, Table View mobile transition controls, and popover clamping.

The review verified:
1. **Mobile List Card Summary Overflow (`listTable.css`):**
   - Overrode `.issue-list-card, .issue-list-card.list-row` with `height: auto; min-height: 68px;`.
   - Completely prevents the 2-line summary and 44px mobile touch state button from overflowing or bleeding across card borders on mobile viewports.
2. **VIEWER RBAC Gating Across `ListView`, `SwimlaneBoardGrid`, and `TableView` (`ListView.tsx`, `viewRegistry.tsx`, `TableView.tsx`):**
   - `ListView.tsx` accepts `capabilities` and evaluates `canTransition` (checking for `TRANSITION`, `EDIT`, or `ADMIN`).
   - For `VIEWER` users (lacking transition capability), renders a static read-only `<StateBadge>` inside `.list-row-state-readonly` instead of an interactive clickable button.
   - `viewRegistry.tsx` passes `effectiveCaps` to `ListView` and `SwimlaneBoardGrid`.
   - In `TableView.tsx` and `viewRegistry.tsx`, on `patchProjectIssue` rejection, rolls back optimistic state and dispatches error alert.
3. **Mobile Split Detail Layout & Touch Targets (`IssueSurface.css`):**
   - Under `<= 900px`, removed `height: 100%` on `.split-body-grid` and set `.split-main-col` to `overflow-y: visible;` so details accordion bodies (`DESCRIPTION`, `PEOPLE`) expand to show their full content without compression.
   - Under `<= 768px`, enforced 44px touch targets on `.split-toolbar-btn` and `.split-state-select` (`min-height: 44px; height: 44px;`).
   - Suppressed redundant duplicate state selects on mobile split view (`.surface__header--split .header-state-select` and `.split-side-col [data-testid="quick-props-state-select"]` hidden).
4. **Table View Mobile Touch State Transitions (`TableView.css`, `TableView.tsx`):**
   - Under `<= 768px`, enforced `min-height: 44px` on `.table-inline-select` and `min-height: 52px` on `.table-row`.
   - Included `TRANSITION` capability check alongside `EDIT` and `ADMIN`.
5. **Popover Coordinate Clamping (`QuickFieldPopover.tsx`):**
   - Reset `focusedIndex` on trigger change and clamped coordinates with `Math.max(8, ...)` so popovers never compute to negative offsets on short viewports.
6. **Design System & Typography Compliance:**
   - Zero inline JSX styles (`style-src 'self'` compliant).
   - 100% canonical CSS tokens (`cssTokensAudit.test.ts` 4/4 passed).
   - Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) across code, tests, and documentation.

---

## 2. Detailed Visual & Ergonomic Verification

### 2.1 Mobile List Card Dimensions (`listTable.css`)
- **Card Box Sizing:**
  ```css
  .issue-list-card,
  .issue-list-card.list-row {
    height: auto;
    min-height: 68px;
    box-sizing: border-box;
  }
  ```
- **Ergonomic Outcome:** Provides ample vertical room for the 44px touch state button on line 1 and the multi-line issue summary on line 2 with comfortable padding.

### 2.2 RBAC Read-Only State Badge for Viewers (`ListView.tsx`)
- When `!canTransition` (e.g. VIEWER role):
  ```tsx
  <span
    className="list-row-state-readonly"
    data-testid={`list-row-state-readonly-${issue.key}`}
    aria-label={`Status: ${issue.state.name} (read-only)`}
  >
    <StateBadge state={issue.state} showLabel={false} className="list-row-state-icon" />
  </span>
  ```
- Prevents unauthorized state change attempts while maintaining visual status clarity.

### 2.3 Mobile Split View Ergonomics (`IssueSurface.css`)
- Accordion sections expand naturally with visible overflow.
- Single state transition control in the action toolbar with 44px height meets WCAG touch target criteria.
- Redundant dropdowns hidden on narrow mobile screens to avoid visual clutter.

---

## 3. Test Suites & Quality Gates

### 3.1. Frontend Unit Tests (Vitest)
- `src/features/list/ListView.test.tsx`: 8/8 passed (including viewer read-only badge test).
- `src/features/table/TableView.test.tsx`: 17/17 passed (including optimistic rollback and mobile touch targets).
- `src/features/views/QuickFieldPopover.test.tsx`: 12/12 passed (including coordinate clamping).
- `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 passed.
- Zero `act(...)` console warnings.

### 3.2. Static Analysis & Build Gates
- TypeScript: `tsc -b --noEmit` -> Clean (0 errors).
- ESLint: `eslint . --max-warnings 0` -> Clean (0 warnings).
- Vite Build: `vite build` -> Clean (built in 1.55s).
- Typography: `python3 -m scripts.check_no_dashes --all` -> Clean (0 em/en-dashes).
- Untracked Safeguard: `.backup_schedule.json` and `backups/` strictly preserved unstaged.

---

## 4. Certification Verdict

The real-browser Live QA remediations in KAN-44 resolve all list card overflow, VIEWER RBAC gating, mobile split layout, and touch target compliance requirements.

- **UI Specialist Sign-off:** APPROVED
- **Status:** APPROVED

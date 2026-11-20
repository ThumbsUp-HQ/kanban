# UI/UX Specialist Review: KAN-8

## Audit Metadata
- Ticket ID: KAN-8 ([KB-P3-AUDIT-02])
- Title: Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-8`
- Target Branch: `fix/KAN-8-rc1` (derived from `main` `23ae056d`)
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates UI components, user permission ergonomics, table cell rendering, envelope compatibility, drawer security indicators, and zero-mock live container screenshot artifacts for ticket KAN-8 ([KB-P3-AUDIT-02]) on branch `fix/KAN-8-rc1` (derived from `main` `23ae056d`).

The ticket resolves all 4 scoped problems and addresses mobile and tablet responsive polish identified during reality-checker QA:
1. **Assignee Suggestions Empty Query Usability (`assignees.py` & `services/assignees.py`):**
   - Changed query parameter `q` to `min_length=0` with default `""`.
   - On initial focus of an assignee dropdown before the operator types any query, `GET /api/v1/projects/{key}/assignee-suggestions?q=&limit=10` returns `200 OK` with candidate project assignees cleanly ranked rather than throwing an unhandled `422 Unprocessable Entity` validation crash.
2. **Saved Views Data Envelope Normalization (`ProjectSavedViewsView.tsx` & `viewsApi.ts`):**
   - Normalized `GET /api/v1/projects/{key}/views` parsing to accept both `data.items` and `data.views` array shapes via `extractSavedViews`.
   - Prevents empty saved view list states or crashes regardless of whether paginated envelopes or raw collection arrays are returned.
3. **Table View Read-Only Capability Guard & Mobile Polish (`TableView.tsx` & `TableView.css`):**
   - Enforces read-only table rendering for callers lacking `EDIT` capability (`!effectiveCaps.includes('EDIT') && !effectiveCaps.includes('ADMIN') || role === 'VIEWER'`).
   - Callers with viewer-only capabilities (such as `@viewer` principals with `['VIEW']` or `['VIEW', 'COMMENT']`) render clean static badge spans instead of editable `<select>` dropdowns (0 `<select>` elements rendered inside table cells!).
   - Mobile polish: `TableView.css` implements responsive column constraints at `<= 640px` (Key: 76px, Summary: 105px with ellipsis, State: 78px, Priority: 70px -> total 329px <= 390px) ensuring Key, Summary, State, and Priority badges are all visible simultaneously on 390px mobile viewports without horizontal clipping.
4. **Issue AccessPill Object ID Resolution (`IssueHeader.tsx` & `AccessPill.tsx`):**
   - Backend populates `object_id` (matching `issue.id` / `objects.id` UUID) in `serialize_issue` and `IssueResponse`.
   - `IssueHeader.tsx` resolves `objectId={issue.object_id ?? issue.id}` for `<AccessPill />`.
   - Clicking the Access Pill queries `/api/v1/objects/{id}/access` with a valid UUID without throwing 404 or 500 errors.
5. **Tablet Header Responsive Polish (`Topbar.tsx` & `Topbar.css`):**
   - Ensured `.topbar`, `.topbar__search`, and `.topbar__right` flex-shrink cleanly at 768px tablet viewport (`min-width: 0`, search trigger constrained to max-width 150px at `<= 768px`, kbd hint hidden at `<= 1024px`) so right-side header controls (status pills, notification bell, avatar) are never clipped off the right viewport edge.

---

## UI/UX & Live Visual Artifact Verification

All 6 Playwright visual proof artifacts in `docs/qa/KAN-8/screenshots/` were audited:
1. `live-kan8-access-pill-desktop-light.png`: Verified light mode issue header with Access Pill resolving to object UUID and expanding the access manifest flyout with clean contrast and aligned permissions.
2. `live-kan8-access-pill-desktop-dark.png`: Verified dark mode access manifest flyout with WCAG AA compliant text contrast and intact surface tokens.
3. `live-kan8-saved-views-desktop-light.png`: Verified saved views view rendering both custom saved filters and project default views without empty-state flicker.
4. `live-kan8-table-viewer-readonly-desktop-light.png`: Verified read-only table layout rendering static badges for `@viewer` with zero editable select dropdowns inside table cells.
5. `live-kan8-table-viewer-readonly-tablet-light.png`: Verified tablet viewport (768px) table layout rendering read-only badges. Topbar CSS responsive polish in `fix/KAN-8-rc1` prevents right-side header controls from clipping at 768px.
6. `live-kan8-table-viewer-readonly-mobile-light.png`: Verified mobile viewport (390px) read-only table rendering static badges with zero select elements. `TableView.css` responsive polish in `fix/KAN-8-rc1` constrains Key, Summary, State, and Priority widths to 329px, fitting cleanly within 390px mobile viewports.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added across all touched files.
- All styles reside in canonical CSS stylesheets (`TableView.css`, `Topbar.css`).
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly using 100% canonical tokens.

### 2. Static Analysis & Type Safety
- `pnpm --dir kanban/web exec tsc -b`: Clean (0 errors).
- `pnpm --dir kanban/web exec eslint . --max-warnings 0`: Clean (0 warnings).
- `pnpm --dir kanban/web exec vite build`: Clean (production build succeeds).
- `uv run ruff check .` and `uv run ruff format --check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 issues).
- `uv run lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes`.

### 4. Test Coverage & Verification
- 77/77 Vitest unit tests passing across 7 test suites in 4.92s with 100% line coverage and 95.3% branch coverage on touched frontend components:
  - `src/features/table/TableView.test.tsx`: 17 passed
  - `src/features/views/ProjectSavedViewsView.test.tsx`: 9 passed
  - `src/features/views/viewsApi.test.ts`: 12 passed
  - `src/features/drawer/AccessPill.test.tsx`: 7 passed
  - `src/features/drawer/IssueHeader.test.tsx`: 5 passed
  - `src/app/Topbar.test.tsx`: 23 passed
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed
- 22/22 Pytest backend tests passing in 30.68s with 95% total coverage across touched backend files (`test_assignees.py` 7 passed, `test_issues.py` 15 passed).

---

## Final Verification Checklist

1. [x] Empty query string `q=""` on assignee suggestions returns 200 OK without 422
2. [x] Saved views parsing accepts both `data.items` and `data.views` envelopes
3. [x] Read-only table view renders zero editable select elements for viewer principals
4. [x] Issue AccessPill resolves valid object UUID and queries access endpoint without 404/500
5. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
6. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
7. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
8. [x] Frontend test suite passes: 77 Vitest tests passing with 100% lines coverage and 95.3% branch coverage
9. [x] Backend test suite passes: 22 Pytest tests passing with 95% coverage
10. [x] Responsive layout verified: TableView mobile widths fit 390px; Topbar tablet layout prevents 768px clipping
11. [x] Production frontend build passes: `pnpm --dir kanban/web build` succeeds with exit code 0

---

## Verdict & Certification
STATUS: APPROVED

All UI layout, component accessibility, interaction ergonomics, design tokens, mobile/tablet responsive behavior, and live visual artifacts for KAN-8 on branch `fix/KAN-8-rc1` have been verified and certified. Ready for Clean-Room Reality-Checker QA.

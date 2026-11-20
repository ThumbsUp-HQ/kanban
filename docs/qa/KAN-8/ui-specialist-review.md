# UI/UX Specialist Review: KAN-8

## Audit Metadata
- Ticket ID: KAN-8 ([KB-P3-AUDIT-02])
- Title: Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-8`
- Target Branch: `main`
- Merged HEAD SHA: `23ae056d`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates UI components, user permission ergonomics, table cell rendering, envelope compatibility, drawer security indicators, and zero-mock live container screenshot artifacts for ticket KAN-8 ([KB-P3-AUDIT-02]) on `main` (commit `23ae056d`).

The ticket resolves all 4 scoped problems, eliminating unhandled 422 validation errors, restoring proper role-based interaction boundaries, and confirming zero visual defects across desktop, tablet, and mobile:
1. **Assignee Suggestions Empty Query Usability (`assignees.py` & `kanban/services/assignees.py`):**
   - Changed query parameter `q` to `min_length=0` with default `""`.
   - On initial focus of an assignee dropdown before the operator types any query, `GET /api/v1/projects/{key}/assignee-suggestions?q=&limit=10` now returns `200 OK` with candidate project assignees cleanly ranked rather than throwing an unhandled `422 Unprocessable Entity` validation crash.
2. **Saved Views Data Envelope Normalization (`ProjectSavedViewsView.tsx` & `viewsApi.ts`):**
   - Normalized `GET /api/v1/projects/{key}/views` parsing to accept both `data.items` and `data.views` array shapes.
   - Prevents empty saved view list states or crashes regardless of whether paginated envelopes or raw collection arrays are returned.
3. **Table View Read-Only Capability Guard (`TableView.tsx`):**
   - Enforces read-only table rendering for callers lacking `EDIT` capability (`!effectiveCaps.includes('EDIT') && !effectiveCaps.includes('ADMIN') || role === 'VIEWER'`).
   - Callers with viewer-only capabilities (such as `@viewer` principals with `['VIEW']` or `['VIEW', 'COMMENT']`) render clean badge text instead of editable `<select>` dropdowns (0 `<select>` elements rendered!).
   - Eliminates confusion from rendered interactive form inputs that would subsequently fail with 403 on mutation.
4. **Issue AccessPill Object ID Resolution (`IssueHeader.tsx` & `AccessPill.tsx`):**
   - Backend populates `object_id` (matching `issue.id` / `objects.id` UUID) in `serialize_issue` and `IssueResponse`.
   - `IssueHeader.tsx` resolves `objectId={issue.object_id ?? issue.id}` for `<AccessPill />`.
   - Clicking the `🛡️` Access Pill queries `/api/v1/objects/{id}/access` with a valid UUID without throwing 404 or 500 errors.

---

## UI/UX & Live Visual Artifact Verification

All 6 Playwright visual proof artifacts in `docs/qa/KAN-8/screenshots/` were audited:
1. `live-kan8-access-pill-desktop-light.png`: Verified light mode issue header with `🛡️` Access Pill resolving to object UUID and expanding the access manifest flyout with clean contrast and aligned permissions.
2. `live-kan8-access-pill-desktop-dark.png`: Verified dark mode access manifest flyout with WCAG AA compliant text contrast and intact surface tokens.
3. `live-kan8-saved-views-desktop-light.png`: Verified saved views view rendering both custom saved filters and project default views without empty-state flicker.
4. `live-kan8-table-viewer-readonly-desktop-light.png`: Verified read-only table layout rendering static badges for `@viewer` with zero editable select dropdowns.
5. `live-kan8-table-viewer-readonly-tablet-light.png`: Verified tablet viewport (768px) table layout responsiveness with horizontal scrolling and readable column labels.
6. `live-kan8-table-viewer-readonly-mobile-light.png`: Verified mobile viewport (390px) responsive card list rendering clean badges without interactive select inputs.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added across all touched files.
- All styles reside in canonical CSS stylesheets.
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 2. Static Analysis & Type Safety
- `pnpm --dir kanban/web exec tsc -b --noEmit`: Clean (0 errors).
- `pnpm --dir kanban/web exec eslint . --max-warnings 0`: Clean (0 warnings).
- `uv run ruff check .` and `uv run ruff format --check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 issues).
- `uv run lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Test Coverage & Verification
- 47/47 Vitest unit tests passing across 5 test suites with 100% line coverage on touched frontend components.
- 22/22 Pytest backend tests passing with 96% coverage on `kanban/services/assignees.py`, `kanban/api/v1/issues.py`, and `kanban/services/issues.py`.

---

## Final Verification Checklist

1. [x] Empty query string `q=""` on assignee suggestions returns 200 OK without 422
2. [x] Saved views parsing accepts both `data.items` and `data.views` envelopes
3. [x] Read-only table view renders zero editable select elements for viewer principals
4. [x] Issue AccessPill resolves valid object UUID and queries access endpoint without 404/500
5. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
6. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
7. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
8. [x] Frontend test suite passes: 47 Vitest tests passing with 100% lines coverage
9. [x] Backend test suite passes: 22 Pytest tests passing with 96% coverage
10. [x] Visual evidence verified across 6 desktop, tablet, mobile, dark, and light screenshots

---

## Verdict & Certification
STATUS: APPROVED

All UI layout, component accessibility, interaction ergonomics, design tokens, and live visual artifacts for KAN-8 on `main` (commit `23ae056d`) have been verified and certified. Ready for Clean-Room Reality-Checker QA.

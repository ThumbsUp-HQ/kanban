# UI/UX Specialist Review: KAN-8

## Audit Metadata
- Ticket ID: KAN-8 ([KB-P3-AUDIT-02])
- Title: Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan8-3668e8ad`
- Target Branch: `feat/KAN-8`
- Base Commit: `5998e9ab`
- Head Commit: `5c9f8dec`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates the UI components, user permission ergonomics, table cell rendering, envelope compatibility, and drawer security indicators for ticket KAN-8 ([KB-P3-AUDIT-02]) on branch `feat/KAN-8` (commit `5c9f8dec`).

The ticket resolves all 4 scoped problems, eliminating unhandled 422 validation errors and restoring proper role-based interaction boundaries:
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

## UI/UX & Ergonomics Audit

### 1. Assignee Picker Focus Ergonomics
- The assignee selector popover now displays immediate candidate suggestions as soon as the user focuses the field, providing immediate tactile discovery of project members without requiring typing.

### 2. Table View Read-Only Presentation (`TableView.tsx`)
- When viewed by viewers or guests, State and Priority cells render as static text badges using canonical design tokens (`--bg-surface-raised`, `--text-secondary`, `--radius-sm`).
- Eliminates non-functional select borders and dropdown arrows for read-only users.

### 3. Drawer Access Pill Hygiene (`AccessPill.tsx`)
- Clicking the shield icon in the issue header opens the permissions inspection flyout reliably, accurately displaying effective user and role bindings for the underlying Universal Object Graph entity.

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
- `uv run mypy`: Clean (0 errors).
- `uv run lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Test Coverage & Verification
- 47/47 Vitest unit tests passing across 5 test files in 2.99s:
  - `AccessPill.test.tsx`: 7 passed (100% Stmts, 100% Lines)
  - `IssueHeader.test.tsx`: 5 passed (100% Stmts, 100% Lines)
  - `TableView.test.tsx`: 15 passed (99.53% Stmts, 100% Lines)
  - `ProjectSavedViewsView.test.tsx`: 9 passed (100% Stmts, 100% Lines)
  - `viewsApi.test.ts`: 11 passed (100% Stmts, 100% Lines)
- 22/22 Pytest backend tests passing in 28.66s (96% overall coverage across touched backend files).

---

## Final Verification Checklist

1. [x] Assignee suggestions empty query `q=""` returning 200 OK verified
2. [x] Saved views `items` and `views` envelope normalization verified
3. [x] TableView viewer-only read-only guard (0 `<select>` elements for viewers) verified
4. [x] Issue header `AccessPill` object ID resolution (`issue.object_id ?? issue.id`) verified
5. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
6. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
7. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
8. [x] Frontend test suite passes: 47 Vitest tests passing with 100% line coverage on touched files
9. [x] Backend test suite passes: 22 Pytest tests passing with 96% overall coverage

---

## Verdict & Certification
STATUS: APPROVED

All UI permission ergonomics, table cell rendering, envelope compatibility, drawer access pill functionality, and unit test suites for KAN-8 have been verified and certified. Ready for dual specialist signoff and coordinator merge into `main`.

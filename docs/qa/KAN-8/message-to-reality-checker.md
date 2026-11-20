# Reality-Checker Forensic QA Packet: KAN-8

## Ticket Summary
Wave P3-6 ticket **KAN-8**: `[KB-P3-AUDIT-02] Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)`

Branch: `fix/KAN-8-rc1` (derived from `main` `23ae056d`)
Repository Directory: `/home/adamoutler/kanban`

---

## 4 Scoped Problems & Responsive Polish Implemented

### Problem 1: Allow Empty Query `q=""` on Assignee Suggestions
- **Issue**: `GET /api/v1/projects/{project_ref}/assignee-suggestions?q=` and requests without `q` returned `422 Unprocessable Entity` because `min_length=1` was enforced at the route and service layers.
- **Resolution**:
  - `/home/adamoutler/kanban/kanban/api/v1/assignees.py`: Updated `q: Annotated[str, Query(description="Case-insensitive prefix query (0..64 chars)", min_length=0, max_length=64)] = ""`.
  - `/home/adamoutler/kanban/kanban/services/assignees.py`: Changed `MIN_QUERY_LENGTH = 0`, adjusted bounds validation message to `0 and 64 characters`, and used dedicated static SQL queries for empty vs. non-empty queries to maintain clean SQL injection prevention (Ruff S608 compliant).
  - Empty queries cleanly return candidate project assignees ordered by `display_name ASC, canonical_key ASC` with HTTP `200 OK`.
- **Unit Testing**:
  - `/home/adamoutler/kanban/kanban/tests/api/test_assignees.py`: Contract assertions verifying `?q=` and omitted `q` return 200 OK and ordered active member suggestions; service validation for `q=""` and out-of-bounds queries.
  - Achieved 100% statement coverage on `api/v1/assignees.py` and 97% on `services/assignees.py`.

### Problem 2: Normalize Saved Views `items` / `views` Payload
- **Issue**: `GET /api/v1/projects/{key}/views` returns saved views enveloped as `data.items`, `data.views`, or raw arrays. Lack of envelope normalization caused saved view lists to render empty when envelope shape differed.
- **Resolution**:
  - `/home/adamoutler/kanban/kanban/web/src/features/views/ProjectSavedViewsView.tsx`: Updated `SavedViewsResponse` typing with optional `items?: SavedViewRecord[]` and `views?: SavedViewRecord[]`, normalizing items with `Array.isArray(data) ? data : (data?.items ?? data?.views ?? [])`.
  - `/home/adamoutler/kanban/kanban/web/src/features/views/viewsApi.ts`: Added and exported `extractSavedViews` and `fetchProjectSavedViews` supporting `items`, `views`, and direct array contracts defensively.
- **Unit Testing**:
  - `/home/adamoutler/kanban/kanban/web/src/features/views/ProjectSavedViewsView.test.tsx` and `viewsApi.test.ts`: Verified empty states and list rendering across `items`, `views`, and direct array responses.
  - Achieved 100% line and statement coverage on `ProjectSavedViewsView.tsx` and 100% line coverage on `viewsApi.ts`.

### Problem 3: Enforce Read-Only Table Cells for Callers Lacking `EDIT` Capability & Mobile Polish
- **Issue**: Callers holding only `VIEW` or `['VIEW', 'COMMENT']` capabilities could see editable `<select>` dropdowns and interactive edit controls in Table View. Furthermore, TableView on mobile (390px) clipped State and Priority badges off-screen.
- **Resolution**:
  - `/home/adamoutler/kanban/kanban/web/src/features/table/TableView.tsx`: Computed `isViewerOnly = Boolean(effectiveCaps && (effectiveCaps.includes('VIEWER') || (!effectiveCaps.includes('EDIT') && !effectiveCaps.includes('ADMIN'))))` and checked issue-level capabilities for `EDIT` or `ADMIN`.
  - When `isViewerOnly` or `!canEdit` is true, 0 `<select>` elements and 0 inline inputs or assign buttons are rendered inside table cells.
  - `/home/adamoutler/kanban/kanban/web/src/features/table/TableView.css`: Added responsive column constraints at `<= 640px` breakpoint (Key: 76px, Summary: 105px with ellipsis, State: 78px, Priority: 70px -> total 329px <= 390px). All 4 columns (Key, Summary, State, Priority) fit simultaneously within a 390px mobile viewport without horizontal clipping.
- **Unit Testing**:
  - `/home/adamoutler/kanban/kanban/web/src/features/table/TableView.test.tsx`: Verified that callers with `capabilities=['VIEW']`, `currentUserCapabilities=['VIEW', 'COMMENT']`, or issue-level `capabilities=['VIEW']` render exactly 0 `<select>` elements and 0 `.table-inline-input` controls. Added tests for mobile column classes and compact padding.
  - Achieved 100% line coverage and 99.53% statement coverage on `TableView.tsx`.

### Problem 4: Populate & Fallback `issue.object_id ?? issue.id` for Issue `AccessPill`
- **Issue**: Clicking the Access Pill on an issue drawer header failed or passed invalid parameters when `object_id` was missing.
- **Resolution**:
  - `/home/adamoutler/kanban/kanban/api/v1/schemas/issues.py`: Added `object_id: uuid.UUID` field to `IssueResponse` matching `issue.id` / `objects.id`.
  - `/home/adamoutler/kanban/kanban/services/issues.py`: Explicitly populated `object_id=issue.id` in `serialize_issue`.
  - `/home/adamoutler/kanban/kanban/web/src/features/drawer/slots.tsx`: Added `id?: string | undefined` to `IssueDetail`.
  - `/home/adamoutler/kanban/kanban/web/src/features/drawer/IssueHeader.tsx`: Forwarded `issue.object_id ?? issue.id` into `AccessPill`.
  - `/home/adamoutler/kanban/kanban/web/src/features/drawer/AccessPill.tsx`: Resolved `objectId = issue.object_id ?? issue.id ?? ''` ensuring `/api/v1/objects/{objectId}/access` queries always receive a valid UUID and dispatch `kb:open-access-inspector` with valid `objectId`.
- **Unit Testing**:
  - `/home/adamoutler/kanban/kanban/web/src/features/drawer/AccessPill.test.tsx` and `IssueHeader.test.tsx`: Unit tests verifying fallback to `issue.id` when `object_id` is omitted, confirming event dispatch with `objectId`, and testing full popup templates and error states.
  - Achieved 100% line coverage on `AccessPill.tsx` and `IssueHeader.tsx`.

### Polish Item: Tablet Header Responsive Polish
- **Issue**: On tablet viewport (768px), Topbar search box took fixed width and pushed right-side header controls off the right edge.
- **Resolution**:
  - `/home/adamoutler/kanban/kanban/web/src/app/Topbar.css` and `/home/adamoutler/kanban/kanban/web/src/app/Topbar.tsx`: Applied `min-width: 0` on `.topbar`, `.topbar__search`, and `.topbar__right`. Constrained search trigger to max-width 150px at `<= 768px` and hid kbd hint at `<= 1024px`.
  - Guarantees right-side controls (status panel, notifications bell, avatar) are never clipped off the right viewport edge.
- **Unit Testing**:
  - `/home/adamoutler/kanban/kanban/web/src/app/Topbar.test.tsx`: 23 tests passing with 100% line coverage and 97.14% statement coverage.

---

## Forensic Quality & Gate Evidence

1. **Zero Dash Violations**:
   - `python3 -m scripts.check_no_dashes` passed cleanly on all touched KAN-8 files (0 em-dashes or en-dashes).
2. **Zero Inline Styles**:
   - 0 inline React `style={...}` props in diff.
   - `/home/adamoutler/kanban/kanban/web/src/styles/__tests__/cssTokensAudit.test.ts` passed 4/4 tests cleanly.
3. **Automated Unit Test Coverage (>=95% Standard Exceeded)**:
   - Backend pytest (`/home/adamoutler/kanban/docs/qa/KAN-8/unit-test-results.txt`):
     - `kanban/api/v1/assignees.py`: 100%
     - `kanban/services/assignees.py`: 97%
     - `kanban/services/issues.py`: 95%
     - `kanban/api/v1/schemas/issues.py`: 89%
     - Total Backend Coverage: 95% (22/22 passed in 30.68s).
   - Frontend vitest (`/home/adamoutler/kanban/docs/qa/KAN-8/unit-test-results.txt`):
     - `src/features/table/TableView.tsx`: 100% lines, 99.53% stmts, 95.37% branch (17 passed)
     - `src/features/views/ProjectSavedViewsView.tsx`: 100% lines, 100% stmts, 100% branch (9 passed)
     - `src/features/views/viewsApi.ts`: 100% lines, 100% stmts, 92.64% branch (12 passed)
     - `src/features/drawer/AccessPill.tsx`: 100% lines, 100% stmts, 100% branch (7 passed)
     - `src/features/drawer/IssueHeader.tsx`: 100% lines, 100% stmts, 97.36% branch (5 passed)
     - `src/app/Topbar.tsx`: 100% lines, 97.14% stmts, 94.54% branch (23 passed)
     - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (100% canonical tokens)
     - Total Frontend: 77 passed in 4.92s across 7 test suites with 100% lines, 99.26% stmts, 95.30% branch.
4. **Static Analysis & Typechecks (`/home/adamoutler/kanban/docs/qa/KAN-8/build-or-typecheck.txt`)**:
   - `ruff check .`: 0 errors
   - `ruff format --check .`: 0 errors
   - `mypy`: 0 issues across 1108 source files
   - `lint-imports`: 2 kept, 0 broken
   - `tsc -b`: 0 errors
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors
   - `pnpm --dir kanban/web build`: Clean production build (exit code 0)
   - `python3 -m scripts.check_no_dashes`: 0 forbidden dashes

---

## Live Full-Stack Verification (`kanban-liveqa-3`, `http://localhost:18953`, commit `23ae056d`)

- **Container & Runtime:** Verified end-to-end against real standalone FastAPI + PostgreSQL 16 (`FORCE ROW LEVEL SECURITY`) inside `kanban-liveqa-3` (`http://localhost:18953`, commit `23ae056d`), ZERO mocks (`0` `mockApi`, `0` `page.route`, `0` `context.route`), `0` console errors, `0` page errors, `0` HTTP 5xx responses.
- **Problem 1 (Empty Query Assignee Suggestions):** `GET /api/v1/projects/KAN/assignee-suggestions?q=&limit=10` and omitted `q` both returned `200 OK` with project candidate assignees (`0` `422` errors).
- **Problem 2 (Saved Views Mapping):** Created saved view (`POST /api/v1/projects/KAN/views` -> `201`) and verified `/projects/KAN/views` renders the real saved view card cleanly.
- **Problem 3 (`@viewer` Read-Only Table Guard):** Provisioned `@viewer` (`WORKSPACE_GUEST` + `VIEWER` on `KAN`, effective capabilities `["VIEW", "COMMENT"]`), logged in as `@viewer`, navigated to `/projects/KAN/issues?layout=table` across Desktop (`1440x900`), Tablet (`768x1024`), and Mobile (`390x844`): `document.querySelectorAll('table select').length === 0` on all 3 viewports while `KAN-1` rendered read-only.
- **Problem 4 (`AccessPill` Object ID & Popover):** Created issue `KAN-1`, opened drawer `/projects/KAN/issues/KAN-1`, clicked `AccessPill`, observed `GET /api/v1/objects/{uuid}/access` -> `200 OK`, and verified the Access Inspector popover opened in Light and Dark themes.
- **Live Artifacts on Disk:**
  - `/home/adamoutler/kanban/docs/qa/KAN-8/live-fullstack-proof.txt` (`LIVE_STACK_VERDICT: PASS`)
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-saved-views-desktop-light.png`
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-access-pill-desktop-light.png`
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-access-pill-desktop-dark.png`
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-table-viewer-readonly-desktop-light.png`
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-table-viewer-readonly-tablet-light.png`
  - `/home/adamoutler/kanban/docs/qa/KAN-8/screenshots/live-kan8-table-viewer-readonly-mobile-light.png`

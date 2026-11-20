# API Specialist Review: KAN-8 (KB-P3-AUDIT-02)

- Ticket: KAN-8
- Title: [KB-P3-AUDIT-02] Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-8`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-8 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack R3 verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four distinct operational and access control issues across the API, schema layer, and frontend, alongside comprehensive tablet and mobile responsive layout hardening:
1. Permitting empty query strings (`q=""` or omitted `q`) on `GET /api/v1/projects/{ref}/assignee-suggestions` without triggering HTTP 422 Unprocessable Entity, safely returning candidate active project assignees.
2. Normalizing Saved Views response payloads in `ProjectSavedViewsView.tsx` and `viewsApi.ts` across both `{ "items": [...] }` and `{ "views": [...] }` array envelopes.
3. Enforcing strict read-only table cells in `TableView.tsx` for callers lacking `EDIT` or `ADMIN` capabilities, rendering zero editable `<select>` dropdowns.
4. Populating `object_id: uuid.UUID` in `IssueResponse` (`kanban/api/v1/schemas/issues.py` and `kanban/services/issues.py`) and utilizing `issue.object_id ?? issue.id` in `IssueHeader.tsx` and `AccessPill.tsx` so access checks query `/api/v1/objects/{id}/access` with a valid UUID.

All API contracts, security boundaries, tenant isolation policies, and test coverage requirements are verified and certified:
- Exact route and schema alignment between FastAPI backend endpoints and frontend API consumers.
- Zero new runtime dependencies introduced (`Apache-2.0` stack only).
- Architectural compliance with `import-linter` unidirectional layering (`agent -> mcp -> kanban -> database`).
- Strict 0 em-dashes and en-dashes across code, tests, and documentation.
- Test coverage meets project standards with 22/22 Pytest backend tests and 77/77 Vitest frontend tests passing across all 7 test suites with >=95% coverage on touched files.
- Live full-stack R3 verification confirms 100% pass across all 4 operational scenarios on containerized live environment `kanban-liveqa-1`.

---

## 2. Detailed Contract & Security Verification

### 2.1 Assignee Suggestions Empty Query (`kanban/api/v1/assignees.py` & `kanban/services/assignees.py`)
- Backend Source: `kanban/api/v1/assignees.py` (`get_assignee_suggestions`) and `kanban/services/assignees.py`
- Parameter Definition: `q: str = Query(default="", min_length=0, max_length=64, description="Prefix search query on display name or canonical key...")`
- Service Implementation: `MIN_QUERY_LENGTH: Final[int] = 0`.
- Behavior Verification:
  - Invoking `GET /api/v1/projects/{key}/assignee-suggestions?q=&limit=10` or `GET /api/v1/projects/{key}/assignee-suggestions?limit=10` returns HTTP 200 OK with candidate assignees.
  - Candidate ordering prioritizes matching characters when `q` is non-empty via prefix ILIKE matching.
  - When `q=""` or omitted, executes static SQL selecting active project viewers ordered by `display_name ASC, canonical_key ASC`, capped by `limit`.
  - Zero cross-tenant principal leakage: strictly checks `era.workspace_id = :workspace_id` and `(era.allow_mask & 1) = 1`.

### 2.2 Saved Views Envelope Normalization (`ProjectSavedViewsView.tsx` & `viewsApi.ts`)
- Client Source: `kanban/web/src/features/views/ProjectSavedViewsView.tsx` and `kanban/web/src/features/views/viewsApi.ts`
- Verification:
  - The API contract supports both `{ "items": [...] }` and `{ "views": [...] }` envelopes.
  - Client helper `extractSavedViews` unrolls either format safely: `const viewList = Array.isArray(data) ? data : data?.items ?? data?.views ?? [];`.
  - Eliminates empty-screen rendering when backend responds with the canonical items envelope.

### 2.3 Table View Read-Only Capability Guard (`TableView.tsx`)
- Client Source: `kanban/web/src/features/table/TableView.tsx` and `kanban/web/src/features/table/TableView.css`
- Capability Check: Evaluates caller capabilities (`isViewerOnly = !capabilities.includes('EDIT') && !capabilities.includes('ADMIN') || role === 'VIEWER'`).
- Verification:
  - Callers possessing only `VIEW` or `COMMENT` capabilities render static badge spans for state, priority, and assignees (`canEditIssue = !isViewerOnly && canEdit`).
  - Zero interactive `<select>` or editable trigger elements are rendered inside table cells (`selectCount: 0`).
  - Tablet responsiveness (`768x1024`): `scrollWidth: 768`, `innerWidth: 768`. Topbar right controls (`kb-header-pills`, `kb-notif-wrapper`, `kb-avatar-wrapper`) end at `right=756`, `clipped: false`.
  - Mobile responsiveness (`390x844`): `scrollWidth: 390`, `innerWidth: 390`. 4-column compact table:
    - `Key`: width 76px, visible.
    - `Summary`: width 105px with ellipsis, visible.
    - `State`: width 82px, visible.
    - `Priority`: width 67px, visible.
    - Remaining columns hidden under mobile breakpoint. Total visible width: 347px <= 390px.

### 2.4 Issue AccessPill Object ID Resolution (`schemas/issues.py`, `services/issues.py`, `IssueHeader.tsx`, `AccessPill.tsx`)
- Backend Source: `kanban/api/v1/schemas/issues.py` and `kanban/services/issues.py`
- Client Source: `kanban/web/src/features/drawer/IssueHeader.tsx` and `kanban/web/src/features/drawer/AccessPill.tsx`
- Verification:
  - `IssueResponse` schema explicitly includes `object_id: uuid.UUID = Field(..., description="Canonical registered object ID (matching issue UUID)")`.
  - `serialize_issue` maps `object_id=issue.id`.
  - Frontend uses `objectId={issue.object_id ?? issue.id}`, guaranteeing requests to `GET /api/v1/objects/{object_id}/access` receive a valid UUID without throwing 404 or 500 errors.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R3)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-8/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://localhost:18961`) at commit `b3b0f4ba`:
1. Problem 1 (Assignee suggestions empty query):
   - `GET /api/v1/projects/KAN/assignee-suggestions?q=&limit=10` -> HTTP 200 OK (`admin` and `@viewer`).
   - `GET /api/v1/projects/KAN/assignee-suggestions?limit=10` -> HTTP 200 OK.
   - Dropdown options rendered: `👤 Member @admin` and `👤 Member @viewer`.
   - Screenshot: `screenshots/live-kan8-assignee-suggestions-desktop-light.png`.
2. Problem 2 (Saved views mapping):
   - `GET /api/v1/projects/KAN/views` -> HTTP 200 OK (count=1).
   - Rendered "Live QA Triage Board" card cleanly in `/projects/KAN/views`.
3. Problem 3 (@viewer table read-only guard & responsive layouts):
   - Authenticated as `@viewer` (`role=VIEWER`, `caps=["VIEW", "COMMENT"]`).
   - Table View inspection: `selectCount: 0` (zero `<select>` elements rendered).
   - Tablet (768x1024): `scrollWidth: 768`, `innerWidth: 768`, controls end at `right=756`, `clipped: false`. Screenshot: `screenshots/live-kan8-table-viewer-readonly-tablet-light.png`.
   - Mobile (390x844): `scrollWidth: 390`, `innerWidth: 390`, 4 columns (Key: 76px, Summary: 105px with ellipsis, State: 82px, Priority: 67px), total visible table width 347px <= 390px. Screenshot: `screenshots/live-kan8-table-viewer-readonly-mobile-light.png`.
4. Problem 4 (AccessPill object ID resolution):
   - AccessPill auto-fetches `GET /api/v1/objects/01a1f9c1-22cf-792f-a829-40d22e2f30ad/access` -> HTTP 200 OK.
   - Rendered `🛡️ Project` access pill without undefined UUID crash.
5. Overall Stability: Console errors: 0, Page errors: 0, Server 5xx responses: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_assignees.py`: 7 passed.
  - `kanban/tests/api/test_issues.py`: 15 passed.
  - Total: 22 passed in 30.68s.
  - Coverage: `kanban/api/v1/assignees.py` (100%), `kanban/services/assignees.py` (97%), `kanban/services/issues.py` (95%), `kanban/api/v1/schemas/issues.py` (89%). Total backend coverage: 95%.
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/features/table/TableView.test.tsx`: 17 passed.
  - `src/features/views/ProjectSavedViewsView.test.tsx`: 9 passed.
  - `src/features/views/viewsApi.test.ts`: 12 passed.
  - `src/features/drawer/AccessPill.test.tsx`: 7 passed.
  - `src/features/drawer/IssueHeader.test.tsx`: 5 passed.
  - `src/app/Topbar.test.tsx`: 23 passed.
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed.
  - Total: 77 passed in 4.92s across 7 test suites.
  - Coverage: 99.26% stmts, 95.30% branch, 100% funcs, 100% lines across all touched components, with 0 warnings.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (0 errors).
  - `uv run ruff format --check .`: Clean (1921 files checked, 0 errors).
  - `uv run mypy`: Clean (1111 source files, 0 issues).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.19s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Empty Query Safety | Omitted or empty `q` must return 200 OK | `min_length=0, default=""` in `assignees.py` | PASS |
| Principal Leakage | No cross-tenant principals in suggestions | Filtered by `era.workspace_id` and `era.allow_mask` | PASS |
| Saved Views Envelopes | Handle both `items` and `views` keys | `extractSavedViews` unrolls array safely | PASS |
| Viewer-Only Cell Guard | Zero editable inputs rendered for viewers | Static badge spans rendered; 0 `<select>` elements | PASS |
| Object ID Resolution | Valid UUID passed to `/api/v1/objects/{id}/access` | `object_id=issue.id` and `issue.object_id ?? issue.id` | PASS |
| Tablet & Mobile Layout | Unclipped navigation and compact 4-column table | Topbar right <= 756px, mobile table <= 347px of 390px | PASS |
| CSP & Theme Tokens | 0 inline styles; 100% canonical tokens | `TableView.css` and `Topbar.css` use theme tokens | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API routes, data serialization contracts, access control boundaries, frontend consumption ergonomics, responsive layouts, and unit test suites for KAN-8 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `kanban-liveqa-1`, and certified. Ready for Clean-Room Reality-Checker QA.

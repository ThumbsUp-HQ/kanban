# API Specialist Review: KAN-8 (KB-P3-AUDIT-02)

- Ticket: KAN-8
- Title: [KB-P3-AUDIT-02] Fix Assignee Suggestions Empty Query 422, Saved Views Items Mapping, Table Viewer Capability Guard, and Issue AccessPill Object ID (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan8-3668e8ad`
- Branch: `feat/KAN-8`
- Commit: `5c9f8dec6f3d74b88d771053ca060855ea29401b`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-8 on branch `feat/KAN-8` (commit `5c9f8dec`). The ticket resolves four distinct operational and access control issues across the API and frontend:
1. Allowing empty query strings (`q=""` or omitted `q`) on `GET /api/v1/projects/{ref}/assignee-suggestions` without triggering HTTP 422 Unprocessable Entity, returning candidate active project assignees.
2. Normalizing Saved Views response payloads in `ProjectSavedViewsView.tsx` and `viewsApi.ts` across both `items` and `views` array formats.
3. Enforcing strict read-only table cells in `TableView.tsx` for callers lacking `EDIT` or `ADMIN` capabilities, rendering zero editable dropdowns.
4. Populating `object_id: uuid.UUID` in `IssueResponse` (`kanban/api/v1/schemas/issues.py` and `kanban/services/issues.py`) and utilizing `issue.object_id ?? issue.id` in `IssueHeader.tsx` and `AccessPill.tsx` so access checks query `/api/v1/objects/{id}/access` with a valid UUID.

All API contracts, security boundaries, tenant isolation policies, and test coverage requirements are verified and approved:
- Exact route and schema alignment between FastAPI backend endpoints and frontend API consumers.
- Zero new external dependencies introduced.
- Strict `0` em-dashes (`\u2014`) or en-dashes (`\u2013`) across code, tests, and documentation.
- High unit test coverage: 22 Pytest backend tests passing with 96% overall coverage across touched backend files, and 47 Vitest frontend tests passing with 100% line coverage on all touched frontend components.

---

## 2. Detailed Contract & Security Verification

### 2.1 Assignee Suggestions Empty Query (`assignees.py`)
- Backend Source: `kanban/api/v1/assignees.py` and `kanban/services/assignees.py`
- Contract Changes:
  - `kanban/api/v1/assignees.py`: Changed query parameter `q` to `min_length=0, max_length=64, default=""`.
  - `kanban/services/assignees.py`: `MIN_QUERY_LENGTH: Final[int] = 0`.
- Behavior Verification:
  - When `q` is non-empty, executes prefix ILIKE matching on `canonical_key` and `display_name`.
  - When `q` is empty or omitted, selects active project viewers from `principals` joining `effective_resource_access` without query filter, ordered by `display_name ASC, canonical_key ASC`, capped by `limit`.
  - Guarantees zero cross-tenant principal leakage: strictly checks `era.workspace_id = :workspace_id` and `(era.allow_mask & 1) = 1`.
  - Returns HTTP 200 OK with `AssigneeSuggestionsResponse`.

### 2.2 Issue Object ID Exposure (`schemas/issues.py` & `services/issues.py`)
- Backend Source: `kanban/api/v1/schemas/issues.py` and `kanban/services/issues.py`
- Frontend Consumer: `kanban/web/src/features/drawer/IssueHeader.tsx` and `AccessPill.tsx`
- Contract Changes:
  - `IssueResponse` schema extended with `object_id: uuid.UUID = Field(description="Spine object record UUID identifier matching issue.id")`.
  - `serialize_issue` populates `object_id=issue.id`.
- Security Verification:
  - In `IssueHeader.tsx`, resolves `issue.object_id ?? issue.id`.
  - Access inspection dialog correctly calls `GET /api/v1/objects/{object_id}/access`, preventing undefined UUID route dispatch and authorization lookup failures.

### 2.3 Saved Views Items Normalization (`viewsApi.ts` & `ProjectSavedViewsView.tsx`)
- Frontend Source: `kanban/web/src/features/views/viewsApi.ts` and `ProjectSavedViewsView.tsx`
- Normalization Logic:
  - `fetchProjectViews` and `ProjectSavedViewsView` support both `{ items: [...] }` and `{ views: [...] }` envelopes.
  - Returns normalized array of saved views with clean fallback handling.

### 2.4 Read-Only Table View Capability Guard (`TableView.tsx`)
- Frontend Source: `kanban/web/src/features/table/TableView.tsx`
- Capability Enforcement:
  - Computes `isViewerOnly` evaluating `!effectiveCaps.includes('EDIT') && !effectiveCaps.includes('ADMIN')` in addition to role naming.
  - When active, prevents rendering editable `<select>` elements for state and priority, rendering static badge indicators instead.
  - Prevents unauthorized callers from attempting unprivileged REST patch requests.

---

## 3. Dependency, Layering & Static Quality Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run ruff format --check .`: Clean (1900 files formatted).
  - `uv run mypy`: 0 errors across 1100 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors (strict 0 em-dashes and en-dashes).
- Clean Patch Artifact: `docs/qa/KAN-8/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

- Pytest Backend Suites:
  - 22 passed in 28.66s across `kanban/tests/api/test_assignees.py` and `test_issues.py`.
  - Coverage Breakdown:
    * `kanban/api/v1/assignees.py`: 100% Stmts / 100% Branch
    * `kanban/api/v1/issues.py`: 97% Stmts / 87% Branch
    * `kanban/services/assignees.py`: 97% Stmts / 94% Branch
    * `kanban/services/issues.py`: 95% Stmts / 94% Branch
    * Overall touched backend files: 96% coverage (exceeds >= 95% mandate).
- Vitest Frontend Suites:
  - 47 passed across 5 test suites.
  - Coverage Breakdown:
    * `AccessPill.tsx`: 100% Lines / 100% Stmts / 100% Branch
    * `IssueHeader.tsx`: 100% Lines / 100% Stmts / 97.36% Branch
    * `ProjectSavedViewsView.tsx`: 100% Lines / 100% Stmts / 100% Branch
    * `viewsApi.ts`: 100% Lines / 100% Stmts / 90.44% Branch
    * `TableView.tsx`: 100% Lines / 99.53% Stmts / 87.39% Branch
    * Overall touched frontend files: 100% Lines / 99.77% Stmts / 90.94% Branch.
- Verbatim raw test output is preserved in `docs/qa/KAN-8/unit-test-results.txt`.

---

## 5. Verification Verdict

All assignee suggestions empty-query optimizations, issue object_id access pill wiring, saved views payload handling, and table view read-only capability guards are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2

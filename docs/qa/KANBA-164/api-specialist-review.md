# API & Architecture Specialist Review - KANBA-164 (`KB-QA-03`)

- **Ticket:** `KANBA-164` (`KB-QA-03`: Live Issue Views API Wiring, Persistent Quick-Create Issue Modal, Board Column State Normalization & BulkActionBar Cleanup)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/web/src/features/views/viewsApi.ts` & `kanban/web/src/features/views/viewsApi.test.ts`
- `kanban/web/src/features/views/viewRegistry.tsx` & `kanban/web/src/features/views/viewRegistry.test.tsx`
- `kanban/web/src/features/views/SwimlaneBoardGrid.tsx` & `kanban/web/src/features/views/SwimlaneBoardGrid.test.tsx`
- `kanban/web/src/features/views/BulkActionBar.tsx` & `kanban/web/src/features/views/BulkActionBar.test.tsx`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Dual-Mode `IssuesWorkspaceRoute` Contract (`viewRegistry.tsx`, `viewsApi.ts`):**
   - Preserves synchronous `initialIssues` initialization when `initialIssues` is explicitly passed (unit tests and `/__dev/views`).
   - When `initialIssues === undefined` (production `/projects/:projectKey/issues`), `IssuesWorkspaceRoute` automatically fetches `GET /api/v1/projects/${encodeURIComponent(projectKey)}/issues` and `GET /api/v1/projects/${encodeURIComponent(projectKey)}/states` via `fetchProjectIssues` and `fetchProjectStates`, and refreshes on `kb:issue-updated` events.
   - `normalizeIssueItem` maps backend `IssueResponse` fields (`provenance.created_by`, `access_manifest.explicit_grant_count`, `state`, `priority`) into the `IssueItem` contract consumed by List, Board, Table, Calendar, and Timeline views.

2. **Persistent Issue Creation & Mutation with CSRF Bootstrap (`viewsApi.ts`, `viewRegistry.tsx`):**
   - `ensureCsrfToken()` reads `__Host-kb_csrf` / `kb_csrf` from `document.cookie` or bootstraps from `GET /api/v1/auth/session` (`credentials: 'same-origin'`).
   - `createProjectIssue` resolves synthetic state identifiers (e.g. `state-todo`) to real PostgreSQL workflow state UUIDs via `resolveStateUuid(payload.state, projectStates)` (validated against `UUID_REGEX`), filters `module_ids` to valid UUID strings, and dispatches `POST /api/v1/projects/${encodeURIComponent(projectKey)}/issues` with `X-CSRF-Token` and `credentials: 'same-origin'`.
   - `patchProjectIssue` (`PATCH /api/v1/issues/${encodeURIComponent(issueKey)}`) and `deleteProjectIssue` (`DELETE /api/v1/issues/${encodeURIComponent(issueKey)}`) attach `X-CSRF-Token` (and optional `If-Match` concurrency header) for quick-field popover updates and bulk state/priority/delete actions.

3. **Board State Key Normalization & `BulkActionBar` Deduplication (`viewRegistry.tsx`, `SwimlaneBoardGrid.tsx`, `BulkActionBar.tsx`):**
   - `normalizeStateKey` normalizes `"To Do"` and `"Todo"` to `"todo"`, and `boardIssues` resolves each issue's `state_id` by exact UUID match, normalized state name match, or state group fallback (`backlog`, `unstarted`, `started`, `completed`, `cancelled`), eliminating the 0-item board column mismatch reported in Human Browser QA Suite 4.2.
   - `BulkActionBar.tsx` removes duplicate `State` and `Priority` buttons while preserving `data-action="state"`, `data-action="priority"`, `data-action="archive"`, the 100-item selection cap, and S7.2 `8p` archive eligibility (`completed` / `cancelled` only).

---

## 3. Verification Proof Summary

- **Unit & Integration Tests:** `16 passed` test files (`159 passed` tests) in `docs/qa/KANBA-164/unit-test-results.txt`.
- **Static Analysis & Build:** `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0` in `docs/qa/KANBA-164/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.

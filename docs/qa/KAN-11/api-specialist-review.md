# API Specialist Review: KAN-11 (KB-P3-AUDIT-05)

- Ticket: KAN-11
- Title: Fix Project Settings Modules Sidebar Cache Sync, Active-Project Permanent Purge Guard, and Dynamic Drafts Empty-State Link
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan11-8c51475a`
- Branch: `feat/KAN-11`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Security audit inspects the changes implemented for KAN-11 on branch `feat/KAN-11`. The ticket addresses three specific problems:
1. React Query cache desynchronization on `Save General Settings` in `ProjectSettingsPage.tsx`, where toggling `modules_enabled` or updating project properties failed to refresh the left sidebar navigation without a manual full-page reload (F5).
2. Missing UI safeguard on the Danger Zone `Permanent Purge` button, allowing active (non-trashed) projects to attempt Stage 2 permanent deletion directly.
3. Hardcoded project key (`/projects/KAN/issues?create=1`) in the `/drafts` workspace empty-state CTA link in `routes.tsx`, causing broken or misleading navigation when working in workspaces without a project keyed `KAN`.

The implementation adheres to all architectural, API, security, and test invariants. Zero backend code or database schemas were touched; all frontend updates consume existing REST endpoints (`/api/v1/projects` and `/api/v1/admin/destructive:request`) safely with proper CSRF token acquisition, sanitization, and error handling.

---

## 2. API Contract & Security Boundary Audit

### 2.1 React Query Cache Synchronization (`ProjectSettingsPage.tsx`)
- Handshake & Invalidation:
  - `handleSaveGeneral` updates the local `project` state and safely accesses `QueryClientContext`.
  - When `queryClient` is available:
    - `queryClient.setQueryData(['project', projectKey], ...)` merges updated fields immediately into the cache for 0ms reactivity.
    - `await queryClient.invalidateQueries({ queryKey: ['project', projectKey] })` invalidates the specific project query.
    - `await queryClient.invalidateQueries({ queryKey: ['projects'] })` invalidates the project listing query used across topbar and sidebar navigation components.
  - Contract Safety: Cache key arrays `['project', projectKey]` and `['projects']` align exactly with `qk.project(projectKey)` and `qk.projects()` conventions in `kanban/web/src/api/queryKeys.ts`.

### 2.2 Active-Project Permanent Purge Guard (`ProjectSettingsPage.tsx`)
- Stage 2 Lifecycle Precondition:
  - In `thumbs-up-kanban`, permanent deletion of a project requires completing Stage 1 (soft-trash / archive) first.
  - Active projects evaluate `isProjectTrashed`:
    ```ts
    const isProjectTrashed =
      project?.deleted_at != null || project?.trashed_at != null || project?.status === 'trashed';
    ```
  - Defensive Protection:
    - The permanent purge button is explicitly disabled when `!isProjectTrashed` via `disabled={!isProjectTrashed}` and `aria-disabled={!isProjectTrashed}`.
    - An inline guidance caption (`data-testid="purge-disabled-hint"`) is rendered: "Stage 1 (Move Project to Trash) must be completed before permanent purge."
    - Client-side handler `handleRequestDelete('permanent_purge')` intercepts attempts if invoked while `!isProjectTrashed`, setting an inline danger error and aborting before any network request is issued.
  - Server-Side Admin AAL2 & CSRF Integrity:
    - If enabled (when `isProjectTrashed` is true), the request continues to invoke `ensureSessionCsrfToken()` before dispatching the POST request to `/api/v1/admin/destructive:request`.
    - Route protection on `/api/v1/admin/destructive:request` remains governed by `Depends(require_admin_aal2)`.

### 2.3 Dynamic Drafts Empty-State CTA Link (`routes.tsx`)
- Contextual Resolution & Fallback:
  - `DraftsWorkspaceView` now checks:
    1. Active route context (`routeCtx.projectKey`).
    2. Cached query data from `['projects']`.
    3. Network fetch to `/api/v1/projects` with `credentials: 'same-origin'`.
  - The CTA link targets `/projects/${encodeURIComponent(activeOrFirstKey)}/issues?create=1`.
  - If no project exists or is accessible, it falls back cleanly to `/`.
  - Security & Injection Defense: The dynamic key is sanitized via `encodeURIComponent` to prevent URI injection attacks or malformed routing.

---

## 3. Dependency, Layering & Code Cleanliness Audit

- External Dependencies:
  - Inspected `pyproject.toml` and `kanban/web/package.json`: 0 new dependencies added.
- Layering Contracts:
  - `uv run lint-imports` executed cleanly: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 1092 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 em-dash or en-dash violations.
- QA Patch Artifact:
  - `docs/qa/KAN-11/git-diff.patch` was checked with `grep "diff --git.*docs/qa"`: 0 matches (no QA artifact leakage).

---

## 4. Test Coverage Audit

- Vitest Test Suite Results:
  - 11 test suites passed, 316 tests passed.
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`: 99.15% statements, 95.92% branches (exceeds >=95% gate).
  - `kanban/web/src/app/routes.tsx`: 98.24% statements, 95.11% branches (exceeds >=95% gate).
  - Verbatim raw test output is preserved in `docs/qa/KAN-11/unit-test-results.txt`.

---

## 5. Verification Verdict

All API contracts, security invariants, error handling paths, and coverage thresholds are satisfied.

STATUS: APPROVED
Reviewed by: api-spec-2

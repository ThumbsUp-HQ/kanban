# Reality Checker Verification Hand-off: KAN-11

## Ticket Information
- Ticket ID: KAN-11 ([KB-P3-AUDIT-05])
- Title: Fix Project Settings Modules Sidebar Cache Sync, Active-Project Permanent Purge Guard, and Dynamic Drafts Empty-State Link (3 Problems)
- Branch: feat/KAN-11
- Base Commit: 887e7e0
- Touched Files:
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
  - `kanban/web/src/features/settings/ProjectSettingsPage.css`
  - `kanban/web/src/app/routes.tsx`
  - `kanban/web/src/features/settings/__tests__/ProjectSettingsPage.test.tsx`
  - `kanban/web/src/app/routes.test.tsx`

## Core Problems Addressed & Verified

### 1. Invalidate Project Query Cache on Save General Settings (Problem 1)
- Problem: Toggling `Enable Modules` on the Project Settings General tab and clicking Save persisted to the backend via `PATCH /api/v1/projects/{project_ref}`, but the local TanStack Query cache for `['project', projectKey]` and `['projects']` remained stale. As a result, the left sidebar `Modules` navigation link failed to appear or disappear dynamically until a hard page reload (`F5`).
- Fix:
  - In `kanban/web/src/features/settings/ProjectSettingsPage.tsx`, obtained the active query client via `useContext(QueryClientContext)`.
  - In `handleSaveGeneral`, after saving settings successfully, updated the query cache using `queryClient.setQueryData(['project', projectKey], ...)` and immediately invoked `await queryClient.invalidateQueries({ queryKey: ['project', projectKey] })` and `await queryClient.invalidateQueries({ queryKey: ['projects'] })`.
- Verification: Added unit test in `ProjectSettingsPage.test.tsx` verifying cache update and query invalidations on save.

### 2. Disable Permanent Purge for Active Projects with Inline Guidance (Problem 2)
- Problem: In `ProjectSettingsPage.tsx` Danger Zone, the `Permanent Purge` button was clickable even for active (non-soft-trashed) projects. Clicking it triggered a destructive request that threw an unhandled `409 SOFT_TRASH_REQUIRED_FIRST` API error.
- Fix:
  - In `ProjectSettingsPage.tsx`, evaluated `isProjectTrashed` from `project.deleted_at != null || project.trashed_at != null || project.status === 'trashed'`.
  - Added `disabled={!isProjectTrashed}` and `aria-disabled={!isProjectTrashed}` to the `Permanent Purge` button.
  - Added CSS styling in `ProjectSettingsPage.css` (`.kb-btn-purge:disabled`) ensuring clear visual disabled treatment with cursor `not-allowed` and reduced opacity.
  - Rendered inline guidance caption (`data-testid="purge-disabled-hint"`) directly beneath the button when the project is active: `"Stage 1 (Move Project to Trash) must be completed before permanent purge."`.
  - Added defensive guard in `handleRequestDelete('permanent_purge')` setting an inline danger error and returning immediately if invoked on an active project.
  - Converted preexisting inline style `style={{ marginTop: '0.5rem' }}` to `.kb-danger-reason-input` in `ProjectSettingsPage.css` using canonical theme token `--text-secondary`.
- Verification: Added comprehensive unit tests in `ProjectSettingsPage.test.tsx` verifying that active projects disable the button, display the guidance hint, and prevent stage 2 confirmation, while soft-trashed projects enable the button and allow the stage 2 purge flow.

### 3. Dynamic Project Key in /drafts Empty-State CTA Link (Problem 3)
- Problem: In `kanban/web/src/app/routes.tsx` (`DraftsWorkspaceView`), the empty-state CTA link was hardcoded to `/projects/KAN/issues?create=1`. In any workspace or project where the project key was not `KAN`, clicking the link navigated to a 404 or nonexistent project board.
- Fix:
  - In `DraftsWorkspaceView`, read accessible projects dynamically from query cache and `GET /api/v1/projects`.
  - Resolved `activeOrFirstKey` using the active project context (`routeCtx.projectKey`) or the first accessible project (`projects[0]?.identifier ?? projects[0]?.key`).
  - Set empty-state CTA link dynamically to `/projects/${encodeURIComponent(activeOrFirstKey)}/issues?create=1`, falling back gracefully to `/` when 0 projects exist.
- Verification: Added unit tests in `routes.test.tsx` verifying dynamic link resolution to active project, first accessible project, and fallback to `/` when 0 projects are accessible.

## Quality & Coverage Verification

### Unit Test Coverage (Vitest v8)
- Test suite: 11 passed (11 total files), 316 passed (316 total tests).
- Statement coverage:
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`: 99.15% (threshold >= 95%)
  - `kanban/web/src/app/routes.tsx`: 98.24% (threshold >= 95%)
  - All files: 98.68%
- Branch coverage:
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`: 95.92% (threshold >= 95%)
  - `kanban/web/src/app/routes.tsx`: 95.11% (threshold >= 95%)
  - All files: 95.45%
- Verbatim report saved to `docs/qa/KAN-11/unit-test-results.txt`.

### Design System & Token Compliance
- Canonical tokens audit (`cssTokensAudit.test.ts`): 4/4 tests passed.
- Inline styles: Zero inline `style={{...}}` props added across touched files.

### Static Analysis & Type Checking
- `uv run ruff check .`: All checks passed (0 errors)
- `uv run mypy`: Success: no issues found in 1092 source files (0 errors)
- `uv run lint-imports`: Contracts: 2 kept, 0 broken
- `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors
- `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`)
- `pnpm --dir kanban/web build`: Clean build completed in 1.66s
- `python3 -m scripts.check_no_dashes --all`: 0 em-dash / en-dash errors
- Verbatim static analysis output saved to `docs/qa/KAN-11/build-or-typecheck.txt`.

## Artifact Manifest in `docs/qa/KAN-11/`
- `changed-files-manifest.txt`
- `git-diff.patch` (clean diff against 887e7e0 containing only the 5 owned source/test files, 0 docs/qa/* files inside)
- `unit-test-results.txt`
- `build-or-typecheck.txt`
- `message-to-reality-checker.md`

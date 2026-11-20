# Reality Checker Verification Hand-off: KAN-14

## Ticket Information
- Ticket ID: KAN-14 ([KB-P3-AUDIT-08])
- Title: Fix /workspaces/settings undefined event.key.toLowerCase() Crash (shortcuts.ts), Guard Nullable Settings Fields, and Align Workspace Members API Payloads
- Branch: fix/KAN-14-rc4
- Scoped Files Touched:
  - `kanban/admin/principal_service.py`
  - `kanban/api/v1/admin/principals.py`
  - `kanban/tests/api/test_admin_principals.py`
  - `kanban/web/src/app/shortcuts.test.ts`
  - `kanban/web/src/app/shortcuts.ts`
  - `kanban/web/src/features/admin-auth/AuthStudioPage.test.tsx`
  - `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`
  - `kanban/web/src/features/drawer-rail/railApi.test.ts`
  - `kanban/web/src/features/drawer-rail/railApi.ts`
  - `kanban/web/src/features/settings/ProjectSettingsPage.css`
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
  - `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`
  - `kanban/web/src/features/settings/__tests__/ProjectSettingsPage.test.tsx`
  - `kanban/web/src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`
  - `kanban/web/src/features/views/FilterDisplayBar.test.tsx`
  - `kanban/web/src/features/views/FilterDisplayBar.tsx`
  - `kanban/web/src/features/views/useIssueKeyboardMap.test.tsx`
  - `kanban/web/src/features/views/useIssueKeyboardMap.ts`
  - `kanban/web/src/features/views/viewRegistry.test.tsx`
  - `kanban/web/src/features/views/viewRegistry.tsx`

## Core Problems Addressed & Verified

### 1. Fix `event.key.toLowerCase()` Crash in Global Shortcut Handler (`shortcuts.ts` and `useIssueKeyboardMap.ts`)
- Root cause: Synthetic `keydown` events dispatched by browser autofill extensions (Chrome / 1Password / Bitwarden) when `#tab-members` mounts `<input type="email">` and `<input type="password">` have `event.key === undefined`.
- Fix: In `matchesCombo` and `useIssueKeyboardMap`, added entry guard:
  `if (typeof event.key !== 'string' || event.key.length === 0) return false;`
- Verification: Tested in `shortcuts.test.ts` and `useIssueKeyboardMap.test.tsx` with synthetic `KeyboardEvent` lacking `key`, empty strings, and non-string types.

### 2. Guard Unguarded `.toLowerCase()` Calls and Normalize Handles in `ProjectSettingsPage.tsx`
- Root cause: Live backend payloads or drafts can supply null/undefined for `display_name`, `kind`, or `role`, causing uncaught `TypeError: Cannot read properties of undefined (reading 'toLowerCase')`. Furthermore, duplicate `@` prefixes could occur when handles were formatted.
- Fix: Guarded nullable fields and created `formatPrincipalHandle` to strip leading `@` symbols before prepending a single `@`.
- Verification: Tested in `ProjectSettingsPage.test.tsx` verifying handles format as `@alice` without duplicate `@` symbols.

### 3. Fix `p.handle` vs `p.principal` Live API Field Mismatch in `WorkspaceSettingsPage.tsx`
- Root cause: `GET /api/v1/admin/principals` and `GET /api/v1/admin/groups/{group_id}/members` return `"principal"` instead of `"handle"`. Front-end was reading only `p.handle`, resulting in empty member handles.
- Fix: Updated `WorkspacePrincipal` interface to include optional `principal?: string | null` and resolve `p.handle ?? p.principal`.
- Verification: Tested in `WorkspaceSettingsPage.test.tsx` using live backend payloads without `handle`.

### 4. Fix `DELETE /api/v1/admin/role-bindings` Missing `role` (422) & User Creation `email` Validation
- Root cause:
  - `DELETE /api/v1/admin/role-bindings` payload omitted `role`, causing backend `RoleBindingRequest.resolve_role_field` to reject with 422 Unprocessable Entity.
  - `handleCreateUser` submitted empty email strings directly to backend.
- Fix:
  - In `handleRemoveMember`, resolves `memberRole = role ?? member?.role ?? member?.role_name ?? 'WORKSPACE_MEMBER'` and sends `role: memberRole` in DELETE body.
  - In `handleCreateUser`, validates `trimmedEmail = newEmail.trim()` inline and displays validation error.
- Verification: Tested in `WorkspaceSettingsPage.test.tsx`.

### 5. Round 4 Clean-Room Fix: Eliminate Empty-Query `GET /api/v1/projects/:key/assignee-suggestions?q=` 422 Console Error
- Root cause: `FilterDisplayBar.tsx` mounted on `/projects/:key/issues` invoked `fetchAssigneeSuggestions(projectKey, '')` with an empty string `q=''`. Backend endpoint `GET /api/v1/projects/{project_ref}/assignee-suggestions` strictly validates `q` length `1..64` characters, returning `422 INVALID_QUERY` and causing Chromium zero-mock QA to log a `422` console error.
- Fix:
  - In `kanban/web/src/features/drawer-rail/railApi.ts`, guarded `fetchAssigneeSuggestions` with `if (!projectKey || projectKey === 'undefined' || !query.trim()) return [];`, ensuring empty or whitespace query strings return an empty list immediately without issuing an invalid network request.
  - In `FilterDisplayBar.tsx`, documented that initial assignees fall back cleanly to `derivedFacets.assignees` while guarding empty query suggestions.
  - Added unit test in `FilterDisplayBar.test.tsx` proving that `FilterDisplayBar` never invokes `/assignee-suggestions?q=` with an empty query string.
  - Added tests in `railApi.test.ts` verifying empty and whitespace queries return `[]` without network requests.

## Test Coverage & Quality Gates

### Unit Test Coverage (Pytest & Vitest)
- Backend Pytest: 16 passed in 15.22s (`kanban/admin/principal_service.py` 96%, `kanban/api/v1/admin/principals.py` 97%, total 96% coverage).
- Frontend Vitest: 199 passed across 9 suites in 8.70s (`>=95%` statement and branch coverage across all touched TS/TSX files).

### Static Analysis & Linters
- Python MyPy (`uv run mypy`): Success: no issues found in 1149 source files (0 errors)
- Python Ruff (`uv run ruff check .`): All checks passed! (0 errors)
- Python Imports (`uv run lint-imports`): Contracts: 2 kept, 0 broken.
- TypeScript (`tsc -b --noEmit`): 0 errors
- ESLint (`eslint . --max-warnings 0`): 0 errors, 0 warnings
- Web Production Build (`vite build`): Clean build in 1.09s
- Punctuation & Style (`python3 -m scripts.check_no_dashes --all`): 0 em-dash / en-dash errors

### Live Stack Visual Proof (Zero Legacy Mocked Screenshots)
All legacy mocked `01-*.png`..`04-*.png` screenshots removed. Live screenshots present in `docs/qa/KAN-14/screenshots/`:
- `live-kan14-admin-auth-desktop-dark.png`
- `live-kan14-admin-auth-desktop-light.png`
- `live-kan14-groups-desktop-dark.png`
- `live-kan14-groups-desktop-light.png`
- `live-kan14-groups-mobile-dark.png`
- `live-kan14-groups-mobile-light.png`
- `live-kan14-members-desktop-dark.png`
- `live-kan14-members-desktop-light.png`
- `live-kan14-members-mobile-dark.png`
- `live-kan14-members-mobile-light.png`
- `live-kan14-project-settings-desktop-dark.png`
- `live-kan14-project-settings-desktop-light.png`
- `live-kan14-project-settings-members-desktop-light.png`

## Artifacts in `docs/qa/KAN-14/`
- `changed-files-manifest.txt`
- `git-diff.patch` (clean against 31aca8e across all 20 touched files, 0 docs/qa/* files inside)
- `unit-test-results.txt`
- `build-or-typecheck.txt`
- `live-fullstack-proof.txt`
- `message-to-reality-checker.md`
- `ui-specialist-review.md`
- `screenshots/` (13 live stack screenshots)

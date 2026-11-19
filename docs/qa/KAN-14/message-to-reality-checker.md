# Reality Checker Verification Hand-off: KAN-14

## Ticket Information
- Ticket ID: KAN-14 ([KB-P3-AUDIT-08])
- Title: Fix /workspaces/settings undefined event.key.toLowerCase() Crash (shortcuts.ts), Guard Nullable Settings Fields, and Align Workspace Members API Payloads
- Branch: feat/KAN-14
- Scoped Files Touched:
  - `kanban/web/src/app/shortcuts.ts`
  - `kanban/web/src/app/shortcuts.test.ts`
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
  - `kanban/web/src/features/settings/__tests__/ProjectSettingsPage.test.tsx`
  - `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`
  - `kanban/web/src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`
  - `kanban/web/e2e/workspaces/kan-14-workspace-settings.spec.ts`

## 4 Problems Addressed & Verified

### 1. Fix `event.key.toLowerCase()` Crash in Global Shortcut Handler (`shortcuts.ts`)
- Root cause: Synthetic `keydown` events dispatched by browser autofill extensions (Chrome / 1Password / Bitwarden) when `#tab-members` mounts `<input type="email">` and `<input type="password">` have `event.key === undefined`.
- Fix: In `matchesCombo` (called by `handleGlobalKeydown`), added entry guard:
  `if (typeof event.key !== 'string' || event.key.length === 0) return false;`
- Verification: Tested in `shortcuts.test.ts` with synthetic `KeyboardEvent` lacking `key`, empty strings, and non-string types. Verified in Playwright E2E by dispatching synthetic `keydown` events directly to the email and password inputs and the window.

### 2. Guard Unguarded `.toLowerCase()` Calls in `ProjectSettingsPage.tsx`
- Root cause: Live backend payloads or drafts can supply null/undefined for `display_name`, `kind`, or `role`, causing uncaught `TypeError: Cannot read properties of undefined (reading 'toLowerCase')`.
- Fix: Guarded nullable fields:
  - `((p.display_name as string | null | undefined) ?? '').toLowerCase().includes(q)`
  - `((t.kind as string | null | undefined) ?? '').toLowerCase() === trashKindFilter.toLowerCase()`
  - `className={'kb-role-badge kb-role-' + ((m.role as string | null | undefined) ?? '').toLowerCase()}`
- Verification: Tested in `ProjectSettingsPage.test.tsx` with project items containing null `display_name`, trash items containing null `kind`, and member items containing null `role`.

### 3. Fix `p.handle` vs `p.principal` Live API Field Mismatch in `WorkspaceSettingsPage.tsx`
- Root cause: `GET /api/v1/admin/principals` and `GET /api/v1/admin/groups/{group_id}/members` return `"principal"` instead of `"handle"`. Front-end was reading only `p.handle`, resulting in empty or undefined member handles.
- Fix: Updated `WorkspacePrincipal` interface to include optional `principal?: string | null`. Updated all 7 rendering points across `#tab-members` and `#tab-groups` to resolve `p.handle ?? p.principal`.
- Verification: Tested in `WorkspaceSettingsPage.test.tsx` using live backend payloads `{ id, principal: '@alice', type: 'USER', role: 'WORKSPACE_MEMBER' }` without `handle`. Verified in Playwright E2E with full visual rendering.

### 4. Fix `DELETE /api/v1/admin/role-bindings` Missing `role` (422) & User Creation `email` Validation
- Root cause:
  - `DELETE /api/v1/admin/role-bindings` payload omitted `role`, causing backend `RoleBindingRequest.resolve_role_field` to reject with 422 Unprocessable Entity.
  - `handleCreateUser` submitted empty email strings directly to the backend.
- Fix:
  - In `handleRemoveMember`, resolves `memberRole = role ?? member?.role ?? member?.role_name ?? 'WORKSPACE_MEMBER'` and sends `role: memberRole` in DELETE body.
  - In `handleCreateUser`, validates `trimmedEmail = newEmail.trim()` inline and displays `Email is required for user provisioning.` error without firing network call.
- Verification: Tested in `WorkspaceSettingsPage.test.tsx` verifying DELETE payload includes `role: 'WORKSPACE_ADMIN'` and verifying missing email displays error state.

## Test Coverage & Quality Gates

### Unit Test Coverage (Vitest v8)
- Target: >= 95.10% line and branch coverage
- Achieved:
  - `kanban/web/src/app/shortcuts.ts`: 100% lines, 98.79% branch
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`: 100% lines, 95.66% branch
  - `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`: 100% lines, 95.51% branch
  - Total across all touched files: 100% lines, 95.99% branch (56 of 56 tests passing)

### Static Analysis & Linters
- TypeScript Typecheck (`tsc -b --noEmit`): 0 errors
- ESLint (`pnpm exec eslint`): 0 errors, 0 warnings
- Dash Check (`python3 -m scripts.check_no_dashes --all`): 0 em-dash / en-dash errors

### Playwright E2E Visual Proof
All 8 test configurations passed on Desktop (1440x900) and Mobile (390x844) viewports:
- `docs/qa/KAN-14/screenshots/01-members-tab-autofill-keydown-desktop.png`
- `docs/qa/KAN-14/screenshots/01-members-tab-autofill-keydown-mobile.png`
- `docs/qa/KAN-14/screenshots/02-members-tab-dark-mode-desktop.png`
- `docs/qa/KAN-14/screenshots/02-members-tab-dark-mode-mobile.png`
- `docs/qa/KAN-14/screenshots/03-groups-tab-principal-payload-desktop.png`
- `docs/qa/KAN-14/screenshots/03-groups-tab-principal-payload-mobile.png`
- `docs/qa/KAN-14/screenshots/04-groups-tab-dark-mode-desktop.png`
- `docs/qa/KAN-14/screenshots/04-groups-tab-dark-mode-mobile.png`

## Artifacts in `docs/qa/KAN-14/`
- `changed-files-manifest.txt`
- `git-diff.patch`
- `unit-test-results.txt`
- `build-or-typecheck.txt`
- `message-to-reality-checker.md`
- `screenshots/` (8 annotated screenshots)

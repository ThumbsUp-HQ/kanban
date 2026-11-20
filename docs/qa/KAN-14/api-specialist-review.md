# API Specialist Security & Architecture Audit Review: KAN-14

## Audit Metadata
- Ticket ID: KAN-14 ([KB-P3-AUDIT-08])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan14-cfe806e5`
- Target Branch: feat/KAN-14
- Base Commit: 31aca8e
- Head Commit: 6f34b61
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the API contracts, client-server payload bindings, security boundaries, and runtime fault-tolerance introduced in ticket KAN-14. The implementation resolves four specific defect categories across workspace settings and global shortcuts without introducing new dependencies or violating architectural layering.

All requirements for backend contract alignment, input validation, null safety, and security invariants have been verified against the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. `DELETE /api/v1/admin/role-bindings` Payload Alignment
- Endpoint: `DELETE /api/v1/admin/role-bindings`
- Contract Invariant: Backend endpoint in `kanban/api/v1/admin/principals.py` (`unbind_role_endpoint`) parses `RoleBindingRequest`. It explicitly enforces `target_role = body.role or body.role_name`. Omitting both triggers RFC 7807 422 Unprocessable Entity (`VALIDATION_FAILED`, "Role is required").
- Client Implementation: In `WorkspaceSettingsPage.tsx`, `handleRemoveMember` previously dispatched payload without the `role` field. It now resolves `memberRole = role ?? member?.role ?? member?.role_name ?? 'WORKSPACE_MEMBER'` and sends `{ principal_id, role: memberRole, scope_type: 'workspace' }`.
- Security & Boundary Check: The call includes the `X-CSRF-Token` header. Scoping is strictly confined to `scope_type: 'workspace'`. Backend `Depends(require_admin_aal2)` protection is maintained on the router.

### 2. Live API Principal Schema Compatibility
- Endpoint: `GET /api/v1/admin/principals` & `GET /api/v1/admin/groups/{group_id}/members`
- Contract Invariant: Backend returns `WorkspacePrincipal` models where the handle identifier is serialized under the key `"principal"` (e.g., `"@alice"`, `"@platform-team"`).
- Client Implementation: `WorkspacePrincipal` interface in `WorkspaceSettingsPage.tsx` was extended to include `principal?: string | null`. `formatHandle` safely resolves `p.handle ?? p.principal`, prepending `@` only when missing. Table display falling back to bare UUID prevents empty or broken DOM nodes when display names are omitted.

### 3. User Provisioning Input Validation (`POST /api/v1/admin/users`)
- Endpoint: `POST /api/v1/admin/users`
- Client Implementation: `handleCreateUser` now validates `trimmedEmail = newEmail.trim()` prior to dispatching network requests, displaying inline validation error `Email is required for user provisioning.` on blank inputs.
- Security Impact: Prevents unnecessary 422 round-trips and ensures clean client-side input validation.

### 4. Nullable Field Defense in `ProjectSettingsPage.tsx` & `shortcuts.ts`
- `shortcuts.ts`: In `matchesCombo`, synthetic autofill events dispatched by password managers with `event.key === undefined` or non-string values now hit `if (typeof event.key !== 'string' || event.key.length === 0) return false;`. This prevents uncaught `TypeError` crashes in the global keyboard listener.
- `ProjectSettingsPage.tsx`: Nullable guards `((p.display_name as string | null | undefined) ?? '').toLowerCase()` prevent unhandled client-side runtime crashes when processing draft or live database objects.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` endpoints remain guarded by `Depends(require_admin_aal2)`. Verified by `kanban/tests/auth/test_aal2_policy.py`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Suite & Coverage:
   - Vitest line coverage: 100% across all touched files.
   - Vitest branch coverage:
     - `shortcuts.ts`: 98.79%
     - `ProjectSettingsPage.tsx`: 95.66%
     - `WorkspaceSettingsPage.tsx`: 95.51%
     - Total: 95.99% (exceeds >= 95.10% threshold).
   - All 56 unit tests passing.
5. [x] Zero Em/En-Dashes: Verified 0 instances of `\u2014` or `\u2013` via `python3 -m scripts.check_no_dashes --all`.
6. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and `message-to-reality-checker.md` verified in `docs/qa/KAN-14/`.

---

## 5. Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-08)

- Target Branch: `fix/KAN-14-liveqa`
- Remediation Head Commit: `1a2f884`
- Remediation Scope:
  1. Modules Gating & 404 Console Error Elimination:
     - Gated `GET /api/v1/projects/:key/modules` queries in `ProjectSettingsPage.tsx` and `PropertiesRail.tsx` behind `modules_enabled !== false`.
     - In `railApi.ts`, gracefully handled 404 responses with code `MODULES_DISABLED` to return an empty array without browser console errors.
  2. Mobile Viewport Overflow & Form Validation:
     - In `ProjectSettingsPage.css`, added `.kb-table-scroll-container` (`overflow-x: auto; max-width: 100%`) wrapping wide member tables, and added responsive `@media (max-width: 640px)` stacking rules for member addition forms.
     - In `WorkspaceSettingsPage.tsx`, updated email input placeholder to `"email@example.com"` with explicit `required` validation.
  3. Group Handle Normalization and Persistence:
     - In `kanban/api/v1/admin/principals.py`: When provisioning `type == "GROUP"`, normalized the supplied `body.handle` using `principal_service.normalize_handle()`, persisting the slug in principal name and returning `res["handle"] = f"@{group_name}"`.
  4. Admin Auth Cache Synchronization:
     - In `AuthStudioPage.tsx`, awaited user list refetch and invalidated query caches before modal close, ensuring newly provisioned members appear immediately.
  5. Test and Quality Verification:
     - 116 Vitest unit tests passing across touched components with >= 95% line coverage.
     - 13 backend Pytest tests passing with 97% coverage on `kanban.api.v1.admin.principals`.
     - Zero new dependencies, zero em-dashes or en-dashes, and clean static checks (`tsc`, `eslint`, `mypy`, `ruff`).

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts and security behaviors are verified clean. Handoff to `@ui-spec-2` for visual, UX, and accessibility verification of `docs/qa/KAN-14/screenshots/`.


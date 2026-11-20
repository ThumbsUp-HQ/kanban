# API Specialist Security & Architecture Audit Review: KAN-14

## Audit Metadata
- Ticket ID: KAN-14 ([KB-P3-AUDIT-08])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan14-rcfix-fd828a4a`
- Target Branch: fix/KAN-14-rc2
- Base Commit: 036216b
- Head Commit: b9ecb89
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the API contracts, client-server payload bindings, security boundaries, and runtime fault-tolerance introduced in ticket KAN-14 and its Clean-Room Reality-Checker Round 2 surgical remediation ([KB-P3-AUDIT-08]). The implementation resolves four specific defect categories across workspace settings and global shortcuts, normalizes principal handle representations across all admin endpoints, and eliminates unhandled exceptions from synthetic keyboard events.

All requirements for backend contract alignment, input validation, null safety, and security invariants have been verified against the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. `DELETE /api/v1/admin/role-bindings` Payload Alignment
- Endpoint: `DELETE /api/v1/admin/role-bindings`
- Contract Invariant: Backend endpoint in `kanban/api/v1/admin/principals.py` (`unbind_role_endpoint`) parses `RoleBindingRequest`. It explicitly enforces `target_role = body.role or body.role_name`. Omitting both triggers RFC 7807 422 Unprocessable Entity (`VALIDATION_FAILED`, "Role is required").
- Client Implementation: In `WorkspaceSettingsPage.tsx`, `handleRemoveMember` resolves `memberRole = role ?? member?.role ?? member?.role_name ?? 'WORKSPACE_MEMBER'` and sends `{ principal_id, role: memberRole, scope_type: 'workspace' }`.
- Security & Boundary Check: Scoping is strictly confined to `scope_type: 'workspace'`. Backend `Depends(require_admin_aal2)` protection is maintained on the router.

### 2. Live API Principal Schema Compatibility & Handle Normalization
- Endpoint: `GET /api/v1/admin/principals`, `GET /api/v1/admin/principals/{id}`, and `GET /api/v1/admin/groups/{group_id}/members`
- Contract Invariant: Backend returns `WorkspacePrincipal` models where both the canonical `"handle"` (`f"@{slug}"`) and backward-compatible `"principal"` fields are populated consistently.
- Backend Implementation (`kanban/admin/principal_service.py`):
  - `_format_principal_entry` now extracts `raw_principal` and ensures `handle = f"@{raw_principal.lstrip('@')}"` is returned alongside `email`, `role`, and `provider`.
  - `list_group_members` formats each group member via `_format_principal_entry`, providing `handle`, `email`, `role`, and `provider`.
  - `provision_group` and `provision_agent` return `handle`, `email: None`, `role: "WORKSPACE_MEMBER"`, and `provider: "LOCAL"`.
  - `get_principal_detail` populates both `principal` and `handle` with leading `@`.
- Backend Verification: In `kanban/tests/api/test_admin_principals.py`, verified assertions confirming `GET /api/v1/admin/principals` and `GET /api/v1/admin/groups/{id}/members` return `@alice`, `@infra-team`, `email`, `role`, and `provider`.

### 3. User Provisioning Input Validation (`POST /api/v1/admin/users`)
- Endpoint: `POST /api/v1/admin/users`
- Client Implementation: `handleCreateUser` validates `trimmedEmail = newEmail.trim()` prior to dispatching network requests, displaying inline validation error `Email is required for user provisioning.` on blank inputs.

### 4. Nullable Field Defense & Synthetic Key Guard
- `shortcuts.ts`: In `matchesCombo`, synthetic autofill events dispatched by password managers with `event.key === undefined` or non-string values now hit `if (typeof event.key !== 'string' || event.key.length === 0) return false;`.
- `useIssueKeyboardMap.ts`: At entry of `handleKeyDown`, added `if (typeof e.key !== 'string' || e.key.length === 0) return;`, preventing uncaught `TypeError` crashes on synthetic autofill keydown events. Verified by unit tests in `useIssueKeyboardMap.test.tsx`.
- `ProjectSettingsPage.tsx`: Nullable guards `((p.display_name as string | null | undefined) ?? '').toLowerCase()` prevent unhandled client-side runtime crashes when processing draft or live database objects.

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-08 Round 2)

- Target Branch: `fix/KAN-14-rc2`
- Remediation Head Commit: `b9ecb89`
- Remediations Verified:
  1. **Keyboard Map Event Key Guard:**
     - In `kanban/web/src/features/views/useIssueKeyboardMap.ts`: added `if (typeof e.key !== 'string' || e.key.length === 0) return;` at entry of `handleKeyDown`.
     - In `useIssueKeyboardMap.test.tsx`: added unit test verifying synthetic keydown events with `key === undefined` or `key === ''` produce zero exceptions.
  2. **Principal Service Handle Contract Synchronization:**
     - In `kanban/admin/principal_service.py`: populated `handle`, `email`, `role`, and `provider` across `_format_principal_entry`, `list_group_members`, `provision_group`, `provision_agent`, and `get_principal_detail`.
     - In `kanban/tests/api/test_admin_principals.py`: added assertions verifying `GET /api/v1/admin/principals` and `GET /api/v1/admin/groups/{id}/members` return `handle` (`@alice`, `@infra-team`), `email`, `role`, and `provider`.
  3. **Quality Gates & Evidence Packet:**
     - Vitest: 137 unit tests passing across 7 suites (`useIssueKeyboardMap.ts` 98.03% lines, 94.89% branches, 100% functions).
     - Pytest: 16 unit tests passing (`principal_service.py` 96%, `principals.py` 97%).
     - Static checks: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `vite build` (clean in 1.29s), `ruff check` (clean), `mypy` (clean).
     - Punctuation: 0 em-dashes and 0 en-dashes across all code, tests, and documentation.
     - Evidence packet: `git-diff.patch` cleanly generated against `31aca8e` with zero `docs/qa/` files included.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` endpoints remain guarded by `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Suite & Coverage:
   - Backend: `principal_service.py` 96% and `principals.py` 97% line and branch coverage (16 pytest tests passing).
   - Frontend: 137 vitest unit tests passing with >= 95% coverage on touched modules.
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy`, `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and screenshots verified in `docs/qa/KAN-14/`.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, principal handle serialization, and test evidence are verified clean. Ready for final coordinator merge into `main`.

# Verification Audit Narrative: KANBA-192 ([KB-WS-PROJ])

- **Ticket**: `KANBA-192` (`[KB-WS-PROJ]`: Fix Default Workspace Project Creation 403, Workspace Switch 403 & Live UI Sync, /objects/KAN/access 422 on Page Load, and Independent Sidebar Project Expand)
- **Author**: `ws-proj-builder`
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/e1f74689-a7a3-4ad2-818b-738c8f3eeab1/swarm-ws-proj-builder-0069c8a6`
- **Branch**: `feat/kanba-192`

---

### 1. Implementation Summary & Invariants

1. **Alembic Forward Migration (`p4_21_workspace_project_rbac_fix`)**:
   - Single linear Alembic forward migration chained strictly from `p4_20_user_personal_settings` (`down_revision = "p4_20_user_personal_settings"`).
   - Generated via official tooling: `uv run kanban-ctl db new-migration p4_21_workspace_project_rbac_fix --message "workspace project rbac fix" --template func`.
   - Database files:
     - `database/migrations/versions/p4_21_workspace_project_rbac_fix.py`
     - `database/migrations/sql/p4_21_workspace_project_rbac_fix.up.sql`
     - `database/migrations/sql/p4_21_workspace_project_rbac_fix.down.sql`
     - `database/tests/migrations/test_p4_21_workspace_project_rbac_fix_migration.py`
   - Validated with:
     - `uv run kanban-ctl db check-migrations --static-only` (OK: All 60 migrations valid. Single head: `p4_21_workspace_project_rbac_fix`).
     - `uv run pytest database/tests/migrations/test_p4_21_workspace_project_rbac_fix_migration.py database/tests/test_migration_consistency_static.py database/tests/test_p1_17_models.py database/tests/test_p1_14_rls_catalog.py` (23 passed).

2. **Backend Project Creation RBAC (`kanban/services/projects.py`)**:
   - Resolved project creation 403 for members in workspaces.
   - `_require_project_creator()` in `kanban/services/projects.py` now permits users with `WORKSPACE_MEMBER` role within the active workspace, satisfying the multi-tenant project bootstrapping contract.

3. **Workspace Switch & CSRF Cookie Synchronization (`kanban/api/v1/workspaces.py`, `kanban/auth/sessions/csrf.py`)**:
   - Hardened `switch_workspace_endpoint()` in `kanban/api/v1/workspaces.py`: extracts active session cookie and resets CSRF tokens cleanly on switch.
   - In `kanban/auth/sessions/csrf.py`, `extract_csrf_cookie()` prioritizes the secure prefix `__Host-kb_csrf` before falling back to `kb_csrf`, preventing stale cookie collision when switching across environments or sessions.
   - Comprehensive test case added: `test_case_9_multi_workspace_switch_roundtrip_project_creation` in `kanban/tests/api/test_workspaces_api.py`, verifying A -> B -> A switch roundtrip under Row Level Security (`FORCE RLS`).

4. **Object Reference Parsing & Access Endpoint (`kanban/services/object_ref.py`, `kanban/api/v1/objects_access.py`)**:
   - `resolve_object_ref()` in `kanban/services/object_ref.py` updated to accept `ref: str | uuid.UUID` and safely convert with `str(ref).strip()`.
   - In `kanban/api/v1/objects_access.py`, endpoint path parameter typed as `object_id: str` and resolved via `resolve_object_ref(db, current_user.tenant_id, object_id)`.
   - Eliminates the 422 Unprocessable Entity error when requesting `/api/v1/objects/KAN/access` or `/api/v1/objects/KAN-1/access` on page load.
   - Verified via `test_case_8_objects_access_and_kill_switch` and `test_objects_access_handlers_direct_unit` in `kanban/tests/api/test_objects_access_endpoint.py`.

5. **Sidebar Independent Project Expand & Live Workspace UI Sync (`kanban/web/src/app/Sidebar.tsx`, `Sidebar.css`)**:
   - Migrated project expand state from a single boolean to independent per-project dictionary: `expandedProjects: Record<string, boolean>`.
   - Clicking collapse (arrow right) on Project A preserves Project B expanded (arrow down) with its subitems intact.
   - Workspace switching triggers live project list and active workspace state update without full page reload.
   - Pure network helper functions `fetchWorkspaces()` and `fetchProjects()` prevent side-effect setState recursion.
   - `CreateProjectModal` updates project list cleanly and handles both CustomEvent with detail and default events without unhandled null exceptions.

6. **Frontend CSRF Precedence (`kanban/web/src/api/client.ts`, `kanban/web/src/features/auth/useSessionGuard.ts`)**:
   - Aligned client cookie extraction to strictly prioritize `__Host-kb_csrf` over `kb_csrf`.

7. **The 7 Vitest Regression Fixes from Main**:
   - Fix 1: `kanban/web/src/app/CommandPalette.test.tsx:377`: Updated search term to `/Go to System Storage, Backups & Deployment/` matching KANBA-188 rename.
   - Fix 2: `kanban/web/src/features/auth/AuthCardButton.test.tsx`:
     - Lines 49 & 166: Updated OIDC start URL assertion to include `&remember_me=1`.
     - Line 129: Clamped long provider display names at 80 characters with `...` and added `title={longName}` attribute in `AuthCardButton.tsx`, while maintaining KANBA-186 200% zoom text wrapping.
   - Fix 3: `kanban/web/src/features/auth/LdapLoginForm.test.tsx`: Updated `submitLdapLogin` mock assertion to expect `remember_me: true`. Verified `LoginPage.test.tsx` passes.
   - Fix 4: `kanban/web/src/features/workflows/__tests__/AttachHookDialog.test.tsx:80` & `workflowCoverageBooster.test.tsx:1085`: Updated label lookups to align with plain-English sandbox copy ("Built-in Formula Sandbox (WebAssembly)").

---

### 2. Forensic Proof Bundle Checklist

| Artifact | Description | Status |
| :--- | :--- | :--- |
| `docs/qa/KANBA-192/git-diff.patch` | Clean patch of changes against `main` excluding `docs/qa/KANBA-192/` | VERIFIED |
| `docs/qa/KANBA-192/changed-files-manifest.txt` | Complete manifest of all changed files relative to `main` | VERIFIED |
| `docs/qa/KANBA-192/unit-test-results.txt` | Raw output of 23 pytest tests + 178 Vitest test files (1893 passed, 0 failures) | PASS (100%) |
| `docs/qa/KANBA-192/build-check.txt` | `make check` (ruff, mypy, lint-imports, check_no_dashes, check-migrations) + frontend typecheck, lint, build | PASS |
| `docs/qa/KANBA-192/contract-sample.json` | Sample payloads for `POST /api/v1/projects`, `POST /api/v1/workspaces/{id}/switch` (A -> B -> A), `GET /api/v1/objects/KAN/access` | VERIFIED |
| `docs/qa/KANBA-192/screenshots/` | Annotated Playwright screenshots across desktop (1440x900), tablet (1024x768), mobile (390x844) | VERIFIED |
| `docs/qa/KANBA-192/message-to-reality-checker.md` | Narrative verification manifest for passive forensic QA audit | VERIFIED |

---

### 3. Screenshot Index

1. `01-project-creation-default-workspace-{desktop,tablet,mobile}.png`:
   - Demonstrates accessible Create Project modal dialog open in default workspace with sanitized name, identifier, and description inputs, valid CSRF token, and zero console errors.
2. `02-sidebar-independent-projects-{desktop,tablet,mobile}.png`:
   - Demonstrates independent expand and collapse across multiple projects (Project KAN collapsed with arrow right, Project INFRA expanded with arrow down showing subitems Work Items, Cycles, Modules, Views, Docs).
3. `03-live-workspace-switch-{desktop,tablet,mobile}.png`:
   - Demonstrates live workspace switching: active workspace brand anchor with checkmark badge on active item, live switch action, and synchronous update of dropdown, breadcrumb, and project list without full page reload.

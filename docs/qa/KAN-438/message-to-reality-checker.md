# Verification Proof & Hand-off: KAN-438

## Ticket Overview
- **Ticket ID:** KAN-438
- **Title:** [FEAT][WORKFLOWS] System-Wide & Workspace Default Workflow Hook Templates Inherited by New Projects (Removable at Project Level)
- **Branch:** `feat/KAN-438-default-workflow-hook-templates`
- **Base Commit:** `a6967d0fc893d0f4ed14ecc8139c0fb746092367`
- **Author:** b-kan438

---

## 1. Summary of Changes

### Database & Alembic Migration #86 (`p6_24_default_workflow_hooks`)
- Added linear migration `database/migrations/versions/p6_24_default_workflow_hooks.py` with down-revision `p6_23_gate_timeouts_and_project_defaults`.
- Created table `default_workflow_hooks` with `scope_kind` (`system`, `workspace`), `workspace_id`, `from_state_name` (nullable, `* Any State` wildcard), `to_state_name`, `hook_kind` (`wasm_sync`, `agent_async`, `builtin`), `sort_rank`, `is_enabled`, `wasm_module_sha256`, `agent_definition_id`, `agent_slug`, `allowed_mutable_fields`, `failure_policy`, `timeout_ms` (1000..600000 ms), and `max_rework_attempts` (1..20).
- Check constraints enforce:
  - System templates must have `workspace_id IS NULL` and `agent_definition_id IS NULL` (strictly using `agent_slug` e.g. `'reality-checker'` to avoid cross-tenant UUID binding and leakage).
  - Workspace templates must have `workspace_id IS NOT NULL`.
  - Non-null `wasm_module_sha256` must be exactly 32 bytes (`octet_length = 32`).
  - Unique index `uq_default_workflow_hooks_scope_ws_name` on `(scope_kind, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name))` preventing duplicate template names per scope.
- Enforced `FORCE ROW LEVEL SECURITY` with `SELECT` policy allowing system templates or workspace-scoped templates, and `INSERT/UPDATE/DELETE` policies requiring workspace admin or server admin.
- Added `inherited_from_template_id UUID NULL REFERENCES default_workflow_hooks(id) ON DELETE SET NULL` on `workflow_transition_hooks` with index.
- Provided clean downgrade `.down.sql` tested in `database/tests/migrations/test_p6_24_default_workflow_hooks_migration.py`.
- Updated SQLAlchemy ORM models in `database/models/workflow.py` (`DefaultWorkflowHook` and `WorkflowTransitionHook.inherited_from_template_id`), passing `database/tests/test_p1_17_models.py` and `database/tests/test_p1_14_rls_catalog.py`.

### Backend Services & API Endpoints
- Implemented `materialize_default_workflow_hooks(...)` in `kanban/workflows/default_hooks.py`, matching templates case-insensitively to project states and resolving agent slugs across system/workspace scopes. Disabled workspace templates suppress same-named system templates.
- Hooked copy-on-create materialization into both project creation paths:
  1. `kanban/services/projects.py` (`create_project`)
  2. `kanban/projects/blueprint_service.py` (`apply_blueprint`, executed after state deletions so state lifecycle guards pass)
- Added Admin CRUD router `/api/v1/admin/default-workflow-hooks` (`kanban/api/v1/admin/default_workflow_hooks.py`) protected by `Depends(require_admin_aal2)` and role checks (Server Admin for system, Workspace Admin for workspace templates; cross-workspace operations strictly rejected with HTTP 403 `CROSS_WORKSPACE_FORBIDDEN`).
- Added workspace convenience routes `/api/v1/workspaces/{workspace}/default-workflow-hooks` (`GET`, `POST`, `PATCH /{template_id}`, `DELETE /{template_id}`).
- Added project sync route `POST /api/v1/projects/{project}/workflow-hooks/sync-defaults` in `kanban/api/v1/workflow_hooks.py`.
- Exposed `inherited_from_template_id` and `inherited_from_scope` on `WorkflowHookResponse`.
- When an inherited hook is removed or disabled on a project (`DELETE /api/v1/workflow-hooks/{hook_id}`), only that project's `WorkflowTransitionHook` row is modified or deleted, preserving default templates and sibling projects.

### Frontend Studio UI & OpenAPI Parity
- Created `DefaultWorkflowHooksStudio.tsx` in `kanban/web/src/features/workflows/`:
  - System templates management at `/admin/workflows` (linked in `AdminStudioSubnav.tsx` under `serverOnly: true`, registered in `routes.tsx`, linked in `Topbar.tsx` avatar menu).
  - Workspace templates management in `WorkspaceSettingsPage.tsx` under the `workflows` tab (`/workspaces/settings/workflows`).
  - Conditional input fields based on `formHookKind`:
    - `agent_interceptor` (`agent_async`): renders required `Agent Slug *` input (`data-testid="template-agent-slug-input"`), sets `wasm_module_sha256 = null`.
    - `wasm_validator` (`wasm_sync`): hides agent input, renders required `Wasm Module SHA-256 *` hex digest input (`data-testid="template-wasm-sha-input"`), sets `agent = null, agent_slug = null`.
    - `builtin`: renders `Builtin Guard *` selector (`data-testid="template-builtin-select"`) populated from verified builtin formulas (`qa-proof-validator`, `security-invariant-validator`, `auto-label-mutator`), sets `agent = null, agent_slug = null`.
    - Edit dialog populates `formWasmSha256` from `tpl.wasm_module_sha256`.
  - Standard `.workflow-dialog` class hierarchy with Escape key handler and `.workflow-form-grid-2` responsive collapse on mobile.
  - Strict UI theme variable usage (`var(--bg-surface)`, `var(--border-subtle)`, `var(--fg-secondary)`, etc.) for dark/light mode compatibility.
  - Client-side validation for timeout range `[1000, 600000]` ms and required fields.
  - `fetchDefaultWorkflowHooks` in `api.ts` does NOT swallow errors; HTTP 403 / 500 / AAL2 errors propagate cleanly to render the error alert banner while suppressing misleading empty states.
- Updated `HookPipelineRow.tsx` with an `Inherited from Default` badge (`data-testid="hook-inherited-badge-{hook.id}"`) using `.hook-inherited-badge` token styles and enabled Project Admins to disable, edit, or detach hooks.
- Added `Sync Default Hooks` button (`data-testid="sync-default-hooks-btn"`) on `WorkflowStudioPage.tsx` with robust error alert banner on failure (`role="alert"`).
- Updated API client functions in `kanban/web/src/features/workflows/api.ts`.
- Exported OpenAPI specification to `kanban/web/openapi.json` and generated TypeScript definitions at `kanban/web/src/api/schema.gen.ts`.

---

## 2. Test Execution & Evidence

### Test Logs
- `docs/qa/KAN-438/build-check.txt`:
  - `ruff check .`: All checks passed.
  - `ruff format --check .`: 2908 files already formatted.
  - `mypy`: Success (0 errors in 1383 source files).
  - `lint-imports`: Contracts kept (2 kept, 0 broken).
  - `scripts.check_no_dashes`: Clean (strictly zero Unicode dashes).
  - `database.migrations.cli check-migrations --static-only`: All 86 migrations valid. Single head: `p6_24_default_workflow_hooks`.
- `docs/qa/KAN-438/unit-test-results.txt`:
  - `kanban/tests/workflows/test_default_workflow_hooks.py`: 10 passed (system/workspace inheritance, detach/non-agentic issue tracker behavior, RBAC 403 / AAL2 checks, cross-tenant isolation, admin bounds and 409 conflict validation, disabled workspace template suppression, blueprint inheritance, wasm & builtin inheritance, and cross-field rejection validations).
  - `database/tests/migrations/test_p6_24_default_workflow_hooks_migration.py`: 1 passed (full migration upgrade/downgrade cycle).
  - `kanban/tests/security/test_admin_routes_protected.py`: 2 passed (`/api/v1/admin/default-workflow-hooks` protected).
  - `DefaultWorkflowHooksStudio.test.tsx`: 13 passed (vitest).
- `docs/qa/KAN-438/changed-files-manifest.txt`: List of all touched files.
- `docs/qa/KAN-438/git-diff.patch`: Complete patch relative to main base commit.

### Responsive Screenshot Matrix
Captured 20 screenshots in `docs/qa/KAN-438/screenshots/`:
1. `01-admin-default-workflow-hooks-desktop-light-1440x900.png`
2. `01-admin-default-workflow-hooks-desktop-dark-1440x900.png`
3. `01-admin-default-workflow-hooks-tablet-768x1024.png`
4. `01-admin-default-workflow-hooks-mobile-390x844.png`
5. `02-add-default-hook-template-dialog-desktop-light-1440x900.png`
6. `02-add-default-hook-template-dialog-desktop-dark-1440x900.png`
7. `02-add-default-hook-template-dialog-tablet-768x1024.png`
8. `02-add-default-hook-template-dialog-mobile-390x844.png`
9. `03-project-workflow-inherited-hooks-desktop-light-1440x900.png`
10. `03-project-workflow-inherited-hooks-desktop-dark-1440x900.png`
11. `03-project-workflow-inherited-hooks-tablet-768x1024.png`
12. `03-project-workflow-inherited-hooks-mobile-390x844.png`
13. `04-workspace-default-workflow-hooks-desktop-light-1440x900.png`
14. `04-workspace-default-workflow-hooks-desktop-dark-1440x900.png`
15. `04-workspace-default-workflow-hooks-tablet-768x1024.png`
16. `04-workspace-default-workflow-hooks-mobile-390x844.png`
17. `desktop-light-1440x900.png`
18. `desktop-dark-1440x900.png`
19. `tablet-768x1024.png`
20. `mobile-390x844.png`

---

## 3. Invariants & Verification Checklist
- [x] Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`).
- [x] No modifications to `k.hackedyour.info` / `192.168.1.101`.
- [x] Linear single-head Alembic migration chain #86 (`p6_24_default_workflow_hooks`).
- [x] `FORCE ROW LEVEL SECURITY` active with explicit RLS policies on `default_workflow_hooks`.
- [x] Admin routes protected with `require_admin_aal2` dependency.
- [x] Non-destructive project detaching allows non-agentic projects to delete inherited hooks without mutating default templates.
- [x] Shared test database left running for swarm peers per coordinator instructions.

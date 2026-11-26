# Round-2 API & Database Specialist Review - KAN-438

**Ticket:** `KAN-438` - `[FEAT][WORKFLOWS] System-Wide & Workspace Default Workflow Hook Templates Inherited by New Projects (Removable at Project Level)`
**Commit:** `81c568ac`

---

## Summary

All four blocking items (`B1` through `B4`) and all non-blocking observations from Round 1 have been cleanly remediated and verified in the codebase, migration SQL, ORM models, OpenAPI/TypeScript schemas, and QA artifacts.

---

## Remediation Verification

### B1. Cross-Tenant `agent_definition_id` Prevention & Workspace Ownership (`VERIFIED`)
- **Database Check Constraint:** `database/migrations/sql/p6_24_default_workflow_hooks.up.sql` enforces `CONSTRAINT chk_default_workflow_hooks_system_agent_def CHECK (scope_kind <> 'system' OR agent_definition_id IS NULL)`, mirrored in `DefaultWorkflowHook.__table_args__` in `database/models/workflow.py`.
- **API Rejection on System Scope:** `admin_create_default_hook` and `admin_update_default_hook` in `kanban/api/v1/admin/default_workflow_hooks.py` reject any non-null `agent_definition_id` or UUID-formatted `agent` on `'system'` templates with HTTP `422` (`SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG`) and keep `agent_definition_id = None`.
- **Materialization Isolation:** `materialize_default_workflow_hooks` in `kanban/workflows/default_hooks.py` explicitly ignores `tpl.agent_definition_id` when `tpl.scope_kind == "system"` and resolves `tpl.agent_slug` strictly within `AgentDefinition.workspace_id == workspace_id`.
- **Workspace Ownership & Stale Agent Cleanup:** `admin_create_default_hook`, `admin_update_default_hook`, and `admin_delete_default_hook` validate `target_ws_id != caller.workspace_id and not is_server_admin` -> HTTP `403` (`CROSS_WORKSPACE_FORBIDDEN`). Workspace template `agent_definition_id` and UUID `agent` inputs are verified against `AgentDefinition.workspace_id == target_ws_id` (`422 AGENT_NOT_FOUND`), and updating `agent` or `agent_slug` on `PATCH` cleanly refreshes or clears `template.agent_definition_id`.

### B2. `max_rework_attempts` Parity, Unique Name Index & Disabled Workspace Override (`VERIFIED`)
- **`max_rework_attempts` Alignment:** `p6_24_default_workflow_hooks.up.sql`, `DefaultWorkflowHook` in `database/models/workflow.py`, `DefaultWorkflowHookCreateRequest`, and `DefaultWorkflowHookUpdateRequest` all enforce `BETWEEN 1 AND 20` (`ge=1, le=20`), matching `ck_workflow_transition_hooks_max_rework` on `workflow_transition_hooks`.
- **Unique Template Name Index:** `p6_24_default_workflow_hooks.up.sql` creates `uq_default_workflow_hooks_scope_ws_name` on `(scope_kind, COALESCE(workspace_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name))`, mirrored in `DefaultWorkflowHook.__table_args__` and cleanly dropped in `p6_24_default_workflow_hooks.down.sql`. `_assert_unique_name` returns HTTP `409` (`TEMPLATE_NAME_CONFLICT`).
- **Disabled Workspace Suppression:** `materialize_default_workflow_hooks` queries both enabled and disabled templates, merges workspace overrides onto system templates by `tpl.name.strip().casefold()`, and filters `if t.is_enabled` afterward so a disabled workspace template suppresses a same-named enabled system template.

### B3. Input Validation, Security Invariants, Ordering & Serialization (`VERIFIED`)
- **WASM SHA-256:** `p6_24_default_workflow_hooks.up.sql` and `DefaultWorkflowHook` enforce `chk_default_workflow_hooks_wasm_len` (`octet_length = 32`), and `_validate_wasm_sha` verifies `ApprovedWasmModule` / `seed_builtin_wasm` / `BUILTIN_WASM_FORMULAS`.
- **Whitespace & Wildcards:** `@field_validator` methods reject whitespace-only `name` and `to_state_name` (`422`) and normalize `"*"` / whitespace `from_state_name` to `None`.
- **Strict `hook_kind`, Mutable Fields & CLI Policy:** Unrecognized `hook_kind` rejected with `422`; `_validate_mutable_fields` and `assert_runtime_argv` enforced.
- **`apply_blueprint` Ordering, Pre-Commit Serialization & Frontend Filter:** `materialize_default_workflow_hooks` runs after `# 3. State deletions` in `kanban/projects/blueprint_service.py`; `sync_default_workflow_hooks` serializes prior to `await session.commit()`; `fetchDefaultWorkflowHooks` in `kanban/web/src/features/workflows/api.ts` filters strictly by `scope_kind`.

### B4. Automated Tests, OpenAPI/TS Parity & Build Gates (`VERIFIED`)
- **Backend Tests (`docs/qa/KAN-438/unit-test-results.txt`):** 11/11 pytest tests passed across `test_default_workflow_hooks.py`, migration lifecycle, AAL2 route compliance, and route registration.
- **Frontend Tests (`docs/qa/KAN-438/unit-test-results.txt`):** 10/10 Vitest tests passed in `DefaultWorkflowHooksStudio.test.tsx`.
- **Static & Migration Checks (`docs/qa/KAN-438/build-check.txt`):** `ruff check .`, `ruff format --check .`, `mypy` (1383 source files), `lint-imports`, `check_no_dashes --all`, and `check-migrations --static-only` (86 migrations valid, single head `p6_24_default_workflow_hooks`) all passed.
- **OpenAPI & TypeScript Schema Parity:** `kanban/web/openapi.json` and `kanban/web/src/api/schema.gen.ts` match all endpoints and constraints.

Verdict: APPROVED

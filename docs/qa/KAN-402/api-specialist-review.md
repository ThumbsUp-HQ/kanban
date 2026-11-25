# API Specialist & Security Review: KAN-402

## Ticket Reference
- **Ticket ID**: `KAN-402` (`[KB-WORKSPACE-PROJECT-AI-AGENTS] Promote AI Providers & Autonomous Agents to Workspace & Project Level`)
- **Reviewer Persona**: API & Security Architect (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Branch**: `feat/KAN-402-workspace-project-ai-agents`
- **Base Commit**: `ea30b70a`
- **Head Commit**: `9e216dfe` (Feature commit `d59ce7fb`)
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. Executive Summary & Verification Objective

The backend changes in `KAN-402` promote AI Provider configurations and Autonomous Agent definitions from being strictly server-admin gated (`require_admin_aal2`) to first-class workspace- and project-scoped resources. This review specifically audits:
1. **Server Admin Route Protection Invariant**: Verification that 100% of `/api/v1/admin/*` routes strictly retain `Depends(require_admin_aal2)` without leakage, accidental unauthenticated exposure, or privilege escalation.
2. **Workspace & Project Scoping / Isolation**: Proper RBAC authorization enforcement via `_assert_admin_for_scope` (`WORKSPACE_ADMIN` for workspace providers/agents, `PROJECT_ADMIN` for project-scoped providers/agents, rejecting cross-project and non-admin calls).
3. **Agent Validation Route Parity & Integrity**: Inspection of `POST /api/v1/agent-definitions/{agent}:validate` (and alias `/validate`), ensuring `AgentDefinitionService.require_admin_role(session, agent_def.project_id)` enforces strict project/workspace admin checks and prevents arbitrary CLI argument injection or execution tampering.
4. **Clean-DB Test Isolation & Pass Rate**: Full execution of integration tests under `FORCE RLS` PostgreSQL session isolation, verifying pass rates, error handling, and zero regressions.
5. **Linting, Typing, and Public Documentation Standard**: Verification of zero warnings in `ruff`, clean type checks in `mypy` (679 files), clean `pnpm typecheck`, clean `pnpm lint`, and strict zero Unicode em/en-dashes (`check_no_dashes.py --all`).

---

## 2. API Architecture & Security Audit

### A. Router Architecture & Server Admin Protection
- **Router Isolation**:
  - `workspace_router` is mounted under `/api/v1/workspaces/{workspace}/ai-providers` in `kanban/api/v1/admin/ai_providers.py` and registered in `kanban/api/v1/__init__.py`.
  - The existing `admin_router` under `/api/v1/admin/ai/providers` remains untouched and explicitly declared with `dependencies=[Depends(require_admin_aal2)]`.
  - The agent definitions router (`kanban/api/v1/agent_definitions.py`) retains its `admin_router` under prefix `/admin/agent-definitions` with `dependencies=[Depends(require_admin_aal2)]`.
- **Automated Catalog Compliance**:
  - Automated security compliance test `kanban/tests/security/test_admin_routes_protected.py` was executed.
  - Asserted all 35 admin endpoints strictly enforce `require_admin_aal2` dependency guards. Zero violations detected.

### B. Scoping & RBAC Authorization Logic
- **`_assert_admin_for_scope(session, caller, project_id)`**:
  - When `project_id` is `None`: requires `WORKSPACE_ADMIN` (or `SERVER_ADMIN`). Plain members or project admins cannot mutate workspace providers.
  - When `project_id` is provided: checks `app_principal_has_role(project_id, ['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN'])`. Project admins can manage their own project's AI providers, but are strictly barred from other projects or workspace-level settings.
  - Tested negative scenarios:
    - Standard member attempting to create/update providers -> `403 Forbidden`.
    - Project Admin of Project A attempting to mutate Project B providers -> `403 Forbidden`.
    - Project Admin attempting to reorder workspace-level providers without project scope -> `403 Forbidden`.
- **Query Filtering & Entity Isolation**:
  - `reorder_providers` explicitly scopes by `AIProviderConfig.workspace_id == caller.workspace_id` and conditionally filters `AIProviderConfig.project_id == body.project_id` (or `project_id.is_(None)`). Row-level locks (`with_for_update()`) are applied within transaction scope.
  - `list_providers` and `list_definitions` accept optional `project_id: uuid.UUID | None` query parameter. Unscoped queries return workspace-scoped resources, preventing cross-tenant leakage.

### C. Agent Definition Validation Route Hardening
- **Endpoint Design**:
  - Added public router endpoints:
    - `POST /api/v1/agent-definitions/{agent}:validate` (operation id: `validate_agent_definition_colon`)
    - `POST /api/v1/agent-definitions/{agent}/validate` (operation id: `validate_agent_definition_slash`)
  - Admin counterparts are preserved under `/admin/agent-definitions/{agent}:validate` with unique operation IDs to prevent OpenAPI schema collisions.
- **Security Invariants**:
  - Resolved through `AgentDefinitionService.get_by_ref(session, caller, agent)` which enforces tenant isolation against `caller.workspace_id`.
  - Explicit authorization check: `await AgentDefinitionService.require_admin_role(session, agent_def.project_id)` ensures callers hold either `WORKSPACE_ADMIN` (for workspace agents) or `PROJECT_ADMIN` (for project agents). Standard members receive `403 Forbidden`.
  - For `cli_pipe` agents, `validate_cli_args(agent_def.cli_args or [])` runs to guarantee no shell escaping or unauthorized argument switches are introduced.
  - Fixed-floor response timing (`timing_floor(floor_ms=25.0)`) prevents side-channel execution timing attacks.

---

## 3. Test Suite & Validation Evidence

### A. Python Backend Test Suite
Executed test suite against hermetic clean-DB PostgreSQL instance:
```bash
/home/adamoutler/kanban/.venv/bin/pytest kanban/tests/security/test_admin_routes_protected.py kanban/tests/api/test_workspace_project_ai_agents.py -v
```
**Results**:
- `test_assert_admin_routes_protected_compliance`: `PASSED`
- `test_multi_source_and_export_routes_registered`: `PASSED`
- `test_workspace_admin_ai_providers_lifecycle`: `PASSED` (Full CRUD, mock Ollama probe, probe-models, test-connection, disable, reorder, token budgets, activity ledger logging)
- `test_project_admin_ai_providers_scoping_and_isolation`: `PASSED` (Project admin CRUD, cross-project isolation, 403 authorization rejections)
- `test_workspace_and_project_agent_definitions_lifecycle`: `PASSED` (Workspace vs project agent creation, project query filtering, `:validate` and `/validate` routes, 403 member rejection, 404 missing agent)
- Total: **5 passed in 3.22s**

### B. Frontend Vitest Test Suite
Executed web unit and integration test suite:
```bash
pnpm vitest run src/features/admin-ai/__tests__/aiAdminApi.test.ts src/features/admin-agents/__tests__/AgentDefinitionEditorDrawer.test.tsx src/features/admin-agents/__tests__/AgentStudioPage.test.tsx src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx src/features/admin-ai/__tests__/AiStudioPage.test.tsx src/app/__tests__/MenuConsolidation_KAN363.test.tsx
```
**Results**:
- `aiAdminApi.test.ts`: 7/7 passed
- `AgentDefinitionEditorDrawer.test.tsx`: 4/4 passed
- `AgentStudioPage.test.tsx`: 25/25 passed
- `AiProviderEditorDrawer.test.tsx`: 42/42 passed
- `AiStudioPage.test.tsx`: 39/39 passed
- `MenuConsolidation_KAN363.test.tsx`: 8/8 passed
- Total: **125 passed across 6 test suites in 2.71s**

### C. Static Analysis & Build Hygiene
- `ruff check .`: 0 warnings, clean exit code 0.
- `mypy`: 679 source files checked, 0 errors, clean exit code 0.
- `pnpm typecheck`: Clean TypeScript compilation, 0 errors.
- `pnpm lint`: 0 warnings, clean exit code 0.
- `scripts/check_no_dashes.py --all`: 0 forbidden Unicode dashes across the codebase.

---

## 4. Final Verdict & Sign-Off

**`APPROVED`**

The implementation of `KAN-402` satisfies all security, API architecture, and role isolation mandates. Server admin AAL2 boundaries remain uncompromised, workspace and project role checks are enforced without tenant leakage, and comprehensive unit tests validate both positive and negative authorization flows.

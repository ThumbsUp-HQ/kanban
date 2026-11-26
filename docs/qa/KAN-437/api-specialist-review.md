# API & Database Specialist Review: KAN-437

**Ticket:** KAN-437 (`[FEAT][WORKFLOWS] Support Per-Project & Per-Hook Gate Timeouts up to 10 Minutes (600,000 ms) with Worker Claim-Lease Heartbeat Renewal`)
**Branch:** `feat/KAN-437-per-project-hook-timeouts-and-lease-heartbeat` (commit `87b93360`, base `7e161c07`)
**Reviewer Role:** Backend Architect (API & Database Specialist)

---

## 1. Executive Summary

Round-1 remediation at commit `87b93360` resolved both previously flagged blocking defects (`GateCoordinator.record_failure` timeout message resolution and OpenAPI/TypeScript schema description parity) as well as the `_heartbeat_lease` active-set termination guard. All schema, migration, timeout precedence, RLS session lifecycle, security, and build/test checks pass cleanly.

---

## 2. Verification Matrix

### 2.1 Alembic Migration #85 & ORM Parity - PASS
- **Linear Single-Head Chain:** `database/migrations/versions/p6_23_gate_timeouts_and_project_defaults.py` sets `revision = "p6_23_gate_timeouts_and_project_defaults"` and `down_revision = "p6_22_mcp_api_keys_capability_mask_boundary"`, matching `p6_22_mcp_api_keys_capability_mask_boundary.py`. `docs/qa/KAN-437/build-check.txt` confirms `OK: All 85 migrations valid. Single head: p6_23_gate_timeouts_and_project_defaults`.
- **Forward DDL (`database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.up.sql`):**
  - `agent_definitions`: replaces prior check constraint with `chk_agent_definitions_timeout_ms CHECK (timeout_ms BETWEEN 1000 AND 600000)`.
  - `projects`: adds nullable `default_gate_timeout_ms INTEGER NULL` with `chk_projects_default_gate_timeout_ms CHECK (default_gate_timeout_ms IS NULL OR default_gate_timeout_ms BETWEEN 1000 AND 600000)`.
  - `workflow_transition_hooks`: adds nullable `timeout_ms INTEGER NULL` with `chk_workflow_transition_hooks_timeout_ms CHECK (timeout_ms IS NULL OR timeout_ms BETWEEN 1000 AND 600000)`.
  - `workflow_hook_invocations`: adds `deadline_at TIMESTAMPTZ NULL` and partial index `idx_workflow_hook_invocations_deadline_at_running ON workflow_hook_invocations (deadline_at) WHERE status = 'running'`.
- **Downgrade DDL (`database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.down.sql`):**
  - Cleanly drops the partial index, `deadline_at`, `timeout_ms`, and `default_gate_timeout_ms` columns/constraints, clamps `agent_definitions.timeout_ms > 300000` back to `300000`, and restores `agent_definitions_timeout_ms_check CHECK (timeout_ms BETWEEN 1000 AND 300000)`.
  - `docs/qa/KAN-437/unit-test-results.txt` confirms `test_p6_23_gate_timeouts_and_project_defaults_migration_lifecycle` (upgrade -> downgrade -> upgrade) passed in 0.63s and `database/tests/test_p1_17_models.py` (7/7 tests) passed.
- **ORM Models:** `database/models/projects.py` (`Project`), `database/models/workflow.py` (`WorkflowTransitionHook`, `WorkflowHookInvocation`), and `database/models/agent_definition.py` (`AgentDefinition`) match the SQL DDL columns, nullability, partial index, and `CHECK` constraints.

### 2.2 Timeout Precedence & Bounds `[1000, 600000]` ms - PASS
- **Shared Resolver (`kanban/workflows/gate_types.py`):** `resolve_effective_gate_timeout_ms(hook_timeout_ms, project_default_timeout_ms, agent_timeout_ms, fallback_default_ms=60000)` implements strict precedence `hook -> project -> agent -> 60000` and clamps the integer result to `[1000, 600000]`.
- **Hooks Service (`kanban/workflows/hooks_service.py`):**
  - `WorkflowHookCreateRequest.timeout_ms` and `WorkflowHookUpdateRequest.timeout_ms` enforce `ge=1000, le=600000` (with `strict=True`, `extra="forbid"`).
  - `WorkflowHookService.update_hook` uses `"timeout_ms" in payload.model_fields_set`, permitting explicit clearing back to `None`.
  - `WorkflowHookResponse` exposes both `timeout_ms` (raw hook override) and `effective_timeout_ms` (computed via `resolve_effective_gate_timeout_ms`).
- **Async Gate Coordinator (`kanban/workflows/async_gate.py`):**
  - `AgentGateDispatcher.dispatch`, sequential `next_hook` scheduling in `GateCoordinator.record_decision` and `GateCoordinator.record_failure`, and `GateCoordinator.record_failure` fail-closed timeout reporting (lines 1130-1136) all resolve `timeout_ms` via `resolve_effective_gate_timeout_ms(hook_timeout_ms=hook.timeout_ms, project_default_timeout_ms=project.default_gate_timeout_ms if project else None, agent_timeout_ms=agent_def.timeout_ms if agent_def else None)`.
- **Gate Sweeper (`kanban/workflows/gate_sweeper.py`):**
  - `GateTimeoutSweeper.run_once` joins `Project` and outer-joins `AgentDefinition`, using `func.coalesce(WorkflowHookInvocation.deadline_at, fallback_deadline)` where `fallback_deadline` resolves `func.coalesce(WorkflowTransitionHook.timeout_ms, Project.default_gate_timeout_ms, AgentDefinition.timeout_ms, 60000)`.
- **Projects, Agent Definitions, AI Providers, and MCP:**
  - `kanban/api/v1/schemas/projects.py` (`ProjectCreate`, `ProjectPatch`, `ProjectResponse`), `kanban/services/projects.py`, and `kanban/api/v1/projects.py` support `default_gate_timeout_ms` (`1000..600000` or `null`, clearing via `model_fields_set` with activity logging).
  - `kanban/agents/schemas.py` (`AgentDefinitionCreate`, `AgentDefinitionPatch`), `kanban/api/v1/admin/ai_schemas.py` (`_MIN_TIMEOUT_MS = 1000`, `_MAX_TIMEOUT_MS = 600000`), `mcp/admin/tools/manage_ai_and_agent_runners.py`, and `agent/providers/{base,ollama,openai_provider,gemini}.py` consistently raise upper bounds to `600000` ms (`600.0` s).

### 2.3 Worker Claim-Lease Heartbeat Renewal & Fail-Closed `GATE_TIMEOUT` - PASS
- **`agent/gates/runner.py` (`poll_once` & `_heartbeat_lease`):**
  - `poll_once` claims `running` `agent_interceptor` rows using `FOR UPDATE SKIP LOCKED`, stamps `claimed_by_worker` and `claim_expires_at = now + timedelta(seconds=self.lease_ttl_s)`, resolves `timeout_ms` via `resolve_effective_gate_timeout_ms` (capped by `provider_timeout_ms` if configured), and commits/closes the `RLSSessionFactory.session(admin_ctx)` block before dispatching. Zero row locks or open DB transactions are held across LLM/CLI inference.
  - `_heartbeat_lease` sleeps `heartbeat_interval_s`, immediately breaks if `invocation_id not in self._active_invocations` (lines 720-721) or `now >= deadline_at` (lines 723-725), caps `new_expiry` at `deadline_at`, and opens a short-lived `RLSSessionFactory.session(admin_ctx)` transaction executing a parameterized `UPDATE workflow_hook_invocations SET claim_expires_at = :new_expiry WHERE id = :inv_id AND status = 'running' AND claimed_by_worker = :worker_id`.
  - Dispatch is wrapped in `asyncio.wait_for(self.worker.handle_dispatch(event), timeout=remaining_s)` against `deadline_at`, and `TimeoutError` invokes `self.record_failure(..., "GATE_TIMEOUT", invocation_id=inv_id, detail="Async agent gate exceeded deadline_at")`. `heartbeat_task` is cancelled and awaited in `finally:`.

### 2.4 OpenAPI Parity, Security Invariants, and Dash Policy - PASS
- **OpenAPI & TypeScript Schema Parity:**
  - `kanban/web/openapi.json` (lines 14186, 14444, 14550) and `kanban/web/src/api/schema.gen.ts` (lines 13011, 13059) match `kanban/api/v1/schemas/projects.py` identically for `ProjectCreate.default_gate_timeout_ms`, `ProjectPatch.default_gate_timeout_ms`, and `ProjectResponse.default_gate_timeout_ms`, as well as `WorkflowHookCreateRequest`, `WorkflowHookUpdateRequest`, `WorkflowHookResponse`, `AgentDefinitionCreate`, and `AgentDefinitionPatch`.
- **Security Invariants:**
  - Strict Pydantic validation (`extra="forbid"`, integer range `1000..600000`, boolean exclusion via `< 1000` check in `ai_schemas.py`), AAL2 enforcement on hook mutations (`WorkflowHookService.require_aal2`) and admin AI routes (`Depends(require_admin_aal2)`), parameterized SQL in `_heartbeat_lease`, and `RLSSessionFactory` binding verified.
- **Zero Unicode Em/En Dashes:**
  - `docs/qa/KAN-437/build-check.txt` confirms `uv run python -m scripts.check_no_dashes --all` executed without violations.
- **Verification Artifacts (`unit-test-results.txt` & `build-check.txt`):**
  - Backend unit, workflow, gate runner, model parity, and OpenAPI tests: 64 passed in 32.83s.
  - Migration lifecycle test: 1 passed in 0.63s.
  - Frontend Vitest suite: 4 test files, 130 tests passed in 5.07s.
  - Static & build checks: `ruff check`, `ruff format --check` (2897 files), `mypy` (1378 files), `lint-imports` (2 contracts kept, 0 broken), `check_no_dashes --all`, `check-migrations --static-only`, `tsc -b --noEmit`, `eslint . --max-warnings 0`, and `vite build` all passed cleanly.

### 2.5 Non-Blocking Observations
1. **API Integration Tests (`kanban/tests/workflows/test_per_project_gate_timeout.py`):** Tests 3 and 4 validate `ProjectCreate`/`ProjectPatch` and `WorkflowHookCreateRequest`/`WorkflowHookUpdateRequest` Pydantic schemas in memory rather than exercising `POST`/`PATCH` HTTP endpoints with `null` clearing against PostgreSQL (while Test 5 exercises HTTP issue transition and `GateTimeoutSweeper` against committed DB).
2. **N+1 Query in `WorkflowHookService.serialize_hook` (`kanban/workflows/hooks_service.py` lines 371-375):** `list_hooks` calls `serialize_hook` per hook, issuing one `SELECT Project.default_gate_timeout_ms` query per hook instead of passing the already-fetched project timeout. Minor optimization opportunity.
3. **Provider Cutoff Lower Bound (`agent/gates/runner.py` lines 348-349, 570-571):** `min(int(prov_timeout), base_timeout)` assumes `provider_row.settings_json["timeout_ms"] >= 1000`; clamping to `[1000, 600000]` guarantees provider settings cannot fail validation if legacy DB data contains a sub-1000ms value.

Verdict: APPROVED

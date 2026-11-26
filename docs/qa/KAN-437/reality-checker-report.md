# Integration Agent Reality-Based Report

## Reality Check Validation
- **Audit Mode:** Clean-room passive forensic audit of KAN-437 (`[FEAT][WORKFLOWS] Support Per-Project & Per-Hook Gate Timeouts up to 10 Minutes (600,000 ms) with Worker Claim-Lease Heartbeat Renewal`) on branch `feat/KAN-437-per-project-hook-timeouts-and-lease-heartbeat` (base `7e161c07`).
- **Artifacts Audited via `read_file`:**
  - `docs/qa/KAN-437/message-to-reality-checker.md`
  - `docs/qa/KAN-437/changed-files-manifest.txt` (45 changed/added files listed)
  - `docs/qa/KAN-437/git-diff.patch`
  - `docs/qa/KAN-437/unit-test-results.txt`
  - `docs/qa/KAN-437/build-check.txt`
  - `docs/qa/KAN-437/api-specialist-review.md` (`Verdict: APPROVED`)
  - `docs/qa/KAN-437/ui-specialist-review.md` (`Verdict: APPROVED`)
  - All 12 PNG screenshots in `docs/qa/KAN-437/screenshots/`
- **Independent Source Cross-Check:** Directly inspected `database/migrations/versions/p6_23_gate_timeouts_and_project_defaults.py`, `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.up.sql`, `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.down.sql`, `database/models/projects.py`, `database/models/workflow.py`, `database/models/agent_definition.py`, `database/tests/migrations/test_p6_23_gate_timeouts_and_project_defaults_migration.py`, `kanban/workflows/gate_types.py`, `kanban/workflows/__init__.py`, `kanban/workflows/hooks_service.py`, `kanban/workflows/async_gate.py`, `kanban/workflows/gate_sweeper.py`, `kanban/api/v1/schemas/projects.py`, `kanban/api/v1/projects.py`, `kanban/services/projects.py`, `kanban/agents/schemas.py`, `kanban/api/v1/admin/ai_schemas.py`, `kanban/tests/workflows/test_per_project_gate_timeout.py`, `agent/gates/runner.py`, `agent/gates/worker.py`, `agent/providers/base.py`, `agent/providers/gemini.py`, `agent/providers/ollama.py`, `agent/providers/openai_provider.py`, `agent/tests/gates/test_gate_runner_lease_heartbeat.py`, `agent/tests/gates/test_gate_runner_rls_session.py`, `agent/tests/providers/test_base_protocol.py`, `mcp/admin/tools/manage_ai_and_agent_runners.py`, and frontend sources/tests (`WorkflowStudioPage.tsx`, `AttachHookDialog.tsx`, `HookPipelineRow.tsx`, `TransitionRuleCard.tsx`, `workflows.css`, `ProjectSettingsPage.tsx`, `AgentDefinitionEditorDrawer.tsx`, `AiProviderEditorDrawer.tsx`, `WorkflowStudioPage.test.tsx`, `AttachHookDialog.test.tsx`).
- **QA Cross-Validation:** Confirmed both `docs/qa/KAN-437/api-specialist-review.md` (`Verdict: APPROVED`) and `docs/qa/KAN-437/ui-specialist-review.md` (`Verdict: APPROVED`). Round-1 remediation items (using `resolve_effective_gate_timeout_ms` in `GateCoordinator.record_failure`, `_heartbeat_lease` active-set fast exit, OpenAPI/`schema.gen.ts` regeneration, dark-mode CSS tokens in `workflows.css`, `.workflow-form-control` / `.workflow-form-hint`, mobile 44px touch targets and `white-space: nowrap` badge, client-side `[1000, 600000]` validation, and `activeOverridesCount` inclusion) are all verified present in the actual files and refreshed screenshots.

## Complete System Evidence
- **Database Migration #85 and ORM Parity:**
  - `database/migrations/versions/p6_23_gate_timeouts_and_project_defaults.py` links cleanly to `down_revision = "p6_22_mcp_api_keys_capability_mask_boundary"`.
  - `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.up.sql` updates `agent_definitions` (`chk_agent_definitions_timeout_ms CHECK (timeout_ms BETWEEN 1000 AND 600000)`), adds `projects.default_gate_timeout_ms INTEGER NULL` (`CHECK (default_gate_timeout_ms IS NULL OR default_gate_timeout_ms BETWEEN 1000 AND 600000)`), adds `workflow_transition_hooks.timeout_ms INTEGER NULL` (`CHECK (timeout_ms IS NULL OR timeout_ms BETWEEN 1000 AND 600000)`), and adds `workflow_hook_invocations.deadline_at TIMESTAMPTZ NULL` with partial index `idx_workflow_hook_invocations_deadline_at_running ON workflow_hook_invocations (deadline_at) WHERE status = 'running'`.
  - `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.down.sql` reverses all additions, clamps `agent_definitions.timeout_ms > 300000` to `300000`, and restores the `[1000, 300000]` constraint.
  - `database/models/projects.py`, `database/models/workflow.py`, and `database/models/agent_definition.py` match the SQL DDL.
- **Backend Precedence, API, Sweeper, and Worker Lease Heartbeat:**
  - `kanban/workflows/gate_types.py` (`resolve_effective_gate_timeout_ms`) enforces `hook -> project -> agent -> 60000` clamped to `[1000, 600000]` ms.
  - `kanban/api/v1/schemas/projects.py`, `kanban/services/projects.py`, and `kanban/api/v1/projects.py` expose `default_gate_timeout_ms` (`ge=1000, le=600000`, nullable, with `model_fields_set` clearing and activity logging).
  - `kanban/workflows/hooks_service.py` enforces `ge=1000, le=600000` on `WorkflowHookCreateRequest` and `WorkflowHookUpdateRequest`, supports clearing via `model_fields_set`, and exposes `timeout_ms` and `effective_timeout_ms` on `WorkflowHookResponse`.
  - `kanban/workflows/async_gate.py` computes `deadline_at` via `resolve_effective_gate_timeout_ms` across `AgentGateDispatcher.dispatch`, sequential hook handoffs, and `GateCoordinator.record_failure`.
  - `kanban/workflows/gate_sweeper.py` (`GateTimeoutSweeper.run_once`) joins `Project`, `WorkflowTransitionHook`, and `AgentDefinition` and evaluates `func.coalesce(WorkflowHookInvocation.deadline_at, fallback_deadline) <= now`.
  - `agent/gates/runner.py` claims rows with `FOR UPDATE SKIP LOCKED`, closes the DB session before dispatch, runs `_heartbeat_lease` every `heartbeat_interval_s` (default `20.0`s) opening short-lived `RLSSessionFactory.session(admin_ctx)` transactions to update `claim_expires_at` capped at `deadline_at`, stops when `invocation_id not in self._active_invocations` or `now >= deadline_at`, enforces `asyncio.wait_for(..., timeout=remaining_s)` recording `GATE_TIMEOUT` on `TimeoutError`, and cancels/awaits `heartbeat_task` in `finally:`.
  - `agent/providers/{base,gemini,ollama,openai_provider}.py`, `kanban/agents/schemas.py`, `kanban/api/v1/admin/ai_schemas.py`, and `mcp/admin/tools/manage_ai_and_agent_runners.py` all align on `600000` ms / `600.0` s maximum ceilings.
- **Visual System Evidence (`docs/qa/KAN-437/screenshots/`):**
  - `01-workflow-studio-default-timeout-desktop-light-1440x900.png` and `desktop-light-1440x900.png`: Clean light-mode layout showing `Project Default Gate Timeout` card, `600000 ms` badge, `600000` input, `60s`/`3m`/`5m`/`10m`/`Inherit`/`Save` controls, and `10m` pill on `QA Gatekeeper Helper`.
  - `01-workflow-studio-default-timeout-desktop-dark-1440x900.png` and `desktop-dark-1440x900.png`: Clean dark-mode `--bg-surface` panel, crisp `--fg-primary` heading, `--fg-secondary` description, and properly themed input/preset controls with zero contrast defects.
  - `01-workflow-studio-default-timeout-tablet-768x1024.png` and `tablet-768x1024.png`: Balanced tablet layout with zero clipping or overflow.
  - `01-workflow-studio-default-timeout-mobile-390x844.png` and `mobile-390x844.png`: Unbroken `600000 ms` badge pill, 44px touch-aligned input and buttons, and clean vertical stacking.
  - `02-attach-hook-timeout-override-desktop-light-1440x900.png`, `02-attach-hook-timeout-override-desktop-dark-1440x900.png`, `02-attach-hook-timeout-override-tablet-768x1024.png`, and `02-attach-hook-timeout-override-mobile-390x844.png`: `Attach Workflow Helper Hook` dialog shows `2 custom settings active`, `Per-Hook Timeout Override (ms)` input (`600000`), `Inherit`, `60s`/`3m`/`5m`/`10m` presets, `.workflow-form-hint` typography, and unobstructed sticky `Cancel` / `Attach Hook` footer across light/dark and desktop/tablet/mobile viewports.

## Integration Testing Results
- **Pytest Workflow, Gate Runner, Models, and OpenAPI Suites (`docs/qa/KAN-437/unit-test-results.txt`):** `64 passed in 32.83s` covering `test_per_project_gate_timeout.py` (5), `test_async_gate.py` (18), `test_gate_runner_lease_heartbeat.py` (3), `test_gate_runner_rls_session.py` (6), `test_base_protocol.py` (10), `test_p1_17_models.py` (7), and `test_export_openapi.py` (15).
- **Pytest Migration Lifecycle (`docs/qa/KAN-437/unit-test-results.txt`):** `1 passed in 0.63s` (`test_p6_23_gate_timeouts_and_project_defaults_migration_lifecycle`, upgrade -> downgrade -> upgrade). Total Pytest: `65/65` passed.
- **Vitest Frontend Unit Tests (`docs/qa/KAN-437/unit-test-results.txt`):** `4 passed (4)` files, `130 passed (130)` tests in `5.07s` (`AttachHookDialog.test.tsx` 17, `AiProviderEditorDrawer.test.tsx` 51, `WorkflowStudioPage.test.tsx` 18, `ProjectSettingsPage.test.tsx` 44).
- **Static Analysis and Production Build (`docs/qa/KAN-437/build-check.txt`):**
  - `uv run ruff check .`: All checks passed
  - `uv run ruff format --check .`: 2897 files already formatted
  - `uv run mypy`: Success: no issues found in 1378 source files
  - `uv run lint-imports`: Contracts: 2 kept, 0 broken
  - `uv run python -m scripts.check_no_dashes --all`: Passed with 0 dash violations
  - `uv run python -m database.migrations.cli check-migrations --static-only`: `OK: All 85 migrations valid. Single head: p6_23_gate_timeouts_and_project_defaults`
  - `tsc -b --noEmit`, `eslint . --max-warnings 0`, and `tsc -b && vite build`: Passed with 0 errors and 0 warnings (`built in 1.30s`).
- **Specification Compliance:** PASS across all 4 Definition of Done criteria.

## Comprehensive Issue Assessment
- **Issues from QA Still Present:** None. All Round-1 items raised by API and UI specialists were verified fixed at commit `87b93360`.
- **Critical Issues:** None.
- **Medium Issues:** None.
- **Non-Blocking Observations (Tracked from `docs/qa/KAN-437/api-specialist-review.md`):**
  1. `kanban/tests/workflows/test_per_project_gate_timeout.py` validates `ProjectCreate`/`ProjectPatch` and `WorkflowHookCreateRequest`/`WorkflowHookUpdateRequest` schemas directly in memory rather than exercising `POST`/`PATCH` HTTP endpoints for `null` clearing (HTTP transition + `GateTimeoutSweeper` are tested against committed DB in test 5).
  2. `WorkflowHookService.serialize_hook` (`kanban/workflows/hooks_service.py`) queries `Project.default_gate_timeout_ms` per hook during `list_hooks` (minor N+1 query opportunity).
  3. `agent/gates/runner.py` relies on `provider_row.settings_json["timeout_ms"]` already being validated `>= 1000` by `ai_schemas.py`; clamping lower bound to `1000` in `runner.py` would harden against legacy out-of-range DB JSON.

## Realistic Quality Certification
- **Overall Quality Rating:** Grade A (96/100)
- **Design Implementation Level:** Excellent
- **System Completeness:** 100% of KAN-437 specification and Definition of Done implemented and verified
- **Production Readiness:** READY

## Deployment Readiness Assessment
- **Status:** READY
- **Required Fixes Before Production:** None. All Definition of Done criteria, database migration roundtrip, RLS-safe lease heartbeat renewal, `GATE_TIMEOUT` fail-closed enforcement, `[1000, 600000]` ms validation across backend/agent/MCP/UI, OpenAPI parity, dual specialist approvals, `65/65` Pytest, `130/130` Vitest, `make check`, `vite build`, and 12 responsive light/dark Playwright screenshots are verified complete.
- **Timeline for Production Readiness:** Immediate merge/deployment eligible.
- **Revision Cycle Required:** NO

---
**Integration Agent:** TestingRealityChecker
**Assessment Date:** 2026-11-26
**Evidence Location:** `docs/qa/KAN-437/`
**Re-assessment Required:** No

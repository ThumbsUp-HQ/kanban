# Message to Reality-Checker: KAN-437

## Ticket Scope and Deliverable Summary
- **Ticket ID:** `KAN-437` (`[FEAT][WORKFLOWS] Support Per-Project & Per-Hook Gate Timeouts up to 10 Minutes (600,000 ms) with Worker Claim-Lease Heartbeat Renewal`)
- **Branch:** `feat/KAN-437-per-project-hook-timeouts-and-lease-heartbeat`
- **Base:** `7e161c07`
- **Visual Proof:** Responsive Playwright screenshots in `docs/qa/KAN-437/screenshots/` across 4 viewports (desktop-light-1440x900, desktop-dark-1440x900, tablet-768x1024, mobile-390x844) showing Project Default Gate Timeout control (`600000 ms` / `10m`) and Per-Hook Timeout Override input with presets.

## Architectural Implementation Summary

### 1. Database Migration #85 (`p6_23_gate_timeouts_and_project_defaults`) & SQL/ORM Parity
- **Migration Scripts:**
  - `database/migrations/versions/p6_23_gate_timeouts_and_project_defaults.py`
  - `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.up.sql`
  - `database/migrations/sql/p6_23_gate_timeouts_and_project_defaults.down.sql`
- **Schema & Model Changes:**
  - `agent_definitions`: Raised timeout check constraint from `[1000, 300000]` to `[1000, 600000]` ms (`chk_agent_definitions_timeout_ms`).
  - `projects`: Added nullable `default_gate_timeout_ms INTEGER NULL` with check constraint `[1000, 600000]` ms (`chk_projects_default_gate_timeout_ms`).
  - `workflow_transition_hooks`: Added nullable `timeout_ms INTEGER NULL` with check constraint `[1000, 600000]` ms (`chk_workflow_transition_hooks_timeout_ms`).
  - `workflow_hook_invocations`: Added nullable `deadline_at TIMESTAMPTZ NULL` with partial index on `(deadline_at) WHERE status = 'running'`.
  - Reversible `.down.sql`: Drops added column/constraints, clamps `agent_definitions.timeout_ms > 300000` to `300000`, and restores `[1000, 300000]` constraint. Full migration upgrade/downgrade roundtrip verified in `database/tests/migrations/test_p6_23_gate_timeouts_and_project_defaults_migration.py`.
  - ORM models updated in `database/models/agent_definition.py`, `database/models/projects.py`, `database/models/workflow.py`, with exact type/nullable parity verified in `database/tests/test_p1_17_models.py`.

### 2. Backend & Agent Runtime (`[1000, 600000]` ms + Precedence + Lease Heartbeat)
- **Shared Precedence Helper (`resolve_effective_gate_timeout_ms`):**
  - Implemented in `kanban/workflows/gate_types.py` (and re-exported in `kanban/workflows/__init__.py`). Resolves effective gate timeout following precedence: `hook.timeout_ms -> project.default_gate_timeout_ms -> agent.timeout_ms -> 60000`, clamped to `[1000, 600000]` ms.
- **Cap Expansion Across Schemas and Services:**
  - `kanban/workflows/hooks_service.py`: Raised `WorkflowHookCreateRequest.timeout_ms` and `WorkflowHookUpdateRequest.timeout_ms` bounds to `ge=1000, le=600000`; exposed `timeout_ms` and `effective_timeout_ms` on `WorkflowHookResponse`.
  - `kanban/api/v1/schemas/projects.py` & `kanban/services/projects.py` & `kanban/api/v1/projects.py`: Added `default_gate_timeout_ms: int | None = Field(default=None, ge=1000, le=600000)` on `ProjectCreateRequest`, `ProjectPatchRequest`, and `ProjectResponse`.
  - `kanban/agents/schemas.py`: Raised `timeout_ms` max to `600000` on `AgentDefinitionCreate` and `AgentDefinitionPatch`.
  - `kanban/api/v1/admin/ai_schemas.py`: Validates settings timeouts up to `600000` ms.
  - `agent/providers/base.py`, `ollama.py`, `openai_provider.py`, `gemini.py`: Raised deadline and timeout limits to `600000` ms / `600.0` s.
  - `mcp/admin/tools/manage_ai_and_agent_runners.py`: Raised JSON schema max to `600000`.
- **Async Gate Deadline & Sweeper:**
  - `kanban/workflows/async_gate.py`: Computes `effective_timeout_ms` via `resolve_effective_gate_timeout_ms` and sets both `inv.deadline_at = now + timedelta(milliseconds=effective_timeout_ms)` and `inv.output_json["deadline_at"]`. In `GateCoordinator.record_failure`, resolves effective timeout via `resolve_effective_gate_timeout_ms` ensuring sweeper vetoes report the true effective timeout.
  - `kanban/workflows/gate_sweeper.py`: Joins `Project`, `WorkflowTransitionHook`, and `AgentDefinition` to resolve fallback deadlines, and never expires running invocations whose `deadline_at` is still in the future.
- **Worker Claim-Lease Heartbeat Renewal (`agent/gates/runner.py`):**
  - Resolves `effective_timeout_ms` following the full precedence hierarchy.
  - Starts background `_heartbeat_lease` task during invocation handling that opens short-lived RLS DB sessions at configurable interval (`heartbeat_interval_s`, default `20.0`s) to renew `claim_expires_at = now + 60s`, preventing duplicate worker claim across long-running gates up to 10 minutes.
  - Deterministically cancels and awaits heartbeat task in `finally:`, with fast-exit check `if invocation_id not in self._active_invocations: break`.
  - If `deadline_at <= now`, stops renewal and marks failure with `GATE_TIMEOUT` (Fail-Closed veto).

### 3. Frontend UI & OpenAPI Parity (`kanban/web/`)
- `WorkflowStudioPage.tsx`: Added Project Default Gate Timeout control panel (`data-testid="project-gate-timeout-panel"`) with input, `60s`/`3m`/`5m`/`10m` presets, Inherit button, and Save button. Styled using CSS variables in `workflows.css` for consistent dark/light themes. Includes client-side validation for `[1000, 600000]` range with `role="alert"` errors.
- `ProjectSettingsPage.tsx`: Added Project Default Gate Timeout control under General Advanced section with presets and client-side bounds validation.
- `AttachHookDialog.tsx`: Removed agent default overwrite bug, added Per-Hook Timeout Override input with `60s`/`3m`/`5m`/`10m`/`Inherit` presets inside Advanced Hook Settings. Added client bounds validation and updated `activeOverridesCount` calculation.
- `HookPipelineRow.tsx`: Formats human-readable durations (`60s`, `3m`, `5m`, `10m`) with source tooltip (`hook override` / `project default` / `agent default`).
- `AgentDefinitionEditorDrawer.tsx` & `AiProviderEditorDrawer.tsx`: Updated max to `600000` ms with client-side bounds validation.
- OpenAPI & TypeScript Parity: Regenerated `kanban/web/openapi.json` and `kanban/web/src/api/schema.gen.ts`. All OpenAPI parity tests pass.

## Round-1 Specialist Review Feedback Addressed (CHANGES_REQUESTED -> Fixed)
1. **API Specialist Item 1 (Effective Timeout in Failure Records):** In `kanban/workflows/async_gate.py` (`GateCoordinator.record_failure`), updated timeout resolution to `resolve_effective_gate_timeout_ms` using hook, project default, and agent definition timeouts so sweeper veto comments accurately reflect the effective timeout.
2. **API Specialist Item 2 (OpenAPI Parity & Heartbeat Exit Guard):** Re-exported `kanban/web/openapi.json` and regenerated `schema.gen.ts`. Added invocation check in `runner.py` `_heartbeat_lease` loop to exit immediately when invocation is no longer active.
3. **UI Specialist Item 3 (Dark-Mode Semantic Variables):** Removed inline styling on `.workflow-project-timeout-panel` in `WorkflowStudioPage.tsx`, replacing it with CSS variables (`var(--bg-surface)`, `var(--border-subtle)`, `var(--fg-primary)`, `var(--fg-secondary)`) in `workflows.css`.
4. **UI Specialist Item 4 (Form Control Styling & Mobile Ergonomics):** Replaced `.workflow-input` with `.workflow-form-control` and added `.workflow-form-hint`. Set mobile control min-height to 44px for touch ergonomics.
5. **UI Specialist Item 5 (Mobile Title Badge No-Wrap):** Added `white-space: nowrap` to `.workflow-studio-title-badge` to prevent awkward line breaks on mobile viewports.
6. **UI Specialist Item 6 (Client Bounds Validation & NaN Guards):** Added `[1000, 600000]` range validation with visible `role="alert"` messages across `WorkflowStudioPage.tsx`, `AttachHookDialog.tsx`, `ProjectSettingsPage.tsx`, `AgentDefinitionEditorDrawer.tsx`, and `AiProviderEditorDrawer.tsx`.
7. **UI Specialist Item 7 (Advanced Overrides Count):** Included per-hook timeout override in `activeOverridesCount` pill in `AttachHookDialog.tsx`.
8. **Screenshots Refreshed:** Re-captured all 12 responsive Playwright screenshots with the new dark-mode tokens and client validation active.

## Verification Evidence and Quality Metrics
- **Pytest Unit & Migration Tests:** 65 of 65 tests passed (see `unit-test-results.txt`).
- **Vitest Frontend Unit Tests:** 130 of 130 tests passed across 4 test suites (see `unit-test-results.txt`).
- **Playwright Responsive Screenshots:** 12 screenshots captured in `docs/qa/KAN-437/screenshots/` for light and dark modes across desktop, tablet, and mobile viewports.
- **Codebase Checks:** `make check` passed with 0 errors, 0 warnings:
  - `ruff`: all checks passed
  - `ruff format`: all files formatted cleanly
  - `mypy`: 1378 source files clean
  - `lint-imports`: 2 kept, 0 broken
  - `check_no_dashes`: 0 dash violations across all files
  - `check-migrations --static-only`: all 85 migrations valid, single head `p6_23_gate_timeouts_and_project_defaults`
  - Frontend typecheck, lint, and build: 0 errors, 0 warnings.
- **Hermetic Cleanliness:** Database container cleanly torn down via `make testdb-down` with 0 lingering test containers.

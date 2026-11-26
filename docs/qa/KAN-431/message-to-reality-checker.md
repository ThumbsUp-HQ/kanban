# Message to Reality-Checker: KAN-431

## Ticket Scope & Deliverable Summary
- **Ticket ID:** `KAN-431` (`[BUG][WORKFLOW-UI] Fix Single-Agent Hook Select 422, Hardcoded kanban-main/60s Card Metadata, and Edit Agent Prompt Reset`)
- **Branch:** `fix/KAN-431-workflow-hook-and-agent-edit-ui`
- **Base:** `1bbc9981`
- **Visual Proof:** 15 zero-mock unclipped Playwright screenshots across 5 viewports (`1440x900` light/dark, `1024x768`, `768x1024`, `390x844`) against local Kanban server on port `18431` saved to `docs/qa/KAN-431/screenshots/`:
  * Screen 1: `01-attach-hook-agent-interceptor-<vp>.png` (AttachHookDialog showing Agent Transition Helper with top-level Agent Definition auto-selected without HTTP 422)
  * Screen 2: `02-hook-pipeline-card-metadata-<vp>.png` (HookPipelineRow showing dynamic attached agent timeout "180s", genuine "frontend-core (:ro mount)" repo badge when attached, and total omission of repo badge and fake "kanban-main" when repo access is none)
  * Screen 3: `03-agent-definition-edit-drawer-<vp>.png` (AgentDefinitionEditorDrawer in Edit mode showing preserved custom Markdown instructions from database "Review changes cleanly.")

## Root Cause & Architecture Fix Summary
1. **Fix Single-Agent `<select>` HTTP 422 and Promote `Agent Definition` to Top-Level (`kanban/web/src/features/workflows/AttachHookDialog.tsx`):**
   - **Root Cause:** When `hookKind === 'agent_interceptor'` and only 1 agent existed in the workspace, the `<select>` visually rendered that agent while the React state `agent` remained empty string `""`. Submitting the form sent an empty agent payload, causing `POST /api/v1/projects/<KEY>/workflow-hooks` to fail with HTTP 422 (`agent parameter is required for agent_interceptor hooks`). Furthermore, the field was buried inside the collapsed `<AdvancedSection>`.
   - **Resolution:** Derived `effectiveAgentSlug = validSelectedSlug || (agentDefinitions[0]?.slug ?? '')` during render to auto-bind single-agent selections without triggering cascading render side-effects. Promoted Agent Definition out of `<AdvancedSection>` into a top-level required field whenever `hookKind === 'agent_interceptor'`, allowing immediate submission without manual interaction.

2. **Remove Hardcoded `60s` and `kanban-main` Fallback Metadata (`kanban/web/src/features/workflows/HookPipelineRow.tsx`, `TransitionRuleCard.tsx`, `WorkflowStudioPage.tsx`, `kanban/workflows/hooks_service.py`):**
   - **Root Cause:** `HookPipelineRow.tsx` rendered `Repo: {hook.repo_binding_slug ?? 'kanban-main'} (:ro mount)` regardless of whether a repo was bound or access mode was `'none'`, and hardcoded `60s` timeout pills even when attached agents had custom timeouts (e.g., `180s` / `300s`). In addition, the backend `WorkflowHookResponse` did not populate `timeout_ms`, `repo_binding_slug`, or `repo_access_mode`.
   - **Resolution:** Updated `hooks_service.py` to resolve `timeout_ms` and `repo_access_mode` from the attached `AgentDefinition`, and resolve `repo_binding_slug` via `ProjectRepoBinding` only when `repo_access_mode != 'none'`. In `HookPipelineRow.tsx`, rendered repo badge only when `Boolean(hook.repo_binding_slug) && hook.repo_access_mode !== 'none'`. Formatted timeout dynamically as `${Math.round(timeout / 1000)}s` without hardcoded fallbacks. Propagated `agents` through `WorkflowStudioPage.tsx` and `TransitionRuleCard.tsx`.

3. **Preserve Saved `system_instructions_md` on Edit (`kanban/web/src/features/admin-agents/AgentDefinitionEditorDrawer.tsx`):**
   - **Root Cause:** Opening Edit mode reset `system_instructions_md` to default text because the agent list DTO did not guarantee the full instructions were populated, and the drawer did not fetch the full detail.
   - **Resolution:** Updated `AgentDefinitionEditorDrawer.tsx` to fetch the complete agent definition via `fetchAgentDefinition` on mount when editing, hydrating `system_instructions_md` while using `hasUserEditedInstructions` ref to ensure in-flight user edits are never overwritten.

## Verification Evidence & Quality Metrics
1. **Frontend Vitest Unit & Component Coverage:**
   - **Execution Command:** `pnpm --dir kanban/web test -- run src/features/workflows/__tests__/ src/features/admin-agents/__tests__/ --coverage --coverage.thresholds.branches=95`
   - **Pass Rate:** 127 of 127 tests passed across 7 test files in 8.95s (0 failures, 0 `act(...)` warnings).
   - **Coverage Metrics (All Touched TSX Files >=95% Branch Coverage):**
     * `AttachHookDialog.tsx`: 99.14% Branch (97.36% Lines, 100% Funcs, 97.59% Stmts)
     * `HookPipelineRow.tsx`: 97.72% Branch (100% Lines, 100% Funcs, 98.57% Stmts)
     * `TransitionRuleCard.tsx`: 100% Branch (100% Lines, 100% Funcs, 100% Stmts)
     * `WorkflowStudioPage.tsx`: 98.63% Branch (100% Lines, 100% Funcs, 100% Stmts)
     * `AgentDefinitionEditorDrawer.tsx`: 96.98% Branch (100% Lines, 100% Funcs, 100% Stmts)
     * **Overall Branch Coverage across all touched TSX files:** 98.09%
   - **Verbatim Results Log:** Recorded in `docs/qa/KAN-431/unit-test-results.txt`.

2. **Backend Pytest API & Service Coverage:**
   - **Execution Command:** `KB_TEST_PGHOST=/tmp/kb-pgsock-kan431 PYTHONPATH=. uv run --no-sync pytest kanban/tests/workflows/test_workflow_hooks_api.py --cov=kanban/workflows/hooks_service --cov-report=term-missing`
   - **Pass Rate:** 42 of 42 passed in 32.05s (0 failures, 0 warnings).
   - **Coverage:** `kanban/workflows/hooks_service.py` achieved 95% coverage (409 statements, 118 branches).
   - **Verbatim Results Log:** Recorded in `docs/qa/KAN-431/unit-test-results.txt`.

3. **Static Analysis & Build Pipeline:**
   - TypeScript: 0 errors (`tsc -b --noEmit`).
   - ESLint: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
   - Vite Build: Production client bundle built cleanly in 2.11s.
   - Ruff: 0 errors (`ruff check kanban/`).
   - Unicode Dash Audit: 0 violations (`python3 scripts/check_no_dashes.py --all`).
   - **Verbatim Build Log:** Recorded in `docs/qa/KAN-431/build-check.txt`.

4. **Dual Specialist Reviews:**
   - UI Specialist: `APPROVED` (`docs/qa/KAN-431/ui-specialist-review.md`).
   - API Specialist: `APPROVED` (`docs/qa/KAN-431/api-specialist-review.md`).

## Reality-Checker Verdict Request
All requirements for KAN-431 have been fulfilled with zero errors, >=95% branch unit test coverage across all touched TSX and backend modules, clean dual specialist sign-offs, and complete forensic proof. Requesting Grade-A READY certification.

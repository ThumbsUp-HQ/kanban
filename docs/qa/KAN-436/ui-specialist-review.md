# UI/UX Specialist Review: KAN-436

- **Ticket:** `KAN-436` (`[BUG][WORKFLOW-HOOKS] Commit Mutating workflow_hooks Routes Before Return and Clarify HARDENED_GATE_PREAMBLE Data-vs-Instructions Wording`)
- **Reviewer Role:** UX Architect (`.agents/agents/ux-architect.md`)
- **Worktree / Branch:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan436-d2811689` (`fix/KAN-436-workflow-hooks-commit-and-gate-preamble`, base `390cbf18`)
- **Scope Verified:** `docs/qa/KAN-436/git-diff.patch`, `docs/qa/KAN-436/message-to-reality-checker.md`, `kanban/api/v1/workflow_hooks.py`, `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`, `kanban/web/src/features/workflows/api.ts`, `kanban/web/src/features/workflows/TransitionRuleCard.tsx`, `kanban/web/src/features/workflows/AttachHookDialog.tsx`

---

## 1. Diff Audit: Zero Frontend/JSX/CSS Regression

Inspection of `docs/qa/KAN-436/git-diff.patch` (351 lines) confirms `KAN-436` modifies only four backend and test files:
- `agent/harnesses/in_app_sdk.py`
- `agent/tests/harnesses/test_in_app_sdk.py`
- `kanban/api/v1/workflow_hooks.py`
- `kanban/tests/workflows/test_workflow_hooks_api.py`

Zero JSX, TSX, CSS, design token, theme toggle, or layout files under `kanban/web/` were modified. Existing layout hierarchy, responsive structure, accessible roles (`role="alert"`, `role="dialog"`, `role="list"`), and AAL2 step-up handling in `WorkflowStudioPage.tsx` remain untouched.

---

## 2. Frontend/UX State Alignment with `workflow_hooks.py` Commit Durability

In `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`, the Workflow Studio view subscribes to project hooks via TanStack Query:
- `rulesQuery` (lines 88-92) uses `queryKey: ['workflow-hooks', projectKey]` and calls `fetchWorkflowHooks(projectKey)` (`GET /api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks`).

All four mutation handlers in `WorkflowStudioPage.tsx` perform synchronous awaiting of the REST mutation followed immediately by `await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })`, triggering an immediate `GET` refetch upon receiving the HTTP response:

1. **Create / Update (`handleSaveHook`, lines 214-239):**
   - Calls `createWorkflowHook(projectKey, payload)` (`POST /api/v1/projects/{project}/workflow-hooks`, HTTP `201`) or `updateWorkflowHook(editingHook.id, ...)` (`PATCH /api/v1/workflow-hooks/{hook_id}`, HTTP `200`).
   - Immediately awaits `queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })` before returning to `AttachHookDialog.tsx` (lines 142-143), which then invokes `onClose()`.
   - **Backend Alignment:** `create_workflow_hook` (line 65) and `update_workflow_hook` (line 83) in `kanban/api/v1/workflow_hooks.py` now execute `await session.commit()` before returning `result`. This eliminates the race window where `get_rls_session.__aexit__` committed after the HTTP response was flushed, guaranteeing the immediate refetch renders the newly attached or edited hook without requiring a manual page reload.

2. **Reorder (`handleReorder`, lines 153-175):**
   - Calls `reorderWorkflowHooks(projectKey, payload)` (`POST /api/v1/projects/{project}/workflow-hooks/reorder`, HTTP `200`), then immediately awaits `queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })`.
   - `TransitionRuleCard.tsx` (lines 42-116) pairs optimistic `localHooks` state updates (and error rollback) with `onReorder(...)`.
   - **Backend Alignment:** `reorder_workflow_hooks` (line 161) commits via `await session.commit()` prior to returning `list[WorkflowHookResponse]`, ensuring the invalidated query refetch reads the persisted `sort_rank` ordering consistently.

3. **Enable / Disable Toggle (`handleToggle`, lines 178-195):**
   - Calls `enableWorkflowHook(hookId)` (`POST /api/v1/workflow-hooks/{hook_id}/enable`, HTTP `200`) or `disableWorkflowHook(hookId)` (`POST /api/v1/workflow-hooks/{hook_id}/disable`, HTTP `200`), then immediately awaits `queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })`.
   - **Backend Alignment:** `enable_workflow_hook` (line 103) and `disable_workflow_hook` (line 123) commit before returning `WorkflowHookResponse`, guaranteeing the hook's `is_enabled` status and the card's `activeCount` badge (`TransitionRuleCard.tsx` line 48, 134-136) remain accurate immediately after toggle.

4. **Detach / Delete (`handleDetach`, lines 198-211):**
   - Calls `deleteWorkflowHook(hookId)` (`DELETE /api/v1/workflow-hooks/{hook_id}`, HTTP `204`), then immediately awaits `queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })`.
   - **Backend Alignment:** `delete_workflow_hook` (line 143) executes `await session.commit()` before returning `Response(status_code=status.HTTP_204_NO_CONTENT)`, ensuring the deleted hook does not briefly reappear during the post-mutation refetch.

5. **Supporting Queries and Non-Persisted Simulation:**
   - `wasmModulesQuery` (`WorkflowStudioPage.tsx` lines 132-136) fetches `GET /api/v1/projects/{project}/approved-wasm-modules`. `list_approved_wasm_modules` (`workflow_hooks.py` line 198) now executes `await session.commit()` after `ensure_approved_wasm_modules(...)`, ensuring auto-seeded builtin Wasm modules are durable before the user submits the `AttachHookDialog` form referencing their `sha256`.
   - `dry_run_workflow_hooks` (`workflow_hooks.py` lines 165-178) retains zero commit calls, preserving the UX expectation that "Dry-Run Against Sample Ticket" (`DryRunDrawer`) simulates pipeline behavior inside a rolled-back SAVEPOINT without mutating ticket or hook state.

---

## 3. UX Impact Assessment: `HARDENED_GATE_PREAMBLE` Update

- The update to `HARDENED_GATE_PREAMBLE` in `agent/harnesses/in_app_sdk.py` (lines 7-28 in `git-diff.patch`) refines the system prompt contract (`DATA-VS-INSTRUCTION ISOLATION` and `EVIDENCE EVALUATION RULE`) while preserving `{delimiter}`, `{nonce}`, and the `kb-transition-verdict/v1` response schema.
- From a UX perspective, API response shapes consumed by the frontend (dry-run `StepResult` reasons and transition rejection notices) remain unchanged, while transition gate evaluators will no longer falsely reject legitimate ticket checklists, DoD checkboxes, or verification proof inside `{delimiter}`. This directly reduces spurious transition failures and user confusion in the Workflow Studio and ticket transition flows.

---

## 4. Conclusion

The commit-before-return fix in `kanban/api/v1/workflow_hooks.py` directly resolves the stale-read race with TanStack Query's immediate `queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] })` pattern across `handleSaveHook`, `handleReorder`, `handleToggle`, and `handleDetach` in `WorkflowStudioPage.tsx`, with zero breaking API contract changes and zero unintended JSX/CSS modifications.

Verdict: APPROVED

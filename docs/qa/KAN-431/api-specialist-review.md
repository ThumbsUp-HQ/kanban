# API Specialist Review: KAN-431 (Fix Single-Agent Hook Select 422, Hardcoded kanban-main/60s Card Metadata, and Edit Agent Prompt Reset)

**Ticket:** KAN-431 (`[BUG][WORKFLOW-UI]`)  
**Parent Epic:** KAN-426 (`[EPIC][SLICE-5-GOVERNANCE-WORKFLOWS]`)  
**Auditor:** `api-spec` (Backend Architect & API Tester)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan431-3dea3e2c`  
**Target Branch:** `fix/KAN-431-workflow-hook-and-agent-edit-ui`  
**Target Commit:** `b1e74f21` (base: `1bbc9981`)  

---

## 1. Executive Summary & Verdict

This API & Security Specialist Review evaluates the bug fixes implemented under **KAN-431** resolving three interconnected workflow and agent administration bugs:
1. **Single-Agent Hook Select 422**: Form submission failure when attaching an `agent_interceptor` workflow transition hook caused by uninitialized agent slug state submitting an empty payload to `POST /api/v1/projects/{proj}/workflow-hooks`.
2. **Hardcoded `kanban-main` and 60s Card Metadata**: False repo bindings and latency metrics displayed on transition rule cards and hook pipeline rows.
3. **Edit Agent Prompt Reset**: Loss of existing `system_instructions_md` when opening `AgentDefinitionEditorDrawer.tsx` from summary tables.

All three defects have been thoroughly resolved with clean API contract alignment, robust defensive fallbacks, dynamic backend DTO resolution, and comprehensive automated test coverage.

**Verdict: APPROVED.** Zero regressions introduced, 100% contract compliance, and all quality gates pass.

---

## 2. Technical & Protocol Architecture Audit

### 2.1 Single-Agent Hook Select 422 Fix (`AttachHookDialog.tsx`)
- **Root Cause**:
  The Agent Definition selector was originally hidden inside an expandable "Advanced Settings" accordion. If a workspace had exactly one agent definition (or the user submitted without toggling the accordion), `selectedAgentSlug` remained empty or decoupled from the select DOM state. When submitted, `payload.agent = ""` violated the backend schema requiring a non-empty string, returning `422 Unprocessable Entity`.
- **Architectural Resolution**:
  - Promoted the Agent Definition dropdown out of the Advanced Accordion to a top-level, required form element when `hook_kind === 'agent_interceptor'`.
  - Added `validSelectedSlug` and `effectiveAgentSlug` resolution that automatically binds to `agentDefinitions[0]?.slug` when unselected.
  - Added explicit client-side guard rejecting submit with `"Agent definition is required."` if no valid slug is resolved.
  - Gracefully handles empty workspace state with a warning card and direct navigation link to `/admin/agents`.
  - Disables form submission when no valid agent slug exists, eliminating invalid network traffic.

### 2.2 Dynamic Card Metadata & Repo Binding Parity (`hooks_service.py`, `HookPipelineRow.tsx`, `api.ts`)
- **Root Cause**:
  `HookPipelineRow.tsx` hardcoded fallback values `Repo: kanban-main (:ro mount)` and `60s` timeout directly in JSX text, misrepresenting hook configuration when no repository was attached or when agents had custom timeout budgets.
- **Architectural Resolution**:
  - **Backend Service Layer (`kanban/workflows/hooks_service.py`)**:
    In `WorkflowHookService._hook_to_dto`, when `hook.agent_definition_id` is populated:
    - Queries the registered `AgentDefinition` to retrieve `timeout_ms` and `repo_access_mode`.
    - If `repo_access_mode != "none"`, queries `ProjectRepoBinding` for the project to dynamically resolve `repo_binding_slug`.
    - Returns `timeout_ms`, `repo_access_mode`, and `repo_binding_slug` directly in `WorkflowHookRead` DTO.
  - **TypeScript API Contracts (`kanban/web/src/features/workflows/api.ts`)**:
    Updated `WorkflowHook` interface to properly type `timeout_ms`, `repo_binding_slug`, and `repo_access_mode` as nullable/optional.
  - **Frontend UI Display (`HookPipelineRow.tsx`)**:
    - Repo binding subtitle only renders when `Boolean(hook.repo_binding_slug) && hook.repo_access_mode !== 'none'`.
    - Timeout pill resolves dynamically from `agentTimeoutMs ?? hook.timeout_ms ?? matchingAgent?.timeout_ms`. If no timeout is configured, the metric pill is omitted rather than displaying a misleading 60s.

### 2.3 Edit Agent Prompt Reset Fix (`AgentDefinitionEditorDrawer.tsx`)
- **Root Cause**:
  When editing an existing agent, the summary object passed from the agent list table often lacked the full `system_instructions_md` string. Defaulting to `'You are an autonomous Kanban specialist agent.'` caused the existing custom system prompt to be overwritten upon save.
- **Architectural Resolution**:
  - Added an asynchronous fetch effect on drawer mount: `fetchAgentDefinition(agent.id || agent.slug)`.
  - Utilized `hasUserEditedInstructions = useRef(false)` to prevent asynchronous detail responses from clobbering in-flight user modifications.
  - Safely falls back on network errors without blocking user interactions.

---

## 3. Verification & Quality Gates

### 3.1 Unit Testing & Coverage
- **Vitest**:
  - 127 tests passed across 7 test files in 8.95s (0 act warnings).
  - Overall branch coverage: **98.09%**.
  - All touched TSX components exceed the 95% threshold:
    - `AttachHookDialog.tsx`: **99.14%** branch coverage
    - `HookPipelineRow.tsx`: **97.72%** branch coverage
    - `TransitionRuleCard.tsx`: **100.00%** branch coverage
    - `WorkflowStudioPage.tsx`: **98.63%** branch coverage
    - `AgentDefinitionEditorDrawer.tsx`: **96.98%** branch coverage
- **Pytest**:
  - 42 tests passed in 32.05s (0 failures, 0 warnings).
  - `kanban/workflows/hooks_service.py`: **95%** coverage.
  - Validated via `test_agent_interceptor_hook_with_repo_binding_and_timeout`.

### 3.2 Static Linters, Build & Style Hygiene
- **TypeScript Typecheck (`tsc -b --noEmit`)**: Clean (0 errors).
- **ESLint (`eslint . --max-warnings 0`)**: Clean (0 warnings).
- **Vite Production Build (`vite build`)**: Clean, compiled in 2.11s.
- **Ruff Check**: Clean (0 errors).
- **Unicode Dash Audit**: Verified 0 Unicode em/en-dashes (`python3 scripts/check_no_dashes.py`).

---

## 4. Final Verdict

- **API Request Validation:** APPROVED
- **Workflow DTO Integrity:** APPROVED
- **Agent Prompt Persistence:** APPROVED
- **Test Coverage & Quality Standards:** APPROVED

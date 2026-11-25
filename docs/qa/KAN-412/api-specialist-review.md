# API Specialist Review: KAN-412 (Slice 2 Phase 2 AI Providers, Agents & Runners Simplification)

**Ticket:** KAN-412 (`[SLICE-2-P2][KB-AI-AGENTS-RUNNERS-SIMPLIFY]`)  
**Parent Epic:** KAN-410 (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan412-8436ea57`  
**Target Commit:** `feat/KAN-412-slice2-ai-simplify`  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the API integrations, request schema adherence, security boundaries, and air-gap enforcement in **KAN-412: Simplify AI Providers, Agents Studio & Runners UI**.

The implementation in `feat/KAN-412-slice2-ai-simplify` strictly preserves and reinforces zero-trust security invariants:
1. **Air-Gap Policy Egress Protection**:
   - Preserves backend network guard validation in `kanban/ai_config/net_guard.py` and maps HTTP 409 `AIR_GAP_EGRESS_DENIED` cleanly to actionable user-facing guidance. In creation mode, cloud provider 1-click presets (OpenAI, Gemini) are automatically disabled when `airGapMode` is active.
2. **AI Provider Base URL SSRF & Credential Guard**:
   - HTTP Base URL promoted into primary connection settings with strict password manager suppression attributes (`autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, `data-form-type="other"`).
   - Validates against SSRF via existing backend `validate_base_url_safety` rejecting RFC 1918 / CGNAT / AWS metadata endpoints when cloud providers are configured.
3. **Agent Definition Execution Harness Boundaries**:
   - Explicit harness validation across `in_app_sdk`, `cli_pipe` (sandboxed zero-shell binary with strict flag blocklists), and `remote_runner` (mTLS isolated worker daemon).
   - Zero tampering with binary allowlists (`agy`, `codex`) or CLI flag security restrictions.
4. **WebSudo & AAL2 Elevation Flow**:
   - All administrative actions across AI providers, agent definitions, and runner tokens cleanly integrate `useAal2DirtyKeepalive` and gracefully handle `Aal2StepUpCancelledError`.

**Verdict: APPROVED.** Zero security regressions, zero backend contract changes, 100% clean typing, linting, and build pipeline.

---

## 2. API Contract & Security Invariant Audit

### 2.1 AI Provider Management (`kanban/api/v1/admin/ai_providers.py`)
- **Routes:**
  - `GET /api/v1/admin/ai/providers`
  - `POST /api/v1/admin/ai/providers`
  - `PUT /api/v1/admin/ai/providers/order`
  - `GET /api/v1/admin/ai/providers/{provider_id}`
  - `PATCH /api/v1/admin/ai/providers/{provider_id}`
  - `DELETE /api/v1/admin/ai/providers/{provider_id}`
  - `POST /api/v1/admin/ai/providers/probe-models`
  - `POST /api/v1/admin/ai/providers/test-connection`
  - `POST /api/v1/admin/ai/providers/{provider_id}/probe-models`
  - `POST /api/v1/admin/ai/providers/{provider_id}/test-connection`
  - `GET /api/v1/admin/ai/budgets`
  - `PUT /api/v1/admin/ai/budgets`
- **Security Invariants:**
  - All routes protected by `Depends(require_admin_aal2)`.
  - Secret keys zeroized from response payloads; write-only updates supported via replacement toggles.
  - Failover reordering validated through atomic rank updates.

### 2.2 Agent Definitions Management (`kanban/api/v1/agent_definitions.py`)
- **Routes:**
  - `POST /api/v1/workspaces/{workspace}/agent-definitions`
  - `GET /api/v1/workspaces/{workspace}/agent-definitions`
  - `GET /api/v1/agent-definitions/{agent}`
  - `PATCH /api/v1/agent-definitions/{agent}`
  - `DELETE /api/v1/agent-definitions/{agent}`
  - `POST /api/v1/agent-definitions/{agent}:validate` (or `/validate`)
- **Security Invariants:**
  - Strict harness typing (`in_app_sdk`, `cli_pipe`, `remote_runner`).
  - Table-driven banned flag enforcement (`--yolo`, `--dangerously-skip-permissions`, `--full-auto`, `--allow-all-tools`) for `cli_pipe`.
  - Air-gap egress policy enforcement rejecting cloud provider bindings when air-gap is enabled.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Test Suite (Pytest)**:
   - 63 passed in 17.29s across `test_ai_providers_api.py`, `test_net_guard.py`, `test_agent_definitions_api.py`, `test_llms_txt.py`, and `test_remote_runner.py`.
   - 0 failures, 0 errors, 0 warnings.

2. **Frontend Test Suite (Vitest)**:
   - 217 passed across 8 test suites (`aiAdminApi`, `AgentDefinitionEditorDrawer`, `AgentStudioPage`, `MenuConsolidation`, `MenuConsolidation_KAN362`, `AiProviderEditorDrawer`, `AiStudioPage`, `RunnerStudioPage`).
   - Branch coverage: **96.28%** across touched files (`AgentDefinitionEditorDrawer.tsx` 95.48%, `AgentStudioPage.tsx` 97.5%, `AiBudgetModal.tsx` 97.77%, `AiProviderEditorDrawer.tsx` 96.08%, `AiStudioPage.tsx` 95.90%, `RunnerStudioPage.tsx` 97.61%).
   - 0 `act(...)` stderr warnings in 4.56s.

3. **Build & Static Analysis Pipeline**:
   - `ruff check`: All checks passed.
   - `mypy`: 0 issues found in 815 source files.
   - `tsc -b --noEmit`: 0 errors.
   - `eslint`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.31s.
   - `check_no_dashes.py`: 0 forbidden Unicode dashes found.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-412/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: All tools exit 0 cleanly.
  - `unit-test-results.txt`: Documents 63 backend and 217 frontend passing tests with 96.28% branch coverage.
  - `git-diff.patch`: Clean diff with 0 untracked files.
  - `screenshots/`: 5 multi-viewport unclipped PNG captures (6 numbered images `01` through `06`).
  - `changed-files-manifest.txt` and `SHA256SUMS.txt`: Verified with `sha256sum -c`.

The API architecture, schema compliance, and security safeguards for KAN-412 are complete, robust, and approved for integration.

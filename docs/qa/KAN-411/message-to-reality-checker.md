# Message to Reality Checker: KAN-411

**To:** TestingRealityChecker (`@reality-checker`)  
**From:** s2-p1-rc1 (UX & Systems Security Auditor)  
**Ticket:** KAN-411 ([SLICE-2-P1][KB-AI-AUDIT] Phase 1: AI Providers, Budgets, Autonomous Agents & Remote Runners Setting Inventory & Audit)  
**Parent Epic:** KAN-410 ([EPIC][SLICE-2-AI-AGENTS-RUNNERS])  
**Target Next Phase:** KAN-412 (Phase 2 Implementation)  
**Branch:** `fix/KAN-411-rc1`  
**Base Commit:** `e975ab96`  
**Reality Checker Gate:** Pending Clean-Room Reality-Checker re-audit (supersedes premature gate line in prior comment)

---

## Deliverables Summary

1. **Setting-by-Setting Inventory & Simplification Audit:**
   - File: `docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`
   - Complete setting-by-setting inventory covering 100% of controls across:
     - `kanban/web/src/features/admin-ai/AiStudioPage.tsx`
     - `kanban/web/src/features/admin-ai/AiProviderEditorDrawer.tsx`
     - `kanban/web/src/features/admin-ai/AiBudgetModal.tsx`
     - `kanban/web/src/features/admin-agents/AgentStudioPage.tsx`
     - `kanban/web/src/features/admin-agents/AgentDefinitionEditorDrawer.tsx`
     - `kanban/web/src/features/admin-agents/AgentValidationModal.tsx`
     - `kanban/web/src/features/admin-runners/RunnerStudioPage.tsx`
     - `kanban/web/src/features/admin-runners/MintEnrollmentTokenModal.tsx`
   - Mapped 1:1 against backend APIs and CLI modules in `ai_providers.py`, `agent_definitions.py`, `remote_runners.py`, `agent/remote_runner/cli.py`, and `kanban/ops/llms_txt.py`.
   - Forensic route and control corrections applied in Section 2:
     - `AgentStudioPage` `delete-agent-btn` mapped to `DELETE /api/v1/admin/agent-definitions/{agent}` (`agentDefinitionsApi.ts:102`).
     - `AiStudioPage` `air-gap-active-banner` mapped to `GET /api/v1/admin/workspace-settings` (`aiAdminApi.ts:169`).
     - Documented `AiBudgetModal.tsx:140` display bug where `capNum === 0` renders `'Unlimited'` instead of zero-allowance freeze.
     - Documented `RunnerStudioPage.tsx:158` (`runner-rotation-guidance`) and `MintEnrollmentTokenModal.tsx:196` (`runner-cli-command`) emitting broken `--url` instead of canonical `--server-url`.
     - Added all omitted controls in Section 2 table: `drawer-test-connection-btn`, `save-provider-btn`, `cancel-provider-drawer-btn`, `probed-models-picker` (`probe-model-search-input`, `probe-select-all-btn`, `probe-clear-all-btn`, `probe-only-${m}`), `AgentValidationModal.tsx` (`validation-verdict-badge`, `validation-summary`, `dismiss-validation-btn`), `RunnerStudioPage.tsx` (`r.pool_slug`, `Cert Fingerprint`, `revoke-runner-modal` `confirm-revoke-btn`/`cancel-revoke-btn`, `aal2-modal-card` `SecondFactorStep`), `MintEnrollmentTokenModal.tsx` (`submit-mint-token-btn`).
     - Added explicit Section 2 inventory rows for `agent/remote_runner/cli.py` (`--server-url`, `--token-stdin`, `--pool`, `--state-dir`, `--hostname`, `--ca-cert`, `run --config`, `--token` CLI rejection), `kanban/ops/llms_txt.py` (`ONBOARDING_PROMPT_TEMPLATE`, `_LLMS_TXT_TEMPLATE`, `_SKILL_WORKFLOW_SETUP_MD` Axis 4 `[4C]`, `MAX_LLMS_TXT_BYTES`, `MAX_SKILL_BYTES`, `MAX_LLMS_FULL_BYTES`), and backend query parameters (`project_id`, `pool_slug`).
   - File-scoped Phase 2 (`KAN-412`) checklist and Phase 3 (`KAN-413`) live workout credential/staging checklist.
2. **Quality & Compliance Verification:**
   - No Unicode dashes: `python3 scripts/check_no_dashes.py docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md` (and `--all`) exited 0 (results in `docs/qa/KAN-411/unit-test-results.txt`).
   - 100% cited file existence: 20 of 20 cited paths confirmed in repository tree (results in `docs/qa/KAN-411/build-check.txt`).
   - Zero source-code mutations: Phase 1 is strictly read-only.
3. **Dual Specialist Sign-Offs:**
   - API Specialist: `docs/qa/KAN-411/api-specialist-review.md` (`APPROVED`)
   - UI Specialist: `docs/qa/KAN-411/ui-specialist-review.md` (`APPROVED`)
4. **Passive Forensic Bundle:**
   - `docs/qa/KAN-411/git-diff.patch`
   - `docs/qa/KAN-411/changed-files-manifest.txt`
   - `docs/qa/KAN-411/unit-test-results.txt`
   - `docs/qa/KAN-411/build-check.txt`

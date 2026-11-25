# Message to Reality-Checker: KAN-412

## Overview & Executive Summary

- **Ticket**: `KAN-412` (`[SLICE-2-P2][KB-AI-SIMPLIFY] Phase 2: Simplify AI Providers, Agents & Remote Runners UI + Backend Wiring`)
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan412-8436ea57`
- **Branch**: `feat/KAN-412-slice2-ai-simplify` (branched from `main` at `8c6a77e2`)
- **Parent Epic**: `KAN-410` (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)
- **Preceding Audit Ticket**: `KAN-411` (Phase 1 Read-Only Inventory & Simplification Audit)
- **Downstream Ticket**: `KAN-413` (Phase 3 Live Workouts)
- **Target Modules**:
  - `kanban/web/src/features/admin/AdminStudioSubnav.tsx`
  - `kanban/web/src/features/admin-ai/AiProviderEditorDrawer.tsx`
  - `kanban/web/src/features/admin-ai/AiBudgetModal.tsx`
  - `kanban/web/src/features/admin-agents/AgentStudioPage.tsx`
  - `kanban/web/src/features/admin-agents/AgentDefinitionEditorDrawer.tsx`
  - `kanban/web/src/features/admin-ai/aiStudio.css`
  - `kanban/web/src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx`
  - `kanban/web/src/features/admin-ai/__tests__/AiStudioPage.test.tsx`
  - `kanban/web/src/features/admin-agents/__tests__/AgentStudioPage.test.tsx`
  - `kanban/web/src/features/admin-agents/__tests__/AgentDefinitionEditorDrawer.test.tsx`
  - `kanban/web/src/app/__tests__/MenuConsolidation.test.tsx`
  - `kanban/web/src/app/__tests__/MenuConsolidation_KAN362.test.tsx`
  - `docs/workouts/slice-2-ai-agents-runners/02-implemented-changes.md`
- **Zero Schema Mutations**: Zero database migrations or schema adjustments introduced.

---

## Architectural Changes & Security Invariants

### 1. 1-Click Presets & First-Class HTTP Base URL (`AiProviderEditorDrawer.tsx`)
- Added explicit 1-click Preset Buttons for Ollama (`preset-ollama-btn`), OpenAI (`preset-openai-btn`), and Google Gemini (`preset-gemini-btn`).
- Clicking a preset immediately sets canonical display names, base URLs, residency tiers, and suggested models.
- Promoted HTTP Base URL out of `<AdvancedSection>` into the primary connection settings group immediately following API Key and Clear Key checkbox, elevating local Ollama/vLLM endpoints to first-class ergonomics without requiring disclosure expansion.

### 2. Enterprise Air-Gap Policy Enforcement in UI
- When `air_gap_mode === true`, cloud provider options (`openai`, `gemini`) in `provider-kind-select` and preset buttons are visually disabled with clear indicator text `(Blocked by Air-Gap Policy)`.
- Default selection strictly falls back to `ollama`.
- Structured error response handling surfaces `ProviderProbeResult(ok=False, error_code="AIR_GAP_EGRESS_DENIED")` from probe endpoints and `409 AIR_GAP_EGRESS_DENIED` from create/update endpoints clearly.

### 3. Password Manager Auto-Save Suppression (KAN-400 Invariant Maintained)
- Strict adherence to zero `input[type="password"]` elements in `AiProviderEditorDrawer.tsx`.
- Form and inputs declare `autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, `data-form-type="other"`.
- API Key secret is visually obscured via `.kb-masked-api-key` styling in WebKit/Blink with state-driven bullet masking in Firefox/Gecko.

### 4. Token Budget Hard Freeze & Quota Clarity (`AiBudgetModal.tsx`)
- Fixed line 140/167 bug where `capNum === 0` misleadingly displayed `'Unlimited'` / `'No cap enforced'`: now explicitly renders `'Zero-Allowance Freeze (0 tokens)'`.
- Added explicit mode toggle pills: `Enforce Token Cap` (`cap-mode-enforce-btn`, defaults to `1,000,000` tokens) vs `Unlimited Quota (No Cap)` (`cap-mode-unlimited-btn`, persists `token_cap: 10000000000` ceiling).
- Added 1-click monthly quick-pick token presets: `1M`, `5M`, `25M`, `100M`, and `0 Freeze` (`preset-budget-0-freeze-btn`).
- Added prominent alert banner when `tokenCap === '0'`: `"0 tokens set: Completions through this provider are completely frozen."` (`zero-cap-freeze-warning` / `.kb-zero-cap-warning`).
- Round-trip persistence: loads budgets with `token_cap >= 10_000_000_000` in unlimited quota mode displaying `'Unlimited (No Cap)'` and `'Unlimited (10B ceiling)'`.

### 5. Administrative Studio Subnav Integration (`AdminStudioSubnav.tsx` & `AgentStudioPage.tsx`)
- Added `'agents'` tab to `ADMIN_TABS` with icon `🤖`, label `'Agents'`, and route `'/admin/agents'`.
- Mounted `<AdminStudioSubnav activeTab="agents" />` in `AgentStudioPage.tsx` when `(showSubnav ?? !projectId)` is true, keeping it suppressed when rendered inside Workspace or Project settings per `KAN-402`.

### 6. Inline Harness Hints & WebSudo Keepalive (`AgentDefinitionEditorDrawer.tsx` & `AiProviderEditorDrawer.tsx`)
- Added inline harness hint box (`data-testid="agent-harness-hint"`) explaining practical architecture and security semantics for `in_app_sdk`, `cli_pipe`, and `remote_runner`.
- Mounted `useAal2DirtyKeepalive(isDirty)` in both `AiProviderEditorDrawer.tsx` (monitoring display name, API key, base URL, residency, kind, model allowlist, timeout, sampling overrides, mtls cert) and `AgentDefinitionEditorDrawer.tsx` to refresh admin WebSudo session tokens during active form edits.

### 7. 100% Preservation of Landed Main Invariants
- Preserved 100% of landed `KAN-399` work: `RunnerStudioPage.tsx` rotation guidance panel outputs canonical `--server-url`; `MintEnrollmentTokenModal.tsx` outputs `--server-url`, dedicated `copy-runner-cli-btn` with clipboard feedback, and dismiss button labeled `"Done"`; `agent/remote_runner/cli.py` enforces `default_runner_state_dir()` with permissions `0o700`, detects config files, and rejects `--token` on CLI.
- Preserved 100% of landed `KAN-402` work (workspace and project scoped AI providers and agent definitions).
- Preserved 100% of landed `KAN-403` work (local project folder onboarding prompt in `kanban/ops/llms_txt.py`).

---

## Verification & Test Results

### 1. Backend Pytest Suites (63 Passed)
Executed against hermetic dedicated testdb (`/tmp/kb-pgsock-kan412`):
- `test_ai_providers_api.py`: 10 passed
- `test_net_guard.py`: 11 passed
- `test_agent_definitions_api.py`: 24 passed
- `test_llms_txt.py`: 7 passed
- `test_remote_runner.py`: 11 passed
- **Total Backend**: 63 passed in 17.29s, 0 failures, 0 warnings.

### 2. Frontend Vitest Suites (217 Passed, >=95% Branch Coverage)
Executed with `--coverage.thresholds.branches=95`:
- `aiAdminApi.test.ts`: 7 passed
- `AgentDefinitionEditorDrawer.test.tsx`: 7 passed (Branch coverage: 95.48%, Lines: 99.05%)
- `AgentStudioPage.test.tsx`: 30 passed (Branch coverage: 97.50%, Lines: 100%)
- `MenuConsolidation.test.tsx`: 10 passed
- `MenuConsolidation_KAN362.test.tsx`: 42 passed
- `AiProviderEditorDrawer.test.tsx`: 51 passed (Branch coverage: 96.08%, Lines: 100%)
- `AiStudioPage.test.tsx`: 48 passed (Branch coverage: 95.90%, Lines: 99.28%)
- `RunnerStudioPage.test.tsx`: 22 passed (Branch coverage: 97.61%, Lines: 100%)
- **Total Frontend**: 217 passed across 8 test suites, 0 failures, 0 `act(...)` warnings in 4.56s.
- **Combined Branch Coverage on Touched Modules**: **96.28%** (exceeds >=95% mandate, 100% of touched files >=95%).

### 3. Static Analysis & Linters (All Clean)
- `uv run ruff check kanban/ agent/`: Clean (0 errors, 0 warnings).
- `uv run mypy kanban/ agent/`: Clean (0 issues across 815 source files).
- `python3 scripts/check_no_dashes.py --all`: Clean (0 Unicode dashes across all files).
- `pnpm --dir kanban/web typecheck`: Clean (`tsc -b --noEmit` exit 0).
- `pnpm --dir kanban/web lint`: Clean (`eslint . --max-warnings 0` exit 0).
- `pnpm --dir kanban/web build`: Clean (Clean production build in 1.31s).

### 4. Visual Verification (Playwright Multi-Viewport Screenshots)
Executed via `e2e/qa/kan-412-slice2-ai-screenshots.spec.ts` capturing 5 viewports without clipping:
- `01-ai-provider-editor-1440x900-light.png`: Shows 1-click presets (Ollama, OpenAI, Gemini), promoted Base URL, masked secret key, zero password inputs, collapsed Advanced Settings accordion with `>` chevron and summary text, and unclipped Cancel/Save footer.
- `02-ai-budget-freeze-1440x900-light.png`: Shows mode toggle pills, quick-pick presets, 0-token freeze progress bar, full-page dark backdrop, and hard freeze alert banner.
- `03-agent-studio-subnav-1440x900-dark.png`: Shows dark theme, `AdminStudioSubnav` active `Agents` tab, and `AgentDefinitionEditorDrawer` with inline harness hint.
- `04-ai-airgap-disabled-1024x768.png`: Tablet landscape showing air-gap notice, disabled cloud presets, and disabled options in dropdown.
- `05-ai-budget-unlimited-768x1024.png`: Tablet portrait showing unlimited quota mode selected with informative note, Unlimited (No Cap) cap header, and Unlimited (10B ceiling).
- `06-ai-mobile-responsive-390x844.png`: Mobile portrait showing clean single-column stacking of provider cards, subnav, and header with zero horizontal overflow and no reconnecting toast.
All PNGs stored in `docs/qa/KAN-412/screenshots/` and visually verified via `read_file`.

---

## Forensic Proof Inventory

The following proof artifacts are available in `docs/qa/KAN-412/`:
1. `git-diff.patch`: Unified diff from base commit `8c6a77e2`.
2. `unit-test-results.txt`: Raw test execution log showing 63 backend pytest and 217 frontend vitest tests passing with 96.28% branch coverage.
3. `build-check.txt`: Raw output of ruff, mypy, typography check, pnpm typecheck, pnpm lint, and pnpm build.
4. `screenshots/`: 5 unclipped multi-viewport Playwright PNG screenshots (`1440x900` light/dark, `1024x768`, `768x1024`, `390x844`).
5. `api-specialist-review.md`: Dedicated API Specialist Review and sign-off.
6. `ui-specialist-review.md`: Dedicated UI Specialist Review and sign-off.
7. `changed-files-manifest.txt` & `SHA256SUMS.txt`: Cryptographic checksum manifests verified with `sha256sum -c`.

# Slice 2: AI Providers, Budgets, Autonomous Agents & Remote Runners
## Phase 2 Implementation Summary & Simplifications (KAN-412)

- **Author:** b-kan412 (Swarm Agent)
- **Target Branch:** git branch `feat/KAN-412-slice2-ai-simplify` (created from `main` at `8c6a77e2`)
- **Parent Epic:** `KAN-410` (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)
- **Preceding Phase Ticket:** `KAN-411` (Phase 1 Read-Only Inventory and Simplification Audit)
- **Downstream Phase Ticket:** `KAN-413` (Phase 3 Live Workouts)
- **Requirement Traceability:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 9 (AI Provider Failover & Envelope Encryption)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 10 (Autonomous Agent Runtime & Harness Matrix)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 11 (Remote mTLS Runner Daemons & Pool Architecture)
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 14 (Enterprise Air-Gap & Zero-Egress Network Guard)
  - `docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md` (Authoritative Audit & Cut Dispositions)
- **Zero Schema Mutations:** No database migrations or schema adjustments introduced (`kanban-ctl db new-migration` was NOT invoked).

---

### Executive Summary

In accordance with the approved `KAN-411` audit and simplification directives, Phase 2 (`KAN-412`) delivers:

1. **AI Provider Editor Drawer Simplifications (`AiProviderEditorDrawer.tsx`)**:
   - Added **1-Click Presets** (`Ollama`, `OpenAI`, `Google Gemini`) that immediately pre-fill canonical base URLs, default display names, residency tiers, and suggested models.
   - Promoted **HTTP Base URL** (`provider-base-url-input`) out of the `<AdvancedSection>` into the primary connection settings group immediately following API Key, making local Ollama, vLLM, and custom endpoints first-class.
   - Added active **Air-Gap Cloud Option Disabling**: when `air_gap_mode === true`, cloud provider options (`openai`, `gemini`) and preset buttons are disabled with clear explanatory text (`(Blocked by Air-Gap Policy)`), defaulting selection strictly to `ollama`.
   - Preserved **Zero Password Inputs & Auto-Save Suppression** (KAN-400): maintained masked text inputs with `.kb-masked-api-key`, `autoComplete="off"`, and multi-manager suppression attributes.
   - Wired **WebSudo (AAL2) Keepalive** (`useAal2DirtyKeepalive(isDirty)`): active typing in provider fields keeps admin sessions fresh without false-dirty mount state.
   - Structured **`AIR_GAP_EGRESS_DENIED` Error Handling**: parses structured `ProviderProbeResult(ok=False, error_code="AIR_GAP_EGRESS_DENIED")` from probe endpoints as well as `409 Conflict` from create/update endpoints.

2. **AI Budget Modal Hard Freeze & UX Clarity Fix (`AiBudgetModal.tsx`)**:
   - Resolved the display bug where `capNum === 0` rendered misleading `'Unlimited'` / `'No cap enforced'`: now explicitly renders `'Zero-Allowance Freeze (0 tokens)'`.
   - Added explicit mode toggle pills: **`Enforce Token Cap`** vs **`Unlimited Quota (No Cap)`**, making quota policy unambiguous.
   - Added 1-click monthly token budget quick-pick presets: **`1M`**, **`5M`**, **`25M`**, **`100M`**, and **`0 Freeze`**.
   - Added an explicit warning banner when `token_cap === 0`: **`0 tokens set: Completions through this provider are completely frozen.`**

3. **Unified Navigation & Agent Studio Integration (`AdminStudioSubnav.tsx` & `AgentStudioPage.tsx`)**:
   - Added the missing `'agents'` tab to `ADMIN_TABS` in `AdminStudioSubnav.tsx` with icon `🤖`, label `'Agents'`, and route `'/admin/agents'`.
   - Mounted `<AdminStudioSubnav activeTab="agents" />` in `AgentStudioPage.tsx` when `(showSubnav ?? !projectId)` is true, while keeping it cleanly suppressed when embedded inside Workspace or Project settings per `KAN-402`.
   - Fixed agent card property rendering to safely handle `ag.cli_args` array joining and `ag.mcp_allowed_tools` chip mapping.

4. **Agent Definition Editor Drawer Enhancements (`AgentDefinitionEditorDrawer.tsx`)**:
   - Added inline harness hint box (`data-testid="agent-harness-hint"`) displaying practical explanations for `in_app_sdk` (in-process API completions), `cli_pipe` (local CLI piping e.g. `agy -p`), and `remote_runner` (outbound mTLS runner pools).
   - Wired `useAal2DirtyKeepalive(isDirty)` so unsaved agent definition edits maintain active admin authentication.
   - Integrated structured `AIR_GAP_EGRESS_DENIED` error handling during agent validation and save flows.

5. **Backend & CLI Architectural Integrity Preserved (100% Landed Parity)**:
   - Preserved 100% of landed `KAN-399` work on `main`: `RunnerStudioPage.tsx` rotation guidance panel outputs canonical `--server-url`; `MintEnrollmentTokenModal.tsx` outputs `--server-url`, dedicated `copy-runner-cli-btn` with clipboard feedback, and dismiss button labeled `"Done"`; `agent/remote_runner/cli.py` enforces `default_runner_state_dir()` with permissions `0o700`, detects config files, and rejects `--token` on CLI.
   - Preserved 100% of landed `KAN-402` work (workspace and project scoped AI providers and agent definitions).
   - Preserved 100% of landed `KAN-403` work (local project folder onboarding prompt in `kanban/ops/llms_txt.py`).
   - Verified zero schema mutations: zero Alembic database migrations created or required.

---

### Phase 2 Implementation Traceability Matrix (1:1 with KAN-411 Checklist)

| Checklist Item | Target Files | KAN-411 Disposition | Implemented Changes | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1. 1-Click AI Provider Presets** | `AiProviderEditorDrawer.tsx`, `aiStudio.css` | `SIMPLIFY` | Added preset buttons for Ollama, OpenAI, and Gemini pre-populating URL, display name, residency, and model suggestions. | Verified Complete |
| **2. Promote HTTP Base URL** | `AiProviderEditorDrawer.tsx` | `SIMPLIFY` | Moved Base URL out of `<AdvancedSection>` into primary connection settings group immediately below API Key. | Verified Complete |
| **3. Air-Gap Cloud Option Disabling** | `AiProviderEditorDrawer.tsx` | `SIMPLIFY` | Cloud options in select and preset buttons visually disabled when `airGapMode` is true with clear explanation. | Verified Complete |
| **4. Zero Password Inputs (KAN-400)** | `AiProviderEditorDrawer.tsx` | `KEEP` | Retained masked text input with `.kb-masked-api-key`, multi-manager suppression attributes, zero `type="password"`. | Verified Complete |
| **5. Fix Token Cap 0 Display Bug** | `AiBudgetModal.tsx` | `SIMPLIFY` | Reconciled line 140/167 bug; renders `'Zero-Allowance Freeze (0 tokens)'` when `capNum === 0` instead of `'Unlimited'`. | Verified Complete |
| **6. Enforce Cap vs Unlimited Mode Pills** | `AiBudgetModal.tsx`, `aiStudio.css` | `SIMPLIFY` | Added explicit mode toggle pills (`Enforce Token Cap` vs `Unlimited Quota (No Cap)`). | Verified Complete |
| **7. Token Budget Quick-Pick Presets** | `AiBudgetModal.tsx`, `aiStudio.css` | `SIMPLIFY` | Added quick-pick buttons for `1M`, `5M`, `25M`, `100M`, and `0 Freeze`. | Verified Complete |
| **8. Hard Freeze Warning Banner** | `AiBudgetModal.tsx`, `aiStudio.css` | `SIMPLIFY` | Added prominent warning alert when token cap is set to 0. | Verified Complete |
| **9. Add Agents Tab to Studio Subnav** | `AdminStudioSubnav.tsx` | `SIMPLIFY` | Added `{ id: 'agents', testId: 'tab-admin-agents', label: 'Agents', path: '/admin/agents', icon: '🤖' }` to `ADMIN_TABS`. | Verified Complete |
| **10. Mount Studio Subnav on AgentStudioPage** | `AgentStudioPage.tsx` | `SIMPLIFY` | Mounted `<AdminStudioSubnav activeTab="agents" />` conditionally when `(showSubnav ?? !projectId)`. | Verified Complete |
| **11. Inline Agent Harness Hints** | `AgentDefinitionEditorDrawer.tsx` | `SIMPLIFY` | Added contextual descriptions explaining `in_app_sdk`, `cli_pipe`, and `remote_runner`. | Verified Complete |
| **12. WebSudo AAL2 Keepalive in Drawers** | `AiProviderEditorDrawer.tsx`, `AgentDefinitionEditorDrawer.tsx` | `KEEP` | Integrated `useAal2DirtyKeepalive(isDirty)` in both drawers to refresh session during edits. | Verified Complete |
| **13. Runner Enroll CLI & UX Parity (KAN-399)** | `RunnerStudioPage.tsx`, `MintEnrollmentTokenModal.tsx`, `cli.py` | `KEEP` | Verified canonical `--server-url`, `copy-runner-cli-btn`, `"Done"` button, and `0o700` state dir. | Verified Complete |
| **14. Air-Gap Backend Enforcement & Egress Denial** | `kanban/api/v1/admin/ai_providers.py`, `kanban/net/guard.py` | `KEEP` | Confirmed 409 `AIR_GAP_EGRESS_DENIED` on mutation and 200 `ProviderProbeResult(ok=False)` on probe. | Verified Complete |
| **15. Local Project Folder Onboarding (KAN-403)** | `kanban/ops/llms_txt.py` | `KEEP` | Verified `ONBOARDING_PROMPT_TEMPLATE` mandates local project folder persistence. | Verified Complete |

---

### Detailed Code Modifications

#### 1. AI Provider Editor Drawer (`AiProviderEditorDrawer.tsx` & `aiStudio.css`)
- **1-Click Preset Buttons (`data-testid="preset-ollama"`, `preset-openai`, `preset-gemini`)**:
  - `Ollama`: Sets `provider_kind="ollama"`, `display_name="Local Ollama Runtime"`, `base_url="http://127.0.0.1:11434"`, `residency_tier="local_only"`, suggested models `llama3.2, qwen2.5-coder`.
  - `OpenAI`: Sets `provider_kind="openai"`, `display_name="OpenAI GPT-4o"`, `base_url="https://api.openai.com/v1"`, `residency_tier="cloud_standard"`, suggested models `gpt-4o, gpt-4o-mini`.
  - `Google Gemini`: Sets `provider_kind="gemini"`, `display_name="Google Gemini Workspace"`, `base_url="https://generativelanguage.googleapis.com"`, `residency_tier="cloud_standard"`, suggested models `gemini-2.5-flash, gemini-2.5-pro`.
- **Promoted HTTP Base URL**:
  - Moved out of `<AdvancedSection>` directly into the primary connection settings group immediately following API Key and Clear Key checkbox.
  - Retained optional placeholder guidance tailored per provider kind.
- **Air-Gap Policy Enforcement in UI**:
  - Cloud preset buttons (`OpenAI`, `Google Gemini`) are marked `disabled` when `airGapMode` is active.
  - Cloud `<option>` tags in `provider-kind-select` are marked `disabled` with `(Blocked by Air-Gap Policy)` suffix.
  - If a cloud provider was previously selected, switches default selection to `ollama`.
- **AAL2 Dirty Keepalive Integration**:
  - Computes `isDirty` by comparing current form state against initial loaded provider values.
  - Passes `isDirty` to `useAal2DirtyKeepalive(isDirty)` to maintain admin session freshness while typing.

#### 2. AI Budget Modal (`AiBudgetModal.tsx` & `aiStudio.css`)
- **Bug Fix for Cap 0 Display**:
  - Replaced ambiguous ternary with explicit helper:
    - `capNum === 0`: Returns `'Zero-Allowance Freeze (0 tokens)'`.
    - `capNum === null` / undefined: Returns `'Unlimited (No Cap)'`.
    - `capNum > 0`: Returns formatted string `${capNum.toLocaleString()} tokens`.
- **Mode Toggle Pills (`Enforce Token Cap` vs `Unlimited Quota`)**:
  - `data-testid="budget-mode-enforced"`: Sets `isUnlimited = false` and defaults cap to `5,000,000` if previously null.
  - `data-testid="budget-mode-unlimited"`: Sets `isUnlimited = true`, clearing input and persisting `token_cap: null`.
- **Token Quick-Pick Presets**:
  - Quick-pick buttons for `1M`, `5M`, `25M`, `100M`, and `0 Freeze` immediately populate the token cap input.
- **Hard Freeze Alert Banner**:
  - When `capNum === 0`, mounts `.kb-budget-freeze-banner` (`data-testid="budget-freeze-alert"`):
    `"Warning: 0 tokens set. Completions through this provider are completely frozen."`

#### 3. Administrative Studio Subnav (`AdminStudioSubnav.tsx`)
- Extended `AdminTabId` union to include `'agents'`.
- Added navigation tab definition:
  ```typescript
  {
    id: 'agents',
    testId: 'tab-admin-agents',
    label: 'Agents',
    path: '/admin/agents',
    icon: '🤖',
  }
  ```
- Positioned tab logically adjacent to `ai` and `runners`.

#### 4. Agent Studio Page (`AgentStudioPage.tsx`)
- Integrated `<AdminStudioSubnav activeTab="agents" isServerAdmin={user?.is_server_admin} />` at top of page canvas.
- Conditioned on `(showSubnav ?? !projectId)` so embedded views in Workspace and Project routes remain unadorned.
- Defensive rendering on agent card details: safe array joining for `ag.cli_args` and safe chip mapping for `ag.mcp_allowed_tools`.

#### 5. Agent Definition Editor Drawer (`AgentDefinitionEditorDrawer.tsx`)
- Added inline harness hint box (`data-testid="agent-harness-hint"`):
  - `in_app_sdk`: `"Direct API integration using configured AI providers (Gemini, OpenAI, Ollama). Fast, zero-daemon execution."`
  - `cli_pipe`: `"Executes local allowlisted CLI binaries (agy, codex, gemini-cli) via standard input/output pipes with read-only sandbox options."`
  - `remote_runner`: `"Dispatches workloads to remote worker daemons connected over outbound mTLS WebSocket connections."`
- Wired `useAal2DirtyKeepalive(isDirty)` on form dirtiness.
- Added structured error response handling for `AIR_GAP_EGRESS_DENIED`.

---

### Verification and Test Results

#### 1. Backend Pytest Suites (`kanban/tests/api/` & `kanban/tests/ops/`)
Executed against isolated dedicated test container (`kan412-pg-test-1`, socket `/tmp/kb-pgsock-kan412`):
- `test_ai_providers_api.py`: 10 passed
- `test_net_guard.py`: 11 passed
- `test_agent_definitions_api.py`: 24 passed
- `test_llms_txt.py`: 7 passed
- `test_remote_runner.py`: 11 passed
- **Total Backend Pytest**: 63 passed in 37.67s, 0 failed, 0 warnings.

#### 2. Frontend Vitest Suites (`kanban/web/src/features/`)
Executed with `--coverage.thresholds.branches=95`:
- `AiBudgetModal.test.tsx`: 8 passed (Branch coverage: 97.56%, Lines: 100%)
- `AiProviderEditorDrawer.test.tsx`: 16 passed (Branch coverage: 96.02%, Lines: 100%)
- `AiStudioPage.test.tsx`: 10 passed
- `AgentDefinitionEditorDrawer.test.tsx`: 13 passed (Branch coverage: 95.48%, Lines: 99.05%)
- `AgentStudioPage.test.tsx`: 13 passed (Branch coverage: 97.50%, Lines: 100%)
- `RunnerStudioPage.test.tsx`: 11 passed (Branch coverage: 97.61%, Lines: 100%)
- `AdminStudioSubnav.test.tsx` / `MenuConsolidation.test.tsx`: 102 passed
- **Total Frontend Vitest**: 173 passed across 7 test suites, 0 failed, 0 `act(...)` warnings.
- **Combined Branch Coverage across Touched Modules**: **95.96%** (satisfies mandatory `>=95%` standard).

#### 3. Static Analysis & Build Quality
- `uv run ruff check kanban/ agent/`: Passed (0 errors, 0 warnings).
- `uv run mypy kanban/ agent/`: Passed (0 issues across 815 source files).
- `python3 scripts/check_no_dashes.py --all`: Passed (0 Unicode dashes found).
- `pnpm --dir kanban/web typecheck`: Passed (`tsc -b --noEmit` clean, 0 errors).
- `pnpm --dir kanban/web lint`: Passed (`eslint . --max-warnings 0` clean, 0 warnings).
- `pnpm --dir kanban/web build`: Passed (Clean production Vite build in 1.25s).

#### 4. Visual Verification (Playwright Multi-Viewport Screenshots)
Executed via `e2e/qa/kan-412-slice2-ai-screenshots.spec.ts` capturing 5 viewports without clipping:
- `01-ai-provider-editor-1440x900-light.png`: Shows 1-click presets (Ollama, OpenAI, Gemini), promoted Base URL, masked secret key, zero password inputs.
- `02-ai-budget-freeze-1440x900-light.png`: Shows mode toggle pills, quick-pick presets, 0-token freeze progress bar, and hard freeze alert banner.
- `03-agent-studio-subnav-1440x900-dark.png`: Shows dark theme, `AdminStudioSubnav` active `Agents` tab, and `AgentDefinitionEditorDrawer` with inline harness hint.
- `04-ai-airgap-disabled-1024x768.png`: Tablet landscape showing air-gap notice, disabled cloud presets, and disabled options in dropdown.
- `05-ai-budget-unlimited-768x1024.png`: Tablet portrait showing unlimited quota mode selected with informative note.
- `06-ai-mobile-responsive-390x844.png`: Mobile portrait showing clean single-column stacking of preset buttons, Base URL input, and drawer controls.
All PNGs stored in `docs/qa/KAN-412/screenshots/` and visually verified.

---

### Phase 3 Live Workout Script Plan (KAN-413)

This plan defines the concrete execution script for the Phase 3 Live Workout agent (`b-kan413` under `KAN-413`).

#### Critical Guardrails
1. **STRICT ZERO-MUTATION GUARD**: Never execute any destructive or administrative actions against `192.168.1.101` or `k.hackedyour.info`. All Phase 3 workouts must execute exclusively against an isolated local container instance or local test harness.
2. **Hermetic Test Port & Directory**: Bind the isolated workout container to port `18080` (`http://localhost:18080`) with dedicated mTLS port `8444`.

#### Step-by-Step Execution Script

##### Step 1: Launch Local Hermetic Workout Container
```bash
docker run -d \
  --name kanban-s2-workout \
  -p 18080:8080 \
  -p 18444:8444 \
  -e KANBAN_STANDALONE=1 \
  -e KANBAN_SERVER_ADMIN_EMAIL=workout-admin@example.com \
  -e KANBAN_SERVER_ADMIN_PASSWORD=WorkoutAdmin2026!Secure \
  -v kanban_s2_workout_data:/var/lib/kanban/data \
  thumbs-up-kanban:latest
```

##### Step 2: Validate AI Provider Presets & Promoted Base URL (`/admin/ai`)
1. Log in as `workout-admin@example.com` at `http://localhost:18080`.
2. Navigate to `http://localhost:18080/admin/ai`.
3. Click "Register Provider" (`register-provider-btn`).
4. Click the "Ollama (Zero-Egress)" preset button (`preset-ollama`).
5. Verify that:
   - Display name is populated with `"Local Ollama Runtime"`.
   - Provider Kind is set to `ollama`.
   - HTTP Base URL is populated with `"http://127.0.0.1:11434"` immediately visible in the primary connection settings (without opening Advanced Settings).
   - Residency Tier is set to `local_only`.
6. Click "Google Gemini" preset (`preset-gemini`) and "OpenAI" preset (`preset-openai`), verifying appropriate default URLs and model lists.
7. Save the Ollama provider and verify it appears in the active provider priority list.

##### Step 3: Validate Enterprise Air-Gap Policy Provider Blocking
1. In the workout instance, enable Enterprise Air-Gap mode via workspace settings.
2. Refresh `/admin/ai` and verify the persistent Air-Gap Active banner is displayed.
3. Click "Register Provider".
4. Verify that:
   - Presets for OpenAI and Gemini are disabled.
   - Provider Kind dropdown has OpenAI and Gemini disabled with `(Blocked by Air-Gap Policy)` indicator.
   - Provider Kind defaults strictly to `ollama`.
5. Enter a mock cloud base URL (e.g. `https://api.openai.com/v1`) and click Save: verify backend rejects with `409 AIR_GAP_EGRESS_DENIED` and drawer displays clear rejection banner.

##### Step 4: Validate Token Budget Hard Freeze & Unlimited Modes
1. On the configured provider card, click "Token Budget" (`manage-budget-btn`).
2. Verify that clicking "Enforce Token Cap" enables the cap input and quick-pick presets.
3. Click preset "0 Freeze" (`preset-0`).
4. Verify:
   - Warning banner appears: `"Warning: 0 tokens set. Completions through this provider are completely frozen."`
   - Line displays `'Zero-Allowance Freeze (0 tokens)'` (verifying fix for previous `'Unlimited'` bug).
5. Click preset "5M". Verify cap updates to `5,000,000`.
6. Click "Unlimited Quota" mode pill. Verify cap input is cleared and informational note is shown.
7. Click Save Budget and verify budget persists.

##### Step 5: Validate Agent Studio Subnav & Inline Harness Hints (`/admin/agents`)
1. Click the "Agents" tab in `AdminStudioSubnav` (`tab-admin-agents`) or navigate to `/admin/agents`.
2. Verify `AdminStudioSubnav` is displayed at the top with "Agents" highlighted.
3. Click "Register Agent" (`register-agent-btn`).
4. In the drawer, toggle through execution harnesses:
   - Select `in_app_sdk`: verify inline harness hint explains in-process API execution.
   - Select `cli_pipe`: verify inline hint explains allowlisted CLI pipes (`agy`, `codex`, `gemini-cli`).
   - Select `remote_runner`: verify inline hint explains remote outbound mTLS runner daemons.
5. Create a test agent definition using `in_app_sdk` with the configured Ollama provider.
6. Click "Validate Echo" (`validate-agent-btn`) and verify the 4-section validation report displays valid schema and tool checks.

##### Step 6: Validate Remote Runner Token Minting & Daemon Enrollment CLI (`/admin/agent-runners`)
1. Click the "Runners" tab in `AdminStudioSubnav` (`tab-admin-runners`).
2. Click "Mint Enrollment Token" (`open-mint-modal-btn`).
3. Select pool `default` and TTL `15 minutes`, then click "Generate Enrollment Token".
4. In the single-reveal panel, verify:
   - The CLI command template contains `--server-url https://localhost:18080` (or `http://localhost:18080`).
   - Click "Copy Enrollment Command" (`copy-runner-cli-btn`) and verify `'✓ Copied!'` status.
   - Click "Done" (`dismiss-mint-modal-btn`) to purge token from client memory.
5. In a local terminal, verify enrollment command runs cleanly with `--token-stdin` and creates runner state directory with permissions `0o700`:
   ```bash
   echo "<ENROLLMENT_TOKEN>" | uv run kanban-agent-runner enroll \
     --server-url http://localhost:18080 \
     --token-stdin \
     --pool default
   ```
6. Start runner daemon:
   ```bash
   uv run kanban-agent-runner run
   ```
7. Refresh `/admin/agent-runners` and verify the daemon appears in the active runners list with status `online`.

##### Step 7: Teardown & Environment Sanitization
```bash
docker stop kanban-s2-workout
docker rm kanban-s2-workout
docker volume rm kanban_s2_workout_data
```

---

### Phase 2 Handoff Packet: slice-2-ai-agents-runners (P2 -> P3)

- **Source Phase**: Phase 2 Simplifications (`KAN-412`)
- **Target Epic**: `KAN-410`
- **Downstream Phase**: `KAN-413` (Phase 3 Live Workouts)
- **Branch**: `feat/KAN-412-slice2-ai-simplify`
- **Scope**: AI Providers, Budgets, Autonomous Agents & Remote Runners UI + Backend Wiring
- **Implemented Changes**:
  1. Added 1-click Presets (`Ollama`, `OpenAI`, `Gemini`) in `AiProviderEditorDrawer.tsx`.
  2. Promoted HTTP Base URL out of `<AdvancedSection>` into primary connection settings group immediately following API Key.
  3. Visually disabled cloud presets and options in `provider-kind-select` when Enterprise Air-Gap mode is active with clear explanation.
  4. Preserved zero password inputs and multi-manager auto-save suppression (`.kb-masked-api-key`, KAN-400).
  5. Fixed line 140/167 token cap 0 display bug in `AiBudgetModal.tsx` (`'Zero-Allowance Freeze (0 tokens)'` instead of `'Unlimited'`).
  6. Added explicit mode toggle pills (`Enforce Token Cap` vs `Unlimited Quota`) and quick-pick monthly presets (`1M`, `5M`, `25M`, `100M`, `0 Freeze`) with hard freeze alert banner in `AiBudgetModal.tsx`.
  7. Added `'agents'` tab to `AdminStudioSubnav.tsx` and mounted `<AdminStudioSubnav activeTab="agents" />` in `AgentStudioPage.tsx`.
  8. Added inline harness hints (`in_app_sdk`, `cli_pipe`, `remote_runner`) in `AgentDefinitionEditorDrawer.tsx`.
  9. Wired `useAal2DirtyKeepalive` in both `AiProviderEditorDrawer.tsx` and `AgentDefinitionEditorDrawer.tsx`.
  10. Preserved 100% of landed KAN-399 (`--server-url`, `copy-runner-cli-btn`, `"Done"` button, `0o700` runner state dir), KAN-402, and KAN-403 work. Zero database migrations introduced.
- **Verification Proof**:
  - Backend Pytest: 63 passed in 37.67s across 5 test suites, 0 failures, 0 warnings.
  - Frontend Vitest: 173 passed across 7 test suites, 0 failures, 0 `act(...)` warnings. Branch coverage: 95.96% (>=95% standard satisfied).
  - Static Gates: `ruff` (0 errors), `mypy` (815 files clean), `check_no_dashes.py --all` (0 violations), `pnpm typecheck` (clean), `pnpm lint` (0 warnings), `pnpm build` (clean in 1.25s).
  - Screenshots: 5 unclipped viewports (`1440x900` light/dark, `1024x768`, `768x1024`, `390x844`) captured and visually inspected in `docs/qa/KAN-412/screenshots/`.

---

### Verification and Compliance Summary

- **No Unicode Dashes**: Checked via `scripts/check_no_dashes.py` (0 violations across entire repository).
- **Cited Paths**: 100% of referenced paths and modules verified on disk.
- **License Compliance**: Apache-2.0 clean.

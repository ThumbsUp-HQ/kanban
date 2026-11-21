# Clean-Room UI Specialist Review: KAN-60

- **Ticket:** KAN-60 (`[KB-AI-STUDIO-01]`)
- **Title:** AI Studio Polish: Move API Secret Key to Top, Replace Defaults with Probed Models, & Configurable Cutoff Timeout
- **Reviewer:** `ui-spec-2` (Clean-Room UI / UX Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-60`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. UI & UX Architectural Review

1. **API Secret Key Ordering & Prominent Labeling (`AiProviderEditorDrawer.tsx`)**:
   - Secret Key form group is positioned at the top of connection fields (directly below Display Name and above Base URL / Model Probing).
   - Prominently labeled "API Secret Key" for cloud providers (OpenAI, Gemini) and "API Secret Key (Optional for Local Endpoints)" for local engines.
   - Includes password toggle (`data-testid="toggle-show-key-btn"`) with proper accessibility `aria-label`, placeholder hints, and "Clear existing API secret key" checkbox.

2. **Zero Hardcoded Model Defaults & Probed Model Replacement (`AiProviderEditorDrawer.tsx`)**:
   - Initialized new provider drafts with empty allowlist (`""`); removed hardcoded `qwen2.5-coder:7b` / `llama3.2:3b` defaults.
   - On successful probe (`probeAiModels`), replaces `modelAllowlist` with discovered models (`res.models.join(', ')`).
   - Probed model chips feature toggle selection (`✓` / `+`), "Select All Probed" action, and dedicated "Only This" buttons (`data-testid="probe-only-${m}"`) in `kb-probed-chip-item` for instantaneous 1-click model narrowing.

3. **Configurable Cutoff Timeout (ms) (`AiProviderEditorDrawer.tsx`)**:
   - Added dedicated numeric input (`data-testid="provider-timeout-ms-input"`) with min="1000", max="300000", step="1000", and default="30000".
   - Integrated with `FieldHelpHint` referencing timeout policies.
   - Correctly persisted to `settings.timeout_ms` on create/update and forwarded in `ProviderProbeRequest`.

4. **Agent Model Quick-Pick Chips & Datalist (`AgentDefinitionEditorDrawer.tsx`)**:
   - Reads configured workspace providers for matching `providerKind` and aggregates their `model_allowlist` into `quickPickModels`.
   - Binds `<datalist id="agent-model-datalist">` for browser autocompletion and renders styled quick-pick chip buttons (`data-testid="quickpick-model-${m}"`) for 1-click model selection.

5. **AttachHookDialog Route Target (`AttachHookDialog.tsx`)**:
   - Fixed empty agent definition alert link to navigate directly to `/admin/agents` (`data-testid="configure-agents-link"`).

6. **Design System Tokens, Accessibility & Zero-Fluff Standard**:
   - Exactly zero inline JSX `style={...}` attributes introduced; 100% canonical CSS tokens (`cssTokensAudit.test.ts` passed 4/4).
   - Full dark theme support for `.kb-quickpick-chip` and `.kb-probed-only-btn`.
   - Exactly 0 em/en-dashes across the commit.
   - 87/87 tests passed across all 6 test suites with 0 `act(...)` warnings; every touched component individually exceeds >=95% branch coverage (admin-agents: 97.17% branch, admin-ai: 96.23% branch, AiProviderEditorDrawer: 95.75% branch).

---

## 2. Live Full-Stack Verification & Screenshots

Verified against `kanban-liveqa-2` (`:18962`, commit `9d5577ad9b50`):
- `live-ai-provider-ollama-115-probed-desktop-light.png`: Ollama probed models (light mode).
- `live-ai-provider-ollama-115-probed-desktop-dark.png`: Ollama probed models (dark mode).
- `live-ai-provider-gemini-top-key-probed-desktop.png`: Gemini secret key at top and probed models.
- `live-ai-provider-gemini-tablet.png`: Gemini provider drawer on tablet.
- `live-ai-provider-gemini-mobile.png`: Gemini provider drawer on mobile.
- `live-agent-editor-probed-quickpick-desktop.png`: Agent editor quick-pick chips.

---

## 3. Verdict & Signoff

STATUS: APPROVED

UI/UX contracts for KAN-60 are fully verified and approved.

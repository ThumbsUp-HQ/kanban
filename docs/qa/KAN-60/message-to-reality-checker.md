# Reality-Checker Verification Packet: KAN-60

**Ticket ID:** `KAN-60` (`[KB-AI-STUDIO-01]`)
**Title:** AI Studio Polish: Move API Secret Key to Top, Replace Defaults with Probed Models, & Configurable Cutoff Timeout
**Branch:** `main` (commit `9d5577ad9b50`)
**Container Environment:** `http://localhost:18962` (container: `kanban-liveqa-2`)
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`

---

## 1. Executive Summary & Verification Highlights

This packet provides forensic verification for ticket **KAN-60** integrated on `main` at commit `9d5577ad9b50`, incorporating empirical results from zero-mock Live Full-Stack QA against container `kanban-liveqa-2` (`http://localhost:18962`, embedded PostgreSQL 16 + FORCE RLS).

All core requirements and acceptance criteria have been implemented, verified, and certified:

1. **API Secret Key Positioned at Top of Connection Inputs**:
   - In `AiProviderEditorDrawer.tsx`, the API Secret Key form group is rendered at the top of connection inputs (directly under Display Name and above Base URL).
   - Live DOM geometry measurement via `getBoundingClientRect().y`:
     * `#provider-key-input` (`type="password"`): `y=408`
     * `#provider-base-url-input`: `y=522`
     * `#provider-timeout-ms-input`: `y=656`
     * `#probe-models-btn`: `y=741`
     * `#provider-models-input`: `y=787`
   - Includes password toggle button (`data-testid="toggle-show-key-btn"`) and "Clear existing API secret key" checkbox.
   - Preserves write-only custody: existing keys display masked placeholder (`********`) and are never exposed in cleartext.

2. **Zero Hardcoded Model Defaults & Clean Probed Model Discovery**:
   - Initial state for new providers and provider-kind switches sets `modelAllowlist` to `""` (empty string). Hardcoded defaults (`qwen2.5-coder:7b`, `llama3.2:3b`, `gpt-4o`) are completely eliminated.
   - Upstream probing against live servers (`POST /api/v1/admin/ai/providers/probe-models`) replaces the allowlist exclusively with verified server models:
     * Fast GPU Ollama (`192.168.1.115:11434`): populated `son-of-emoji-monster:latest, deepseek-r1:7b, granite3.3:2b, gemma3:4b, qwen3-vl:4b`.
     * Google Gemini (`AQ.Ab8R...REDACTED`): discovered 50 live Gemini models (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, etc.).
     * OpenAI (`sk-proj-...REDACTED`): discovered 99 live models (`gpt-4o-mini`, etc.).
   - Interactive model picker features toggle selection (`✓` / `+`), "Select All Probed", "Clear", and dedicated 1-click "Only This" buttons (`data-testid="probe-only-${m}"`).

3. **Configurable Cutoff Timeout (ms)**:
   - Dedicated numeric input (`data-testid="provider-timeout-ms-input"`) with `min="1000"`, `max="300000"`, `step="1000"`, defaulting to `30000`.
   - Persisted to `provider.settings.timeout_ms` and propagated in `ProviderProbeRequest` and downstream evaluation runs.

4. **Agent Definition Quick-Pick Chips & Datalist**:
   - In `AgentDefinitionEditorDrawer.tsx`, models from enabled providers of the matching kind are dynamically aggregated into `quickPickModels`.
   - Binds `<datalist id="agent-model-datalist">` for native autocompletion and renders styled quick-pick chip buttons (`data-testid="quickpick-model-${m}"`) for 1-click model selection.

5. **AttachHookDialog Route Target**:
   - Fixed empty agent definition alert link in `AttachHookDialog.tsx` to navigate directly to `/admin/agents` (`data-testid="configure-agents-link"`).

---

## 2. Test Suite & Coverage Evidence

- **Unit Tests**: 87/87 passed across 6 test suites with 0 `act(...)` warnings.
- **Component Coverage**:
  * `admin-agents`: 97.17% branch coverage
  * `admin-ai`: 96.23% branch coverage
  * `AiProviderEditorDrawer`: 95.75% branch coverage
  * Overall touched module coverage exceeds >=95% gate standard.
- **Lint & Types**: 0 ESLint warnings, 0 TypeScript errors (`tsc -b --noEmit`), 4/4 CSS design tokens audit passed (`cssTokensAudit.test.ts`).

---

## 3. Artifact Index in `docs/qa/KAN-60/`

- `live-fullstack-proof.txt`: Zero-mock live execution telemetry against `kanban-liveqa-2` (`:18962`, commit `9d5577ad9b50`).
- `unit-test-results.txt`: Verbatim execution outputs for frontend unit test suites (87 passed).
- `build-or-typecheck.txt`: Verbatim TypeScript typecheck and build outputs.
- `git-diff.patch`: Complete git diff patch.
- `api-specialist-review.md`: Dual-specialist API and architecture audit signoff (STATUS: APPROVED).
- `ui-specialist-review.md`: Dual-specialist UI and layout audit signoff (STATUS: APPROVED).
- `screenshots/live-ai-provider-ollama-115-probed-desktop-light.png`: Ollama probed models (light desktop).
- `screenshots/live-ai-provider-ollama-115-probed-desktop-dark.png`: Ollama probed models (dark desktop).
- `screenshots/live-ai-provider-gemini-top-key-probed-desktop.png`: Gemini masked key at top + probed models (desktop).
- `screenshots/live-ai-provider-gemini-tablet.png`: Gemini provider drawer (tablet).
- `screenshots/live-ai-provider-gemini-mobile.png`: Gemini provider drawer (mobile).
- `screenshots/live-agent-editor-probed-quickpick-desktop.png`: Agent definition quick-pick chips (desktop).

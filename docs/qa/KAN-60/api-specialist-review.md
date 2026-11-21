# Clean-Room API Specialist Review: KAN-60

- **Ticket:** KAN-60 (`[KB-AI-STUDIO-01]`)
- **Title:** AI Studio Polish: Move API Secret Key to Top, Replace Defaults with Probed Models, & Configurable Cutoff Timeout
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Security Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-60`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Audit Scope

A clean-room API, Security, Schema, and Contract audit was conducted for ticket **KAN-60** integrated on branch `main` at commit `9d5577ad9b50`. The review integrates empirical evidence from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-2` (`http://127.0.0.1:18962`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-60/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-60/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-60 resolves critical usability and custody friction in AI Studio configuration, enforces clean model allowlist discovery, provides configurable timeout bounds, and connects quick-pick models to agent definitions.

Key architectural and security invariants certified:
1. **Schema Integrity & Validation (`kanban/api/v1/admin/ai_schemas.py`)**:
   - `SavedProviderProbeRequest`: Added `settings_json: dict[str, Any] | None = Field(default=None, description="Optional override settings (uses saved settings if omitted)")`.
   - `ProviderProbeRequest`: Validates `settings_json` along with `provider_kind`, `base_url`, and `api_key`.
   - Both schemas maintain strict `ConfigDict(extra="forbid")`, forbidding unexpected parameter injection or oracle leakage.
   - Secret key constraints: `api_key` remains `SecretStr | None` bounded by `_validate_api_key_len` (`_MAX_KEY_LENGTH = 4096`), ensuring zero cleartext leakage in serialization or logging.
2. **API Client & Request Routing (`aiAdminApi.ts`)**:
   - `probeAiModels` correctly accepts `payload: ProviderProbeRequest` forwarding `settings_json: { timeout_ms: timeoutMs }`.
   - Targets draft endpoint `POST /api/v1/admin/ai/providers/probe-models` or saved provider endpoint `POST /api/v1/admin/ai/providers/{id}/probe-models`.
   - Test connection endpoint `testProviderConnection` similarly propagates `settings_json`.
3. **Security Invariants & Write-Only Custody (`AiProviderEditorDrawer.tsx`)**:
   - Secret key field is moved to the TOP of connection inputs (above Base URL and Probe Models), improving developer workflow ergonomics.
   - Preserves write-only custody: existing keys display masked placeholder (`********`), and keys are only modified when explicitly entered or cleared via `clear-key-checkbox`.
   - If `clearExistingKey` is checked, `api_key: ""` is sent to trigger secure erasure; if untouched, `api_key` is omitted (`undefined`), preserving existing encrypted KEK-wrapped envelope storage.
   - Air-gap enforcement remains active: cloud kinds (OpenAI, Gemini) are blocked when `airGapMode` is set.
4. **Model Allowlist Sanitization & Probing Mechanics**:
   - Initial state for new providers and provider-kind switches sets `modelAllowlist` to `""` (empty string), completely eliminating unvetted hardcoded defaults (`qwen2.5-coder:7b`, `llama3.2:3b`, `gpt-4o`).
   - On successful probe (`probeAiModels`), `modelAllowlist` is set exclusively to probed server models (`res.models.join(', ')`), preventing hallucinated models.
   - Interactive model picker provides toggle selection, `Select All Probed`, `Clear`, and dedicated `Only This` narrowing buttons (`data-testid="probe-only-${m}"`).
5. **Configurable Timeout Bounds**:
   - `timeout_ms` input (`#provider-timeout-ms-input`) enforces strict numeric bounds: `min="1000"`, `max="300000"`, `step="1000"`, defaulting to `30000`.
   - Persisted to `provider.settings.timeout_ms` and propagated to downstream probe/test calls.
6. **Agent Definition & Hook Dialog Integration**:
   - `AgentDefinitionEditorDrawer.tsx` dynamically populates quick-pick chips and `<datalist>` from matching enabled workspace providers for 1-click model selection.
   - `AttachHookDialog.tsx` correctly routes the empty agent alert link to `/admin/agents`.

---

## 2. Live Container Verification (`kanban-liveqa-2`, `:18962`, commit `9d5577ad9b50`)

- **Vertical DOM Geometry (`AiProviderEditorDrawer`)**:
  * `#provider-key-input` (type="password"): y=408 (TOP of connection fields).
  * `#provider-base-url-input`: y=522.
  * `#provider-timeout-ms-input`: y=656.
  * `#probe-models-btn`: y=741.
  * `#provider-models-input`: y=787.
- **Empty Initial Model Allowlist**:
  * Initialized empty (`""`) across openai, ollama, and gemini.
- **Live Upstream Probing & Model Discovery**:
  * Ollama GPU (`http://192.168.1.115:11434`): populated exclusively with probed models (`gemma3:4b`, `granite3.3:2b`, `deepseek-r1:7b`, `qwen3-vl:4b`, `son-of-emoji-monster:latest`).
  * Gemini (`AQ.Ab8R...`): discovered 50 live Gemini models. Selected `gemini-2.5-flash-lite`.
  * OpenAI (`sk-proj-...`): discovered 99 live OpenAI models. Selected `gpt-4o-mini`.
- **Agent Quick-Picks & AttachHook Link**:
  * `/admin/agents` link verified in `AttachHookDialog`.
  * `AgentDefinitionEditorDrawer` quick-pick chips rendered and functional for 1-click selection.
- **Screenshots in `docs/qa/KAN-60/screenshots/`**:
  * `live-ai-provider-ollama-115-probed-desktop-light.png`
  * `live-ai-provider-ollama-115-probed-desktop-dark.png`
  * `live-ai-provider-gemini-top-key-probed-desktop.png`
  * `live-ai-provider-gemini-tablet.png`
  * `live-ai-provider-gemini-mobile.png`
  * `live-agent-editor-probed-quickpick-desktop.png`
- **Runtime Telemetry**:
  * Console errors: 0. Page errors: 0. 5xx responses: 0.
  * Secret leakage: 0 (zero raw keys in DOM or logs).

---

## 3. Test Suite & Coverage Verification

- Vitest Results: 87/87 passed across all 6 suites in 2.86s.
- Coverage:
  * Statements: 99.16%, Branch: 96.52%, Lines: 100%.
  * Every touched module meets or exceeds the >=95% gate standard.
- Static Analysis:
  * `tsc -b --noEmit`: Clean.
  * `eslint`: Clean (0 warnings).
  * `check_no_dashes`: Clean (0 em/en-dashes).

---

## 4. Verdict & Signoff

STATUS: APPROVED

All API contracts, security bounds, drawer workflows, and model probing mechanics for KAN-60 are certified on main at commit `9d5577ad9b50`.

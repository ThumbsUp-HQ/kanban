# KAN-22: Redesign AI Providers Studio UX

## Summary of Changes
Ticket: `KAN-22` ([KB-P3-AUDIT-16])
Target Modules:
- `kanban/web/src/features/admin-ai/aiAdminApi.ts`
- `kanban/web/src/features/admin-ai/AiProviderEditorDrawer.tsx`
- `kanban/web/src/features/admin-ai/AiStudioPage.tsx`
- `kanban/web/src/features/admin-ai/aiStudio.css`
- `kanban/web/src/features/admin-ai/AiBudgetModal.tsx`
- `kanban/web/src/features/admin-ai/__tests__/aiAdminApi.test.ts`
- `kanban/web/src/features/admin-ai/__tests__/AiStudioPage.test.tsx`
- `kanban/web/e2e/qa/kan-22-screenshots.spec.ts`

### 1. Clean 3-Protocol Selector & Local Key UX
- Removed broken `<option value="custom">Custom Compatible</option>` which generated 422 validation errors on the backend.
- Provided 3 clean, first-class protocols in `AiProviderEditorDrawer.tsx`:
  - `Ollama`: Defaults to `http://127.0.0.1:11434` with LAN/host guidance.
  - `OpenAI / OpenAI-Compatible`: Defaults to `https://api.openai.com/v1` with guidance on vLLM, LM Studio, llama.cpp, and LiteLLM endpoints.
  - `Google Gemini`: Defaults to `https://generativelanguage.googleapis.com`.
- API Secret Key is marked optional when `Ollama` is selected or when a local/private endpoint is used with `OpenAI`.
- Providers running on local endpoints without a configured key display a clear `🔓 No Key Required (Local)` badge instead of a warning.

### 2. Live [🔍 Probe Models] Picker & [Test Connection] Button
- Added `[🔍 Probe Models]` button adjacent to the Model Allowlist field in `AiProviderEditorDrawer.tsx`.
- Calls `/api/v1/admin/ai/providers/probe-models` for draft configurations and `/{id}/probe-models` for saved providers.
- Displays probed models as interactive chips with search filtering, multi-select toggling, `Select All`, and `Clear` controls, alongside manual text input fallback.
- Added `[Test Connection]` button in the drawer footer and on each provider card in `AiStudioPage.tsx`, displaying live latency and model count (`Connected in Xms - N models available`) or actionable errors.

### 3. Auto-Inferred Data Residency Tier in Collapsible Advanced Settings
- Added `isLocalEndpoint` utility in `aiAdminApi.ts` detecting loopback (`127.0.0.1`, `localhost`), RFC1918 private IPv4 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv6 ULA/loopback (`::1`, `fc00::/7`, `fd00::/8`), and private hostnames (`.local`, `.lan`, `.internal`).
- Added `inferResidencyTier` auto-inferring `local_only` for Ollama or private/local endpoints, and `cloud_standard` for public HTTPS endpoints.
- Displays subtle `🏠 Local / Zero-Egress` or `☁️ Cloud` residency badge on provider cards.
- Encapsulated manual `residency_tier` override dropdown inside a collapsed `<details className="kb-advanced-settings">` (`▸ Advanced Settings`) section in `AiProviderEditorDrawer.tsx`.

### 4. Drag-and-Drop #1..#N Failover Stack & Strict CSP CSS
- Removed numeric `Priority Order (100)` input from provider creation/editing; new providers append to the bottom of the failover priority stack.
- Redesigned `AiStudioPage.tsx` into a numbered `#1..#N` Failover Priority Stack.
- Added pointer drag-and-drop support via `⋮⋮` grab handle and accessible `▲` Move Up / `▼` Move Down buttons.
- Reordering calls `PUT /api/v1/admin/ai/providers/order` with optimistic UI updates and automated rollback upon server or network failure.
- Strict CSP `style-src 'self'`: Eliminated 100% of inline `style={{...}}` JSX attributes across all `admin-ai` components, moving all styles into `aiStudio.css` using canonical CSS variables validated by `cssTokensAudit.test.ts`.

---

## Verification Evidence

1. **Unit & Branch Coverage**:
   - `pnpm --filter @kanban/web exec vitest run --coverage --coverage.include="src/features/admin-ai/**" src/features/admin-ai`
   - Output: 39 tests passing across 2 test suites.
   - Coverage: 100% Lines, 96.73% Branches across all touched files (all exceed `>= 95.10%`).
   - Detailed breakdown:
     - `AiBudgetModal.tsx`: 100% Lines, 96.15% Branches
     - `AiProviderEditorDrawer.tsx`: 100% Lines, 96.75% Branches
     - `AiStudioPage.tsx`: 100% Lines, 96.05% Branches
     - `aiAdminApi.ts`: 100% Lines, 98.14% Branches

2. **Automated Token Audit**:
   - `pnpm --filter @kanban/web exec vitest run src/styles/__tests__/cssTokensAudit.test.ts`
   - Result: 4 of 4 tests passing; 100% of `var(--*)` references resolve to canonical tokens.

3. **Static Analysis & Linters**:
   - `python3 -m scripts.check_no_dashes --all`: Passed with 0 em/en dashes.
   - `pnpm --filter @kanban/web run typecheck`: Passed with 0 errors (`tsc -b --noEmit`).
   - `pnpm --filter @kanban/web run lint`: Passed with 0 errors and 0 warnings (`eslint . --max-warnings 0`).

4. **Playwright Visual Verification**:
   - Spec: `kanban/web/e2e/qa/kan-22-screenshots.spec.ts`
   - Viewports: Desktop (1440x900) and Mobile (390x844) in Light and Dark themes (14 tests passed).
   - Artifacts generated in `docs/qa/KAN-22/screenshots/`:
     - `01-failover-stack-light-desktop.png` & `01-failover-stack-light-mobile.png` (5-provider stack)
     - `02-failover-stack-dark-desktop.png` & `02-failover-stack-dark-mobile.png` (Dark theme stack)
     - `03-test-connection-card-desktop.png` & `03-test-connection-card-mobile.png` (Inline card test latency & models)
     - `04-probe-models-chips-desktop.png` & `04-probe-models-chips-mobile.png` (Interactive probed model chips)
     - `05-advanced-settings-collapsed-desktop.png` & `05-advanced-settings-collapsed-mobile.png` (Collapsed Advanced Settings)
     - `06-advanced-settings-expanded-desktop.png` & `06-advanced-settings-expanded-mobile.png` (Expanded Advanced Settings)
     - `07-drawer-test-connection-desktop.png` & `07-drawer-test-connection-mobile.png` (Drawer Test Connection button & status)

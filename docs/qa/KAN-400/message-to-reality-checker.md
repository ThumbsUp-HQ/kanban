# Message to Reality-Checker (KAN-400)

## Forensic Handover Packet: KAN-400

- **Ticket**: `KAN-400` (`[KB-AI-PROVIDER-NO-PASSWORD-SAVE] Suppress browser password save prompt on AI Provider Drawer with visual bullet masking fallback & 0 input[type="password"] elements`)
- **Author Agent**: Builder `b-kan400`
- **Target Auditor**: Clean-Room `reality-checker` (`rc-kan400`)
- **Review Mode**: Passive Forensic Verification Mode (Zero shared implementation assumptions)

---

## 1. Summary of Changes

This ticket resolves the credential manager autofill issue where Chromium, Safari, Firefox, Edge, 1Password, LastPass, and Bitwarden mistook the AI Provider Registration/Editor form for an account login prompt (offering to save the provider name as a username and the API key as the account login password for `k.hackedyour.info`).

1. **Root Cause Analysis**:
   - Web browsers (specifically Blink/Chromium's password manager heuristics) trigger save-login prompts whenever an `input[type="text"]` is paired with an `input[type="password"]` inside or outside a `<form>`.
   - Third-party extension password managers (1Password, Bitwarden, LastPass) also inject autofill and overlay icons unless explicit ignore hints are declared.

2. **Complete Elimination of `input[type="password"]`**:
   - `AiProviderEditorDrawer.tsx` now renders `provider-key-input` strictly as `type="text"` across its entire lifecycle.
   - Zero `input[type="password"]` elements exist anywhere inside `AiProviderEditorDrawer`.
   - Automated assertions verify `container.querySelectorAll('input[type="password"]').length === 0`.

3. **Form & Input Password-Manager Ignore Attributes**:
   - Form declared with `autoComplete="off"` and `data-form-type="other"`.
   - `provider-name-input` declared with:
     - `autoComplete="off"`
     - `data-1p-ignore="true"`
     - `data-lpignore="true"`
     - `data-bwignore="true"`
     - `data-form-type="other"`
   - `provider-key-input` declared with:
     - `autoComplete="off"`
     - `data-1p-ignore="true"`
     - `data-lpignore="true"`
     - `data-bwignore="true"`
     - `data-form-type="other"`
     - `spellCheck={false}`
     - `autoCorrect="off"`
     - `autoCapitalize="off"`
     - `inputMode="text"`

4. **Visual Masking & Non-Webkit Fallback Engine**:
   - In modern Chromium and WebKit browsers supporting `-webkit-text-security`, the class `.kb-masked-api-key` in `aiStudio.css` obscures the input value with `-webkit-text-security: disc;`.
   - In Firefox/Gecko browsers where `!CSS.supports?.('-webkit-text-security', 'disc')`:
     - An intelligent masking fallback (`computeNextApiKey()`) renders bullet glyphs (`•`, `\u2022`) in the input while storing the pristine secret in React state.
     - Handles typing, backspace deletion, and multi-character paste replacement without state corruption.
     - The submitted payload transmits `apiKey` (the pristine secret), never the visual bullet string.
   - Eye icon button (`aria-label="Show secret key"` / `"Hide secret key"`) allows administrators to reveal the key in clear text.

---

## 2. Verification Artifacts & Test Results

All verification artifacts are located in `docs/qa/KAN-400/`:

- `docs/qa/KAN-400/unit-test-results.txt`:
  - Vitest test suite `src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx`:
  - 42/42 tests passing in 2.59s.
  - Coverage:
    - Statements: 100%
    - Branches: 96.04% (exceeds mandatory >=95% gate)
    - Functions: 100%
    - Lines: 100%
  - Test suites include Chromium mode, Firefox fallback mode, show/hide toggle, backspace/typing/paste logic, 0 `input[type="password"]` assertions, and exact payload submission.

- `docs/qa/KAN-400/build-check.txt`:
  - `python3 scripts/check_no_dashes.py --all`: 0 violations across all files.
  - `pnpm --dir kanban/web typecheck`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings across all files.
  - `pnpm --dir kanban/web build`: Vite production build passed cleanly in 1.36s (and `scripts/capture_kan400_screenshots.mjs` renders the real Vite production build).

- `docs/qa/KAN-400/api-specialist-review.md`:
  - Signed by API Specialist (`@api-spec`) with STATUS: APPROVED.
  - Note: `N/A - Pure Frontend Credential-Manager Suppression`.

- `docs/qa/KAN-400/ui-specialist-review.md`:
  - Signed by UI Specialist (`@ui-spec`) with STATUS: APPROVED.
  - Confirms design system token compliance, visual bullet masking, accessibility ARIA labels, zero password elements, and responsive layout across all 5 viewports.

- `docs/qa/KAN-400/screenshots/`:
  - Desktop 1440x900 Light: `01-desktop-1440x900-light.png`, `01-desktop-1440x900-light-masked.png`, `01-desktop-1440x900-light-revealed.png`
  - Desktop 1440x900 Dark: `02-desktop-1440x900-dark.png`, `02-desktop-1440x900-dark-masked.png`, `02-desktop-1440x900-dark-revealed.png`
  - Tablet 1024x768: `03-tablet-1024x768.png`, `03-tablet-1024x768-masked.png`, `03-tablet-1024x768-revealed.png`
  - Tablet Portrait 768x1024: `04-tablet-portrait-768x1024.png`, `04-tablet-portrait-768x1024-masked.png`, `04-tablet-portrait-768x1024-revealed.png`
  - Mobile Portrait 390x844: `05-mobile-390x844.png`, `05-mobile-390x844-masked.png`, `05-mobile-390x844-revealed.png`
  - All canonical alias files (`1440x900-desktop-light.png`, `1440x900-desktop-dark.png`, `1024x768-tablet.png`, `768x1024-tablet-portrait.png`, `390x844-mobile-portrait.png`).

- `docs/qa/KAN-400/changed-files-manifest.txt`:
  - Cryptographic SHA-256 hashes of all changed and artifact files.

- `docs/qa/KAN-400/git-diff.patch`:
  - Full unified git diff from `main` to HEAD.

---

## 3. Scope Boundary Compliance

Strict adherence to task constraints:
- Only modified:
  - `kanban/web/src/features/admin-ai/AiProviderEditorDrawer.tsx`
  - `kanban/web/src/features/admin-ai/aiStudio.css`
  - `kanban/web/src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx`
  - `scripts/capture_kan400_screenshots.mjs`
  - `docs/qa/KAN-400/*`
- Zero unintended edits to other files or backend modules.

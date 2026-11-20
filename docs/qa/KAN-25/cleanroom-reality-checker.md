# Forensic Reality-Checker Certification Report: KAN-25

- **Ticket:** KAN-25 (`[KB-P3-AUDIT-19] Add Self-Service Passkey & FIDO2 Security Key Registration, Key Testing, and AAL2 Step-Up Handling on Profile Settings (3 Problems)`)
- **Auditor:** `TestingRealityChecker` (Clean-Room Passive Forensic Audit)
- **Target Path:** `/home/adamoutler/kanban`
- **Inspected Commit / Proof Baseline:** `53f7b6e` (`docs/qa/KAN-25/`)
- **Verdict:** `READY`
- **Grade:** `A`

---

## 1. Executive Summary & Forensic Cross-Validation

Independent read-only inspection of the source files on disk, `docs/qa/KAN-25/git-diff.patch`, `docs/qa/KAN-25/changed-files-manifest.txt`, `docs/qa/KAN-25/unit-test-results.txt`, `docs/qa/KAN-25/build-or-typecheck.txt`, `docs/qa/KAN-25/api-specialist-review.md`, `docs/qa/KAN-25/ui-specialist-review.md`, `docs/qa/KAN-25/live-fullstack-proof.txt`, `docs/qa/KAN-25/message-to-reality-checker.md`, and all 10 PNG screenshots in `docs/qa/KAN-25/screenshots/` confirms that all three problems in **KAN-25** are implemented, tested above the `>=95%` coverage threshold, and verified end-to-end against a live unmocked PostgreSQL + FastAPI + React + CDP CTAP2 stack.

Two minor non-blocking visual/UX polish observations were identified during screenshot and code inspection (detailed in Section 5); neither violates any ticket specification, security invariant, or responsiveness requirement.

---

## 2. Specification Compliance Matrix

### Problem 1: `PasskeyEnrollModal.tsx`, `webauthn.ts`, and Secure-Context Guard (`PASS`)
- **`isWebAuthnSupported()` (`kanban/web/src/features/auth/webauthn.ts:200-210`):** Verified directly on disk to check `typeof window !== 'undefined'`, `window.isSecureContext`, `typeof window.PublicKeyCredential !== 'undefined'`, `typeof navigator !== 'undefined'`, `typeof navigator.credentials !== 'undefined'`, `typeof navigator.credentials.create === 'function'`, and `typeof navigator.credentials.get === 'function'`.
- **Self-Service Enrollment Modal (`kanban/web/src/features/settings/PasskeyEnrollModal.tsx`):**
  - Supports `platform` (`Passkey`), `cross-platform` (`FIDO2 Hardware Key`), and `any` (`Any Authenticator`) choices, initialized via `initialAttachment` from `+ Add Passkey` (`platform`) and `+ Add FIDO2 Security Key` (`cross-platform`) in `PersonalSettingsPage.tsx:694-717`.
  - Required `Nickname` field (`maxLength={64}`, `required`, trimmed validation rejecting empty or `> 64` chars).
  - Flow verified: `fetchWebauthnRegistrationOptions(attachmentHint)` (`POST /api/v1/auth/webauthn/register/options`) -> `prepareCreationOptions()` -> `navigator.credentials.create()` -> `serializeRegistrationCredential()` -> `verifyWebauthnRegistration()` (`POST /api/v1/auth/webauthn/register/verify`).
  - Query invalidation verified (`PasskeyEnrollModal.tsx:139-143`): invalidates `['myPasskeys']`, `['myMfaStatus']`, `qk.me()`, `['myProfile']`, and `['auth', 'me']`.
  - Modal accessibility verified: single `✕` header close button (`aria-label="Close"`, `min-width: 44px; min-height: 44px` in `PasskeyEnrollModal.css:51-52`), `Escape` dismiss blocked while `isSubmitting`, and `Tab` / `Shift+Tab` focus trap (`PasskeyEnrollModal.tsx:56-111`).
- **Insecure Context Notice (`PersonalSettingsPage.tsx:98-99, 699, 710, 720-728`):** Renders `data-testid="webauthn-insecure-context-notice"` (`"Browser WebAuthn requires HTTPS or localhost to register and use passkeys or security keys."`) using `.kb-personal-settings-alert-warning` (defined in `PersonalSettingsPage.css:55-59` with `var(--warn-bg)` and `var(--warn-fg)`) and disables `+ Add Passkey` and `+ Add FIDO2 Security Key` when `!isSecure || !isSupported`.

### Problem 2: Credential Table Device Badges, Clone Warning, and Scoped `[Test Key]` (`PASS`)
- **API & Schema Alignment:**
  - `WebauthnCredentialItem` (`kanban/web/src/features/settings/personalSettingsApi.ts:50-60`) includes `credential_id`, `transports`, `sign_count`, `aaguid`, and `suspect_clone_at`.
  - Backend `list_credentials` (`kanban/api/v1/auth_webauthn.py:577-594`) emits `"credential_id": bytes_to_base64url(bytes(r.credential_id))` alongside internal UUID `"id"`, verified in `kanban/tests/auth/test_webauthn.py:266-268`.
- **Device Badges & Clone Warning (`PersonalSettingsPage.tsx:760-790`):**
  - Renders `🔑 FIDO2 Security Key` (`kb-passkey-badge--security-key`) when transports include `usb`/`nfc`/`ble` without `internal`/`hybrid`, and `📱 Passkey` (`kb-passkey-badge--passkey`) otherwise.
  - Renders `⚠️ Suspected Clone` pill (`data-testid="passkey-clone-warning-<id>"`, `aria-label="Suspected cloned credential"`) when `pk.suspect_clone_at` is non-null.
- **Scoped `[Test Key]` (`PersonalSettingsPage.tsx:152-212`):**
  - Calls `fetchWebauthnAuthenticationOptions()` (`POST /api/v1/auth/webauthn/authenticate/options`), filters `optionsJson.allowCredentials` to the clicked credential (`cred.credential_id ?? cred.id`), runs `prepareRequestOptions()` -> `navigator.credentials.get()` -> `serializeAssertionCredential()` -> `verifyWebauthnAuthentication()`.
  - Verifies `verifyRes.credential_id` matches `cred.id` or `cred.credential_id` (throwing `'A different credential responded than the one tested.'` on mismatch).
  - Displays section-scoped `[data-testid="passkey-verified-banner"]` (`👍 Key verified (<nickname>)`) with dismiss button directly above the passkeys table and invalidates `['myPasskeys']` to refresh `last_used_at`.
  - Live proof Check 3 confirms with two simultaneous active CDP CTAP2 authenticators that testing `YubiKey 5C NFC` incremented only YubiKey's `sign_count` (`1 -> 2`) and `last_used_at`, leaving `MacBook Touch ID` at `sign_count=1`, `last_used_at=null`.

### Problem 3: `AAL2_REQUIRED` and `AAL2_STALE` Step-Up Interception (`PASS`)
- **`handleInterceptAal2` (`PersonalSettingsPage.tsx:138-150`):** Intercepts `ApiProblem` with `err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE'`, opens `aal2-stepup-dialog` (layered via `.kb-personal-settings-modal-backdrop--stepup` at `z-index: 1100` above `PasskeyEnrollModal`'s `z-index: 1000`), and stores `retryAction` in `pendingAction` to automatically resume on `SecondFactorStep` `onSuccess` (`PersonalSettingsPage.tsx:1190-1195`).
- **Coverage Across Required Workflows:**
  - Passkey enrollment: `PasskeyEnrollModal.tsx:148` delegates to `onInterceptAal2(err, executeRegistration)`.
  - Passkey deletion: `handleDeletePasskey` (`PersonalSettingsPage.tsx:411`).
  - TOTP management: `handleStartTotpEnroll` (`326`), `handleDisableTotp` (`360`), `handleRegenerateRecoveryCodes` (`378`).
  - Also wired on password change (`308`), identity unlink (`428`), and `Test Key` (`197`).
- **Live Verification:** `live-fullstack-proof.txt` Check 7 proved both `403 AAL2_REQUIRED` on passkey `Remove` (Sub-test 3A) and `403 AAL2_STALE` on `+ Add FIDO2 Security Key` (Sub-test 3B) against real PostgreSQL session state mutations, with automatic retry succeeding (`HTTP 200`) without a second user click.

---

## 3. Quality Gates, Coverage & Static Analysis Evidence

- **Diff Scope (`docs/qa/KAN-25/git-diff.patch` vs `changed-files-manifest.txt`):** 2530 lines covering exactly 12 scoped source/test files (`0` `docs/qa/*` files inside patch).
- **Backend Unit/Integration Coverage (`docs/qa/KAN-25/unit-test-results.txt`):**
  - Pytest (`test_webauthn.py`, `test_kan24_fido2_enrollment_and_guards.py`): **23 passed** in 9.97s; `kanban/api/v1/auth_webauthn.py` coverage = **98%** (`>=95%` met).
- **Frontend Unit Coverage (`docs/qa/KAN-25/unit-test-results.txt`):**
  - Vitest (5 files): **105 passed** (0 failed).
  - Combined coverage: **99.32% Stmts, 96.35% Branch, 99.21% Funcs, 99.76% Lines**.
  - Per-file Stmts / Branch: `webauthn.ts` (100% / 97.56%), `PasskeyEnrollModal.tsx` (98.92% / 98.59%), `PersonalSettingsPage.tsx` (99.32% / 95.39%), `personalSettingsApi.ts` (100% / 100%).
  - `cssTokensAudit.test.ts`: **4 passed** (`0` undefined CSS tokens).
- **Static Checks & Build (`docs/qa/KAN-25/build-or-typecheck.txt`):**
  - `ruff check .`: passed.
  - `ruff format --check .`: 1880 files formatted.
  - `mypy`: 0 issues across 1096 source files.
  - `lint-imports`: Contracts: 2 kept, 0 broken.
  - `tsc -b --noEmit`, `eslint . --max-warnings 0`, `vite build` (1.17s), and `scripts.check_no_dashes --all`: 0 errors.
- **Zero-Mock & Hygiene Verification:**
  - `docs/qa/KAN-25/live-fullstack-proof.txt`: 0 `mockApi` or `page.route` stubs; all 7 checks executed live against container `kanban-liveqa-1` (`http://localhost:18951` and `http://172.17.0.4:8080`) with PostgreSQL 16 (`FORCE RLS`) and CDP CTAP2 authenticators; `0` uncaught application console errors, `0` pageerrors.
  - Touched TSX files (`PasskeyEnrollModal.tsx`, `PersonalSettingsPage.tsx`): `0` inline `style={...}` props.
  - Punctuation: `0` em-dashes or en-dashes found in touched source/test files or `docs/qa/KAN-25/` artifacts.
- **Specialist Approvals:** `api-specialist-review.md` (`STATUS: APPROVED`) and `ui-specialist-review.md` (`STATUS: APPROVED`) verified on disk.

---

## 4. Visual Audit of All 10 Live Screenshots (`docs/qa/KAN-25/screenshots/`)

1. `live-kan25-enroll-modal-desktop-light.png`: Centered dialog, single `✕` close button, focused `Nickname` input, 3 authenticator radio cards (`Passkey`, `FIDO2 Hardware Key`, `Any Authenticator`), `Cancel` and disabled `Continue`. Crisp alignment.
2. `live-kan25-enroll-modal-desktop-dark.png`: High-contrast dark-theme rendering, crisp borders and active radio highlight.
3. `live-kan25-enroll-modal-mobile-light.png`: 390x844 bottom-sheet layout, full-width, zero clipping, readable labels and accessible tap targets.
4. `live-kan25-profile-verified-desktop-light.png`: Section 3 renders `👍 Key verified (YubiKey 5C NFC)` banner with `Dismiss` directly above the passkeys table; `YubiKey 5C NFC` (`🔑 FIDO2 Security Key`, `Last Used: 11/20/2026`), `MacBook Touch ID` (`📱 Passkey`, `Never`), and fallback `Passkey` (`📱 Passkey`, `Never`).
5. `live-kan25-profile-verified-desktop-dark.png`: Dark-mode Section 3 verified banner and passkeys table, consistent contrast and single-row action buttons (`Test Key`, `Rename`, `Remove`).
6. `live-kan25-insecure-context-desktop-light.png`: Real `http://172.17.0.4:8080` origin (`isSecureContext: false`). `+ Add Passkey` and `+ Add FIDO2 Security Key` are disabled; yellow warning banner (`Browser WebAuthn requires HTTPS or localhost to register and use passkeys or security keys.`) is visible within the 1440x900 viewport.
7. `live-kan25-profile-mobile-light.png`: 390x844 light mobile cards. `👍 Key verified (YubiKey 5C NFC)` banner wraps cleanly; `CREATED 11/20/2026` and `LAST USED 11/20/2026` / `Never` render cleanly separated on opposite ends of each card (`56.8px` gap, zero horizontal overflow); badges stay single-line (`white-space: nowrap`); `Test Key`, `Rename`, `Remove` buttons align cleanly.
8. `live-kan25-profile-mobile-dark.png`: 390x844 dark mobile cards, matching crisp layout and dark-theme token contrast.
9. `live-kan25-clone-warning-desktop-light.png`: `MacBook Touch ID` displays both `📱 Passkey` and high-contrast red `⚠️ Suspected Clone` pill.
10. `live-kan25-aal2-stepup-desktop-light.png`: `Security Verification Required (AAL2)` dialog rendered cleanly centered with `Passkey` and `Recovery code` tabs, `Use passkey`, `Cancel`, and `Cancel and return to sign-in`.

---

## 5. Minor Non-Blocking Observations (Transparency Notes)

1. **0px Vertical Gap Above Section 3 Alert Banners on Wrapped Desktop Header:** In `live-kan25-profile-verified-desktop-light.png`, `live-kan25-profile-verified-desktop-dark.png`, and `live-kan25-insecure-context-desktop-light.png`, because `.kb-personal-settings-header-row` wraps the `+ Add Passkey` / `+ Add FIDO2 Security Key` buttons onto a second line and lacks `margin-bottom` while `.kb-personal-settings-alert` lacks `margin-top`, the top border of `[data-testid="passkey-verified-banner"]` / `[data-testid="webauthn-insecure-context-notice"]` sits flush against the bottom of the buttons. Non-blocking cosmetic polish.
2. **`Test Key` Button State on Insecure Origins:** On `!isSecure` (`PersonalSettingsPage.tsx:804`), `+ Add Passkey` and `+ Add FIDO2 Security Key` are disabled, while per-row `Test Key` buttons remain enabled (clicks are safely caught by `try/catch` in `handleTestKey` and show an error alert). Non-blocking.

---

## 6. Final Certification

- **Verdict:** `READY`
- **Grade:** `A`
- **Certification Summary:** All KAN-25 functional, security, accessibility, test-coverage (`>=95%`), static-analysis, specialist-review, and zero-mock live full-stack requirements are verified by concrete on-disk evidence. Approved for ticket closure.

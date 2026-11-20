# Reality Checker Verification Hand-off: KAN-25

## Ticket Information
- Ticket ID: KAN-25 ([KB-P3-AUDIT-19])
- Title: Add Self-Service Passkey & FIDO2 Security Key Registration, Key Testing, and AAL2 Step-Up Handling on Profile Settings (3 Problems)
- Branch: feat/KAN-25
- Base Commit: 887e7e029127b77b5868a4d7c35dd2b818d3a4e5
- Head Commit: 2db09d6
- Scoped Files Touched:
  - `kanban/web/src/features/auth/webauthn.ts`
  - `kanban/web/src/features/auth/webauthn.test.ts`
  - `kanban/web/src/features/settings/personalSettingsApi.ts`
  - `kanban/web/src/features/settings/personalSettingsApi.test.ts`
  - `kanban/web/src/features/settings/PasskeyEnrollModal.css`
  - `kanban/web/src/features/settings/PasskeyEnrollModal.tsx`
  - `kanban/web/src/features/settings/__tests__/PasskeyEnrollModal.test.tsx`
  - `kanban/web/src/features/settings/PersonalSettingsPage.css`
  - `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
  - `kanban/web/src/features/settings/__tests__/PersonalSettingsPage.test.tsx`

---

## Core Problems Addressed & Verified

### 1. Self-Service Passkey & FIDO2 Security Key Registration Modal (`PasskeyEnrollModal.tsx` & `.css`)
- Root cause: Profile settings previously lacked self-service WebAuthn credential enrollment, only allowing renaming or deleting existing passkeys. Users could not register new synced platform passkeys or hardware security keys.
- Implementation:
  - Updated `isWebAuthnSupported()` in `kanban/web/src/features/auth/webauthn.ts` to strictly verify `window.isSecureContext === true`, `typeof window.PublicKeyCredential !== 'undefined'`, and `typeof navigator.credentials?.create === 'function' && typeof navigator.credentials?.get === 'function'`. Added helper functions `prepareCreationOptions` and `prepareRequestOptions` to safely decode base64url challenges and IDs into ArrayBuffers.
  - In Section 3 (`Passkeys & Security Keys`) of `PersonalSettingsPage.tsx`, added `+ Add Passkey` and `+ Add FIDO2 Security Key` action buttons that launch `PasskeyEnrollModal.tsx`.
  - In `PasskeyEnrollModal.tsx`, users select between authenticator attachments (`Passkey (Device / Synced)` -> `"platform"`, `FIDO2 Hardware Key (USB / NFC)` -> `"cross-platform"`, or `Any` -> `undefined`) and input a required `Nickname` (max 64 characters).
  - Wires live backend WebAuthn endpoints: `fetchWebauthnRegistrationOptions` (`POST /api/v1/auth/webauthn/register/options`) -> `navigator.credentials.create()` -> `serializeRegistrationCredential()` -> `verifyWebauthnRegistration` (`POST /api/v1/auth/webauthn/register/verify`).
  - Automatically invalidates QueryClient caches for `['myPasskeys']`, `['myMfaStatus']`, and `qk.me()` upon successful enrollment.
  - When `!window.isSecureContext`, displays an explicit inline alert banner (`webauthn-insecure-context-notice`) explaining that browser WebAuthn requires HTTPS or localhost, and cleanly disables enrollment buttons.

### 2. Credential Table Device Badges, Clone Warning Pill, & `[Test Key]` Verification
- Root cause: Passkey table previously displayed raw rows without indicating whether a credential was a synced platform passkey or a hardware security key, omitted clone detection warnings, and lacked an interactive key testing mechanism.
- Implementation:
  - Extended `WebauthnCredentialItem` in `personalSettingsApi.ts` with `transports`, `sign_count`, `aaguid`, and `suspect_clone_at` matching the live backend schema from `GET /api/v1/auth/webauthn/credentials`.
  - Added device badges to each credential row: `📱 Passkey` for `internal` / `hybrid` transports, vs `🔑 FIDO2 Security Key` for `usb` / `nfc` / `ble` transports.
  - Added clone warning badge (`⚠️ Suspected Clone`) when `suspect_clone_at` is non-null.
  - Added an interactive per-row `[Test Key]` button executing `fetchWebauthnAuthenticationOptions` (`POST /api/v1/auth/webauthn/authenticate/options`) -> `navigator.credentials.get()` -> `verifyWebauthnAuthentication` (`POST /api/v1/auth/webauthn/authenticate/verify`). Displays a green `👍 Key verified` banner and refreshes `last_used_at`.

### 3. Complete `AAL2_REQUIRED` & `AAL2_STALE` Step-Up Interception + Mobile 390px Polish
- Root cause: Profile settings previously only intercepted `AAL2_REQUIRED`, failing when the server challenged with `AAL2_STALE`. Additionally, tables on small mobile viewports (390px) suffered from horizontal overflow bleeding.
- Implementation:
  - Updated `handleInterceptAal2` in `PersonalSettingsPage.tsx` to intercept both `AAL2_REQUIRED` and `AAL2_STALE` across passkey enrollment, passkey deletion, password changes, and TOTP management. Automatically resumes and retries the intercepted action once 2FA step-up completes.
  - Wrapped passkey credentials table in `.kb-table-scroll-container` (`overflow-x: auto; max-width: 100%; box-sizing: border-box; -webkit-overflow-scrolling: touch;`).
  - Added responsive CSS containment to `.kb-personal-settings-container` (`width: 100%; max-width: 100%; box-sizing: border-box; overflow-x: hidden;`) and responsive modal sizing (`@media (max-width: 480px)` with 100% width and clean padding).

---

## Test Coverage & Quality Gates

### Unit Test Coverage (Vitest v8)
- Test Files: 4 passed (4 suites, 93 total unit tests)
  - `src/features/auth/webauthn.test.ts`: 6 tests passed (100% Stmts, 97.56% Branch, 100% Funcs, 100% Lines)
  - `src/features/settings/personalSettingsApi.test.ts`: 21 tests passed (100% Stmts, 100% Branch, 100% Funcs, 100% Lines)
  - `src/features/settings/__tests__/PasskeyEnrollModal.test.tsx`: 14 tests passed (96.77% Stmts, 97.61% Branch, 100% Funcs, 96.72% Lines)
  - `src/features/settings/__tests__/PersonalSettingsPage.test.tsx`: 52 tests passed (99.29% Stmts, 96.31% Branch, 98.78% Funcs, 100% Lines)
- Combined Coverage across all touched files:
  - Statements: 99.00% (target >= 95%)
  - Branches: 96.73% (target >= 95%)
  - Functions: 99.17% (target >= 95%)
  - Lines: 99.48% (target >= 95%)

### Static Analysis & Linters
- Python Ruff (`uv run ruff check .`): All checks passed! (0 errors)
- Python MyPy (`uv run mypy`): Success: no issues found in 1091 source files (0 errors)
- Python Imports (`uv run lint-imports`): Contracts: 2 kept, 0 broken.
- TypeScript (`npm --prefix kanban/web run typecheck`): 0 errors
- ESLint (`npm --prefix kanban/web run lint`): 0 errors, 0 warnings
- Web Production Build (`npm --prefix kanban/web run build`): Clean build in 1.13s
- CSS Tokens Audit (`cssTokensAudit.test.ts`): 4 tests passed, 100% canonical tokens
- Punctuation & Style (`python3 -m scripts.check_no_dashes --all`): 0 em-dash / en-dash errors

---

## Artifacts in `docs/qa/KAN-25/`
- `changed-files-manifest.txt`
- `git-diff.patch` (clean diff against 887e7e0 across all 10 touched code and test files, 0 docs/qa/* files inside)
- `unit-test-results.txt` (verbatim Vitest coverage output)
- `build-or-typecheck.txt` (verbatim output of ruff, mypy, lint-imports, typecheck, lint, build, check_no_dashes)
- `message-to-reality-checker.md`
- `api-specialist-review.md`
- `ui-specialist-review.md`

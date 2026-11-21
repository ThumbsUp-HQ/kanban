# Verification Summary: KAN-59

## Ticket Metadata
- **Ticket ID:** KAN-59
- **Title:** [KB-AUTH-PASSKEY-01] Switch Passkey (WebAuthn) to Default 2FA Across Backend, Login AAL2, & Setup Claim
- **Branch:** `feat/KAN-59-passkey-default`
- **Base Commit:** `3663ef46b4819201280351633030c8a9acc5b74d`
- **Scope Classification:** Full-Stack (Backend MFA policy, WebAuthn endpoints, Local login step-up discovery, React SecondFactorStep, SetupClaimPage, LoginPage, and PersonalSettingsPage)

---

## 1. Architectural & Functional Changes

### Backend Passkey-First Method Ordering & Discovery
1. **Methods Ordering Invariant:**
   - Updated `kanban/auth/mfa/policy.py` (`_get_enrolled_methods` and `require_admin_aal2`), `kanban/api/v1/auth_local.py`, `kanban/api/v1/auth_identities.py`, and `kanban/api/v1/auth_webauthn.py`:
     - Available enrolled 2FA methods are strictly ordered as `["webauthn", "totp", "recovery"]`, placing `"webauthn"` first whenever registered.
2. **Preferred Method Indication:**
   - Extended RFC 7807 problem details in `kanban/api/problems.py` with `preferred_method: "webauthn" | "totp" | None`.
   - Wired `preferred_method` into:
     - `POST /api/v1/auth/local/login` (inspects `kb_auth.mfa_status` for the principal).
     - `GET /api/v1/auth/mfa/status` (indicates `"webauthn"` when passkeys are enrolled, else `"totp"`).
     - `403 AAL2_REQUIRED` and `403 AAL2_STALE` step-up exception details across local auth, identity linking, and webauthn registration guards.
3. **First-Enrollment Recovery Codes Generation Parity:**
   - In `kanban/api/v1/auth_webauthn.py` (`register_verify`):
     - When `is_first_enrollment` is `True` and the principal has `unused_recovery_codes == 0`, automatically invokes `RecoveryCodeService.regenerate_codes(conn, principal_id)` within the same transaction.
     - Returns `"recovery_codes": codes` in the response payload, matching parity with `confirm_totp` so users are immediately provisioned with 10 Crockford Base32 emergency recovery codes upon enrolling their initial passkey.

### Frontend Passkey-First User Experience
1. **SecondFactorStep Component:**
   - In `kanban/web/src/features/auth/SecondFactorStep.tsx`:
     - Normalizes `activeMethods` to place `'webauthn'` before `'totp'` and `'recovery'`.
     - Defaults `selectedMethod` to `'webauthn'` whenever `'webauthn'` is enrolled and `supportsWebAuthn` is `true`.
     - Only falls back to `'totp'` when WebAuthn is unsupported by the browser or un-enrolled.
     - Renders the Passkey tab first (leftmost) and Authenticator code second.
     - Provides a 1-click fallback action button: `"Use 6-digit authenticator code instead"`, allowing instant switching if a user cancels or dismisses the browser passkey prompt.
2. **SetupClaimPage Component:**
   - In `kanban/web/src/features/auth/SetupClaimPage.tsx`:
     - Initializes `enrollMethod` to `'webauthn'` (`Passkey (Recommended)`) whenever `supportsWebAuthn && !isPlainHttp`.
     - Removed the restrictive `isUserVerifyingPlatformAuthenticatorAvailable() === false` check, ensuring cross-platform hardware security keys (USB/NFC YubiKeys) and phone passkeys remain on Passkey by default.
     - Removed redundant duplicate copy button from the TOTP fallback panel.
3. **LoginPage & authApi:**
   - In `kanban/web/src/features/auth/LoginPage.tsx` and `kanban/web/src/features/auth/authApi.ts`:
     - Fallback methods order changed to `['webauthn', 'totp', 'recovery']`.
     - `verifyWebauthnRegistration` extracts and retains returned recovery codes on first enrollment.
4. **PersonalSettingsPage Component:**
   - In `kanban/web/src/features/settings/PersonalSettingsPage.tsx`:
     - Added a `Passkeys (Primary 2FA)` status card (`{passkeys.length} Enrolled` / `Default 2FA`) as the first card in the MFA status grid.
     - Updated section descriptive copy to highlight Passkeys as the primary, default 2FA factor.

---

## 2. Quality Gates & Verification Evidence

All 7 required quality gates passed cleanly with zero warnings and zero errors:

| Quality Gate | Tool / Command | Result | Evidence File |
| :--- | :--- | :--- | :--- |
| Zero Em/En-Dashes | `python3 -m scripts.check_no_dashes --all` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| Python Linter | `ruff check .` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| Python Formatter | `ruff format --check .` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| Python Typecheck | `mypy kanban/api kanban/auth` | PASS (0 errors in 144 files) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| TypeScript Check | `tsc -b --noEmit` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| Frontend Linter | `eslint . --max-warnings 0` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |
| Production Build | `vite build` | PASS (0 errors) | `docs/qa/KAN-59/build-or-typecheck.txt` |

### Unit Test Execution & Coverage Summary
- **Backend Auth Unit Tests:** 77 passed in 25.41s (`kanban/tests/auth/` and `kanban/tests/api/test_user_personal_settings.py`).
- **Frontend Auth Unit Tests:** 218 passed across 12 test suites in 8.38s.
- **Frontend Code Coverage (v8):**
  - **Statements:** 98.68% (Threshold >=95%) -> PASS
  - **Branches:** 95.69% (Threshold >=95%) -> PASS
  - **Functions:** 98.23% (Threshold >=95%) -> PASS
  - **Lines:** 99.72% (Threshold >=95%) -> PASS

---

## 3. Cryptographic Manifest
Verifiable via `sha256sum -c docs/qa/KAN-59/changed-files-manifest.txt`:
All 28 modified implementation, test, and QA artifact files verified OK.

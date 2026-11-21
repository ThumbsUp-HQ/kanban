# Clean-Room API Specialist Review: KAN-59

- **Ticket:** KAN-59 (`[KB-AUTH-PASSKEY-01]`)
- **Title:** Switch Passkey (WebAuthn) to Default 2FA Across Backend, Login AAL2, & Setup Claim
- **Reviewer:** `api-spec-2` (Clean-Room Backend / API / Security / Authentication Specialist)
- **Date:** 2026-11-21
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-59`
- **Branch:** `main` (commit `9d5577ad9b50`)
- **Container Environment:** `http://localhost:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary & Authentication Audit

A clean-room API, Security, Authentication, and Schema audit was conducted for ticket **KAN-59** integrated on `main` at commit `9d5577ad9b50`. The review validates empirical verification from zero-mock Live Full-Stack QA against container `kanban-liveqa-1` (`http://localhost:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-59/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-59/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

KAN-59 elevates WebAuthn / Passkeys to the primary, default multi-factor authentication mechanism throughout the platform while strictly maintaining fallback TOTP and emergency recovery code paths.

Key architectural and security invariants certified:
1. **Passkey-First Method Ordering & Preferred Method Discovery (`policy.py`, `auth_local.py`, `auth_identities.py`, `auth_mfa.py`)**:
   - `_get_enrolled_methods` and `require_admin_aal2` order enrolled MFA methods as `["webauthn", "totp", "recovery"]`, placing WebAuthn/FIDO2 credentials first whenever present.
   - `local_login` in `kanban/api/v1/auth_local.py` queries `kb_auth.mfa_status` for the authenticating principal and returns dynamic `methods` with `preferred_method = "webauthn" if has_webauthn else "totp"`.
   - `ProblemException` for `403 AAL2_REQUIRED` and `AAL2_STALE` includes `preferred_method` in Problem Details RFC 7807/9457 responses.
   - `get_mfa_status` in `kanban/api/v1/auth_mfa.py` returns `"preferred_method": "webauthn" if passkeys_count > 0 else "totp"`.
2. **First-Enrollment Recovery Code Generation Parity (`auth_webauthn.py`)**:
   - In `kanban/api/v1/auth_webauthn.py` (`register_verify`), when `is_first_enrollment` is True and `unused_recovery_codes == 0`, calls `RecoveryCodeService.regenerate_codes(session, principal.principal_id)` within the enrollment transaction.
   - Returns `"recovery_codes": codes` in the elevated session response payload, ensuring users who choose Passkey as their first MFA factor during setup-claim or personal settings receive 10 Crockford Base32 emergency recovery codes matching `confirm_totp` behavior.
3. **Frontend Default Selection & Seamless Fallback**:
   - `SecondFactorStep.tsx` normalizes `activeMethods` with `"webauthn"` first and defaults `selectedMethod` to `"webauthn"` when supported and enrolled. Renders dedicated 1-click fallback `"Use 6-digit authenticator code instead"` (`data-testid="use-totp-fallback-btn"`).
   - `SetupClaimPage.tsx` defaults `enrollMethod` to `'webauthn'` unless plain HTTP or unsupported; eliminated the platform-authenticator false-negative constraint so external hardware keys (YubiKeys) are fully supported as first factor; removed duplicate copy button in TOTP.
   - `PersonalSettingsPage.tsx` displays "Passkeys (Primary 2FA)" card first in the 2FA grid.

---

## 2. Live Container Verification (`kanban-liveqa-1`, `:18961`, commit `9d5577ad9b50`)

- **Step 1 (/setup Passkey-First Default & Virtual WebAuthn Registration)**:
  * `/setup` Step 2 selects `Passkey (Recommended)` by default (`aria-selected="true"`).
  * CDP Virtual Authenticator registration returns 10 one-time `recovery_codes` in HTTP 200 response payload.
  * Verified 10 code items rendered on Step 3.
- **Step 2 (Personal Settings - Dual Enrollment)**:
  * "Passkeys (Primary 2FA)" is the first card in the 2FA grid ("1 Enrolled").
  * Both Passkey and TOTP enrolled and active simultaneously.
- **Step 3 (Fresh Login & SecondFactorStep)**:
  * Local Admin login returns `status: "mfa_required"`, `methods: ["webauthn", "totp", "recovery"]`, `preferred_method: "webauthn"`.
  * `SecondFactorStep` opens with Passkey tab active by default (`[data-testid="webauthn-verify-btn"]`).
  * 1-click fallback `[data-testid="use-totp-fallback-btn"]` switches to TOTP input.
- **Screenshots Captured (`docs/qa/KAN-59/screenshots/`)**:
  * `live-setup-step2-passkey-default-desktop-light.png`
  * `live-setup-step2-passkey-default-mobile.png`
  * `live-personal-settings-2fa-passkey-primary.png`
  * `live-login-2fa-passkey-default-desktop-light.png`
  * `live-login-2fa-passkey-default-desktop-dark.png`
  * `live-login-2fa-passkey-default-tablet.png`
  * `live-login-2fa-passkey-default-mobile.png`

---

## 3. Test Suite & Coverage Verification

- Pytest Results: 77/77 backend tests passed in 42.11s.
- Vitest Results: 218/218 frontend tests passed across 12 suites.
- Coverage:
  * Frontend: 98.68% Statements, 95.69% Branch, 98.23% Functions, 99.72% Lines (all >= 95%).
- Static Analysis:
  * Python: clean (`ruff check`, `mypy`).
  * Web: clean (`tsc -b --noEmit`, `eslint . --max-warnings 0`).
  * Typography: 0 unicode em/en-dashes.

---

## 4. Verdict & Signoff

STATUS: APPROVED

All API contracts, authentication policy ordering, recovery code generation parity, and live container executions for KAN-59 are certified on main at commit `9d5577ad9b50`.

# KANBA-207: Fix Setup Wizard Fields, Stale Session/CSRF Wedges, and Personal Settings TOTP Enrollment 404 & Identity Controls

## Overview
This ticket addresses critical setup wizard and identity management defects identified in security audit KB-AUDIT-01.

## Key Changes
1. **Setup Wizard Completeness & Resilience (/setup):**
   - Added Step 1 inputs: Workspace Name, auto-slugified Workspace Slug, Initial Project Name, and Initial Project Key (`^[A-Z][A-Z0-9]{1,9}$`).
   - Removed stray floating top-left text and immediately stripped URL setup token via `history.replaceState`.
   - Prevented MFA bypass on Step 2: reloading `/setup` or visiting `/login` preserves `mfa_pending` status without bypassing required MFA enrollment.
   - Auto-detects platform authenticator availability via `window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()` and falls back gracefully to TOTP.
   - Added plain-HTTP HTTPS notices for WebAuthn, 1-click `Copy Secret` and `Copy setup key` buttons with clipboard fallbacks, and replaced raw `AAL2` jargon with plain English.
2. **Strict MFA_PENDING State Isolation:**
   - Rejected all protected API routes with `401 MFA_REQUIRED` when `principal.mfa_pending` is true (`kanban/api/deps.py` and `resolver.py`).
   - Prevented redirection from `/login` to tokenless `/setup` when `mfa_pending: true`.
3. **Personal Settings 404 & Identity Controls (/settings/profile):**
   - Fixed TOTP confirmation endpoint mapping to `/api/v1/auth/mfa/totp/confirm` and registered `/api/v1/auth/mfa/totp/verify` alias returning 200 OK.
   - Disabled `Regenerate Recovery Codes` button when 2FA is not active with an informative hint: `"Enable TOTP or Passkey 2FA first"`.
   - Rendered Connected Accounts & External Identities table with Unlink action gated by fresh AAL2 step-up challenge.

## Verification
- Unit test suites passed (24 pytest, 57 vitest).
- Playwright screenshot tests generated desktop, tablet, and mobile artifacts in `docs/qa/KANBA-207/screenshots/`.

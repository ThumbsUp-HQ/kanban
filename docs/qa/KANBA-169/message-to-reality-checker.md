# KANBA-169 (`KB-QA-01`) Verification Proof Packet

## 1. Summary of Changes (Slice 1: First-Boot Setup, CSRF Bootstrap, MFA Enrollment, Session Lifecycle, and `/api/v1/auth/me`)
- **Frontend CSRF Bootstrap & Cookie Mirroring (`kanban/web/src/api/client.ts` & `client.test.ts`):**
  - Added `setCsrfToken(token)` and automatic `bootstrapCsrfToken()` via `GET /api/v1/auth/session` (`credentials: 'same-origin'`) when `UNSAFE_METHODS` (`POST`, `PUT`, `PATCH`, `DELETE`) are called and no CSRF cookie/cached token is present.
  - Automatically updates the cached CSRF token and `kb_csrf` cookie whenever an API response returns `{ csrf_token }` (`POST /api/v1/setup/claim`, `POST /api/v1/auth/local/login`, `POST /api/v1/auth/mfa/totp/confirm`, `POST /api/v1/auth/mfa/verify`, `GET /api/v1/auth/session`) and clears it on `POST /api/v1/auth/logout`.
- **Backend Plain-HTTP Cookie & CSRF Compatibility (`kanban/auth/sessions/cookies.py`, `kanban/auth/sessions/csrf.py`):**
  - Preserved `__Host-kb_session` and `__Host-kb_csrf` `Secure` cookie builders while adding plain-HTTP fallback helpers (`kb_session` and `kb_csrf`) for standalone HTTP deployments (`http://localhost`, `http://127.0.0.1`, LAN HTTP origins).
  - Updated `extract_session_cookie` to fall back to a signed 80..128-char `kb_session` token when `__Host-kb_session` is absent (while still rejecting unsigned/short non-Host cookies).
  - Updated `extract_csrf_cookie` and `CsrfMiddleware._validate_double_submit` to accept matching `kb_csrf` cookies and `PRE_SESSION_ID` tokens on `/api/v1/setup/claim` and `/api/v1/auth/local/login`.
- **Setup Wizard Step 1 -> Step 2 -> Step 3 & MFA Endpoints (`kanban/api/v1/auth_setup.py`, `kanban/api/v1/auth_mfa.py`, `kanban/web/src/features/auth/authApi.ts`, `SetupClaimPage.tsx`):**
  - Added optional `#setup-email` input field to `SetupClaimPage.tsx` Step 1 and forwarded `email` in `submitSetupClaim` when provided.
  - Returned `csrf_token` in `POST /api/v1/setup/claim` response JSON so Step 2 requests use the new `mfa_pending` session's CSRF token.
  - Updated `POST /api/v1/auth/mfa/totp/enroll` to return both `secret` and `secret_base32`.
  - Updated `POST /api/v1/auth/mfa/totp/confirm` to accept optional `enrollment_id`; when provided during setup enrollment, atomically confirms the TOTP factor, elevates the session to AAL2 (`aal_level=2, mfa_pending=False`), rotates session + CSRF cookies, and generates the 10 one-time recovery codes (`status: "enrolled"`, `recovery_codes`).
  - Added `POST /api/v1/auth/mfa/recovery-codes/generate` alias on `regenerate_recovery_codes`.
- **Session Identity, Local Admin Login, & Second-Factor Aliases (`kanban/api/v1/auth_session.py`, `kanban/api/v1/auth_local.py`, `kanban/web/src/features/settings/settingsApi.ts`):**
  - Added `GET /api/v1/auth/me` returning `{ id, principal_id, workspace_id, handle, username, display_name, email, is_server_admin, aal_level, mfa_pending }` so `AuthStudioPage` (`/admin/auth`) renders for Server Admins.
  - Included `status`, `challenge_id`, and `methods` in `POST /api/v1/auth/local/login` response JSON and added `/api/v1/auth/totp/verify` and `/api/v1/auth/recovery/verify` compatibility routes in `auth_session.py`.
  - Normalized `McpApiKeyItem` fields in `kanban/web/src/features/settings/settingsApi.ts`.

## 2. Artifacts in `docs/qa/KANBA-169/`
- `docs/qa/KANBA-169/git-diff.patch`
- `docs/qa/KANBA-169/unit-test-results.txt` (Vitest 11 files / 135 tests passed + Pytest 228 auth tests passed)
- `docs/qa/KANBA-169/build-check.txt` (`ruff check`, `mypy`, `pnpm typecheck`, `eslint`, `vite build`, and `check_no_dashes.py` all exit 0)
- `docs/qa/KANBA-169/screenshots/`:
  - `desktop-setup-step1-claim.png` (`1440x900`)
  - `desktop-setup-step2-totp.png` (`1440x900`)
  - `desktop-setup-step3-recovery-codes.png` (`1440x900`)
  - `desktop-login-mfa-step.png` (`1440x900`)
  - `desktop-auth-studio.png` (`1440x900`)
  - `tablet-setup-step1-claim.png` (`768x1024`)
  - `mobile-setup-step1-claim.png` (`390x844`)

# API & Architecture Specialist Review - KANBA-169 (`KB-QA-01`)

- **Ticket:** `KANBA-169` (`KB-QA-01`: First-Boot Setup Wizard, Pre-Session CSRF Bootstrap, Standalone HTTP Cookie Compatibility, MFA Enrollment, Session Lifecycle, and `/api/v1/auth/me`)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- **Backend:**
  - `kanban/auth/sessions/cookies.py`
  - `kanban/auth/sessions/csrf.py`
  - `kanban/api/v1/auth_session.py`
  - `kanban/api/v1/auth_setup.py`
  - `kanban/api/v1/auth_local.py`
  - `kanban/api/v1/auth_mfa.py`
  - `kanban/tests/auth/test_setup_claim.py`
- **Frontend:**
  - `kanban/web/src/api/client.ts` & `kanban/web/src/api/client.test.ts`
  - `kanban/web/src/features/auth/authApi.ts`
  - `kanban/web/src/features/auth/SetupClaimPage.tsx` & `kanban/web/src/features/auth/SetupClaimPage.test.tsx`
  - `kanban/web/src/features/settings/settingsApi.ts`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Session-Bound Double-Submit CSRF & Pre-Session Bootstrap (`csrf.py`, `auth_session.py`, `client.ts`):**
   - `GET /api/v1/auth/session` mints an HMAC-SHA256 CSRF token bound to the resolved `session_id` (or `PRE_SESSION_ID = 00000000-0000-0000-0000-000000000000` when unauthenticated) using HKDF-derived subkey `"session/csrf"`.
   - `apiFetch` in `kanban/web/src/api/client.ts` automatically calls `bootstrapCsrfToken()` (`GET /api/v1/auth/session`, `credentials: 'same-origin'`) before any `POST`/`PUT`/`PATCH`/`DELETE` request when no CSRF cookie/token is present, caches the returned `csrf_token`, mirrors it to `kb_csrf` (`SameSite=Strict`, `Path=/`), and rotates the cached token whenever a response payload includes a rotated `csrf_token` (or clears it on `/api/v1/auth/logout`).
   - `CsrfMiddleware._validate_double_submit` enforces constant-time comparison (`hmac.compare_digest(header_token, cookie_token)`) AND verifies the cryptographic HMAC signature `validate_csrf_token(header_token, session_id, hmac_key)`. On `/api/v1/setup/claim` and `/api/v1/auth/local/login`, it also permits a valid `PRE_SESSION_ID`-signed token when re-authenticating over an existing cookie.
   - `Sec-Fetch-Site` (`same-origin` / `none`) and `Origin` header validation remain strictly enforced before token checks.

2. **Hardened Cookie Extraction & Standalone HTTP Fallback (`cookies.py`, `csrf.py`, `auth_*.py`):**
   - `build_set_cookie_header` (`__Host-kb_session`; `HttpOnly; Secure; SameSite=Lax; Path=/`) and `build_set_csrf_cookie_header` (`__Host-kb_csrf`; `Secure; SameSite=Strict; Path=/`) preserve their exact HTTPS `__Host-` contracts.
   - When serving over plain `http://` in standalone mode (`request.url.scheme == "http"`), `/api/v1/auth/session`, `/api/v1/setup/claim`, `/api/v1/auth/local/login`, `/api/v1/auth/mfa/totp/confirm`, `/api/v1/auth/mfa/verify`, and `/api/v1/auth/logout` additionally emit `kb_session` (`HttpOnly; SameSite=Lax; Path=/`) and `kb_csrf` (`SameSite=Strict; Path=/`) headers so non-TLS standalone deployments function in browsers that reject `__Host-` over plain HTTP.
   - `extract_session_cookie` continues to reject duplicate `__Host-kb_session` cookies (ambiguity defense) and rejects short/unsigned `kb_session` values (`"." in candidate and 80 <= len(candidate) <= 128`), ensuring every accepted fallback cookie still passes full 32-byte token + 32-byte HMAC-SHA256 verification in `parse_session_cookie`.

3. **3-Step First-Boot Setup & Immediate AAL2 Elevation (`auth_setup.py`, `auth_mfa.py`, `SetupClaimPage.tsx`):**
   - `SetupClaimRequest` adds optional `email: str | None = Field(default=None, max_length=320)` (defaulting to `{username}@local.kanban`) while enforcing `extra="forbid"`, username regex `^[a-z0-9][a-z0-9._-]{2,62}$`, and password length 14..1024 UTF-8 bytes.
   - `SetupClaimPage.tsx` immediately strips `?token=...` from the browser URL via `window.history.replaceState(null, '', '/setup')`, renders `#setup-email`, zeroes `tokenRef.current` and password states after submission, and transitions through Step 2 (`POST /api/v1/auth/mfa/totp/enroll` + `POST /api/v1/auth/mfa/totp/confirm` with `enrollment_id` or WebAuthn registration) to Step 3 (10 one-time recovery codes).
   - When `confirm_totp` receives `enrollment_id`, it atomically elevates the session to `aal_level = 2` (`session_service.elevate_aal`), rotates the session & CSRF cookies, and generates the 10 recovery codes in a single transaction.

4. **Principal Profile & Role Summary Endpoint (`GET /api/v1/auth/me` in `auth_session.py`):**
   - Executes inside an RLS-scoped session (`RLSContext` bound to the caller's `principal_id`, `workspace_id`, `token_scopes`, and `aal_level`), returning `id`, `principal_id`, `workspace_id`, `handle`, `username`, `display_name`, `email`, `is_server_admin` (via `app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])`), `aal_level`, and `mfa_pending`.

---

## 3. Verification Proof Summary

- **Frontend Unit Tests:** `11 passed` test files (`135 passed` tests) in `docs/qa/KANBA-169/unit-test-results.txt`.
- **Backend Auth & CSRF Suite:** `228 passed` in `kanban/tests/auth/` in `docs/qa/KANBA-169/unit-test-results.txt`.
- **Static Analysis & Build:** `ruff`, `mypy`, `tsc -b`, `eslint`, `vite build`, and `check_no_dashes.py` all exit `0` in `docs/qa/KANBA-169/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.

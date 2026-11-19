# KAN-28 Forensic Verification & QA Gate Packet

## Ticket Summary
- Ticket ID: KAN-28
- Branch: feat/KAN-28
- Worktree: /home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan28-b42849d9
- Summary: [KB-P3-AUDIT-22] Harden /oauth/authorize/decision CSRF & policy checks, add + Connect OAuth App & Enter Device Code flows on /settings/mcp, add Admin + Register OAuth Client API/modal on /admin/oauth, and add route aliases.

---

## 1. Problem Descriptions and Forensic Solutions

### Problem 1: Security Hardening on /oauth/authorize and /oauth/authorize/decision
- **Requirements:**
  1. Replace random `csrf_token` with short-TTL (<= 600s) HMAC-SHA256 token signed with `session_hmac_key` binding `(caller.session_id, client_id, redirect_uri, code_challenge, state, surface)`.
  2. Verify HMAC token via `hmac.compare_digest` in `POST /oauth/authorize/decision`.
  3. Verify same-origin request via `Sec-Fetch-Site` in `("same-origin", "none")` and Origin/Referer matching allowed host (`403 CSRF_INVALID` on mismatch) while keeping HTML `<form method="POST">` submission working without requiring `x-kb-csrf-token` header.
  4. Re-verify `client_record.status == "active"` (redirect with 302 `unauthorized_client` if disabled or suspended).
  5. Enforce `surface == "admin" and caller.aal_level < 2` policy check on both GET and POST (redirect with 302 `access_denied&error_description=aal2_required`).
  6. Reject empty approved scopes (redirect with 302 `invalid_scope`).
  7. Remove `'unsafe-inline'` from `render_consent_screen` CSP (`oauth/server.py`) using SHA-256 style hash `CONSENT_STYLE_SHA256`.
- **Solution:**
  - `kanban/oauth/server.py`: Added `CONSENT_STYLE_CSS` stylesheet and computed base64 `CONSENT_STYLE_SHA256`. Updated CSP header to `style-src 'self' 'sha256-{CONSENT_STYLE_SHA256}'` completely eliminating `'unsafe-inline'`. Implemented `generate_consent_csrf_token()` and `verify_consent_csrf_token()` bound to caller session ID and authorization parameters with 600s TTL.
  - `kanban/auth/sessions/csrf.py`: Implemented `verify_same_origin_request(request)` verifying `Sec-Fetch-Site` and Origin/Referer matching allowed host.
  - `kanban/api/v1/oauth.py`:
    * In `oauth_authorize`: Generated HMAC-SHA256 CSRF token with `session_hmac_key`.
    * In `oauth_authorize_decision`: Verified same-origin request (`403 CSRF_INVALID`), verified HMAC token (`403 CSRF_INVALID`), re-verified active client status (`302 unauthorized_client`), enforced AAL2 for admin surface (`302 access_denied`), and rejected empty scopes (`302 invalid_scope`).

### Problem 2: User OAuth Connect Flows on /settings/mcp
- **Requirements:**
  1. In Connected OAuth Apps card header and empty state, add `+ Connect OAuth App` button opening `ConnectOAuthAppModal.tsx`.
  2. Add `Enter Device Code` button navigating to `/oauth/device`.
  3. Modal includes surface picker (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` if admin) and scope picker.
  4. Copyable MCP OAuth Resource URL and RFC 8414 URL (`/.well-known/oauth-authorization-server`).
  5. 1-click configuration snippet tabs for Claude Code (`claude mcp add --transport http ...`), Cursor / VS Code, Antigravity (`agy mcp add kanban ...`), and Codex (`codex mcp add kanban ...`).
  6. Added OAuth discovery tab inside `McpConfigSnippetModal.tsx`.
- **Solution:**
  - Created `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx` and `.css` with full responsive layout, surface and scope pickers, copyable URLs, and 4 CLI tool configuration snippet tabs.
  - Updated `kanban/web/src/features/settings/McpAccessStudio.tsx` and `.css` adding `+ Connect OAuth App` button and `Enter Device Code` link in both the Connected OAuth Apps card header and empty state.
  - Updated `kanban/web/src/features/settings/McpConfigSnippetModal.tsx` adding the `tab-oauth` RFC 8414 discovery configuration tab.

### Problem 3: Admin OAuth Client Registration API & Modal
- **Requirements:**
  1. Implement `POST /api/v1/admin/oauth-clients` (and `/oauth/admin/oauth-clients`) with `Depends(require_admin_aal2)`.
  2. Enforce strict redirect URI validation allowing HTTPS or loopback HTTP (`127.0.0.1`, `localhost`, `::1`).
  3. Validate `token_endpoint_auth_method` in `("none", "private_key_jwt")` and client type `"public"`.
  4. Record audit event `OAUTH_CLIENT_REGISTERED`.
  5. Add `+ Register OAuth Client` button and modal on `/admin/oauth` with copyable `client_id`.
- **Solution:**
  - `kanban/api/v1/oauth.py`: Added `AdminOAuthClientCreateRequest` model and `admin_register_oauth_client` route with `Depends(require_admin_aal2)`, strict redirect URI validation, auth method validation, 201 response with `token_endpoint_auth_method`, and audit logging via `record_activity`.
  - `kanban/services/activity.py`: Added `OAUTH_CLIENT_REGISTERED` to `ActivityEventType`.
  - `kanban/web/src/features/oauth/oauthApi.ts`: Added `registerAdminOAuthClient` and updated `OAuthClientItem`.
  - `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx` and `.css`: Added `+ Register OAuth Client` header button and modal with Client Name, Redirect URIs, Auth Method selector, error banner, and registration success view with copyable `client_id`.

### Problem 4: Route Aliases
- **Requirements:**
  1. Add `<Navigate replace />` redirects for `/settings/mcp-keys` -> `/settings/mcp`.
  2. Add `<Navigate replace />` redirects for `/admin/oauth-clients` -> `/admin/oauth`.
  3. Ensure `/oauth/device` resolves to `<DeviceActivatePage />`.
- **Solution:**
  - `kanban/web/src/app/routes.tsx`: Added `Navigate` redirects for `settings/mcp-keys` and `admin/oauth-clients`. Added route for `oauth/device` mapping to `<DeviceActivatePage />`.

---

## 2. Test Execution & Coverage Audit

All unit and integration tests executed with v8 coverage:
- **Backend Tests (`kanban/tests/oauth/`):** 36 tests passed in 18.45s.
  * `test_device_flow.py` (6 tests)
  * `test_oauth_flow.py` (13 tests)
  * `test_oauth_unit.py` (17 tests)
- **Frontend Unit Tests:**
  * `OAuthClientGovernanceStudio.test.tsx` (17 tests)
  * `oauthApi.test.ts` (5 tests)
  * `ConnectOAuthAppModal.test.tsx` (6 tests)
  * `McpAccessStudio.test.tsx` (15 tests)
  * `McpConfigSnippetModal.test.tsx` (3 tests)
  * `routes.test.tsx` (35 tests)
- **Frontend Coverage Audit on Touched Files:**
  * `oauthApi.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines
  * `ConnectOAuthAppModal.tsx`: 100% Statements, 97.22% Branches, 100% Functions, 100% Lines
  * `OAuthClientGovernanceStudio.tsx`: 100% Statements, 100% Branches, 100% Functions, 100% Lines
  * Combined Frontend Coverage: 100% Statements, 99.06% Branches, 100% Functions, 100% Lines (All >= 95.10%).
- Full Vitest `--coverage` output table and Pytest coverage results recorded in `docs/qa/KAN-28/unit-test-results.txt`.

---

## 3. Static Analysis & Build Checks

- **Ruff Check:** Clean (0 errors, All checks passed).
- **Ruff Format Check:** Clean (1806 files formatted).
- **Mypy Typecheck:** Clean (Success: no issues found in 4 source files).
- **Lint Imports:** Clean (Contracts: 2 kept, 0 broken).
- **TypeScript Typecheck (`tsc -b --noEmit`):** Clean (0 errors).
- **ESLint (`eslint . --max-warnings 0`):** Clean (0 errors, 0 warnings).
- **Dash Rules (`python3 -m scripts.check_no_dashes --all`):** Clean (0 em-dashes, 0 en-dashes).
- Raw output recorded in `docs/qa/KAN-28/build-or-typecheck.txt`.

---

## 4. Visual Proof & Screenshots

The Playwright test suite `kanban/web/e2e/qa/kan-28-screenshots.spec.ts` ran against preview server on isolated port 4828 (hermetic environment, 0 external calls, 0 unmocked endpoints) and captured 16 screenshots saved to `docs/qa/KAN-28/screenshots/`:

1. `/settings/mcp` Connect OAuth App Modal (Surface & Scope Pickers, Copyable URLs, 4 Tool Tabs):
   - `01-connect-oauth-app-modal-light-desktop.png` (Desktop 1440x900 Light)
   - `01-connect-oauth-app-modal-dark-desktop.png` (Desktop 1440x900 Dark)
   - `01-connect-oauth-app-modal-light-mobile.png` (Mobile 390x844 Light)
   - `01-connect-oauth-app-modal-dark-mobile.png` (Mobile 390x844 Dark)

2. `/oauth/authorize` Server-Rendered Consent Screen (HMAC-SHA256 CSRF, SHA-256 Style CSP Hash, AAL2 Indicator):
   - `02-oauth-authorize-consent-light-desktop.png` (Desktop 1440x900 Light)
   - `02-oauth-authorize-consent-dark-desktop.png` (Desktop 1440x900 Dark)
   - `02-oauth-authorize-consent-light-mobile.png` (Mobile 390x844 Light)
   - `02-oauth-authorize-consent-dark-mobile.png` (Mobile 390x844 Dark)

3. `/oauth/device` Device Code Activation & Authorization Confirmation:
   - `03-oauth-device-light-desktop.png` (Desktop 1440x900 Light)
   - `03-oauth-device-dark-desktop.png` (Desktop 1440x900 Dark)
   - `03-oauth-device-light-mobile.png` (Mobile 390x844 Light)
   - `03-oauth-device-dark-mobile.png` (Mobile 390x844 Dark)

4. `/admin/oauth` Admin OAuth Client Governance Studio & Register OAuth Client Modal:
   - `04-admin-register-oauth-client-light-desktop.png` (Desktop 1440x900 Light)
   - `04-admin-register-oauth-client-dark-desktop.png` (Desktop 1440x900 Dark)
   - `04-admin-register-oauth-client-light-mobile.png` (Mobile 390x844 Light)
   - `04-admin-register-oauth-client-dark-mobile.png` (Mobile 390x844 Dark)

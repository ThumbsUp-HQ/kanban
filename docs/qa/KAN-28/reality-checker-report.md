# Reality-Checker Forensic QA Report: KAN-28

## Executive Summary
- Ticket ID: KAN-28 ([KB-P3-AUDIT-22])
- Title: Harden /oauth/authorize/decision CSRF & policy checks, add + Connect OAuth App & Enter Device Code flows on /settings/mcp, add Admin + Register OAuth Client API/modal on /admin/oauth, and add route aliases
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan28-b42849d9`
- Target Branch: `feat/KAN-28`
- Reviewer: rc-gate-2 (Clean-Room Forensic QA Gate)
- Review Date: 2026-11-19
- Overall Quality Rating: A
- Production Readiness: READY

---

## Forensic Audit Verification Matrix

### Problem 1: Authorization Endpoint Security Hardening & Cryptographic CSRF Binding
- Defect: The OAuth 2.1 authorization and consent endpoints previously used simple random tokens vulnerable to cross-session fixation, lacked same-origin header verification on standard form POSTs, failed to re-verify client active status at decision time, omitted AAL2 enforcement on admin surface consent requests, allowed empty approved scopes, and contained 'unsafe-inline' in consent screen CSP.
- Verification:
  - Inspected `kanban/oauth/server.py`: Implemented `generate_consent_csrf_token()` computing an HMAC-SHA256 signature using `session_hmac_key` over `(v1, session_id, client_id, redirect_uri, code_challenge, state, surface, exp)` with a strict 600s TTL.
  - Inspected `kanban/auth/sessions/csrf.py`: `verify_same_origin_request()` inspects `Sec-Fetch-Site` in `("same-origin", "none")` and matches Origin or Referer against allowed hosts, returning RFC 7807 403 `CSRF_INVALID` on mismatch while keeping standard HTML form submissions functional.
  - Inspected `kanban/api/v1/oauth.py`:
    * Re-verifies `client_record.status == "active"`, redirecting inactive clients with 302 `unauthorized_client`.
    * Enforces `surface == "admin" and caller.aal_level < 2` on both GET and POST, redirecting with 302 `access_denied&error_description=aal2_required`.
    * Rejects empty approved scopes with 302 `invalid_scope`.
    * Validates CSRF token with `hmac.compare_digest`.
  - Inspected CSP configuration: Computed base64 SHA-256 hash `CONSENT_STYLE_SHA256` for `CONSENT_STYLE_CSS` and configured CSP header to `style-src 'self' 'sha256-{CONSENT_STYLE_SHA256}'`, completely eliminating `'unsafe-inline'`.
  - Status: VERIFIED RESOLVED

### Problem 2: User OAuth Connect Flows on `/settings/mcp`
- Defect: Users had no guided workflow in the Web UI to connect third-party MCP clients (Claude Code, VS Code, Cursor, Antigravity, Codex) via OAuth 2.1 or device flow, nor were discovery endpoints clearly exposed.
- Verification:
  - Inspected `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`: Implemented modal with surface picker (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`), scope selectors, copyable Resource URL and RFC 8414 Authorization Server discovery URL, and 1-click configuration snippet tabs for Claude Code (`claude mcp add --transport http ...`), Cursor / VS Code, Antigravity (`agy`), and Codex (`codex`).
  - Inspected `kanban/web/src/features/settings/McpAccessStudio.tsx`: Added `+ Connect OAuth App` button and `Enter Device Code` link in both card header and empty state.
  - Inspected `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`: Added dedicated RFC 8414 discovery configuration tab.
  - Status: VERIFIED RESOLVED

### Problem 3: Administrative OAuth Client Registration API & Studio
- Defect: Registering OAuth 2.1 clients required direct database inserts; administrators had no authenticated API endpoint or UI modal to register external clients with strict redirect URI policies.
- Verification:
  - Inspected `kanban/api/v1/oauth.py`: Implemented `POST /api/v1/admin/oauth-clients` protected with `Depends(require_admin_aal2)`.
  - Enforces HTTPS or loopback HTTP (`127.0.0.1`, `localhost`, `[::1]`) for redirect URIs, forbidding cleartext public internet schemes.
  - Validates `token_endpoint_auth_method` in `("none", "private_key_jwt")`.
  - Logs `ActivityEventType.OAUTH_CLIENT_REGISTERED` audit event with client metadata.
  - Inspected `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`: Added `+ Register OAuth Client` button and modal with instant client ID copy feedback upon creation.
  - Status: VERIFIED RESOLVED

### Problem 4: Navigation and Route Aliases
- Defect: Legacy routes `/settings/mcp-keys` and `/admin/oauth-clients` caused 404 errors, and `/oauth/device` lacked clean client-side routing.
- Verification:
  - Inspected `kanban/web/src/app/routes.tsx`: Added `<Navigate replace />` redirects for `/settings/mcp-keys` -> `/settings/mcp` and `/admin/oauth-clients` -> `/admin/oauth`.
  - Added route mapping for `/oauth/device` resolving to `<DeviceActivatePage />`.
  - Status: VERIFIED RESOLVED

---

## Automated Test & Static Analysis Evidence

1. Unit & Integration Tests:
   - Python Pytest: 36 passed in 19.12s (`test_device_flow.py`, `test_oauth_flow.py`, `test_oauth_unit.py`).
   - Frontend Vitest: 28 passed in 2.39s across touched components (`OAuthClientGovernanceStudio.tsx`, `oauthApi.ts`, `ConnectOAuthAppModal.tsx`).
   - Frontend Coverage: 100% Statements, 99.06% Branches, 100% Functions, 100% Lines (exceeding mandatory >= 95.10% threshold across all touched components).
   - Raw output logged in `docs/qa/KAN-28/unit-test-results.txt`.

2. Static Analysis & Type Checking:
   - Ruff check: clean (All checks passed).
   - Ruff format check: 1807 files verified clean.
   - Mypy check: Success, no issues found in 4 source files.
   - Import Linter: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database` strictly preserved).
   - TypeScript compiler (`tsc -b --noEmit`): 0 errors.
   - ESLint: 0 warnings, 0 errors.
   - Strict ASCII character check: Zero `\u2014` em-dashes and zero `\u2013` en-dashes across all modified files.
   - Raw output logged in `docs/qa/KAN-28/build-or-typecheck.txt`.

---

## Dual Specialist Gate Audits

1. API Specialist Audit:
   - File: `docs/qa/KAN-28/api-specialist-review.md`
   - Reviewer: `api-spec-2`
   - Status: APPROVED
   - Findings: Verified HMAC-SHA256 CSRF binding, same-origin Origin/Referer checks, AAL2 admin surface policy, SHA-256 CSP style hash, and admin client registration.

2. UI/UX Specialist Audit:
   - File: `docs/qa/KAN-28/ui-specialist-review.md`
   - Reviewer: `ui-spec-2`
   - Status: APPROVED
   - Findings: Verified WCAG AA contrast compliance across Light and Dark themes, modal whitespace and ergonomics, responsive touch targets, and mobile adaptations across 16 screenshots.

---

## Visual Proof Artifacts (16 Screenshots Audited)

1. `01-connect-oauth-app-modal-light-desktop.png`: Connect OAuth App Modal (Light, Desktop 1440x900).
2. `01-connect-oauth-app-modal-dark-desktop.png`: Connect OAuth App Modal (Dark, Desktop 1440x900).
3. `01-connect-oauth-app-modal-light-mobile.png`: Connect OAuth App Modal (Light, Mobile 390x844).
4. `01-connect-oauth-app-modal-dark-mobile.png`: Connect OAuth App Modal (Dark, Mobile 390x844).
5. `02-oauth-authorize-consent-light-desktop.png`: OAuth 2.1 Consent Screen (Light, Desktop 1440x900).
6. `02-oauth-authorize-consent-dark-desktop.png`: OAuth 2.1 Consent Screen (Dark, Desktop 1440x900).
7. `02-oauth-authorize-consent-light-mobile.png`: OAuth 2.1 Consent Screen (Light, Mobile 390x844).
8. `02-oauth-authorize-consent-dark-mobile.png`: OAuth 2.1 Consent Screen (Dark, Mobile 390x844).
9. `03-oauth-device-light-desktop.png`: Device Flow Authorization Screen (Light, Desktop 1440x900).
10. `03-oauth-device-dark-desktop.png`: Device Flow Authorization Screen (Dark, Desktop 1440x900).
11. `03-oauth-device-light-mobile.png`: Device Flow Authorization Screen (Light, Mobile 390x844).
12. `03-oauth-device-dark-mobile.png`: Device Flow Authorization Screen (Dark, Mobile 390x844).
13. `04-admin-register-oauth-client-light-desktop.png`: Admin Register OAuth Client Modal (Light, Desktop 1440x900).
14. `04-admin-register-oauth-client-dark-desktop.png`: Admin Register OAuth Client Modal (Dark, Desktop 1440x900).
15. `04-admin-register-oauth-client-light-mobile.png`: Admin Register OAuth Client Modal (Light, Mobile 390x844).
16. `04-admin-register-oauth-client-dark-mobile.png`: Admin Register OAuth Client Modal (Dark, Mobile 390x844).

All 16 visual screenshots confirm WCAG AA contrast compliance, correct component layout, and responsive mobile adaptations.

---

## Clean-Room Reality-Checker Remediation (Round 2)

### Defect 1: DeviceActivatePage Project ID Contract & Authorize Fail-Closed Invariants
- Finding: `DeviceActivatePage.tsx` previously sent string project identifiers (`["KAN", "OPS"]`) in `allowed_projects` to `POST /api/v1/oauth/device/activate`, which requires `list[uuid.UUID] | None`, resulting in HTTP 422 upon approval. Additionally, `kanban/api/v1/oauth.py` fell back to null byte keys (`b"\x00" * 32`) if key material was missing, and only checked `pending_admin_approval` and `disabled` on GET `/oauth/authorize`.
- Remediation:
  - Updated `DeviceActivatePage.tsx` to fetch `/api/v1/projects`, parse `{ id: string, identifier: string, name?: string }`, display `Project: {p.identifier}`, and store/submit `p.id` (UUID strings) in `selectedProjects` / `allowed_projects`.
  - Updated `DeviceActivatePage.test.tsx` to assert valid UUID strings (`/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`) are submitted on approve.
  - In `kanban/api/v1/oauth.py`: Fail closed (`raise RuntimeError("Session HMAC key material is not configured.")`) if `key_material` and `session_service` are absent and fail to load; reject `client_record.status != "active"` consistently on `GET /oauth/authorize` (redirecting 302 `unauthorized_client&error_description=client_{status}`).
  - Added unit test coverage in `kanban/tests/oauth/test_oauth_unit.py` verifying fail-closed runtime error and rejection of all non-active client statuses (`suspended`, `revoked`, `pending_admin_approval`, `disabled`).
- Status: VERIFIED RESOLVED

### Defect 2: Mobile 390x844 Viewport Horizontal Overflow Remediation
- Finding: `OAuthClientGovernanceStudio.css` and `DeviceActivatePage.css` suffered from horizontal scrolling/overflow on mobile 390x844 viewports due to fixed padding, non-wrapping header rows, and long Target Resource URLs.
- Remediation:
  - In `OAuthClientGovernanceStudio.css`: added `min-width: 0; max-width: 100%; box-sizing: border-box;` on container and sections, `flex-wrap: wrap; gap: 12px;` on section header and subnav, compact padding (`padding: 16px 12px` under `@media (max-width: 640px)`), and `overflow-x: auto; max-width: 100%;` on table wrap, guaranteeing `document.documentElement.scrollWidth <= 390`.
  - In `DeviceActivatePage.css`: reduced mobile card padding (`padding: 20px 16px` under `@media (max-width: 480px)`), added `flex-wrap: wrap; gap: 4px 12px;` on `.kb-device-app-row`, and `overflow-wrap: anywhere; word-break: break-all; max-width: 100%;` on `.kb-device-app-prop-value` so long Target Resource URLs never overflow card boundaries or viewport. Zero inline `style={{...}}`, canonical `theme.css` tokens.
- Status: VERIFIED RESOLVED

### Defect 3: Complete Unit Suite, Static Gates, and Cumulative Diff Patch
- Verification:
  - Python Pytest: 44 passed in 23.12s (`test_device_flow.py`, `test_oauth_flow.py`, `test_oauth_unit.py`, `test_web_static.py`, `test_aal2_policy.py`).
  - Python Coverage: 98% total across touched modules (`kanban/oauth/server.py` 97%, `kanban/web_static.py` 100%).
  - Frontend Vitest: 40 passed in 2.77s (`ConnectOAuthAppModal.test.tsx`, `DeviceActivatePage.test.tsx`, `OAuthClientGovernanceStudio.test.tsx`).
  - Frontend Coverage: 99.7% Statements, 96.38% Branches, 99.02% Functions, 100% Lines (exceeding mandatory >= 95% threshold).
  - CSS Tokens Audit: 4 passed in 0.88s (`cssTokensAudit.test.ts`).
  - Static Gates: `ruff check` (clean), `ruff format` (clean), `mypy` (clean across 3 files), `lint-imports` (2 kept, 0 broken), `check_no_dashes --all` (0 em/en-dashes), `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 errors/warnings), `vite build` (clean in 1.18s).
  - Cumulative Diff: Clean patch `docs/qa/KAN-28/git-diff.patch` generated via `git diff 31aca8e HEAD -- ...` (zero `docs/qa/*` files included).
- Status: VERIFIED RESOLVED

---

## Final Gate Certification
- Overall Quality Rating: A
- Production Readiness: READY
- Recommendation: Proceed to merge into `main` branch.

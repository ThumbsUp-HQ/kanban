# API Specialist Security & Architecture Audit Review: KAN-28

## Audit Metadata
- Ticket ID: KAN-28 ([KB-P3-AUDIT-22])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan28-b42849d9`
- Target Branch: feat/KAN-28
- Base Commit: 3dd6b9d
- Head Commit: 476daa4
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the OAuth 2.1 protocol implementation, cryptographic CSRF token generation and validation, same-origin protections, consent screen Content-Security-Policy (CSP), and administrative client governance endpoints delivered for ticket KAN-28. The delivery resolves four core architectural and security requirements across user and administrative OAuth flows without introducing new dependencies or compromising security invariants.

All changes adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Authorization Endpoint Hardening & Cryptographic CSRF Binding
- Files: `kanban/api/v1/oauth.py`, `kanban/oauth/server.py`, `kanban/auth/sessions/csrf.py`
- Invariant: User authorization decisions must be cryptographically bound to the initiating user session, client ID, PKCE challenge, state, surface, and redirect URI with short expiration, preventing cross-session and cross-site authorization forgery.
- Audit Findings:
  - `generate_consent_csrf_token()` computes an HMAC-SHA256 signature using `session_hmac_key` over `(v1, session_id, client_id, redirect_uri, code_challenge, state, surface, exp)` with a strict 600s TTL.
  - In `POST /oauth/authorize/decision`, `verify_consent_csrf_token()` verifies the signature via `hmac.compare_digest` and checks token expiration.
  - `verify_same_origin_request()` inspects `Sec-Fetch-Site` in `("same-origin", "none")` and ensures `Origin` or `Referer` matches the host, rejecting mismatched requests with RFC 7807 403 `CSRF_INVALID`.
  - Re-verifies `client_record.status == "active"`, rejecting suspended or disabled clients with 302 `unauthorized_client`.
  - Enforces `surface == "admin" and caller.aal_level < 2` on both GET and POST endpoints, redirecting to redirect URI with 302 `access_denied&error_description=aal2_required`.
  - Empty approved scope lists are rejected with 302 `invalid_scope`.
  - Content Security Policy: Removed `'unsafe-inline'` from consent screen style-src, replacing it with `style-src 'self' 'sha256-{CONSENT_STYLE_SHA256}'`.

### 2. User OAuth Connect Flows on `/settings/mcp`
- Files: `kanban/web/src/features/settings/ConnectOAuthAppModal.tsx`, `kanban/web/src/features/settings/McpAccessStudio.tsx`, `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
- Audit Findings:
  - Added `+ Connect OAuth App` modal with surface picker (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` when caller is admin), scope selection, copyable Resource URL and RFC 8414 discovery URL.
  - Includes 1-click configuration snippet generators for Claude Code, Cursor / VS Code, Antigravity (`agy`), and Codex (`codex`).
  - Added `Enter Device Code` link directly navigating to `/oauth/device`.
  - Added RFC 8414 OAuth discovery tab in `McpConfigSnippetModal.tsx`.

### 3. Administrative OAuth Client Registration API & Studio
- Files: `kanban/api/v1/oauth.py`, `kanban/web/src/features/oauth/OAuthClientGovernanceStudio.tsx`, `kanban/web/src/features/oauth/oauthApi.ts`, `kanban/services/activity.py`
- Invariant: Dynamic client registration by administrators must require AAL2, enforce secure redirect URI schemes, validate authentication methods, and log an audit record.
- Audit Findings:
  - `POST /api/v1/admin/oauth-clients` declares `Depends(require_admin_aal2)`.
  - Enforces HTTPS or loopback HTTP (`127.0.0.1`, `localhost`, `[::1]`) for redirect URIs, forbidding cleartext public internet schemes.
  - Validates `token_endpoint_auth_method` in `("none", "private_key_jwt")`.
  - Emits `ActivityEventType.OAUTH_CLIENT_REGISTERED` audit record.
  - `OAuthClientGovernanceStudio.tsx` renders `+ Register OAuth Client` modal with client ID copy feedback.

### 4. Navigation & Route Aliases
- File: `kanban/web/src/app/routes.tsx`
- Audit Findings:
  - Added `<Navigate replace />` redirects for `/settings/mcp-keys` -> `/settings/mcp` and `/admin/oauth-clients` -> `/admin/oauth`.
  - Added route mapping for `/oauth/device` resolving to `<DeviceActivatePage />`.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` endpoints maintain mandatory `Depends(require_admin_aal2)`. Verified by `kanban/tests/auth/test_aal2_policy.py`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: 36 unit and integration tests passing in `kanban/tests/oauth/` (device flow, authorization flows, PKCE, CSRF).
   - Frontend: 28 vitest tests passing across touched components (`ConnectOAuthAppModal.tsx`, `OAuthClientGovernanceStudio.tsx`, `oauthApi.ts`).
   - Combined frontend coverage: 100% Statements, 99.06% Branches, 100% Functions, 100% Lines (all exceeding >= 95.10% threshold).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy` (4 source files), `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `message-to-reality-checker.md`, and 16 Playwright screenshot PNGs verified in `docs/qa/KAN-28/`.

---

## 5. Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-22)

- Target Branch: `fix/KAN-28-liveqa`
- Remediation Head Commit: `e895795`
- Remediation Scope:
  1. Modal Tab Layout and Interaction: Fixed `.kb-connect-oauth-tabs` height collapse by configuring `flex-shrink: 0`, `flex-wrap: wrap`, and `min-height: 40px` with child `height: 36px`, ensuring all 4 tabs remain visible and clickable without pointer interception on Desktop and Mobile viewports.
  2. Dynamic Resource URL Formatting: Replaced hardcoded `'KANBA'` fallback in `ConnectOAuthAppModal.tsx` with dynamic workspace project resolution via `GET /api/v1/projects`, emitting canonical workspace or project URLs without hardcoded tenant keys.
  3. Direct SPA Routing to `/oauth/device`: In `kanban/web_static.py`, implemented `is_oauth_device_spa` allowing direct browser access to `/oauth/device` via SPA fallback to `index.html` while strictly preserving 404/405 protection on backend OAuth protocol routes.
  4. Device Activation Project Scoping: Updated `DeviceActivatePage.tsx` with dynamic project loading via `GET /api/v1/projects` to populate project scope selection dynamically.
  5. Chromium CSP Compliance: In `kanban/oauth/server.py`, replaced invalid W3C CSP3 `http://[::1]:*` grammar with exact dynamic origin extraction (`f"{scheme}://{netloc}"`) appended to `form-action`, eliminating Chromium console errors.
  6. Test and Coverage Verification: 26 Pytest backend tests passing (100% coverage on `kanban.web_static`, 95% total across touched files); 23 Vitest unit tests passing with 100% lines and 96.49% branch coverage (exceeding >= 95.10%); `cssTokensAudit.test.ts` (4/4 passed); zero em/en-dashes; clean ruff, mypy, and typecheck.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for visual, UX, and accessibility verification of `docs/qa/KAN-28/screenshots/`.


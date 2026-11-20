# Forensic QA Verification Packet: KAN-28 ([KB-P3-AUDIT-22])

## 1. Executive Summary & Verification Context
- **Ticket ID:** KAN-28 ([KB-P3-AUDIT-22])
- **Repository Root:** `/home/adamoutler/kanban`
- **Status:** READY FOR CLEAN-ROOM AUDIT

This packet provides indisputable zero-mock forensic proof for all 4 scoped KAN-28 problems plus clean-room security, mobile containment, and read-after-write consistency fixes:
1. **Session+Request-Bound Consent CSRF & Policy Enforcement (`POST /oauth/authorize/decision`):**
   - `kanban/oauth/server.py` signs short-TTL (`<= 600s`) HMAC-SHA256 `csrf_token` values with `session_hmac_key` binding `(caller.session_id, client_id, redirect_uri, code_challenge, state, surface)` verified in constant time via `hmac.compare_digest`.
   - `kanban/auth/sessions/csrf.py` (`verify_same_origin_request`) enforces same-origin `Sec-Fetch-Site` and `Origin`/`Referer`, explicitly permitting `Origin: null` **strictly and only** when browser-enforced `Sec-Fetch-Site: same-origin` is present (supporting real Chromium HTML `<form method="POST">` navigations under `Referrer-Policy: no-referrer` while rejecting `cross-site`, `same-site`, `none`, or missing `Sec-Fetch-Site` with `403 CSRF_INVALID`).
   - `kanban/api/v1/oauth.py` re-verifies `client_record.status == "active"`, re-enforces `surface == "admin"` `AAL2`, rejects empty `approved_scopes`, and `render_consent_screen` uses SHA-256 style hashing (`CONSENT_STYLE_SHA256`) with zero `'unsafe-inline'` CSP directives.
2. **Self-Service `+ Connect OAuth App` & `Enter Device Code` on `/settings/mcp`:**
   - `ConnectOAuthAppModal.tsx`, `McpAccessStudio.tsx`, and `McpConfigSnippetModal.tsx` expose surface/scope pickers, live Resource + RFC 8414 URLs, 4 non-collapsed CLI client tabs (`Claude Code`, `VS Code / Cursor`, `Antigravity`, `Codex`), and RFC 8628 `/oauth/device` (`DeviceActivatePage.tsx` with dynamic UUID project scoping + `web_static.py` SPA fallback).
3. **Admin `+ Register OAuth Client` API & Modal on `/admin/oauth`:**
   - `POST /api/v1/admin/oauth-clients` enforces `Depends(require_admin_aal2)`, strict HTTPS / loopback HTTP redirect URI validation, and audit logging; `OAuthClientGovernanceStudio.tsx` & `.css` enforce `390x844` mobile layout containment (`main.scrollWidth === 390`, `0` horizontal clipping).
4. **Route Aliases & Immediate `0ms` Project Read-After-Write Commit:**
   - `routes.tsx` redirects `/settings/mcp-keys` -> `/settings/mcp` and `/admin/oauth-clients` -> `/admin/oauth`; `kanban/api/v1/projects.py` commits project mutations prior to HTTP response dispatch.

## 2. Unit Test, Coverage & Static Quality Proof
- **Unit Tests & Coverage (`docs/qa/KAN-28/unit-test-results.txt`):** Full Pytest + Vitest coverage suites passing with `>=95%` coverage across touched backend and frontend modules, plus `cssTokensAudit.test.ts` (4/4).
- **Static Checks (`docs/qa/KAN-28/build-or-typecheck.txt`):** `ruff check`, `ruff format`, `mypy` (`0` errors), `lint-imports` (`2 kept, 0 broken`), `tsc -b --noEmit` (`0` errors), `eslint . --max-warnings 0` (`0` warnings/errors), `vite build`, and `check_no_dashes` (`0` em/en-dashes).

## 3. Zero-Mock Live Full-Stack Proof (`docs/qa/KAN-28/live-fullstack-proof.txt`)
Verified against live standalone container `kanban-liveqa-3` (`thumbs-up-kanban:local-qa` on `http://localhost:18953`, **zero** `mockApi` / `page.route` stubs):
- `0ms` immediate `GET /api/v1/projects` returned `["KAN", "OPS"]` after `POST /api/v1/projects` (`201`).
- `/admin/oauth` registered `Daybreak CLI` (`201`) and verified `390x844` mobile containment (`docScrollWidth=390, mainScrollWidth=390, containerRight=374`).
- Real Chromium **Approve** click on `/oauth/authorize` -> `POST /oauth/authorize/decision` `302` to real local loopback HTTP listener `http://127.0.0.1:49152/callback?code=...&state=...` -> `POST /oauth/token` PKCE `S256` -> `200` `access_token`; all 3 negative CSRF probes (`Origin: https://evil.example`, `Origin: null` + `Sec-Fetch-Site: cross-site`, forged `csrf_token`) rejected `403 CSRF_INVALID`.
- RFC 8628 Device Flow (`POST /oauth/device/authorize` -> `/oauth/device` UI Approve `200` with `KAN` + `OPS` -> `POST /oauth/token` `200` `access_token`).
- `/settings/mcp-keys` -> `/settings/mcp` + `ConnectOAuthAppModal` 4 tabs (`offsetHeight=36px`); `0` `console.error`, `0` `pageerror`, `0` `5xx`.

## 4. Live Zero-Mock Screenshots (`docs/qa/KAN-28/screenshots/`)
- `live-admin-oauth-desktop-light.png`, `live-admin-oauth-desktop-dark.png`
- `live-admin-oauth-mobile-light.png`, `live-admin-oauth-mobile-dark.png`
- `live-admin-oauth-register-modal-desktop-light.png`, `live-admin-oauth-register-modal-desktop-dark.png`
- `live-admin-oauth-registered-success-desktop-light.png`
- `live-oauth-authorize-desktop-light.png`, `live-oauth-authorize-desktop-dark.png`
- `live-oauth-authorize-mobile-light.png`, `live-oauth-authorize-mobile-dark.png`
- `live-oauth-device-desktop-light.png`, `live-oauth-device-desktop-dark.png`
- `live-oauth-device-mobile-light.png`, `live-oauth-device-mobile-dark.png`
- `live-oauth-device-spa-desktop-light.png`, `live-activate-device-desktop-light.png`
- `live-connect-oauth-desktop-light.png`, `live-connect-oauth-desktop-dark.png`
- `live-connect-oauth-mobile-light.png`, `live-connect-oauth-mobile-dark.png`

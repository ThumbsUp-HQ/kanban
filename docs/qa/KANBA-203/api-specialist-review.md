# API Specialist Review: KANBA-203 ([KB-QA-ADMIN])

**Ticket Title:** [KB-QA-ADMIN] Admin Browser QA Setup: Multi-Situation Workspace, RBAC, Workflow, Sticky/Doc & MCP Seeding  
**Reviewer:** Backend Architect & API Specialist  
**Date:** 2026-11-18  
**Status:** APPROVED (Grade A)  

---

## 1. Scope & Verification Target

Review of API interactions, authentication endpoints, and security contracts exercised in `kanban/web/e2e/qa/admin-browser-setup.spec.ts` and audited against `https://k.hackedyour.info`:

1. **Setup Claim Token Endpoint (`POST /api/v1/setup/claim`):**
   - Validates that short or invalid setup claim tokens are rejected fail-closed with 400 Bad Request or 404 Not Found.
   - Enforces URL token parameter purging via `history.replaceState` preventing credential leakage via `Referer` headers, browser history, or server access logs.
2. **Public Auth Cards Projection (`GET /api/v1/auth/cards`):**
   - Public auth card projection renders provider cards (`google-oauth`, `local-admin`) with display ordering and visual presets.
   - Verifies sensitive configuration fields (`client_secret`, `bind_dn`, `bind_password`) are strictly pruned from public schemas.
3. **Local Admin Authentication & CSRF (`POST /api/v1/auth/local/login`):**
   - Mandates strict `X-CSRF-Token` header verification matching session token.
   - Transitions valid credential flow to AAL2 (`SecondFactorStep`) for TOTP/WebAuthn verification.
4. **Admin Auth Studio & Break-Glass Lockout Prevention (`POST /api/v1/admin/auth-cards/{card_ref}/disable`):**
   - Disabling the last administrative card fails closed with `409 Conflict` (`LOCKOUT_PREVENTED`).
   - Surfaces deterministic operator recovery command: `kanban-ctl auth emergency-unlock --enable-local-admin`.
   - In edit drawers, write-only secrets (`#card-client-secret`) remain empty unless an explicit replace action is initiated.
5. **Admin & Personal MCP Key Minting Protocol (`POST /api/v1/auth/mcp-keys`):**
   - Returns structured key object (`id`, `label`, `surface`, `key_prefix`, `raw_key`).
   - Plaintext secret is revealed exclusively once in `McpConfigSnippetModal` and wiped from DOM upon modal dismissal.

---

## 2. API Contract Conformance Audit

| Contract / Endpoint | Expected Method | Payload / Response Invariant | Audit Result |
| :--- | :--- | :--- | :--- |
| `/api/v1/setup/claim` | `POST` | Rejects malformed tokens (`kb_setup_short`); returns error banner | PASS |
| `/api/v1/auth/cards` | `GET` | Preserves priority ordering; strictly zero `client_secret` exposure | PASS |
| `/api/v1/auth/local/login` | `POST` | Enforces `X-CSRF-Token`; transitions to second factor step | PASS |
| `/api/v1/admin/auth-cards/{id}/disable` | `POST` | Fail-closed `409 Conflict: LOCKOUT_PREVENTED` on last admin card | PASS |
| `/api/v1/admin/principals` | `POST` | User creation with username, email, full_name, and role bindings | PASS |
| `/api/v1/auth/mcp-keys` | `POST` | Mint key with surface (`admin`), returns `raw_key`, masks in table | PASS |

---

## 3. Security & Access Control Assessment

- **AAL2 & CSRF Enforcement:** All local administrative logins enforce anti-CSRF token checks and challenge second-factor verification prior to privilege grant.
- **Fail-Closed Lockout Prevention:** The `409 LOCKOUT_PREVENTED` handler protects administrators against self-lockout by verifying at least one enabled authentication card remains capable of administrative login.
- **Secret Ephemerality in MCP Modal:** The raw generated key exists in client component state only while `McpConfigSnippetModal` is open. When closed or dismissed via Escape or backdrop click, the secret is purged immediately from memory and DOM.

---

## 4. Verdict

**APPROVED.** The API client interactions conform strictly to the security architecture, REST contracts, and zero-leakage standards of `👍kanban`.

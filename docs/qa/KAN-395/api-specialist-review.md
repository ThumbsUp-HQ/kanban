# API Specialist Review: KAN-395

**Ticket:** `KAN-395` (`Support 1,200+ character OAuth state tokens for Google Gemini MCP OAuth 2.1 integration`)
**Reviewer:** `@api-spec` (Backend Architect & API Security Specialist)
**Branch:** `main` (merged from `feat/KAN-395-gemini-oauth-state`)
**Commit:** `93a1a7a94c66f7f2aece1d46acd3f4d5cd66e621`
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket hardens the OAuth 2.1 authorization server and Model Context Protocol (MCP) authentication endpoints to support enterprise-grade Google Gemini (`gemini.google.com`) Connected Apps and real-world MCP OAuth 2.1 clients:
1. **OAuth State Expansion & Validation:** Raised `MAX_STATE_LEN` from 512 to 4096 (4 KiB) in `kanban/api/v1/oauth.py` with strict boundary validation (4096 accepted, 4097 rejected with 400 `invalid_request`).
2. **RFC 6749 Redirect URI Parameter Integrity:** Implemented `_redirect_with_params` using `sep = "&" if "?" in redirect_uri else "?"` across all eight OAuth authorization 302 redirect points in `kanban/api/v1/oauth.py`, preventing corrupt `?a=1?code=...` URLs when clients provide pre-existing callback query parameters.
3. **Deep Login Redirect & Query Parameter Safety:**
   - Raised query parameter length limits in `kanban/api/v1/auth_cards_public.py` (`next` and `return_to`) and `kanban/api/v1/auth_oidc.py` (`return_to`) from 2048 to 8192 characters.
   - Updated `RETURN_TO_REGEX` in `kanban/auth/oidc/flow.py` to allow `{0,8192}` characters and RFC 3986 sub-delim characters (`@,;!$'()*`).
   - Updated `SAFE_NEXT_REGEX` in `kanban/web/src/features/auth/authApi.ts` to accommodate valid query sub-delimiters and characters without dropping long OAuth authorization redirects back to `/`.
4. **RFC 9728 Protected Resource Discovery Hardening:**
   - Fixed path parsing in `mcp/metadata.py` (`protected_resource_metadata_endpoint`) so scoped paths like `/mcp/w/{ws}` and `/mcp/w/{ws}/p/{proj}` correctly default to surface `agent` rather than setting surface to `"w"` and returning 404.
   - Tolerated trailing slashes in `eff_resource` matching during `POST /oauth/token` exchange (`code_record.resource.rstrip('/') == eff_resource.rstrip('/')`).
5. **Chained Reverse-Proxy & TLS Termination Support:**
   - Hardened `resolve_public_base_url` across `kanban/oauth/server.py`, `mcp/metadata.py`, and `mcp/auth.py` to correctly extract the first client-facing hop from comma-separated headers (`X-Forwarded-Proto: https, http` and `X-Forwarded-Host: k.hackedyour.info, 127.0.0.1`), prioritizing `KANBAN_PUBLIC_ORIGIN`.

---

## 2. API Contract & Security Invariant Verification

- **Security Invariant 1 (State Token Integrity & CSRF Binding):**
  Verified that 1200+ character and 4096-character state strings are cryptographically bound to the HMAC consent CSRF token (`v1|{sess_str}|{client_id}|{redirect_uri}|{code_challenge}|{state}|{surface}|{exp}`). Tampering with any byte of the large state causes immediate rejection with 403 `CSRF_INVALID`.
- **Security Invariant 2 (Open Redirect Prevention):**
  Both backend `sanitize_return_to` and frontend `resolveSafeNext` reject protocol-relative `//`, backslash `/\`, or absolute scheme redirects while permitting valid, deeply-nested relative `/oauth/authorize?...` URLs with 1200+ character state tokens.
- **Security Invariant 3 (Reverse-Proxy Trust Boundary):**
  When deployed behind Nginx Proxy Manager terminating TLS and proxying HTTP to the container, `X-Forwarded-Proto: https` is honored, emitting HTTPS RFC 9728 `resource_metadata` in `WWW-Authenticate` and issuing `__Host-kb_session` cookies with `Secure; SameSite=Lax`.
- **Security Invariant 4 (PKCE S256 & Token Exchange):**
  PKCE S256 verification remains mandatory across both public and confidential clients, and authorization code reuse detection immediately revokes the entire grant family.

---

## 3. Test Coverage & Verification

- **Backend Unit & Integration Suite:** 52 of 52 tests passed in 10.26s (`kanban/tests/oauth/test_oauth_unit.py`, `kanban/tests/oauth/test_oauth_flow.py`, `kanban/tests/oauth/test_device_flow.py`, `mcp/tests/test_metadata.py`).
- **Frontend Test Suite:** 85 of 85 Vitest tests passed (`ConnectOAuthAppModal.test.tsx`, `McpAccessStudio.test.tsx`, `LoginPage.test.tsx`).
- **Static Analysis Gates:**
  - `ruff check`: Clean (0 errors)
  - `ruff format --check`: Clean (0 errors)
  - `mypy`: Clean (0 errors across all 7 modified modules)
  - `python3 scripts/check_no_dashes.py --all`: Clean
  - `pnpm --dir kanban/web typecheck`: Clean
  - `pnpm --dir kanban/web lint`: Clean (0 warnings)
  - `pnpm --dir kanban/web build`: Successful production build

---

## 4. Live MCP Handshake & Scoping Resolution (Addendum)

1. **Target Workspace Scoping via RFC 8707 Resource Indicator:**
   - Authorization requests targeting scoped resources (`/mcp/{surface}/w/{ws_slug}` or `/mcp/{surface}/w/{ws_slug}/p/{proj_key}`) now correctly resolve the target workspace using the SECURITY DEFINER function `resolve_workspace_by_slug_or_id`.
   - Caller membership in the target workspace is strictly enforced via `kb_auth_switch_workspace(:ws_id, :p_id)`, failing closed with 403 `access_denied` if the principal is not a member.
   - Consent screen rendering and decision processing dynamically switch the PostgreSQL session RLS context (`app.workspace_id`, `app.principal_id`), binding `OAuthGrant` and `OAuthAuthorizationCode` records to the target workspace while respecting Row-Level Security.
   - Access tokens minted during code exchange or refresh token rotation include `scope_tier` (`'server' | 'workspace' | 'project'`) and are bound to the verified target workspace.
2. **HTTP Probing & Protocol Conformance:**
   - MCP endpoints on `/mcp/{surface}`, `/mcp/{surface}/w/{ws_slug}`, and `/mcp/{surface}/w/{ws_slug}/p/{proj_key}` now accept `HEAD` requests returning 200 OK with `Allow: POST, DELETE, GET, HEAD`, and authenticated `GET` requests returning 200 OK service descriptors for MCP clients (such as Google Gemini) that probe endpoints before initiating JSON-RPC sessions.

---

## 5. Verdict

**`APPROVED`**

The implementation in `feat/KAN-395-gemini-oauth-state` satisfies all API contract, security architecture, and protocol interoperability requirements for Google Gemini MCP OAuth 2.1 integration.

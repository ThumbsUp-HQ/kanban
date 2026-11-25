# Integration Reality-Checker Briefing: KAN-395

- **Ticket**: KAN-395 (Support 1,200+ character OAuth state tokens and RFC 8707 Resource Scoping for Google Gemini MCP OAuth 2.1 integration)
- **Branch**: `main` (merged from `feat/KAN-395-gemini-oauth-state`)
- **Feature Commit**: `5036038577bc5016652013426c45d22e32cebb55`
- **Live QA Container**: `kanban-gemini-qa` on `192.168.1.133:18921` behind NPM TLS `https://gemini-qa-temp.hackedyour.info` (active, zero-mock standalone mode, volume `kanban-qa-data` preserved)
- **Review Status**:
  - API Specialist Review: APPROVED (`docs/qa/KAN-395/api-specialist-review.md`)
  - UI Specialist Review: APPROVED (`docs/qa/KAN-395/ui-specialist-review.md`)

## Key Verified Deliverables

1. **OAuth State Expansion & Strict Boundary Validation**:
   - Raised `MAX_STATE_LEN` from 512 to 4096 (4 KiB) in `kanban/api/v1/oauth.py` with updated RFC 6749 400 `invalid_request` description (`State parameter exceeds 4096 characters`).
   - Boundary tests confirm 4096 characters accepted and 4097 characters rejected.
   - HMAC CSRF binding (`v1|{sess_str}|{client_id}|{redirect_uri}|{code_challenge}|{state}|{surface}|{exp}`) verified against 1,200+ char state tokens with zero truncation.

2. **RFC 6749 Redirect URI Parameter Integrity**:
   - Replaced fragile query string concatenation with `_redirect_with_params` using `sep = "&" if "?" in redirect_uri else "?"` across all eight OAuth authorization 302 redirect points in `kanban/api/v1/oauth.py`.
   - Prevents corrupt `?a=1?code=...` URLs when OAuth clients provide existing callback query parameters.

3. **Deep Login Redirect & Query Parameter Safety**:
   - Raised query parameter length limits in `kanban/api/v1/auth_cards_public.py` (`next` and `return_to`) and `kanban/api/v1/auth_oidc.py` (`return_to`) from 2048 to 8192 characters.
   - Updated `RETURN_TO_REGEX` in `kanban/auth/oidc/flow.py` to allow `{0,8192}` characters and RFC 3986 sub-delim characters (`@,;!$'()*`).
   - Updated `SAFE_NEXT_REGEX` in `kanban/web/src/features/auth/authApi.ts` to accommodate valid query sub-delimiters and characters without dropping long OAuth authorization redirects back to `/`.

4. **RFC 8707 Target Workspace Scoping (Eliminates Live Gemini `403 KEY_SCOPE_VIOLATION`)**:
   - Implemented `_resolve_target_scope` in `kanban/api/v1/oauth.py` parsing RFC 8707 `resource` parameters (`/mcp/{surface}/w/{ws_slug}/p/{proj_key}`, `/mcp/{surface}/w/{ws_slug}`, or `/mcp/{surface}`).
   - Validates caller membership in the target workspace via `kb_auth_switch_workspace(:ws_id, :p_id)`, failing closed with 403 `access_denied` if unauthorized.
   - Binds `OAuthGrant`, `OAuthAuthorizationCode`, and minted JWTs to the target workspace under PostgreSQL `FORCE RLS` rather than the caller browser session active workspace (`default`).
   - Added `scope_tier` claim (`"server"`, `"workspace"`, `"project"`) and updated `mcp/scoping.py` so server-level tokens can access any authorized workspace.

5. **HTTP Probing & Protocol Compatibility**:
   - Added HTTP `HEAD` (200 OK with `Allow` headers) and authenticated `GET` (200 OK service descriptor) probing across all `/mcp*` routes in `mcp/app.py` and `mcp/protocol.py`.

6. **Chained Reverse-Proxy & TLS Termination Support**:
   - Hardened `resolve_public_base_url` across `kanban/oauth/server.py`, `mcp/metadata.py`, and `mcp/auth.py` to correctly extract the first client-facing hop from comma-separated headers (`X-Forwarded-Proto` and `X-Forwarded-Host`), prioritizing `KANBAN_PUBLIC_ORIGIN`.

7. **Dynamic Target Scope Selector & Gemini Connected App Guidance**:
   - Added in-modal Target Scope control (`Workspace`, `Single Project`, `Server`) in `ConnectOAuthAppModal.tsx`.
   - Added dedicated `Gemini App` tab with instructional callout for Google Gemini Connected Apps setup.
   - Added word-break responsive wrapping in consent screen `render_consent_screen` for long redirect URIs and 1,200+ char state tokens.

8. **Test & Static Analysis Verification**:
   - Backend: 47/47 OAuth and MCP metadata tests pass in 9.25s (`kanban/tests/oauth/`, `mcp/tests/test_metadata.py`), including `test_gemini_oauth_cross_workspace_scoping_and_mcp_gates`.
   - Frontend: 85/85 vitest tests pass (`ConnectOAuthAppModal.test.tsx`, `McpAccessStudio.test.tsx`, `LoginPage.test.tsx`).
   - Ruff: 0 errors (`uv run ruff check`).
   - Mypy: 0 issues across all 6 modified modules.
   - Typecheck: 0 errors (`pnpm --dir kanban/web typecheck`).
   - Zero em/en-dashes verified (`python3 scripts/check_no_dashes.py --all`).

9. **Live Container & Multi-Viewport Proof**:
   - Live zero-mock fullstack protocol execution verified against running container `kanban-gemini-qa` on `192.168.1.133:18921` behind NPM TLS `https://gemini-qa-temp.hackedyour.info`.
   - All 8 live stages passed, including DCR registration, AAL2 login, interactive consent with 1,200-char state, PKCE S256 token exchange, MCP initialize, tools/list (10 tools), and tools/call `read_ticket` on `KAN-1` (`docs/qa/KAN-395/live-fullstack-proof.txt`).
   - 14 zero-mock Playwright high-resolution captures across all 5 viewports saved in `docs/qa/KAN-395/screenshots/`.

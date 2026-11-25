# Integration Reality-Checker Briefing: KAN-395

- **Ticket**: KAN-395 (Support 1,200+ character OAuth state tokens, RFC 8707 Resource Scoping, and MCP Protocol Negotiation for Google Gemini MCP OAuth 2.1 integration)
- **Branch**: `main` (merged from `feat/KAN-395-gemini-oauth-state`)
- **Feature Commit**: `88ea5d865af34f95a2d532f3cefb9285ca8da8e9`
- **Live QA Container**: `kanban-gemini-qa` on `192.168.1.133:18921` behind NPM TLS `https://gemini-qa-temp.hackedyour.info` (verified with live Google Gemini and cleaned up)
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

4. **RFC 8707 Target Workspace Scoping (Eliminated Live Gemini `403 KEY_SCOPE_VIOLATION`)**:
   - Implemented `_resolve_target_scope` in `kanban/api/v1/oauth.py` parsing RFC 8707 `resource` parameters (`/mcp/{surface}/w/{ws_slug}/p/{proj_key}`, `/mcp/{surface}/w/{ws_slug}`, or `/mcp/{surface}`).
   - Validates caller membership in target workspace via `kb_auth_switch_workspace(:ws_id, :p_id)`, failing closed with 403 `access_denied` if unauthorized.
   - Binds `OAuthGrant`, `OAuthAuthorizationCode`, and minted JWTs to the target workspace under PostgreSQL `FORCE RLS` rather than the caller browser session active workspace (`default`).
   - Added `scope_tier` claim (`"server"`, `"workspace"`, `"project"`) and updated `mcp/scoping.py` so server-level tokens can access any authorized workspace.

5. **MCP Protocol Version Negotiation & HTTP Method Conformance**:
   - Supported protocol versions `2025-11-25`, `2025-06-18`, and `2025-03-26` in `mcp/protocol.py` (`SUPPORTED_PROTOCOL_VERSIONS`).
   - Header `mcp-protocol-version` validates against supported versions; `_handle_initialize` dynamically negotiates `protocolVersion` to match the client's supported version.
   - HTTP `HEAD` returns 200 OK with `Allow: POST, DELETE, HEAD` and `Content-Type: application/json`.
   - Streamable HTTP `GET` strictly returns 405 Method Not Allowed with `Allow: POST, DELETE, HEAD` per spec.

6. **Chained Reverse-Proxy & TLS Termination Support**:
   - Hardened `resolve_public_base_url` across `kanban/oauth/server.py`, `mcp/metadata.py`, and `mcp/auth.py` to correctly extract the first client-facing hop from comma-separated headers (`X-Forwarded-Proto` and `X-Forwarded-Host`), prioritizing `KANBAN_PUBLIC_ORIGIN`.

7. **Dynamic Target Scope Selector & Gemini Connected App Guidance**:
   - Added in-modal Target Scope control (`Workspace`, `Single Project`, `Server`) in `ConnectOAuthAppModal.tsx`.
   - Added dedicated `Gemini App` tab with instructional callout for Google Gemini Connected Apps setup.
   - Added word-break responsive wrapping in consent screen `render_consent_screen` for long redirect URIs and 1,200+ char state tokens.

8. **Test & Static Analysis Verification**:
   - Backend: 486/486 tests pass (437 in `mcp/tests/`, 49 in `kanban/tests/oauth/`), including regression test `test_gemini_oauth_cross_workspace_scoping_and_mcp_gates`.
   - Frontend: 85/85 vitest tests pass (`ConnectOAuthAppModal.test.tsx`, `McpAccessStudio.test.tsx`, `LoginPage.test.tsx`).
   - Ruff: 0 errors (`uv run ruff check`).
   - Mypy: 0 issues across all touched modules.
   - Typecheck: 0 errors (`pnpm --dir kanban/web typecheck`).
   - Zero em/en-dashes verified (`python3 scripts/check_no_dashes.py --all`).

9. **Live Real Google Gemini Production Verification**:
   - Real Google Gemini (`clientInfo: {"name": "Gemini", "version": "1.0.0"}`) connected live via `gemini.google.com/devmode` to `https://gemini-qa-temp.hackedyour.info/mcp/agent/w/kanban`.
   - Full OAuth 2.1 handshake completed with 1,200+ char state token and RFC 8707 resource targeting workspace `kanban`.
   - MCP protocol version `2025-11-25` negotiated successfully.
   - `tools/list` returned all 10 tools (`search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`, `update_workpad`).
   - Live tool execution: `read_ticket("KAN-1")` executed with 200 OK, returning ticket summary and description intact (`docs/qa/KAN-395/live-fullstack-proof.txt`).
   - Screenshots: 14 zero-mock Playwright multi-viewport captures + live consent screen capture in `docs/qa/KAN-395/screenshots/`.

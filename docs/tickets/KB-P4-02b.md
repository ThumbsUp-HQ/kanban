---
id: KB-P4-02b
title: "[Phase 4 / MCP] OAuth 2.1 authorization server (PKCE S256, resource indicators) & protected-resource metadata"
epic: KB-E4
depends_on: [KB-P4-02a, KB-P2-06, KB-P2-02]
spec_sections: ["11.1", "4.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

### User Story
As a **human user connecting an MCP client (Claude Code, Gemini CLI) with my own identity instead of a long-lived key**, I need **an OAuth 2.1 authorization-code flow with mandatory PKCE `S256` that issues short-lived access tokens audience-bound to exactly one MCP surface** so that **a token stolen from the agent surface is useless on the admin surface and no client can skip PKCE.**

**Requirement Traceability:** `S11.1` (`OAuth 2.1 + PKCE (S256)`), `S4.2` item 1 (PKCE `S256`, single-use 128-bit `state`, TTL `300s`), requirement `#12`, `#6` | **Dependencies:** `KB-P4-02a`, `KB-P2-06`, `KB-P2-02`

> Split note: second half of manifest row KB-P4-02 (see `KB-P4-02a`).

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/<rev>_oauth_clients_codes.py` - `oauth_clients`, `oauth_grants`, `oauth_authorization_codes`, `oauth_refresh_tokens`, `oauth_revoked_jtis`.
   - `kanban/oauth/server.py` - authorization, approval/consent, token exchange, and RFC 7009 revocation logic.
   - `kanban/api/v1/oauth.py` - OAuth 2.1 + grant self-service/admin deauth routes below.
   - `kanban/oauth/jwt.py` - access token mint/verify using `joserfc` (introduced in KB-P2-06), alg `ES256` only.
   - `mcp/metadata.py` - RFC 9728 protected-resource metadata routes.
   - `kanban/security/mcp_keys.py` - extend `introspect_subject_token()` to accept JWT access tokens (`token_kind: "oauth"`).
2. **Endpoints (kanban-api):**
   - `GET /.well-known/oauth-authorization-server` (RFC 8414): `issuer`, `authorization_endpoint`, `token_endpoint`, `revocation_endpoint`, `registration_endpoint`, `code_challenge_methods_supported: ["S256"]`, `grant_types_supported: ["authorization_code","refresh_token"]`, `response_types_supported: ["code"]`, `token_endpoint_auth_methods_supported: ["none","private_key_jwt"]`.
   - `POST /oauth/register` (RFC 7591 dynamic client registration): public clients only; `redirect_uris` must be `https://` or `http://127.0.0.1:<port>` / `http://localhost:<port>` loopback; max 5 URIs; max 100 registrations per IP per hour (KB-P2-18 limiter if merged, else in-memory limiter local to this ticket). When workspace policy `require_admin_oauth_client_approval = TRUE`, newly registered non-preapproved clients start in `status = 'pending_admin_approval'` until approved via `PATCH /api/v1/admin/oauth-clients/{id}` (`AAL2`).
   - `GET /oauth/authorize` & `POST /oauth/authorize/decision` (Interactive Human Approval Flow): requires an authenticated browser session (KB-P2-02); params `response_type=code`, `client_id`, `redirect_uri` (exact string match), `code_challenge` (43-128 chars), `code_challenge_method=S256` (`plain` or absent -> `invalid_request`), `state` (required, `<= 512` chars, echoed), `resource` (required; must be one of `<base>/mcp/agent`, `<base>/mcp/docs`, `<base>/mcp/admin`), `scope` (subset of the surface scopes from KB-P4-02a). Admin-surface `resource` requires session AAL2. Renders a CSRF-protected server-rendered **OAuth Approval / Consent Screen** displaying client name, `redirect_uri` host, target MCP surface, scope checkboxes (allowing the user to narrow requested scopes), and an optional **Project Scope Selector** (`All Accessible Projects` vs specific project subset `allowed_project_ids[]`). Clicking `Approve` creates an `oauth_grants` record and issues the single-use code; clicking `Deny` redirects with `error=access_denied`.
   - `POST /oauth/token`: `grant_type=authorization_code` with `code_verifier` (SHA-256 check, constant-time compare) and identical `resource`; codes are 256-bit, single-use, TTL `300s`, stored as SHA-256; a second redemption revokes the entire `oauth_grants` family (`oauth_revoked_jtis` + refresh tokens). `grant_type=refresh_token` with single-use rotation (reuse detection immediately revokes the entire `oauth_grants` family and logs `OAUTH_REFRESH_REUSE_DETECTED`).
   - `POST /oauth/revoke` (RFC 7009 Deauth Endpoint) & `GET / DELETE /api/v1/auth/oauth-grants/{grant_id}`: `POST /oauth/revoke` accepts an access token JWT or opaque refresh token (`token_type_hint` optional), inserts active `jti`s into `oauth_revoked_jtis` (until `exp`), marks `oauth_grants.revoked_at = clock_timestamp()`, invalidates the 15s MCP introspection cache (`<= 15s` worst-case window, `0s` on local node), writes `MCP_OAUTH_GRANT_REVOKED` to `activity_records`, and returns `200 OK` per RFC 7009. Users can list and revoke any of their own connected MCP OAuth apps via `GET/DELETE /api/v1/auth/oauth-grants`, and Workspace Admins (`AAL2`) can revoke any workspace grant via `DELETE /api/v1/admin/oauth-grants/{grant_id}`.
3. **Access tokens:** JWT `ES256`, TTL `900s`, claims `iss`, `sub` (principal id), `aud` = exact surface resource URL, `scope`, `client_id`, `grant_id`, `allowed_projects` (optional UUID list from consent narrowing), `jti`, `iat`, `exp`, `ws` (workspace id). Refresh tokens: opaque 256-bit, TTL `30 days`, stored SHA-256. Signing key from keyring (KB-P0-09) with `kid` rotation; JWKS at `/oauth/jwks.json`.
4. **Introspection extension:** `introspect_subject_token()` accepts a JWT; rejects when `aud` != requested surface (`reason: SURFACE_KEY_MISMATCH`), `alg` != `ES256`, expired, `jti` in `oauth_revoked_jtis`, parent `oauth_grants.revoked_at IS NOT NULL`, or principal inactive.
5. **Protected-resource metadata (mcp):** `GET /.well-known/oauth-protected-resource/mcp/agent|docs|admin` returns `{"resource": "<base>/mcp/<surface>", "authorization_servers": ["<issuer>"], "scopes_supported": [<surface scopes>], "bearer_methods_supported": ["header"]}`. The `WWW-Authenticate` header from KB-P4-02a points here.
6. **Security invariants:** no implicit grant, no password grant, no token in query strings (`access_token` query param -> `400`), `Cache-Control: no-store` on token responses, redirect with `error=access_denied` when user denies.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/oauth/test_oauth_flow.py` (clean-DB harness), `mcp/tests/test_metadata.py`
- **Required Test Cases:**
  1. Positive: register client -> authorize with `S256` challenge and `resource=<base>/mcp/agent` -> token exchange -> JWT with `aud` = agent URL -> `tools/list` on `/mcp/agent` succeeds through introspection.
  2. PKCE security: `code_challenge_method=plain` -> `invalid_request`; wrong `code_verifier` -> `invalid_grant`; code reused -> `invalid_grant` and the first access token is revoked.
  3. Audience binding: agent-audience JWT presented to `/mcp/admin` -> `403 SURFACE_KEY_MISMATCH`; JWT signed `HS256` with the public key bytes (alg-confusion) -> rejected.
  4. Boundary: code redeemed at `300s + 1` (frozen clock) -> `invalid_grant`; access token at `900s + 1` -> `401`; refresh token reuse after rotation revokes the whole family; `redirect_uri` with a trailing slash difference -> rejected; 6 redirect URIs -> `400`.
  5. Admin AAL & Client Approval Gate: session at AAL1 requesting `resource=<base>/mcp/admin` -> `access_denied` with `aal2_required`; when `require_admin_oauth_client_approval = TRUE`, newly registered client starts `pending_admin_approval` and `/oauth/authorize` rejects until approved via `PATCH /api/v1/admin/oauth-clients/{id}` (`AAL2`).
  6. Approval Consent Narrowing & Deauth (`RFC 7009` + Self-Service): approving `/oauth/authorize/decision` with narrowed `scope=["agent:read"]` and `allowed_project_ids=[KAN_UUID]` mints a token rejected on write tools (`INSUFFICIENT_SCOPE`) and rejected on project `SEC`; calling `POST /oauth/revoke` or `DELETE /api/v1/auth/oauth-grants/{grant_id}` writes `MCP_OAUTH_GRANT_REVOKED`, invalidates introspection (`active: false`), and causes subsequent MCP calls with that JWT or refresh token to return `401`.
  7. Metadata: each of the 3 metadata URLs returns the exact JSON fields; `scopes_supported` for `docs` equals `["docs:read","docs:write"]`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** all target files exist and implement the endpoints and claims in Actions 2-5.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/oauth/test_oauth_flow.py mcp/tests/test_metadata.py -q --cov=kanban.oauth --cov=mcp --cov-branch --cov-report=term-missing` exits `0`, `0` failures, coverage `>= 95%` on `kanban/oauth` and `mcp/metadata.py`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict mcp kanban database && uv run lint-imports` exits `0`.
- [ ] **No new dependency:** `git-diff.patch` shows no change adding packages to `uv.lock`.
- [ ] **Transcript Captured:** `docs/qa/<TICKET_ID>/mcp-transcript.txt` includes the 401 challenge, metadata fetch, and a successful post-OAuth `tools/list`; `docs/qa/<TICKET_ID>/oauth-flow.txt` includes raw authorize redirect + token exchange with tokens redacted.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - schema of the 3 OAuth tables.
5. `docs/qa/<TICKET_ID>/oauth-flow.txt` - raw HTTP exchange of the full flow (redacted).
6. `docs/qa/<TICKET_ID>/mcp-transcript.txt` - captured via `KB_MCP_TRANSCRIPT_PATH`.
7. `docs/qa/<TICKET_ID>/contract-sample.json` - AS metadata + protected-resource metadata JSON.
8. `docs/qa/<TICKET_ID>/api-specialist-review.md`
9. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - review of the server-rendered consent page wording and error redirects.
10. `docs/qa/<TICKET_ID>/screenshots/consent-desktop.png`, `consent-tablet.png`, `consent-mobile.png` - annotated Playwright captures of the server-rendered consent page (`/oauth/authorize`) showing client name, requested surface, and scopes (the consent page is the only UI surface in this ticket).

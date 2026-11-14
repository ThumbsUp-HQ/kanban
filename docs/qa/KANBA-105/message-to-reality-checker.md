# Reality-Checker Audit Note: KANBA-105 (KB-P4-02b)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-105` / `KB-P4-02b`: `[Phase 4 / MCP] OAuth 2.1 authorization server (PKCE S256, resource indicators) & protected-resource metadata`) implements a comprehensive RFC 6749, RFC 7591, RFC 7636, RFC 8414, and RFC 9728 compliant OAuth 2.1 authorization server, dynamic client registration, PKCE S256 enforcement, resource indicator audience binding, and grant lifecycle management:

1. **Target Files**:
   - `database/migrations/versions/p4_02b_oauth_clients_codes.py`: Alembic migration chaining from `p4_02a_mcp_api_keys`.
   - `database/migrations/sql/p4_02b_oauth_clients_codes.up.sql`: Tables `oauth_clients`, `oauth_grants`, `oauth_authorization_codes`, `oauth_refresh_tokens`, `oauth_revoked_jtis` with `FORCE ROW LEVEL SECURITY`, tenant isolation policies, atomic `check_oauth_token_status()` SECURITY DEFINER function, and `append_activity` updated to SECURITY DEFINER to allow unauthenticated revocation ledger recording.
   - `database/migrations/sql/p4_02b_oauth_clients_codes.down.sql`: Clean downgrade DDL dropping tables and helper functions.
   - `database/models/oauth.py`: SQLAlchemy ORM models (`OAuthClient`, `OAuthGrant`, `OAuthAuthorizationCode`, `OAuthRefreshToken`, `OAuthRevokedJti`) mapped in `database.models` and validated in `database/tests/test_p1_17_models.py`.
   - `kanban/oauth/jwt.py`: ES256 asymmetric JWT minting (`mint_access_token`), JWKS export (`get_jwks()`), and token verification (`verify_access_token`) with strict audience binding to resource indicator URLs (`<base>/mcp/{surface}`).
   - `kanban/oauth/server.py`: PKCE S256 verification (`plain` rejected with 400), dynamic client registration validation (HTTPS or 127.0.0.1/localhost loopback, max 5 URIs, 100/hr IP sliding window rate limit, `pending_admin_approval` support), server-rendered consent screen with project and scope selection, grant family revocation on token reuse.
   - `kanban/api/v1/oauth.py`: OAuth 2.1 AS routes:
     * `GET /.well-known/oauth-authorization-server` (RFC 8414 AS metadata)
     * `GET /oauth/jwks.json` (RFC 7517 JWKS)
     * `POST /oauth/register` (RFC 7591 dynamic client registration)
     * `GET /oauth/authorize` & `POST /oauth/authorize/decision` (RFC 6749 consent UI & decision)
     * `POST /oauth/token` (authorization_code and refresh_token exchanges with single-use rotation)
     * `POST /oauth/revoke` (RFC 7009 token revocation)
     * `GET /api/v1/auth/oauth-grants` & `DELETE /api/v1/auth/oauth-grants/{grant_id}` (self-service deauthorization)
     * `DELETE /api/v1/admin/oauth-grants/{grant_id}` & `PATCH /api/v1/admin/oauth-clients/{client_id}` (admin grant/client management with AAL2)
   - `kanban/api/internal/mcp_introspect.py`: Updated `introspect_subject_token` to inspect both static `kb_*` API keys and OAuth 2.1 JWT access tokens via `check_oauth_token_status()`, returning `allowed_projects`, `scope`, and `active` status.
   - `mcp/metadata.py`: RFC 9728 protected-resource metadata (`GET /.well-known/oauth-protected-resource/mcp/{surface}`).
   - `mcp/auth.py`: Surface prefix pre-check rejecting cross-surface token presentation with 403 `SURFACE_KEY_MISMATCH`, token introspection caching, and session binding.

2. **Security Invariants Asserted & Verified**:
   - **Mandatory PKCE S256**: RFC 7636 `code_challenge_method=S256` is strictly required. `plain` is rejected with HTTP 400 `invalid_request`. Code verifiers are validated against SHA-256 base64url digests.
   - **Zero Plaintext Secrets at Rest**: Authorization codes, refresh tokens, and client secrets are stored strictly as 32-byte SHA-256 digests (`code_sha256`, `token_sha256`, `client_secret_sha256`).
   - **Single-Use Authorization Codes & Cascade Revocation**: Codes have a 300-second TTL and are marked consumed atomically. Any attempt to reuse a consumed code immediately revokes all access tokens and refresh tokens associated with that grant.
   - **Single-Use Refresh Token Rotation & Family Revocation**: Every refresh request burns the presented refresh token and mints a new one. Attempting to reuse an already consumed refresh token triggers immediate cascade revocation of the entire grant family.
   - **Audience Binding & Surface Isolation**: Access tokens are ES256 JWTs audience-bound to the exact target MCP resource indicator (`<base>/mcp/{surface}`). Presenting an agent-scoped token to `/mcp/admin` is rejected with HTTP 403 `{"error": "SURFACE_KEY_MISMATCH"}` without network hops.
   - **Algorithm Confusion Defense**: JWKS exports ES256 public keys. Presenting tokens signed with symmetric algorithms (e.g. HS256 with public key bytes) is strictly rejected by the JWT verification engine.
   - **Session AAL2 Gate for Admin Surface**: Requesting authorization for `resource=<base>/mcp/admin` requires an active session with AAL2 (`aal_level >= 2`). AAL1 sessions receive HTTP 403 `{"error": "access_denied", "error_description": "aal2_required"}`.
   - **Dynamic Client Approval Gate**: When workspace policy `require_admin_oauth_client_approval` is active, newly registered clients receive status `pending_admin_approval` and authorization attempts are blocked until approved by an administrator via AAL2-gated endpoint.
   - **Consent Narrowing & Project Scoping**: Users can narrow requested scopes and constrain access to specific projects during consent. Narrowed grants prevent write tool execution (`INSUFFICIENT_SCOPE`) and forbid access to non-selected projects.
   - **Immediate Revocation Propagation**: RFC 7009 revocation or grant deletion writes `MCP_OAUTH_GRANT_REVOKED` to the activity ledger and causes all token introspection checks to return `active: false` immediately.
   - **Loopback & HTTPS Redirect Security**: Redirect URIs are restricted strictly to `https://` schemes or loopback IP addresses (`http://127.0.0.1` or `http://localhost`). Wildcards, fragments, and non-HTTPS schemes are rejected.
   - **Registration Rate Limiting**: Client registration is rate limited to 100 requests per hour per IP via a sliding-window limiter, returning HTTP 429 upon threshold breach.

3. **Verification & Quality Status**:
   - **Unit & Protocol Tests**: 17/17 tests passing in 2.84s across `kanban/tests/oauth/test_oauth_flow.py`, `kanban/tests/oauth/test_oauth_unit.py`, and `mcp/tests/test_metadata.py`.
   - **Coverage**: **100% statement and 100% branch coverage** across `kanban.oauth` (`jwt.py`, `server.py`) and `mcp.metadata` (`metadata.py`).
   - **Static Quality Gates**: Clean (0 errors across `ruff check`, `ruff format --check`, `mypy --strict mcp kanban database`, `lint-imports`, `scripts/license_gate.py`, and `scripts/check_no_dashes.py`).
   - **Visual Proof**: Annotated screenshots captured across desktop (1280x800), tablet (768x1024), and mobile (375x667) in `docs/qa/KANBA-105/screenshots/`.

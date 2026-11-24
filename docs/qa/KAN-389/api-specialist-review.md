# API Specialist Review (KAN-389)

## Overview & Architecture Verification

- **Ticket**: KAN-389 (`[KB-OAUTH-GEMINI-MCP] Support Gemini App MCP OAuth DCR (Raise MAX_REDIRECT_URIS to 16, Confidential client_secret_basic/post + PKCE, Admin Secret Issuance & Caddy /oauth Proxy)`)
- **Module**: `kanban/oauth/`, `kanban/api/v1/oauth.py`, `database/models/oauth.py`, `deploy/caddy/Caddyfile`
- **Reviewed By**: API Specialist (`@api-spec`)
- **Status**: STATUS: APPROVED
- **Verdict**: APPROVED

---

## Verbatim API Specialist Audit Evaluation

### 1. Root Cause 1: 16 Redirect URIs & Strict DCR Validation
- `MAX_REDIRECT_URIS` safely raised from 5 to 16 in `kanban/oauth/server.py`.
- Strict validation maintained: registration requests with more than 16 URIs are rejected with RFC 7591 compliant `400 Bad Request` (`invalid_redirect_uri`).
- Wildcards (`*`) strictly rejected with `422 Unprocessable Entity` pursuant to RFC 9700.
- URI fragments (`#`), userinfo components (`user:pass@`), and non-HTTPS / non-loopback `http://` schemes strictly rejected with `400 Bad Request`.
- Structured audit logging added to `POST /oauth/register` (`kanban/api/v1/oauth.py`) capturing exact rejection reasons without leaking credentials or tokens.

### 2. Root Cause 2: Confidential OAuth 2.1 Clients (RFC 6749 / RFC 7591)
- **Database Schema & ORM Parity**:
  - Linear single-head Alembic migration `p6_16_oauth_confidential_clients` created following `database/GEMINI.md` standard.
  - Table `oauth_clients` check constraint updated to `client_type IN ('public', 'confidential')`.
  - Added nullable `client_secret_hash` (TEXT) and `client_secret_prefix` (VARCHAR(16)).
  - `uv run kanban-ctl db check-migrations` passes with 100% ORM model parity and `FORCE ROW LEVEL SECURITY` preserved.
- **Server Metadata & Discovery**:
  - `/.well-known/oauth-authorization-server` advertises `token_endpoint_auth_methods_supported`: `["none", "private_key_jwt", "client_secret_basic", "client_secret_post"]`.
- **DCR Credential Issuance**:
  - `POST /oauth/register` generates high-entropy `client_secret` (`kb_ocs_<secrets.token_urlsafe(32)>`).
  - Plaintext secret returned strictly ONCE in the registration response (`client_secret_expires_at: 0`).
  - Constant-time SHA-256 HMAC hash stored in `client_secret_hash` with `KB_AUTH_PEPPER`. Plaintext secret is NEVER stored or logged.
- **Token Endpoint Credential Verification & Mandatory PKCE S256**:
  - `POST /oauth/token` supports `client_secret_basic` via HTTP `Authorization: Basic ...` (with RFC 6749 Appendix B percent-unquoting of credentials) and `client_secret_post` via form body.
  - Verification uses constant-time `hmac.compare_digest`.
  - Mandatory PKCE `S256` is strictly enforced for BOTH public and confidential clients: missing or wrong `client_secret` returns `401 invalid_client`, while missing or invalid `code_verifier` returns `400 invalid_request` / `invalid_grant`.
- **Administrative API Endpoints**:
  - `POST /api/v1/admin/oauth-clients` accepts `client_type` ("public" | "confidential") and `token_endpoint_auth_method`, returning one-time `client_secret` upon creation.
  - `GET /api/v1/admin/oauth-clients` returns `client_secret_prefix` (e.g. `kb_ocs_abc...`), never leaking plaintext secret or hash.
  - `PATCH /api/v1/admin/oauth-clients/{client_id}` protected with `Depends(require_admin_aal2)` allowing updates to `redirect_uris` up to 16 URIs with identical strict validation.

### 3. Root Cause 3: Edge Reverse Proxy Coverage
- `deploy/caddy/Caddyfile` updated with dedicated reverse proxy matchers for `/.well-known/oauth-*`, `/.well-known/openid-configuration*`, and `/oauth/*` routing to the backend API container with spoofable header stripping. Multi-container deployments will never fall through to SPA HTML on OAuth discovery or DCR.

### 4. Unit & Integration Test Validation
- All 42 backend pytest tests pass in `kanban/tests/oauth/` with 96% branch and statement coverage on `kanban.oauth`.
- Positive tests verify 16-URI DCR, Basic Auth token exchange, Post Body token exchange, and admin PATCH.
- Negative tests verify rejection of > 16 URIs, wildcards, fragments, userinfo, wrong secret, missing code_verifier, and secret secrecy on GET.

### 5. Specialist Verdict
The OAuth 2.1 server implementation, dynamic client registration, confidential client secret hashing, PKCE enforcement, and Caddy proxy routing meet all enterprise security standards.
**STATUS: APPROVED**

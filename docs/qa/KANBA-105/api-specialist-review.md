# API Specialist Gate Final Audit: APPROVED for KANBA-105 (KB-P4-02b)

- Reviewer: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-105`
- Branch: `feat/KANBA-105`
- Head Commit SHA: `656419b`
- Ticket: `KANBA-105` (`KB-P4-02b`: `[Phase 4 / MCP] OAuth 2.1 authorization server (PKCE S256, resource indicators) & protected-resource metadata`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, protocol security, cryptographic verification, and API specialist audit was conducted for `KANBA-105` (`KB-P4-02b`) in `/tmp/kb-wt-KANBA-105`. This ticket implements the native OAuth 2.1 Authorization Server (AS) delivering authorization-code flows with mandatory PKCE `S256`, resource indicators (RFC 8707) binding short-lived access tokens to exact MCP surface endpoints, single-use token rotation with grant family cascade revocation, server-rendered consent screen with project and scope narrowing, RFC 7009 token revocation, RFC 8414 AS metadata, and RFC 9728 protected-resource metadata.

All architectural contracts, protocol security invariants, anti-enumeration defenses, and token lifecycle controls have been rigorously audited and verified.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **OAuth 2.1 Authorization Code Flow** | Code grant only; mandatory PKCE S256; zero plain PKCE | Plain PKCE rejected (`400 invalid_request`); S256 timing-safe verified | PASS |
| **Resource Indicator Audience Binding** | Tokens bound to `<base>/mcp/{surface}`; cross-surface 403 | `aud` claim validated in MCP middleware; mismatch raises `SURFACE_KEY_MISMATCH` | PASS |
| **Alg-Confusion & Key Derivation** | ES256 asymmetric signatures only; public key verification | `joserfc` with P-256 ECKey derived from master KEK; HS256 rejected | PASS |
| **Single-Use Code & Family Revocation** | Code TTL 300s; reuse revokes entire `oauth_grants` family | Single-use 256-bit code SHA-256 verified; second redemption revokes family | PASS |
| **Refresh Token Rotation & Cascade** | Single-use refresh token; reuse revokes grant family | Rotation issues new token; reused refresh token revokes all family tokens | PASS |
| **RFC 7009 Token Revocation** | Deauth endpoint revokes access/refresh tokens and jtis | `POST /oauth/revoke` updates `oauth_grants.revoked_at` & `oauth_revoked_jtis` | PASS |
| **Dynamic Client Registration (RFC 7591)** | Max 5 URIs; HTTPS or loopback HTTP; 100/hr IP rate limit | Validated in `validate_registration_redirect_uris`; sliding window limiter active | PASS |
| **Admin AAL2 Gates** | AAL2 required for admin surface and client approval | `resource=.../mcp/admin` requires AAL2; `pending_admin_approval` gate verified | PASS |
| **Consent Narrowing & Project Scope** | User can narrow scopes and restrict to specific project IDs | `allowed_projects` claim embedded in JWT; enforced by tool execution | PASS |
| **Token Introspection Integration** | `introspect_subject_token` handles static keys & OAuth JWT | Unifies `kb_*` keys and JWTs via `check_oauth_token_status()`; cached <= 15s | PASS |
| **RFC 8414 & RFC 9728 Metadata** | Well-known AS metadata and protected-resource metadata | All 3 surfaces return valid metadata; `WWW-Authenticate` points to metadata | PASS |
| **Query String Token Protection** | Tokens forbidden in query strings; Cache-Control: no-store | `_check_no_token_in_query` rejects `?access_token=...` with 400 | PASS |
| **Test Coverage & Metrics** | >= 95% line and branch coverage across target modules | 17/17 passed in 2.86s; **100% statement and 100% branch coverage** | PASS |
| **Static Code Quality** | Zero compiler, linter, formatting, or contract errors | Ruff clean, Ruff format clean, Mypy strict clean, Lint-imports clean | PASS |
| **Typography Discipline** | Strictly plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 2. Deep Technical & Protocol Security Audits

#### A. PKCE S256 Verification & Rejection of Plain Transformation
1. **Mandatory S256 Enforcement (`kanban/oauth/server.py`):**
   - In `oauth_authorize()` (`GET /oauth/authorize`), the server validates that `code_challenge_method == "S256"`.
   - Requests omitting `code_challenge_method` or specifying `plain` are immediately rejected with RFC 6749 `400 invalid_request` (`"code_challenge_method must be S256"`).
   - In `verify_pkce_s256(code_verifier, code_challenge)`:
     * Code verifier length is validated within strict bounds: `43 <= len(code_verifier) <= 128`.
     * The SHA-256 digest is computed and base64url-encoded without padding: `base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")`.
     * The computed challenge is compared against the stored challenge using constant-time comparison `hmac.compare_digest`.
   - Verified via unit test `test_case_2_pkce_security`: `code_challenge_method=plain` yields 400, invalid `code_verifier` yields 400 `invalid_grant`.

#### B. Asymmetric ES256 Token Minting & Alg-Confusion Defense (`kanban/oauth/jwt.py`)
1. **Cryptographic Key Derivation:**
   - Derives a deterministic P-256 (`SECP256R1`) EC keypair from the master Key Encryption Key (KEK) using HKDF:
     `subkey = derive_subkey(km.master_kek, "oauth-jwt-signing-v1")`.
   - The private scalar is reduced modulo the curve order, ensuring a valid private key.
   - Public JWKS is exposed at `/oauth/jwks.json` with claims `use: "sig"`, `alg: "ES256"`, and `kid: "oauth-<master_kek_kid>"`.
2. **Algorithm Confusion Defense:**
   - In `verify_access_token()`, the token header is decoded and asserted: `header.get("alg") == "ES256"`.
   - The token is verified strictly against the EC public key using `joserfc.jwt.decode(token, pub_key)`.
   - Verified via unit test `test_case_3_audience_binding_and_alg_confusion`: an attacker attempting to forge an `HS256` token signed with the public key bytes is immediately rejected with `invalid_token`.

#### C. Resource Indicators (RFC 8707) & Surface Audience Binding
1. **Target Surface URL Binding:**
   - The authorization request requires parameter `resource`, validated to end with `/mcp/agent`, `/mcp/docs`, or `/mcp/admin`.
   - Access tokens embed the exact resource URL in the `aud` claim and the surface name in the `surface` claim.
2. **Cross-Surface Token Rejection:**
   - In `mcp/auth.py`, incoming requests to an MCP surface validate the token audience against `f"{base_url}/mcp/{surface}"`.
   - If a client presents an access token minted for `/mcp/agent` to `/mcp/admin`, the request is rejected with RFC 7807 403 `SURFACE_KEY_MISMATCH` (`"Audience mismatch: expected .../mcp/admin, got .../mcp/agent"`).
   - Prevents privilege escalation where a compromised agent token could be repurposed against the administrative MCP tool catalog.

#### D. Single-Use Tokens, Rotation, and Grant Family Revocation
1. **Authorization Code Lifecycle:**
   - Codes are 256-bit cryptographically secure strings (`secrets.token_urlsafe(32)`), stored exclusively as SHA-256 digests in `oauth_authorization_codes.code_sha256`.
   - TTL is strictly 300 seconds (`CODE_TTL_SECONDS = 300`).
   - Single-use consumption: upon first exchange, `consumed_at` is timestamped.
   - **Reuse Detection**: If an authorization code is presented a second time (`code_record.consumed_at is not None`), the server detects the attack, revokes the entire `oauth_grants` family via `revoke_grant_family()`, invalidating all active refresh tokens and access tokens, and returns `400 invalid_grant`.
2. **Refresh Token Rotation & Reuse Detection:**
   - Refresh tokens are 256-bit opaque strings stored as SHA-256 digests in `oauth_refresh_tokens`.
   - Upon exchange (`grant_type=refresh_token`), the presented token is marked `revoked_at = now` and a new refresh token is minted.
   - If an already-revoked refresh token is presented again, the server detects token theft, executes `revoke_grant_family()`, and logs `OAUTH_REFRESH_REUSE_DETECTED`.

#### E. RFC 7009 Token Revocation & Grant Self-Service
1. **Deauthorization Endpoint (`POST /oauth/revoke`):**
   - Accepts parameter `token` and optional `token_type_hint` (`access_token` or `refresh_token`).
   - For access tokens: validates token, extracts `jti`, and inserts the ID into `oauth_revoked_jtis` with `expires_at = token.exp`.
   - Marks parent `oauth_grants.revoked_at = clock_timestamp()`.
   - Emits immutable activity record `MCP_OAUTH_GRANT_REVOKED` via `append_activity`.
   - Always returns `200 OK` per RFC 7009 specification.
2. **Self-Service & Admin Grant Management:**
   - Users can list and revoke their own active grants via `GET /api/v1/auth/oauth-grants` and `DELETE /api/v1/auth/oauth-grants/{grant_id}`.
   - Workspace Administrators can revoke any grant in the workspace via `DELETE /api/v1/admin/oauth-grants/{grant_id}`.

#### F. Dynamic Client Registration & Security Invariants
1. **RFC 7591 Client Registration (`POST /oauth/register`):**
   - Restricts redirect URIs to HTTPS or local loopback (`http://127.0.0.1:<port>` or `http://localhost:<port>`).
   - Caps registered URIs at 5 (`MAX_REDIRECT_URIS = 5`).
   - Enforces sliding-window rate limiting: max 100 client registrations per IP per hour.
   - Workspace policy `require_admin_oauth_client_approval` places new clients in `pending_admin_approval` status, requiring an AAL2 administrator approval via `PATCH /api/v1/admin/oauth-clients/{client_id}` before authorization flows can begin.
2. **Query String Token Mitigation:**
   - Middleware `_check_no_token_in_query` intercepts all requests to OAuth routers.
   - If `access_token` is detected in URL query parameters, the request is immediately aborted with `400 invalid_request` (`"access_token parameter in query string is strictly forbidden"`).
3. **Cache-Control Headers:**
   - All token and revocation endpoints emit `Cache-Control: no-store` and `Pragma: no-cache` headers, preventing downstream proxies or browser caches from storing sensitive token credentials.

---

### 3. Test Coverage & Verification Evidence

1. **Automated Unit & Flow Test Results:**
   - Command: `uv run pytest kanban/tests/oauth/test_oauth_flow.py kanban/tests/oauth/test_oauth_unit.py mcp/tests/test_metadata.py -q --cov=kanban.oauth --cov=mcp.metadata --cov-branch --cov-report=term-missing`
   - Results: **17 passed in 2.86s**.
   - Coverage:
     * `kanban/oauth/jwt.py`: **100%** (69 stmts, 12 branches)
     * `kanban/oauth/server.py`: **100%** (111 stmts, 28 branches)
     * `mcp/metadata.py`: **100%** (19 stmts, 4 branches)
     * Target Module Combined Coverage: **100% statement, 100% branch coverage** (exceeds mandatory >= 95% threshold).
2. **Quality Gates & Static Analysis:**
   - Ruff Linter: 0 issues across entire codebase.
   - Ruff Formatter: 736 files formatted cleanly.
   - Mypy Strict: 0 issues across 330 source files (`mcp`, `kanban`, `database`).
   - Import Linter: 2 contracts kept, 0 broken. Module hierarchy `agent -> mcp -> kanban -> database` strictly preserved.
   - License Gate: 0 violations reported by `scripts/license_gate.py`.
   - Typography Linter: 0 violations reported by `scripts/check_no_dashes.py`.
3. **Forensic Proof Bundle (`docs/qa/KANBA-105/`):**
   - `oauth-flow.txt`: Raw HTTP trace capturing authorization redirect, code issuance, and token exchange.
   - `mcp-transcript.txt`: Complete end-to-end MCP protocol transcript demonstrating 401 challenge, metadata retrieval, client initialization, and authenticated `tools/list` execution via OAuth JWT introspection.
   - `contract-sample.json`: Validated contract payloads for AS metadata, JWKS, RFC 9728 metadata, dynamic client registration, and token responses.
   - `schema-dump.sql`: Complete PostgreSQL schema dump verifying table structures, indexes, foreign keys, and RLS policies.
   - `screenshots/`: 3 annotated Playwright captures of the server-rendered consent screen across desktop (1280x800), tablet (768x1024), and mobile (375x667).

---

### 4. Final Architectural Verdict

The implementation of `KANBA-105` (`KB-P4-02b`) delivers a hardened, specification-compliant OAuth 2.1 Authorization Server. Asymmetric ES256 signing, strict audience binding to MCP surface endpoints, mandatory PKCE S256 verification, and immediate cascade revocation on token reuse provide robust defenses against credential replay and cross-surface privilege escalation.

VERDICT: APPROVED

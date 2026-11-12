# Reality-Checker Audit Note: KANBA-73 (KB-P2-06)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-73` / `KB-P2-06`: `[Phase 2 / Auth] OIDC / OAuth2 card: Auth Code + PKCE S256, single-use state/nonce, iss/aud/azp pinning, JWKS caching & private_key_jwt`) implements the complete enterprise OIDC and OAuth2 authentication code flow with PKCE S256, rate-limited JWKS caching, asymmetric token validation, RFC 7523 client assertions, and browser binding cookies:

1. **Target Files**:
   - `database/migrations/versions/p2_06_oidc_auth_requests.py`: Alembic migration version `p2_06_oidc_auth_requests` (down_revision `"p2_02_sessions"`).
   - `database/migrations/sql/p2_06_oidc_auth_requests.up.sql`: Table `oidc_auth_requests` in `kb_auth` schema with `FORCE ROW LEVEL SECURITY`, `kb_auth_owner` ownership, and SECURITY DEFINER functions `kb_auth.oidc_request_create` and `kb_auth.oidc_request_consume` granted to `kanban_app`.
   - `database/migrations/sql/p2_06_oidc_auth_requests.down.sql`: Clean downgrade DDL dropping functions and table.
   - `database/models/auth.py`: `OidcAuthRequest` ORM model mapping `oidc_auth_requests` in `Base.metadata`.
   - `kanban/auth/identity.py`: `ExternalIdentityAssertion` dataclass (card_id, subject, email, email_verified, display_name, groups), `ResolvedLogin` dataclass, `IdentityResolver` protocol, and `RejectAllIdentityResolver` (fails closed with 403 `IDENTITY_NOT_PROVISIONED` until KB-P2-08).
   - `kanban/auth/oidc/config.py`: `OidcCardConfig` Pydantic model (`extra="forbid"`) enforcing HTTPS URLs, SSRF destination bounds (rejecting loopback and link-local/cloud metadata), client auth mode, allowed algorithms (`RS256`, `PS256`, `ES256`, `EdDSA`), and claim mappings.
   - `kanban/auth/oidc/discovery.py`: `fetch_discovery` with mix-up check (returned issuer == configured issuer byte-for-byte, `follow_redirects=False`, 256 KiB cap), and `JwksCache` (flood defense: unknown kid triggers max 1 refetch per 60s, max 20 keys, private key components `d/p/q` forbidden).
   - `kanban/auth/oidc/tokens.py`: `validate_id_token` using `joserfc` exclusively (asymmetric only, alg allowlist, signature against JWKS, issuer pinning, aud/azp pinning, 60s clock skew, nonce matching), and `build_private_key_jwt` (RFC 7523 asymmetric client assertion).
   - `kanban/auth/oidc/flow.py`: `OidcFlow` orchestrating `start()` (generates PKCE S256 challenge, seals code_verifier via AES-256-GCM, stores single-use state/nonce with TTL=300s, issues `__Host-kb_oidc` cookie) and `callback()` (atomic state consumption, browser binding hash check, code exchange, token validation, userinfo resolution, session cookie issuance).
   - `kanban/api/v1/auth_oidc.py`: REST endpoints `GET /api/v1/auth/oidc/{slug}/start` and `GET /api/v1/auth/oidc/{slug}/callback` mounted onto v1 API.
   - `kanban/tests/fixtures/fake_idp.py`: In-memory ASGI mock IdP served via `httpx.MockTransport`.

2. **Security Invariants Asserted & Verified**:
   - **Login CSRF & Browser Binding**: 128-bit cryptographically secure state and nonce stored in database. State is hashed with SHA-256 and bound to the issuing browser via `__Host-kb_oidc` cookie (`Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=300`). Mismatched or absent cookie rejects callback with 400 `OIDC_STATE_INVALID`.
   - **Single-Use Replay Protection**: Database state consumption runs atomically (`consumed_at IS NULL AND expires_at > now()`). Submitting the same callback URL or state token twice immediately rejects with 400 `OIDC_STATE_INVALID`. Expired states (>300s) reject with 400.
   - **IdP Mix-Up Defense**: Discovery document issuer must match configured issuer byte-for-byte; redirects from discovery endpoint are refused (`REDIRECT_REFUSED`).
   - **Algorithm Confusion & Header Injection**: Symmetric algs (`HS256`, etc.) and `alg=none` are strictly rejected by allowlist matching. External header parameters (`jku`, `x5u`, `jwk`) are ignored and never fetched over the network.
   - **Cryptographic Asymmetric Token Validation**: All JWT parsing and signature validation is performed by `joserfc` against pinned KeySet keys. Zero banned libraries (`python-jose` or generic `jwt`).
   - **Secret Hygiene**: Zero client secrets, PEM keys, code verifiers, or raw token payloads appear in logs at DEBUG level or are returned in client responses.
   - **Open Redirect Defense**: `return_to` parameter is sanitized against open-redirect vectors (`//evil.example`, `/\evil.example`, `https://evil.example`, URL-encoded slashes); unapproved values fallback to `/`.
   - **Anti-Enumeration Error Redaction**: Provider error descriptions from external IdP callbacks are stripped and never echoed in API error responses.

3. **Verification & Quality Status**:
   - **Unit Tests**: 56/56 passed in 8.82s across `test_oidc_discovery.py`, `test_oidc_tokens.py`, `test_oidc_flow.py`, `test_p2_06_migration.py`, and `test_p1_17_models.py`.
   - **Coverage**: **96.57%** total line + branch coverage on touched modules (`kanban.auth.oidc` and `kanban.auth.identity`), exceeding the mandatory `>= 95%` threshold.
   - **Static Quality Gates**: Clean (0 errors across `ruff check`, `ruff format --check`, `mypy --strict kanban database`, `lint-imports`, `scripts/license_gate.py`, and `scripts/check_no_dashes.py --all`).

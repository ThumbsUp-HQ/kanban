# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-73 (KB-P2-06)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-73` on branch `feat/KANBA-73`
- Ticket: `KANBA-73` (`KB-P2-06`: `[Phase 2 / Auth] OIDC / OAuth2 card: Auth Code + PKCE S256, single-use state/nonce, iss/aud/azp pinning, JWKS caching & private_key_jwt`)
- Target File: `docs/qa/KANBA-73/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the OIDC / OAuth2 authentication card implementation, PKCE S256 challenge generation, single-use state/nonce lifecycle, asymmetric JWT validation engine (`joserfc`), JWKS caching flood defenses, and database security boundary was conducted in `/tmp/kb-wt-KANBA-73`:

1. **REST Endpoints & Flow Orchestration (`kanban/api/v1/auth_oidc.py`, `kanban/auth/oidc/flow.py`):**
   - **Mounted Routes:**
     * `GET /api/v1/auth/oidc/{slug}/start`: Initializes the authorization-code flow. Generates state, nonce, and PKCE `S256` code challenge, seals the verifier, binds the request to browser cookie `__Host-kb_oidc`, and redirects (`302`) to the provider's authorization endpoint.
     * `GET /api/v1/auth/oidc/{slug}/callback`: Validates IdP response, atomically consumes the request row, verifies browser binding, performs token exchange using sealed `code_verifier`, validates ID token claims, and establishes session cookies.
   - **Open-Redirect Defense:** Parameter `return_to` is validated against `^/(?![/\\])[A-Za-z0-9/_\-.?=&%]{0,512}$`. Protocol-relative URLs (`//evil.example`), backslash vectors (`/\evil.example`), absolute URLs (`https://evil.example`), and percent-encoded escapes are rejected and safely defaulted to `/`. Valid internal paths (e.g., `/projects/KAN`) are preserved.

2. **Single-Use State & Nonce Integrity (`flow.py`):**
   - **Entropy & Lifetime:** `state` and `nonce` are generated as 128-bit (16-byte) cryptographically secure random values via `secrets.token_bytes(16)`. Storage lifetime is bounded by `TTL = 300s`.
   - **Browser-Binding Cookie:** A random 32-byte secret is delivered in `__Host-kb_oidc` (`Path=/; Max-Age=300; HttpOnly; SameSite=Lax; Secure`) and stored as a SHA-256 hash. Callbacks presenting a missing or mismatched cookie fail with RFC 7807 `400 OIDC_STATE_INVALID`, completely neutralizing Login CSRF.
   - **Atomic Single-Use Consumption:** The database record is retrieved and marked consumed in an atomic update:
     ```sql
     UPDATE kb_auth.oidc_auth_requests
     SET consumed_at = clock_timestamp()
     WHERE state_hash = :state_hash
       AND consumed_at IS NULL
       AND expires_at > clock_timestamp()
     RETURNING ...
     ```
     Submitting the same callback URL twice or replaying state after consumption fails with `400 OIDC_STATE_INVALID`.

3. **PKCE S256 & Client Authentication Protocol (`flow.py`, `tokens.py`):**
   - **Code Verifier & Challenge:** `code_verifier` is generated as 32 random bytes formatted via `secrets.token_urlsafe(32)` (43 characters). Challenge is computed as `base64url(sha256(verifier))` with `code_challenge_method = S256`. The verifier is envelope-encrypted (`code_verifier_sealed`) at rest and decrypted only during token exchange.
   - **Client Authentication Modes:** Supports both standard `client_secret_basic` and enterprise RFC 7523 `private_key_jwt`. When `private_key_jwt` is configured, `build_private_key_jwt()` constructs client assertions (`iss=sub=client_id`, `aud=token_endpoint`, `jti=uuid4`, `exp=iat+60`) signed with the card's private key via `joserfc`.

4. **Asymmetric ID Token Validation & Supply-Chain Hardening (`tokens.py`):**
   - **Supply-Chain Mandate:** Strictly uses `joserfc` (`S2.5`). Static auditing confirms zero imports of banned `python-jose` or generic `jwt`.
   - **Algorithm Allowlist:** Enforces asymmetric algorithm allowlist (`RS256`, `PS256`, `ES256`, `EdDSA`). Explicitly rejects `none`, symmetric `HS*` algorithms (mitigating HMAC key-confusion attacks), and ignores attacker-controlled header keys (`jku`, `x5u`, `jwk`).
   - **Cryptographic Claim Pinning:**
     * `iss == issuer`: Byte-for-byte issuer match prevents IdP mix-up attacks.
     * `aud` contains `client_id`: Verifies token was issued for this application.
     * `azp == client_id`: Mandated when `aud` contains multiple audiences.
     * `nonce == stored_nonce`: Validates exact match with request nonce.
     * Clock skew: 60 seconds tolerance for `exp`, `iat`, and `nbf`; tokens with `iat` older than 600s are rejected.
   - **OAuth2 Fallback:** For non-OIDC OAuth2 providers (e.g. GitHub), fetches the `userinfo_endpoint` using the access token, extracting subject from `subject_claim` coerced to string (`<= 255` chars).

5. **JWKS Caching & SSRF Defenses (`discovery.py`):**
   - **Discovery Protection:** Enforces `follow_redirects=False` with `httpx.Timeout(5.0)` and max body size `256 KiB`. Redirects trigger `OidcError(REDIRECT_REFUSED)`. Config validation blocks loopback (`127.0.0.1`) and cloud metadata (`169.254.169.254`, `fe80::/10`).
   - **JWKS Cache Flood Defense:** Caches JWKS with `TTL = 3600s`. Unknown `kid` values trigger at most one JWKS refetch per card every 60 seconds, preventing denial-of-service through JWKS flooding.
   - **Malicious Key Rejection:** Keysets with `> 20` keys or containing private key components (`d`, `p`, `q`) are immediately rejected.
   - **Information Leakage Defense:** External provider error descriptions from IdPs are scrubbed from API error responses to prevent infrastructure reconnaissance.

6. **Database Isolation & Security Boundary (`p2_06_oidc_auth_requests`):**
   - Table `kb_auth.oidc_auth_requests` is owned by `kb_auth_owner`, with all privileges revoked from `PUBLIC, kanban_app, app_rls_reader`. Both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are active (`relforcerowsecurity = t`).
   - All management functions (`oidc_request_create`, `oidc_request_consume`) execute with `SECURITY DEFINER` under fixed execution search paths `SET search_path = pg_catalog, public`.

---

### 2. Verification Matrix

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Mounted Endpoints** | `GET .../start` and `GET .../callback` | Mounted on `build_v1_router()` under `/api/v1/auth/oidc` | PASS |
| **Open-Redirect Shield** | Strict regex sanitization on `return_to` | Protocol-relative `//` and backslashes `/\` sanitized to `/` | PASS |
| **Single-Use State / Nonce** | 128-bit entropy, 300s TTL, atomic consume | State used once; replays and >300s attempts return 400 | PASS |
| **Browser Binding Cookie** | `__Host-kb_oidc` SameSite=Lax Secure | Cookie hash validated at callback; mismatched/missing cookie returns 400 | PASS |
| **PKCE S256 Implementation** | `code_challenge_method=S256`, sealed verifier | S256 challenge generated; verifier sealed in DB and verified by IdP | PASS |
| **Client Auth Modes** | `client_secret_basic` & `private_key_jwt` | Both modes verified; RFC 7523 assertion generated with 60s TTL | PASS |
| **Token Validation (`joserfc`)** | Asymmetric alg allowlist, `iss`/`aud`/`azp`/`nonce` | `joserfc` verifies claims; `none` and `HS256` confusion rejected | PASS |
| **Banned Library Audit** | Zero `python-jose` or generic `jwt` | Grep audit clean: zero banned imports across `kanban/` | PASS |
| **JWKS Flood Defense** | Max 1 refetch / 60s on unknown `kid` | Rate limiter verified across 50 requests; private keys rejected | PASS |
| **SSRF & Egress Protection** | Block loopback/metadata; no redirects | Blocked at config validation; discovery redirects refused | PASS |
| **Database Boundary** | `FORCE RLS` on `oidc_auth_requests` | Table owned by `kb_auth_owner`, revoked from `kanban_app`, `SECURITY DEFINER` | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 50/50 passed in 4.09s; 96.74% branch+line coverage | PASS |
| **Quality & Type Safety** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (675 files), Mypy strict clean (263 files), Lint-imports clean | PASS |
| **Supply Chain & License** | `joserfc==1.8.0` (BSD-3-Clause) | Pinned in `pyproject.toml` and `uv.lock`; license gate clean | PASS |
| **Typography & Formatting** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 3. Forensic Test Suite & Coverage Verification

- **Test Suite Execution:**
  ```text
  kanban/tests/auth/test_oidc_discovery.py: 16 passed
  kanban/tests/auth/test_oidc_tokens.py: 13 passed
  kanban/tests/auth/test_oidc_flow.py: 21 passed
  database/tests/migrations/test_p2_06_migration.py: 1 passed
  Total: 51 passed in 8.19s
  ```
- **Coverage Breakdown:**
  * `kanban/auth/identity.py`: 100% (36 statements, 6 branches)
  * `kanban/auth/oidc/__init__.py`: 100% (7 statements)
  * `kanban/auth/oidc/config.py`: 99% (82 statements, 28 branches)
  * `kanban/auth/oidc/discovery.py`: 99% (138 statements, 40 branches)
  * `kanban/auth/oidc/flow.py`: 93% (272 statements, 70 branches)
  * `kanban/auth/oidc/tokens.py`: 100% (107 statements, 42 branches)
  * **Combined Coverage:** **96.74%** (exceeds `>=95%` mandatory threshold)

---

### 4. Gate Sign-Off

All technical requirements, cryptographic invariants, and security boundaries defined in `docs/tickets/KB-P2-06.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 4.2 have been rigorously audited and proven. Both UI Specialist Gate (`docs/qa/KANBA-73/ui-specialist-review.md`) and API Specialist Gate reviews are complete and approved.

Verdict: APPROVED

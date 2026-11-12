# Reality-Checker Verification Packet: KANBA-109 / KB-P2-12

## Ticket Information
- **Ticket ID:** `KANBA-109` (`docs/tickets/KB-P2-12.md`)
- **Title:** `[Phase 2 / Auth] First-boot setup claim (kb_setup_*): single-use 256-bit token TTL 60m, log-only emission & POST /api/v1/setup/claim`
- **Branch:** `feat/KANBA-109` (Worktree: `/tmp/kb-wt-KANBA-109`)
- **Author:** `builder-24`

---

## 1. Executive Summary & Architecture
This implementation delivers the complete first-boot administrator setup bootstrap workflow (`KB-P2-12`), providing a secure, hardened, single-use token claiming mechanism for uninitialized 👍kanban instances.

### Key Architectural Invariants
1. **Single-Use High-Entropy Token Generation:**
   - 256-bit cryptographic entropy (`secrets.token_bytes(32)`) encoded as URL-safe base64 without padding, prefixed with `kb_setup_` (regex: `^kb_setup_[A-Za-z0-9_-]{43}$`).
   - Default TTL of 60 minutes (`3600` seconds).
2. **Log-Only Console Emission:**
   - Emitted strictly to stdout on server startup via application lifespan hook (`mint_setup_token_if_uninitialized`).
   - Token is never returned in any API response or HTTP headers, and is never logged in application logs (verified with `caplog` at `DEBUG`).
   - If the database is already initialized (`users` count > 0), zero tokens are minted and nothing is written to stdout.
3. **At-Rest Cryptographic Boundary (`kb_auth` Schema):**
   - Table `setup_claim_tokens` is owned by `kb_auth_owner`, completely revoked from `kanban_app` and `app_rls_reader`, with `ENABLE` and `FORCE ROW LEVEL SECURITY` enforced via policy `kb_auth_owner_all`. Direct access by `kanban_app` raises SQLSTATE `42501`.
   - The token is persisted exclusively as an HMAC-SHA256 digest keyed with `derive_subkey(auth_pepper, "auth/setup_token")`. Neither plaintext nor raw SHA-256 digests are stored.
   - All mutations execute through `SECURITY DEFINER` functions in `kb_auth` (`setup_is_initialized`, `setup_mint_token`, `setup_consume_and_create_admin`) using `SET search_path = pg_catalog, public`.
4. **Concurrency & Atomicity:**
   - Functions acquire transactional advisory locks (`hashtextextended('kb_setup_claim', 0)`) to prevent concurrency races. Exactly one claim request can succeed; concurrent requests receive `401 SETUP_TOKEN_INVALID`.
5. **Constant-Work Timing Equalization:**
   - On malformed token syntax or failed validation paths, the service executes a single Argon2id verification against `DUMMY_HASH` using `verify_password(DUMMY_HASH, "dummy_password_for_timing")`, neutralizing timing and enumeration side channels.
   - All token invalidity scenarios (malformed, non-existent, expired, revoked, already claimed) return byte-identical RFC 7807 problem details: `401 SETUP_TOKEN_INVALID`.
6. **Rate Limiting Guardrail:**
   - `POST /api/v1/setup/claim` is guarded by `rate_limited(SETUP_CLAIM_IP)` (10 requests per 3600 seconds per client IP). Exceeding this quota immediately yields `429 RATE_LIMITED`.
7. **Mandatory AAL2 Second-Factor Enrollment Gate:**
   - After atomic claim, the service provisions the initial `SERVER_ADMIN` account with Argon2id password hash and creates an initial session with `aal_level=1, mfa_pending=True`.
   - The response status is `enrollment_required`. Access to administrative routes remains gated until the administrator completes TOTP or WebAuthn Passkey registration and elevates to AAL2.

---

## 2. Verification Checklist & Test Proofs

| Gate / Requirement | Status | Evidence |
| :--- | :---: | :--- |
| **Unit Test Suite & Coverage** | **PASS** | 22 tests passing in 7.47s; 98.24% test coverage on `kanban.auth.setup` (100%) and `kanban.api.v1.auth_setup` (97%), exceeding `>=95%` requirement. |
| **Database Boundary Tests** | **PASS** | Direct access to `setup_claim_tokens` by `kanban_app` raises `42501`; at-rest token is confirmed peppered HMAC. |
| **Migration Reversibility** | **PASS** | `database/tests/migrations/test_p2_12_migration.py` cleanly verifies upgrade -> downgrade -1 -> upgrade. |
| **ORM / Schema Parity** | **PASS** | `database/tests/test_p1_17_models.py` confirms 1:1 ORM table parity across 48 tables including `SetupClaimToken`. |
| **RLS Catalog Enforcement** | **PASS** | `database/tests/test_p1_14_rls_catalog.py` and `test_p1_14_rls_policies.py` pass cleanly. |
| **Ruff Check & Format** | **PASS** | 846 files scanned; 0 errors, 100% compliant. |
| **Mypy Strict Static Typing** | **PASS** | 384 source files analyzed; 0 errors. |
| **Lint Imports Layering** | **PASS** | Unidirectional layering verified (2 kept, 0 broken). |
| **License Compliance** | **PASS** | `make license` reports python=115, node=1, violations=0 (`Apache-2.0`). |
| **ASCII Hyphen Cleanliness** | **PASS** | `python -m scripts.check_no_dashes --all` exits 0 with zero Unicode dashes. |

---

## 3. Verification Artifact Inventory
All proof artifacts are populated in `docs/qa/KANBA-109/`:
- `git-diff.patch`: Complete cumulative unified diff against main.
- `unit-test-results.txt`: Verbatim pytest execution output with coverage metrics.
- `build-check.txt`: Static suite execution log (ruff, mypy, lint-imports, license, dashes).
- `schema-dump.sql`: Complete DDL and RLS policies for `setup_claim_tokens` and `kb_auth.setup_*`.
- `contract-sample.json`: Representative HTTP requests/responses for uninitialized status, successful claim with cookies, initialized status, invalid token problem, and rate limit exhaustion.
- `message-to-reality-checker.md`: This architecture and audit summary document.
- `api-specialist-review.md`: Independent API Specialist Gate sign-off.
- `ui-specialist-review.md`: Independent UI Specialist Gate sign-off.

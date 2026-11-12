# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-64 (KB-P2-02)

- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-64` on branch `feat/KANBA-64`
- Ticket: `KANBA-64` (`KB-P2-02`: [Phase 2 / Auth] Server-side sessions, HMAC-signed __Host- cookies, rotation, timeouts & CSRF)
- Target File: `docs/qa/KANBA-64/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the server-side session infrastructure, cookie signing protocol, timeout policies, and CSRF protection was conducted in `/tmp/kb-wt-KANBA-64`:

1. **Database Isolation & Security Boundary (DDL & kb_auth functions):**
   - **Table Hardening:** The `sessions` table is strictly owned by `kb_auth_owner`, with all privileges revoked from `PUBLIC`, `kanban_app`, and `app_rls_reader`. Both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are enforced. Direct SQL execution as `kanban_app` raises SQLSTATE `42501` (permission denied).
   - **Cryptographic Hash Storage:** Tokens are generated as 32 cryptographically secure random bytes via `secrets.token_bytes(32)`. The database stores strictly `token_sha256 BYTEA NOT NULL UNIQUE CHECK (octet_length(token_sha256) = 32)`. Even in the event of an unauthorized database dump, no usable session credentials can be recovered.
   - **SECURITY DEFINER Integrity:** All five management functions (`session_create`, `session_resolve`, `session_revoke`, `session_rotate`, `session_revoke_all_for_principal`) are marked `SECURITY DEFINER` with fixed `SET search_path = pg_catalog, public`. Introspection verifies that `session_resolve` strictly returns session metadata without exposing `token_sha256`.
   - **Write Amplification Throttling:** `session_resolve` verifies that `revoked_at IS NULL AND now() < idle_expires_at AND now() < absolute_expires_at`. It updates `last_seen_at` and slides `idle_expires_at` only when `last_seen_at < now() - interval '60 seconds'`. Verified via PostgreSQL triggers that 10 consecutive requests within 30s perform exactly 1 update.

2. **HMAC Cookie Signing & Anti-Forgery Gate:**
   - **Format & Attributes:** Cookies are delivered under the prefix `__Host-kb_session` formatted as `b64url(token) + "." + b64url(HMAC-SHA256(derive_subkey(session_hmac_key, "session/cookie"), token))`. Cookie attributes are strictly `Secure; HttpOnly; SameSite=Lax; Path=/` with no `Domain` attribute, completely mitigating cookie-tossing attacks from sibling subdomains.
   - **Short-Circuit Verification:** `parse_session_cookie` enforces a hard limit of 128 characters, splits on the single dot delimiter, and verifies the HMAC signature using `hmac.compare_digest` BEFORE initiating any database connection. Forged tokens, corrupted signatures, and invalid sizes are rejected at memory speed.
   - **Ambiguity Defense:** `extract_session_cookie` fails closed if duplicate `__Host-kb_session` cookie headers are presented.

3. **Session Lifecycle & Privilege Separation:**
   - **Fixation Defense:** `SessionService.create_after_login` generates a fresh UUIDv7 session ID and token, and explicitly resolves and revokes any pre-login session cookie presented in the request.
   - **Atomic Elevation Rotation:** `SessionService.elevate_aal` invokes `kb_auth.session_rotate` in a single transaction, revoking the previous session ID, linking `rotated_from_id`, setting `aal2_verified_at`, and preserving the original `absolute_expires_at`.
   - **Clean Logout:** `POST /api/v1/auth/logout` calls `session_revoke` and appends two `Set-Cookie` clearing headers (`__Host-kb_session` and `__Host-kb_csrf`) with `Max-Age=0`.

4. **Session-Bound Double-Submit CSRF Middleware:**
   - **Cryptographic Binding:** Tokens are generated as `b64url(nonce16) + "." + b64url(HMAC(derive_subkey(session_hmac_key, "session/csrf"), session_id.bytes + nonce16))`.
   - **Delivery & Validation:** Delivered via `__Host-kb_csrf` (`Path=/; Secure; SameSite=Strict`, non-HttpOnly for client access) and returned in `GET /api/v1/auth/session`.
   - **Strict Method Checking:** Unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) on `/api/*` require header `X-CSRF-Token` to match the cookie and cryptographically validate against the active session ID (or `PRE_SESSION_ID`). Mismatches return RFC 7807 403 `CSRF_REJECTED`.
   - **Defense in Depth:** Verifies `Sec-Fetch-Site` (must be `same-origin` or `none`) and `Origin` against `KANBAN_PUBLIC_ORIGIN`. Safe read methods and explicitly justified endpoints (`CSRF_EXEMPT_PATHS`) bypass validation without compromising state.

5. **MFA Guard Integration:**
   - `require_full_session` inspects `principal.mfa_pending`. When true, any route not explicitly annotated with `allow_mfa_pending=True` immediately returns RFC 7807 403 `MFA_REQUIRED`.

---

### 2. Independent Verification & Test Execution

- **Test Suite Results:** 28 / 28 unit, boundary, and migration tests passed cleanly in 1.06s.
  - `kanban/tests/auth/test_sessions.py`: Cases 1, 2, 5, 6, 9, 10, 12, resolver and policy tests.
  - `kanban/tests/auth/test_cookies.py`: Token generation, roundtrips, forgery rejection, cookie tossing, oversize rejections.
  - `kanban/tests/auth/test_csrf.py`: Case 8 CSRF protections, double-submit validation, metadata checks, exempt paths.
  - `database/tests/test_sessions_boundary.py`: Case 7 throttling trigger, Case 11 RLS 42501 privilege denials, hash non-exposure.
  - `database/tests/migrations/test_p2_02_migration.py`: Reversible migration lifecycle (upgrade head -> downgrade -1 -> upgrade head).
- **Coverage:** **97.95%** combined line and branch coverage across `kanban.auth.sessions` (exceeds the 95% project threshold).
- **Static Quality & Build Checks:**
  - `ruff check .`: 0 errors.
  - `ruff format --check .`: Clean (526 files formatted).
  - `mypy --strict kanban database`: Clean (0 errors across 174 files).
  - `lint-imports`: 2 kept, 0 broken.
  - `make license`: Clean (SUMMARY python=110 node=1 violations=0).
  - `scripts/check_no_dashes.py --all`: Clean (0 non-ASCII dashes repo-wide).

---

### 3. Verdict

The session infrastructure, cryptographic cookie signing, database boundary enforcement, and CSRF defense-in-depth in `/tmp/kb-wt-KANBA-64` satisfy all security, performance, and API requirements for `KB-P2-02`.

APPROVED

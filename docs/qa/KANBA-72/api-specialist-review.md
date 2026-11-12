# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-72 (KB-P2-04)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-72` on branch `feat/KANBA-72`
- Ticket: `KANBA-72` (`KB-P2-04`: `[Phase 2 / Auth] Local Admin card: Argon2id + HMAC-SHA256 pepper login with constant-time miss path and rate limits`)
- Target File: `docs/qa/KANBA-72/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the break-glass Local Admin authentication service, Argon2id hashing engine, HMAC pepper pipeline, constant-work anti-enumeration miss path, and database security boundary was conducted in `/tmp/kb-wt-KANBA-72`:

1. **Database Privilege Boundary & DDL Isolation (`kb_auth` schema):**
   - **Table Hardening:** Table `local_admin_credentials` is strictly owned by `kb_auth_owner`. All privileges are revoked from `PUBLIC`, `kanban_app`, and `app_rls_reader`. Both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are active (`relrowsecurity = t`, `relforcerowsecurity = t`), with policy `kb_auth_owner_all` restricting direct table access exclusively to `kb_auth_owner`.
   - **Integrity Constraints:** Username is validated via regex `^[a-z0-9][a-z0-9._-]{2,62}$`; password hash is validated via `CHECK (password_hash LIKE '$argon2id$%')`.
   - **SECURITY DEFINER Functions:** All credential management functions (`kb_auth.local_get_credential`, `kb_auth.local_set_password_hash`, `kb_auth.local_admin_create`) are owned by `kb_auth_owner`, execute with `SECURITY DEFINER`, and have fixed execution search paths `SET search_path = pg_catalog, public`.
   - **Administrative Creation Gate:** `kb_auth.local_admin_create` strictly requires either `SERVER_ADMIN` role binding with `app.aal_level = '2'` or an active setup-claim context (`app.is_setup_claim = 'true'`), raising SQLSTATE `42501` otherwise.

2. **Cryptographic Hashing & HMAC Pepper Pipeline (`hashing.py`):**
   - **Argon2id Parameters:** Configured with `time_cost=3`, `memory_cost=65536` KiB (64 MiB), `parallelism=4`, `hash_len=32`, `salt_len=16`, and `type=Type.ID`. Generated hash strings match `$argon2id$v=19$m=65536,t=3,p=4$`.
   - **Pepper Normalization:** Password input undergoes `unicodedata.normalize("NFKC", password)` followed by UTF-8 encoding. Length is strictly enforced between 8 and 1024 bytes before cryptographic operations. An HMAC-SHA256 pepper is applied (`hmac.new(auth_pepper, pw_bytes, sha256).digest()`) and base64-encoded prior to Argon2id hashing. An offline database compromise yields hashes that cannot be verified or cracked without `KB_AUTH_PEPPER`.
   - **Transparent Parameter Upgrade:** `needs_rehash` checks whether the stored hash meets current parameter standards. Upon successful login with legacy parameters (e.g. `t=2`), the service rehashes the password with current parameters (`t=3`) and updates the database via `kb_auth.local_set_password_hash`.

3. **Constant-Work Anti-Enumeration Miss Path (`hashing.py`, `service.py`):**
   - **Dummy Hash Verification:** A precomputed `DUMMY_HASH` is generated once at module import with identical Argon2id parameters.
   - **Work Equalization:** On every authentication failure path (unknown user, wrong password, disabled LOCAL_ADMIN card, suspended principal status, or password length out of bounds), the service executes exactly one Argon2id verification (`ph.verify(DUMMY_HASH, _DUMMY_INPUT_FAIL)`).
   - **Timing Side-Channel Verification:** Forensic timing analysis in `enumeration-timing.txt` (50 samples per class) measures unknown-user median latency at 53.33 ms vs wrong-password median latency at 52.99 ms. The median delta of **0.34 ms** easily passes the maximum allowable threshold of `<= 15.00 ms`.
   - **Response Uniformity:** All failure conditions emit identical RFC 7807 `401 INVALID_CREDENTIALS` payloads (`"Invalid username or password"`) with byte-identical bodies (excluding dynamic `request_id`).

4. **Resource Exhaustion Defense & Concurrency Limiting (`hashing.py`):**
   - **Memory Bounding:** Argon2id hashing operations execute in thread workers (`anyio.to_thread.run_sync`) governed by `asyncio.Semaphore(4)`. This strictly bounds server RAM utilization to a maximum of `4 x 64 MiB = 256 MiB`.
   - **Timeout & Backoff:** If a concurrency permit cannot be acquired within 2.0 seconds, the request aborts with RFC 7807 `503 AUTH_BUSY` delivering `Retry-After: 2`.

5. **Rate Limiting & Account Reset (`service.py`):**
   - **Dual-Tier Throttling:** Enforces sliding-window rate limits before credential verification:
     * `AUTH_LOGIN_IP`: 20 attempts per IP across distinct usernames.
     * `AUTH_LOGIN_ACCOUNT`: 5 attempts per normalized username within 900 seconds.
   - **Account Reset:** Successful login resets the `AUTH_LOGIN_ACCOUNT` rate limit bucket.
   - **Header Feedback:** Tripped rate limits emit `429 RATE_LIMITED` accompanied by standard `Retry-After` headers.

6. **Session Issuance & Step-Up MFA Handoff (`auth_local.py`):**
   - **Intermediate Session State:** Successful login invokes `SessionService.create_after_login` with `aal_level=1` and `mfa_pending=True`, reflecting the security requirement that administrative accounts require secondary authentication (S4.2 item 3).
   - **Hardened Cookies:** Delivers `__Host-kb_session` (`HttpOnly; Secure; SameSite=Lax; Path=/`) and `__Host-kb_csrf` (`Secure; SameSite=Strict; Path=/`).
   - **Secret Hygiene:** Verification confirms that passwords and usernames for failed login attempts are never written to server logs, exception messages, or activity ledger rows (`LOCAL_ADMIN_LOGIN_FAILED` records only hashed IP and card ID).

---

### 2. Verification Matrix

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Argon2id Hash Parameters** | `m=65536, t=3, p=4, len=32, salt=16` | Generated hashes match `$argon2id$v=19$m=65536,t=3,p=4$` | PASS |
| **HMAC Pepper Pipeline** | HMAC-SHA256 over NFKC UTF-8 bytes | Verified with `KeyMaterial.auth_pepper`; wrong pepper fails | PASS |
| **Constant-Work Miss Path** | Exactly 1 Argon2 verify on all failures | Spy verification confirms 1 verify for unknown/wrong/disabled/suspended | PASS |
| **Anti-Enumeration Timing** | Median latency delta <= 15.00 ms | Measured median delta **0.34 ms** (53.33 ms vs 52.99 ms in `enumeration-timing.txt`) | PASS |
| **Concurrency Semaphore** | Max 4 workers, 2s acquire timeout | Semaphore bounds RAM to 256 MiB; timeout emits 503 `AUTH_BUSY` (`Retry-After: 2`) | PASS |
| **Rate Limit Protection** | 5/account/900s, 20/IP | 6th attempt yields 429 `RATE_LIMITED`; success resets account bucket | PASS |
| **Database Boundary** | `FORCE RLS` on credentials, `kb_auth_owner` | Table owned by `kb_auth_owner`, revoked from `kanban_app`, `SECURITY DEFINER` | PASS |
| **Step-Up MFA Handoff** | Admin login issues `aal=1, mfa_pending=True` | `LocalLoginResponse` returns `mfa_pending: true`, `aal_level: 1` | PASS |
| **Secret Hygiene** | Zero passwords or failed usernames logged | Audited logs and activity ledger payloads; zero credentials leaked | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 12/12 passed in 10.60s; 100.00% branch+line coverage across `kanban.auth.local` | PASS |
| **Quality & Type Safety** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (604 files), Mypy strict clean (229 files), Lint-imports clean | PASS |
| **Supply Chain & License** | `argon2-cffi==25.1.0` (MIT) | Pinned in `pyproject.toml` and `uv.lock`; license gate clean (violations=0) | PASS |
| **Typography & Formatting** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 3. Forensic Test Suite & Coverage Verification

- **Test Suite Execution:**
  ```text
  kanban/tests/auth/test_local_hashing.py: 1 passed
  kanban/tests/auth/test_local_login.py: 11 passed
  database/tests/migrations/test_p2_04_migration.py: 1 passed
  database/tests/test_p1_17_models.py: 5 passed
  Total: 18 passed in 17.55s
  ```
- **Coverage Breakdown:**
  * `kanban/auth/local/__init__.py`: 100% (3 statements)
  * `kanban/auth/local/hashing.py`: 100% (96 statements, 8 branches)
  * `kanban/auth/local/service.py`: 100% (88 statements, 18 branches)
  * **Combined Coverage:** **100.00%** (exceeds `>=95%` mandatory threshold)

---

### 4. Gate Sign-Off

All technical requirements, cryptographic invariants, and security boundaries defined in `docs/tickets/KB-P2-04.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 4.2 have been rigorously audited and proven. Both UI Specialist Gate (`docs/qa/KANBA-72/ui-specialist-review.md`) and API Specialist Gate reviews are complete and approved.

Verdict: APPROVED

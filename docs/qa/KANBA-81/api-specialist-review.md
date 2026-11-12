# API Specialist Gate Final Audit: APPROVED for KANBA-81 (KB-P2-05a)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-81`
- Branch: `feat/KANBA-81`
- Ticket: `KANBA-81` (`KB-P2-05a`: `[Phase 2 / Auth] RFC 6238 TOTP with replay rejection, hashed one-time recovery codes & mandatory AAL2 for admin roles`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-81` in `/tmp/kb-wt-KANBA-81`. `KB-P2-05a` implements multi-factor authentication (MFA) using pure Python standard library RFC 6238 TOTP, atomic replay prevention, HMAC-SHA256 hashed one-time Crockford Base32 recovery codes, bound envelope secret encryption at rest, and mandatory AAL2 policies for administrative routes. All DDL schemas, security definer functions, rate limits, timing equalizations, and route protections were evaluated against Spec Section 4.2 (item 3), Section 3.3, and Section 5.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Pure Stdlib TOTP** | RFC 6238 HMAC-SHA1, 6 digits, 30s step | Pure Python stdlib (`hmac`, `hashlib`, `struct`, `secrets`); zero external OTP dependencies | PASS |
| **Appendix B Vectors** | 100% RFC 6238 test vector compliance | 6/6 test vectors match expected outputs in `rfc6238-vectors.txt` | PASS |
| **Envelope Secret Encryption**| AES-256-GCM envelope with principal binding | Encrypted at rest via `seal_bound()` using `b"kanban/totp/v1|" + principal_id.bytes` AAD | PASS |
| **Volatile Memory Zeroing** | Ephemeral secret zeroed in memory | Explicit bytearray zeroing in `finally` blocks prevents heap residue | PASS |
| **Strict Replay Rejection** | Step accepted at most once per principal | Monotonic `last_accepted_step` check; atomic conditional DB update; race test passes | PASS |
| **Recovery Codes Hashing** | 10 Crockford Base32 codes stored as HMAC | Stored as HMAC-SHA256 via `derive_subkey(auth_pepper, "mfa/recovery")`; raw codes never stored | PASS |
| **Atomic Code Consumption**| Single-use recovery code consumption | Atomic `kb_auth.recovery_code_consume` marks `used_at`; subsequent use fails with 401 | PASS |
| **AAL2 Policy Enforcement**| Mandatory AAL2 on admin routes | `require_admin_aal2` blocks AAL1 admins (403) and un-enrolled admins (403) | PASS |
| **Route Security Audit** | 100% of admin routes protected | `assert_admin_routes_protected(app)` confirms zero unprotected `/api/v1/admin/*` routes | PASS |
| **Brute-Force Rate Limiting**| Rate limit verify endpoint | `AUTH_MFA_VERIFY` enforces 5 attempts per 300s window; 6th attempt yields 429 | PASS |
| **Database DDL & Boundaries**| Tables owned by `kb_auth_owner` + FORCE RLS | `totp_factors` and `recovery_codes` revoked from `kanban_app`; accessed via `kb_auth` functions | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 23/23 passed in 3.29s; 97.30% branch+line coverage across `kanban/auth/mfa/` | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (618 files), Mypy strict clean (239 files) | PASS |

---

### 2. Forensic Architectural Analysis

1. **RFC 6238 TOTP Engine & Secret Hygiene:**
   - Implemented in `kanban/auth/mfa/totp.py` using strictly Python standard library modules (`hmac`, `hashlib`, `struct`, `secrets`, `base64`, `time`). Zero third-party OTP packages (`pyotp`, `onetimepass`, etc.) were introduced, preserving our strict supply-chain dependency envelope.
   - Validates code structure prior to HMAC calculation: code must be exactly 6 ASCII digits (`^[0-9]{6}$`). Non-ASCII or malformed input immediately returns `(False, 0)` without executing expensive cryptographic operations, neutralizing malformed input timing attacks.
   - Code comparison uses `hmac.compare_digest` over zero-padded 6-digit strings.
   - **Secret Protection:** Secrets are generated with `secrets.token_bytes(20)` (160 bits entropy) and encrypted using AES-256-GCM via `seal_bound()` with authenticated data `b"kanban/totp/v1|" + principal_id.bytes`. Corrupted blobs or mismatched principal IDs fail closed with `EnvelopeDecryptError`. Decrypted secrets in memory are held in mutable `bytearray` buffers and actively zeroed in `finally` clauses.

2. **Atomic Replay Prevention & Race Safety:**
   - In `verify_totp()`, verification accepts steps in the window `[current_step - 1, current_step + 1]`, but strictly requires `step > last_accepted_step`.
   - Advancing the step is executed via `kb_auth.totp_update_step(:p_factor_id, :p_step)` which performs:
     ```sql
     UPDATE totp_factors
     SET last_accepted_step = p_step, updated_at = clock_timestamp()
     WHERE id = p_factor_id AND last_accepted_step < p_step AND status = 'ACTIVE';
     ```
   - In concurrent race conditions (`test_case_4_concurrency_race`), 10 parallel verification requests using the exact same code yield exactly 1 success; the remaining 9 fail with `401 MFA_INVALID`.

3. **Crockford Base32 Recovery Codes Service:**
   - In `kanban/auth/mfa/recovery.py`, generates 10 backup codes formatted as `XXXXX-XXXXX` (10 characters, 50 bits of entropy) from Crockford's Base32 alphabet.
   - Normalization converts lookalike characters (`O/o -> 0`, `I/i/L/l -> 1`) and strips hyphens and whitespace.
   - **Cryptographic Storage:** Raw codes are never stored. The system derives a dedicated subkey `derive_subkey(auth_pepper, "mfa/recovery")` and stores only the `HMAC-SHA256` digest in `recovery_codes.code_hmac`.
   - Single-use consumption is enforced by `kb_auth.recovery_code_consume`, which atomically sets `used_at = clock_timestamp()` where `used_at IS NULL`. Re-submitting a consumed code returns -1, causing the verify endpoint to emit RFC 7807 `401 MFA_INVALID`.

4. **AAL2 Session Policy & Route Boundary Auditing:**
   - `require_aal2(max_age_seconds: int | None = None)` in `kanban/auth/mfa/policy.py` checks `principal.aal_level >= 2`. Sessions at AAL1 receive RFC 7807 `403 AAL2_REQUIRED`. If `max_age_seconds` is configured and `now - aal2_verified_at > max_age_seconds`, the policy raises `403 AAL2_STALE`.
   - `require_admin_aal2` enforces:
     * Callers with `SERVER_ADMIN` or `PROJECT_ADMIN` who have not enrolled and confirmed a factor receive `403 MFA_ENROLLMENT_REQUIRED`.
     * Enrolled administrators operating with AAL1 sessions receive `403 AAL2_REQUIRED`.
   - The route auditor `assert_admin_routes_protected(app)` inspects all registered FastAPI route handlers beginning with `/api/v1/admin` to guarantee that `require_admin_aal2` is declared in the dependency tree.

5. **Database Boundary & Security Definer Schema:**
   - Migration `p2_05a_mfa_totp_recovery` establishes `totp_factors` and `recovery_codes` under table owner `kb_auth_owner`. Permissions are explicitly revoked from `kanban_app`.
   - Both tables have `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - Data access is mediated entirely through 9 `SECURITY DEFINER` functions in schema `kb_auth` (`totp_enroll`, `totp_confirm`, `totp_verify`, `totp_get_pending`, `totp_get_active`, `totp_update_step`, `totp_delete`, `recovery_codes_replace`, `recovery_code_consume`, `mfa_status`).

6. **Endpoints & Rate Limiting:**
   - Mounted in `kanban/api/v1/auth_mfa.py` under `/api/v1/auth/mfa`:
     * `POST /totp/enroll`: Returns `otpauth_uri` and secret Base32 string once.
     * `POST /totp/confirm`: Validates pending factor and marks it `ACTIVE`. Pending factors older than 600s are rejected.
     * `DELETE /totp`: Revokes factor.
     * `POST /verify`: Accepts TOTP or recovery code; upgrades session to `aal_level = 2`, rotates session ID, and issues new CSRF token. Rate-limited by `AUTH_MFA_VERIFY` (5 attempts / 300s window).
     * `POST /recovery/regenerate`: Requires active AAL2; invalidates all old recovery codes and returns 10 new codes.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-81`. All RFC 6238 invariants, replay rejections, envelope encryption controls, recovery code hashing, and administrative AAL2 policies are satisfied.

Verdict: APPROVED
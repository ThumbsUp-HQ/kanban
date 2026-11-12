# Reality-Checker Verification Packet: KANBA-81 (KB-P2-05a)

## Ticket Overview
- **Ticket ID**: `KANBA-81`
- **Spec Section**: `KB-P2-05a` (S4.2 item 4, S2.2 item 2, S2.5, S3.4)
- **Title**: `[Phase 2 / Auth] RFC 6238 TOTP with replay rejection, hashed one-time recovery codes & mandatory AAL2 for admin roles`
- **Wave**: `W15`
- **Git Branch**: `feat/KANBA-81` in isolated worktree `/tmp/kb-wt-KANBA-81`

---

## Technical Actions & File Manifest

1. **Database Migration & DDL**:
   - `database/migrations/versions/p2_05a_mfa_totp_recovery.py` (`down_revision = "p2_04_local_admin_credentials"`)
   - `database/migrations/sql/p2_05a_mfa_totp_recovery.up.sql`
   - `database/migrations/sql/p2_05a_mfa_totp_recovery.down.sql`
   - Tables `totp_factors` and `recovery_codes` created under schema `public`, owned by `kb_auth_owner`, revoked from `PUBLIC, kanban_app, app_rls_reader`, with `ENABLE` and `FORCE ROW LEVEL SECURITY`, and policy `kb_auth_owner_all`.
   - 9 Security Definer functions in `kb_auth`:
     * `kb_auth.totp_enroll(p_principal_id, p_encrypted_blob, p_wrapped_dek, p_dek_kid)`
     * `kb_auth.totp_get_pending(p_principal_id)` (filtered to factors < 600s old)
     * `kb_auth.totp_confirm(p_factor_id, p_step)` (atomic step transition to ACTIVE)
     * `kb_auth.totp_get_active(p_principal_id)`
     * `kb_auth.totp_update_step(p_factor_id, p_step)` (atomic replay-safe step advance)
     * `kb_auth.totp_delete(p_principal_id)`
     * `kb_auth.recovery_codes_replace(p_principal_id, p_hmacs)`
     * `kb_auth.recovery_code_consume(p_principal_id, p_hmac)` (atomic single-use consumption)
     * `kb_auth.mfa_status(p_principal_id)` (returns has_active_totp and unused_recovery_codes)
   - Models `TotpFactor` and `RecoveryCode` mapped in `database/models/auth.py` and exported in `database/models/__init__.py`. Table count in `database/tests/test_p1_17_models.py` updated to 41 tables (`len(orm_tables) == 41`). `database/GEMINI.md` manifest updated.

2. **Core MFA Services & Policy**:
   - `kanban/auth/mfa/totp.py`:
     * Stdlib RFC 6238 TOTP implementation using `hmac`, `hashlib`, `struct`, `secrets`, `base64` (strictly zero external OTP packages).
     * Parameters: `HMAC-SHA1`, `6` digits, `30s` step, `T0 = 0`, acceptance window `step - 1 .. step + 1`.
     * Strict format validation `^[0-9]{6}$` before any HMAC computation.
     * Constant-time verification with `hmac.compare_digest`.
     * Envelope encryption with `b"kanban/totp/v1|" + principal_id.bytes` bound AAD.
     * Volatile memory sanitization: bytearray secret wiped to zero in finally blocks.
   - `kanban/auth/mfa/recovery.py`:
     * 10 Crockford Base32 codes (`XXXXX-XXXXX`, 50 bits of entropy).
     * Normalization handles uppercase conversion and lookalike substitutions (`O`/`o` -> `0`, `I`/`i`/`L`/`l` -> `1`).
     * Codes stored only as `HMAC-SHA256(derive_subkey(auth_pepper, "mfa/recovery"), normalized_code)`.
     * Single-use atomic consumption via `kb_auth.recovery_code_consume`.
   - `kanban/auth/mfa/policy.py`:
     * `require_aal2(max_age_seconds: int | None = None)` dependency enforcing `aal_level >= 2` (403 `AAL2_REQUIRED`) and staleness checking (403 `AAL2_STALE`).
     * `require_admin_aal2` dependency protecting all `/api/v1/admin/*` endpoints: un-enrolled admin returns 403 `MFA_ENROLLMENT_REQUIRED`; enrolled admin with AAL1 session returns 403 `AAL2_REQUIRED`.
     * `assert_admin_routes_protected(app)` audit utility verifying zero unprotected `/api/v1/admin/*` routes exist.
   - `kanban/security/envelope.py`: Added bound envelope helpers `seal_bound(plaintext, aad, kek, kid)` and `open_bound(sealed, aad, kek)`.
   - `kanban/services/activity.py`: Added `MFA_VERIFIED`, `MFA_FAILED`, `RECOVERY_CODE_USED`, `RECOVERY_CODES_REGENERATED` activity events.
   - `kanban/api/v1/auth_mfa.py`: Mounted 5 routes:
     * `POST /api/v1/auth/mfa/totp/enroll`
     * `POST /api/v1/auth/mfa/totp/confirm`
     * `DELETE /api/v1/auth/mfa/totp`
     * `POST /api/v1/auth/mfa/verify` (rate limited by `AUTH_MFA_VERIFY`, 5 / 300s)
     * `POST /api/v1/auth/mfa/recovery/regenerate` (requires AAL2)

---

## Verification & Quality Metrics

1. **Unit Test Suite & Coverage**:
   - Test files: `kanban/tests/auth/test_totp.py`, `kanban/tests/auth/test_recovery_codes.py`, `kanban/tests/auth/test_aal2_policy.py`, `database/tests/migrations/test_p2_05a_migration.py`, `database/tests/test_p1_17_models.py`.
   - Results: **23/23 tests passed** in 3.29s.
   - Combined coverage across `kanban/auth/mfa/`: **97.30% branch + line** (exceeding the >= 95% mandate).
     * `kanban/auth/mfa/__init__.py`: 100%
     * `kanban/auth/mfa/policy.py`: 98%
     * `kanban/auth/mfa/recovery.py`: 96%
     * `kanban/auth/mfa/totp.py`: 97%
   - Migration lifecycle: Reversible test passed (upgrade -> downgrade -1 -> upgrade).
   - Database schema & RLS parity: 41 ORM models verified 1:1 against `pg_tables` in `test_p1_17_models.py`, and `test_06_rls_catalog_gate` passed.

2. **Zero New Third-Party Dependencies**:
   - `pyproject.toml` and `uv.lock` are 100% untouched.
   - Stdlib only (`hmac`, `hashlib`, `struct`, `secrets`, `base64`) used for TOTP; zero `pyotp` or `onetimepass`.
   - `make license`: `SUMMARY python=110 node=1 violations=0`.

3. **Build & Static Integrity**:
   - `ruff check .`: Clean (0 errors).
   - `ruff format --check .`: Clean (618 files already formatted).
   - `mypy --strict kanban database`: Clean (0 errors across 239 source files).
   - `lint-imports`: 2 contracts kept, 0 broken.
   - `check_no_dashes --all`: Clean (0 non-ASCII dashes repo-wide).

4. **Proof Artifacts**:
   - `docs/qa/KANBA-81/git-diff.patch`
   - `docs/qa/KANBA-81/unit-test-results.txt`
   - `docs/qa/KANBA-81/build-check.txt`
   - `docs/qa/KANBA-81/schema-dump.sql`
   - `docs/qa/KANBA-81/rfc6238-vectors.txt`
   - `docs/qa/KANBA-81/contract-sample.json`
   - `docs/qa/KANBA-81/message-to-reality-checker.md`

---
id: KB-P2-05a
title: "[Phase 2 / Auth] RFC 6238 TOTP with replay rejection, hashed one-time recovery codes & mandatory AAL2 for admin roles"
epic: KB-E2
depends_on: [KB-P2-04]
spec_sections: ["4.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P2-05` is split into `KB-P2-05a` (TOTP, recovery codes, AAL2 policy) and `KB-P2-05b` (WebAuthn/Passkeys). Tickets that depended on `KB-P2-05` for AAL2 depend on `KB-P2-05a`.

### User Story
As a **server or project administrator**, I need **a second factor (RFC 6238 TOTP or recovery code) that upgrades my session to AAL2, with each TOTP step and each recovery code accepted at most once, and with every admin-role route refusing AAL1 sessions** so that **a phished or stuffed password alone can never exercise admin capability, and an intercepted OTP cannot be replayed**.

**Requirement Traceability:** `S4.2` item 3 (TOTP `AAL2` for Admin roles, offline one-time recovery codes), `S3.3` (`app.aal_level`), requirement `#6` | **Dependencies:** `KB-P2-04` (Local Admin login producing `mfa_pending` sessions; transitively `KB-P2-02`, `KB-P2-03`, `KB-P2-18`)

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/<rev>_mfa_totp_recovery.py`, `database/models/auth.py` (add `TotpFactor`, `RecoveryCode`)
   - `kanban/auth/mfa/__init__.py`, `kanban/auth/mfa/totp.py`, `kanban/auth/mfa/recovery.py`, `kanban/auth/mfa/policy.py`
   - `kanban/api/v1/auth_mfa.py`
2. **TOTP (`totp.py`), stdlib only (`hmac`, `hashlib`, `struct`, `secrets`), no third-party OTP package:**
   - RFC 6238 parameters: `HMAC-SHA1`, `6` digits, `30s` step, `T0 = 0`; acceptance window `step - 1 .. step + 1`.
   - Secret `secrets.token_bytes(20)` (160 bit), stored sealed with the KB-P2-03 envelope (`seal_card_secret` style AAD replaced by `b"kanban/totp/v1|" + principal_id.bytes`; add `seal_bound(aad: bytes, ...)` helper to `envelope.py` if not present).
   - Replay: table column `last_accepted_step BIGINT`; verification passes only if matched step `> last_accepted_step`; update performed with `UPDATE ... WHERE last_accepted_step < $step` and row-count check (atomic, race-safe).
   - Comparison via `hmac.compare_digest` over zero-padded strings; input must match `^[0-9]{6}$`.
   - Enrollment: `POST /api/v1/auth/mfa/totp/enroll` (requires full or `mfa_pending` session) returns `otpauth://totp/Kanban:<username>?secret=<b32>&issuer=Kanban&algorithm=SHA1&digits=6&period=30` exactly once; factor is `PENDING` until `POST /api/v1/auth/mfa/totp/confirm {code}` succeeds; a `PENDING` factor older than `600s` is discarded.
3. **Recovery codes (`recovery.py`):** `10` codes, each `10` chars from Crockford base32 (50 bits), displayed grouped `XXXXX-XXXXX`, returned once by `POST /api/v1/auth/mfa/recovery/regenerate` (requires AAL2, invalidates all prior codes). Stored as `HMAC-SHA256(derive_subkey(auth_pepper, "mfa/recovery"), normalized_code)`; consumption via atomic `UPDATE ... SET used_at = now() WHERE code_hmac = $1 AND used_at IS NULL` row-count `1`.
4. **Verify endpoint:** `POST /api/v1/auth/mfa/verify {method: "totp"|"recovery", code}` allowed for `mfa_pending` sessions; rate limited by `AUTH_MFA_VERIFY` (5 / 300s per principal); success calls `SessionService.elevate_aal(session, 2)` (rotates session id, clears `mfa_pending`); failure -> `401 MFA_INVALID` (same body for wrong, replayed, expired-window, or used code). Activity events `MFA_VERIFIED`, `MFA_FAILED`, `RECOVERY_CODE_USED` (remaining count), `RECOVERY_CODES_REGENERATED`.
5. **AAL2 policy (`policy.py`):**
   - `require_aal2(max_age_seconds: int | None = None)` dependency: `aal_level < 2` -> `403 AAL2_REQUIRED`; when `max_age_seconds` is set and `now - aal2_verified_at > max_age_seconds` -> `403 AAL2_STALE`.
   - `require_admin_aal2` dependency used by every `/api/v1/admin/*` route: principal with role `SERVER_ADMIN` or `PROJECT_ADMIN` (KB-P1-13 role bindings) and no enrolled confirmed factor -> `403 MFA_ENROLLMENT_REQUIRED`; with factor but AAL1 -> `403 AAL2_REQUIRED`.
   - `assert_admin_routes_protected(app)` utility walks the route table and returns admin routes lacking `require_admin_aal2`; a test asserts the returned list is empty (prevents future regressions).
6. **Security invariants asserted:** (a) each TOTP step accepted at most once per principal, including under concurrency; (b) each recovery code usable once; (c) no admin route executes for an AAL1 session; (d) TOTP secret never leaves the server after enrollment and is encrypted at rest.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/auth/test_totp.py`, `kanban/tests/auth/test_recovery_codes.py`, `kanban/tests/auth/test_aal2_policy.py`
- **Required Test Cases:**
  1. RFC 6238 Appendix B vectors (SHA1 seed `12345678901234567890`, times `59`, `1111111109`, `1111111111`, `1234567890`, `2000000000`, `20000000000`) truncated to 6 digits match.
  2. Positive: enroll -> confirm -> logout -> local login -> verify TOTP -> session id rotated, `aal_level=2`, `mfa_pending=FALSE`.
  3. Security (replay): same code submitted twice within its 30s step -> second `401 MFA_INVALID`; code for step `s-1` after step `s` accepted -> `401`.
  4. Security (race, `@pytest.mark.committed_db`): 10 concurrent verifies with the same valid code -> exactly 1 success.
  5. Boundary (window): codes for `s-1`, `s`, `s+1` accept (fresh factor each); `s-2`, `s+2` reject.
  6. Security (format): `"12345"`, `"1234567"`, `"12 3456"`, `"١٢٣٤٥٦"` (Arabic-Indic digits) -> `401` without HMAC computation.
  7. Security (brute force): 6th verify in 300s -> `429 RATE_LIMITED`.
  8. Recovery: code consumed once; second use `401`; regenerate invalidates all 10 old codes; codes stored only as HMAC (raw code absent from DB dump).
  9. AAL2 policy: AAL1 admin on admin test route -> `403 AAL2_REQUIRED`; admin without factor -> `403 MFA_ENROLLMENT_REQUIRED`; `require_aal2(max_age_seconds=900)` at `901s` -> `403 AAL2_STALE`.
  10. Route audit: `assert_admin_routes_protected(app)` returns `[]`; registering an unprotected `/api/v1/admin/x` test route makes it return that path.
  11. Secret hygiene: TOTP secret absent from every response after enrollment, from caplog, and stored only as envelope blob (bit-flip on blob -> verify fails closed with `401`, logged `ERROR` without secret).
  12. Pending expiry: unconfirmed factor older than 600s cannot be confirmed.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** files above exist and define `totp_at`, `verify_totp`, `TotpFactor`, `RecoveryCode`, `generate_recovery_codes`, `consume_recovery_code`, `require_aal2`, `require_admin_aal2`, `assert_admin_routes_protected`, and routes `/api/v1/auth/mfa/totp/enroll`, `/api/v1/auth/mfa/totp/confirm`, `/api/v1/auth/mfa/verify`, `/api/v1/auth/mfa/recovery/regenerate`.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/auth/test_totp.py kanban/tests/auth/test_recovery_codes.py kanban/tests/auth/test_aal2_policy.py -q --cov=kanban/auth/mfa --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 12 cases.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban database && uv run lint-imports` exits `0`.
- [ ] **No OTP package added:** `git-diff.patch` shows no new `pyotp`/`onetimepass` dependency.
- [ ] **Forensic Proof Packet Complete:** all files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - TOTP and recovery tables, grants, `kb_auth` functions.
5. `docs/qa/<TICKET_ID>/rfc6238-vectors.txt` - raw test output for the Appendix B vectors.
6. `docs/qa/<TICKET_ID>/contract-sample.json` - enroll (secret redacted to `<REDACTED>` in the sample only), verify success, `MFA_INVALID`, `AAL2_REQUIRED`, `MFA_ENROLLMENT_REQUIRED`.
7. `docs/qa/<TICKET_ID>/api-specialist-review.md`
8. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - confirms the enrollment/verify/recovery flows have distinct UI states for each problem code.
9. Screenshots: N/A - Non-UI Ticket.

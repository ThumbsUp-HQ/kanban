# Message to Reality-Checker: KANBA-97 (KB-P2-05b)

## Overview & Executive Summary

- **Ticket**: `KANBA-97` (`KB-P2-05b`: WebAuthn / Passkeys registration & assertion (`userVerification=required`) as AAL2 factor)
- **Worktree**: `/tmp/kb-wt-KANBA-97`
- **Branch**: `feat/KANBA-97`
- **Target Module**: `kanban/auth/mfa/webauthn.py`, `kanban/api/v1/auth_webauthn.py`, `database/migrations/versions/p2_05b_webauthn_credentials.py`

This implementation delivers enterprise-grade FIDO2 / WebAuthn Level 3 registration and assertion ceremonies for administrative AAL2 step-up authentication. The system enforces strict origin/RP ID binding, server-side atomic single-use challenges bound to the active session, mandatory user verification (`userVerification = REQUIRED`), monotonic signature counter clone detection with automated security event recording, and tamper-resistant credential deletion guarding administrator last-factor lockouts.

---

## Mandates, Invariants & Design Decisions

### 1. Mandatory User Branding Mandate (#199)
- **Specification vs Mandate**: The ticket prose in `KB-P2-05b.md` suggested `rp_name="Kanban"`. Per Swarm Board Directive #199, all platform user-facing branding must use `👍kanban`.
- **Implementation**: WebAuthn Relying Party name is configured with default `webauthn_rp_name = "👍kanban"` in `kanban/settings.py` (accessible via `Settings.webauthn_rp_name`), while maintaining `webauthn_rp_id` as a strictly valid ASCII domain derived from `PUBLIC_BASE_URL` or explicit environment configuration.

### 2. DDL & PostgreSQL Row-Level Security
- Migration: `database/migrations/versions/p2_05b_webauthn_credentials.py` (`down_revision = "p2_05a_mfa_totp_recovery"`).
- Tables:
  - `webauthn_credentials`: Primary credential storage with length bounds (`CHECK (octet_length(credential_id) BETWEEN 16 AND 1023)`), public key bytes, signature counter, optional AAGUID, transports array, nickname length constraints (`<= 64`), and clone detection timestamp.
  - `webauthn_challenges`: Challenge storage bound to `session_id` and purpose (`register` vs `authenticate`) with 32-byte exact length constraint (`CHECK (octet_length(challenge) = 32)`).
- Hardening:
  - Both tables are owned by `kb_auth_owner`.
  - Permissions are strictly revoked: `REVOKE ALL ON webauthn_credentials FROM PUBLIC, kanban_app, app_rls_reader`.
  - `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are enforced.
  - Policy: `CREATE POLICY kb_auth_owner_all ... FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true)`.
  - All operations are gated through 10 `SECURITY DEFINER` functions in `kb_auth` schema with `SET search_path = pg_catalog, public`.

### 3. Clone Detection & Transaction Isolation
- The signature counter regression check detects cloned authenticators whenever `new_sign_count <= stored_sign_count` (for authenticators supporting non-zero counters).
- Upon clone detection, the credential is immediately stamped with `suspect_clone_at`, a security activity record `WEBAUTHN_SIGN_COUNT_REGRESSION` is appended to the audit log, and the transaction commits successfully before throwing `401 MFA_INVALID` to the client.

### 4. Zero Information Leakage & Timing Defense
- Verification errors (malformed payloads, signature mismatches, expired challenges, origin mismatches) are uniformly logged at `INFO` without sensitive client data and return generic `401 MFA_INVALID`.
- Delete credential verifies admin last factor constraint: administrators attempting to delete their sole remaining AAL2 factor receive `409 LAST_FACTOR`. Stale AAL2 sessions (>900s) receive `403 AAL2_STALE`.

---

## Test Verification & Coverage

1. **Mandatory Test Cases (All 11 Pass)**:
   - Case 1 (Positive registration & assertion -> AAL2 + session rotation): PASSED
   - Case 2 (Security - phishing origin rejection): PASSED
   - Case 3 (Security - RP ID hash mismatch): PASSED
   - Case 4 (Security - UV missing UP=1 UV=0): PASSED
   - Case 5 (Security - challenge replay, expiration >300s, cross-session reuse): PASSED
   - Case 6 (Security - credential substitution across principals): PASSED
   - Case 7 (Security - clone detection sign-count regression & 0/0 acceptance): PASSED
   - Case 8 (Security - type confusion between create and get): PASSED
   - Case 9 (Boundary - 11th credential limit 409 & nickname length 65 chars 422): PASSED
   - Case 10 (Deletion - admin last factor 409 & stale AAL2 901s 403): PASSED
   - Case 11 (Configuration - RP ID mismatch with origin host & http:// cleartext validation): PASSED

2. **Automated Test Results**:
   - Total tests executed: 21 passed (15 in `test_webauthn.py`, 1 in `test_p2_05b_migration.py`, 5 in `test_p1_17_models.py`).
   - Line and branch coverage:
     - `kanban/api/v1/auth_webauthn.py`: 100% (212/212 statements, 58/58 branches)
     - `kanban/auth/mfa/webauthn.py`: 93% (189 statements, 44 branches)
     - Total combined coverage: **96.82%** (exceeds the 95% threshold)

3. **Coverage Invocation Note**:
   - In pytest-cov, when measuring coverage on modules imported during application setup, the module notation `--cov=kanban.auth.mfa.webauthn --cov=kanban.api.v1.auth_webauthn` is required to ensure coverage hooks attach prior to module initialization. Both syntax formats measure identical files.

---

## Verification Artifacts in `docs/qa/KANBA-97/`

- `git-diff.patch`: Complete git diff against base.
- `unit-test-results.txt`: Verbatim test execution and coverage output.
- `build-check.txt`: Verbatim execution logs for ruff check, ruff format --check, mypy --strict, lint-imports, make license, and check_no_dashes.
- `schema-dump.sql`: Complete DDL and security definer function definitions.
- `contract-sample.json`: Wire samples for registration/auth options, registration/auth verify, and 401 MFA_INVALID error responses.
- `dependency-evaluation.md`: Supply chain audit for `webauthn==3.0.1` and transitive dependencies.
- `api-specialist-review.md`: Independent audit by `@arch-reviewer`.
- `ui-specialist-review.md`: Independent audit by `@ui-specialist`.

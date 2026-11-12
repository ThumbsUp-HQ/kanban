# API Specialist Gate Review: KANBA-97 (KB-P2-05b)

- **Ticket**: `KANBA-97` (`KB-P2-05b`: WebAuthn / Passkeys registration & assertion (userVerification=required) as AAL2 factor)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-97` (`HEAD: 9ba604e`)
- **Worktree**: `/tmp/kb-wt-KANBA-97`
- **Scope**: `database/migrations/versions/p2_05b_webauthn_credentials.py`, `kanban/auth/mfa/webauthn.py`, `kanban/api/v1/auth_webauthn.py`, `database/models/auth.py`

---

### 1. Architectural & Security Evaluation

#### A. Registration, Assertion & Challenge Binding (S4.2 / S2.5)
- Implementation adheres to W3C WebAuthn Level 3 specifications via `py_webauthn` (permissively licensed under BSD-3, verified compatible with Apache-2.0).
- Single-use 32-byte cryptographic challenges (`secrets.token_bytes(32)`) are stored in `kb_auth.webauthn_challenges` bound to the caller's active `session_id` with a strict 300s TTL (`expires_at`).
- Verification immediately consumes the challenge atomically in the database (`consumed_at = clock_timestamp()`), preventing challenge replay attacks across concurrent or subsequent requests.
- `userVerification = REQUIRED` is strictly enforced on both registration (`generate_registration_options`) and assertion (`verify_authentication_response`). Assertions with User Verified (UV=0) flag are immediately rejected.
- Registration enforces a per-principal credential ceiling of 10 (`409 CREDENTIAL_LIMIT`) and caps nicknames at 64 characters (`422`).

#### B. Anti-Phishing & Origin / RP ID Invariants
- `expected_origin` strictly validates against `KANBAN_PUBLIC_ORIGIN` (`https://...` or standalone loopback). Presentation of mismatched origins (e.g. `https://kanban.example.evil`) is rejected with uniform HTTP 401 `MFA_INVALID`.
- `expected_rp_id` validates against `KANBAN_WEBAUTHN_RP_ID`. Startup checks guarantee that the RP ID is a valid suffix of the public origin host.
- User Branding Mandate #199 is respected: WebAuthn Relying Party name defaults to `webauthn_rp_name = "👍kanban"` for user-facing browser dialogs while keeping `rp_id` strictly ASCII domain.

#### C. Sign-Counter Clone Detection & Audit Trail
- For authenticators supporting sign counters (`new_sign_count != 0 or stored_sign_count != 0`), any non-increasing counter (`new_sign_count <= stored_sign_count`) triggers clone detection.
- Detected clones immediately reject authentication with HTTP 401 `MFA_INVALID`, stamp `suspect_clone_at = clock_timestamp()` on the credential record, and record a `WEBAUTHN_SIGN_COUNT_REGRESSION` audit event in the activity ledger. Authenticators operating with constant 0/0 counters remain supported.

#### D. Session Elevation & Last-Factor Guard
- Successful assertion invokes `SessionService.elevate_aal(session, 2)`, rotating the session identifier, generating fresh CSRF tokens, and emitting secure `__Host-` cookies.
- Credential registration requires an existing AAL2 session, or an `mfa_pending` session for initial factor enrollment.
- Credential deletion (`DELETE /api/v1/auth/webauthn/credentials/{id}`) enforces `require_aal2(max_age_seconds=900)`. Stale AAL2 sessions return HTTP 403 `AAL2_STALE`.
- Last-factor guard: attempting to delete the final AAL2 factor of an administrator principal is blocked with HTTP 409 `LAST_FACTOR`.

#### E. Rate Limiting & Error Sanitization (Hostile Wire S4.1)
- Both `/register/verify` and `/authenticate/verify` enforce the `AUTH_MFA_VERIFY` sliding-window rate limit policy (returning HTTP 429 with `Retry-After` header when exceeded).
- All cryptographic and protocol verification failures map uniformly to HTTP 401 `MFA_INVALID`. Internal library exception details are logged securely server-side at `INFO` level without reflecting raw client data to the caller.

#### F. Database Boundary & RLS Enforcement
- Storage resides behind the `kb_auth` schema boundary. Tables `webauthn_credentials` and `webauthn_challenges` have all privileges revoked from `PUBLIC`, `kanban_app`, and `app_rls_reader`.
- Access is mediated exclusively through 10 `SECURITY DEFINER` stored procedures in `kb_auth`, ensuring application code cannot perform unauthenticated reads or arbitrary writes to passkey key material.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 15/15 pytest passed in 4.38s across `test_webauthn.py`, covering all 11 mandatory test scenarios (positive flow, phishing origin, invalid RP ID, UV missing, challenge replay, credential substitution, clone detection, type confusion, credential limits, deletion guards, and configuration validation).
- **Coverage**: 96.82% branch+line across touched modules:
  - `kanban/api/v1/auth_webauthn.py`: 100%
  - `kanban/auth/mfa/webauthn.py`: 93%
- **Static Analysis**: Ruff check clean, Ruff format clean (630 files), Mypy strict clean (246 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Proof Bundle**: Complete forensic proof bundle (`git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `schema-dump.sql`, `contract-sample.json`, `dependency-evaluation.md`, `ui-specialist-review.md`).

---

### 3. Gate Verdict

The WebAuthn / Passkeys authentication subsystem complies with all architectural, security, anti-phishing, cryptographic, and quality invariants.

**VERDICT: APPROVED**

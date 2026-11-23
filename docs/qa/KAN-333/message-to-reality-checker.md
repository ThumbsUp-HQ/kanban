# Message to Reality-Checker: KAN-333 (`[KB-REDTEAM-02]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-333` - `[KB-REDTEAM-02] Deny TOTP Factor Overwrite and Factor Re-Enrollment for Active MFA Accounts from MFA-Pending Sessions`
- **Branch:** `feat/KAN-329-336`
- **Browser Screenshots:** `N/A - Non-UI Security Ticket` (Authentication, MFA Domain Logic, and Security Gating)
- **Owned Slice Modified:**
  - `kanban/api/v1/auth_mfa.py`
  - `kanban/auth/mfa/totp.py`
  - `kanban/tests/security/test_totp_re_enrollment_protection.py`
  - `docs/qa/KAN-333/*`

## Requirement-to-Evidence Mapping

1. **Deny TOTP Overwrite for Active MFA from AAL1 Sessions:**
   - **Implementation:** Added active factor check in `kanban/auth/mfa/totp.py` (`has_active_factor`) and enforced in `kanban/api/v1/auth_mfa.py` (`enroll_totp`). AAL1 callers attempting to re-enroll an active account are denied with HTTP 403 Forbidden (`AAL2_REQUIRED`).
   - **Evidence:** `docs/qa/KAN-333/git-diff.patch` and `test_aal1_session_cannot_re_enroll_totp_when_mfa_active` in `kanban/tests/security/test_totp_re_enrollment_protection.py`.

2. **Allow AAL2 Factor Management:**
   - **Implementation:** Users with validated AAL2 sessions can replace or re-enroll factors as expected.
   - **Evidence:** `test_aal2_session_can_re_enroll_totp_when_mfa_active` in `kanban/tests/security/test_totp_re_enrollment_protection.py`.

3. **Allow First-Time Enrollment for New Users:**
   - **Implementation:** Initial enrollment without an active factor remains permitted for AAL1 sessions.
   - **Evidence:** `test_first_time_totp_enrollment_allowed_with_aal1` and all 10 tests passing in `kanban/tests/auth/test_totp.py`.

4. **Mandatory Quality & Code Hygiene:**
   - Zero em-dashes or en-dashes (`uv run python -m scripts.check_no_dashes --all` exits 0).
   - Full static validation passed (`make check` exits 0).
   - Test suite coverage: 96% line+branch coverage on `kanban/auth/mfa/totp.py`.

All artifacts and checksums are verified in `docs/qa/KAN-333/changed-files-manifest.txt`.

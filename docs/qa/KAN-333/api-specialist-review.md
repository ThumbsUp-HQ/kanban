# API Specialist Forensic QA Review: KAN-333

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-333 ([KB-REDTEAM-02] Deny TOTP Factor Overwrite and Factor Re-Enrollment for Active MFA Accounts from MFA-Pending Sessions)
Branch: feat/KAN-329-336
Review Date: 2026-11-23

## 1. Architectural and Security Assessment

### 1.1 Threat Model & Vulnerability Analysis
Multi-Factor Authentication (MFA) step-up protection ensures that a compromised primary credential (AAL1 session: password or single-factor OAuth) cannot hijack an account.
Prior to this remediation:
- If a user had already enrolled and activated TOTP (or WebAuthn), an attacker who stole the password could establish an MFA-pending session (AAL1).
- The attacker could then call the TOTP enrollment endpoint (`/api/v1/auth/totp/enroll`), overwriting or generating a replacement TOTP secret without ever proving possession of the existing second factor.
- By verifying their newly registered secret, the attacker could elevate to AAL2, completely locking out the legitimate user.

### 1.2 Remediations Implemented
1. MFA Domain Service Hardening (`kanban/auth/mfa/totp.py`):
   - Added `has_active_factor(session, user_id)` helper to check for confirmed active MFA factors (`mfa_factors` table with `status = 'active'`).
   - Added keyword-only parameter `deny_if_active: bool = True` to `generate_totp_secret`. If an active factor exists and re-enrollment is attempted without proper AAL2 verification, raises `ProblemException(code="MFA_FACTOR_ALREADY_ACTIVE", status=409)`.
2. MFA API Route Enforcement (`kanban/api/v1/auth_mfa.py`):
   - In `enroll_totp`, the endpoint queries whether the current user account already has an active MFA factor.
   - If an active factor exists, the caller must possess an elevated AAL2 session (`current_user.aal_level >= "aal2"`).
   - If the caller only holds an AAL1 / MFA-pending session, the endpoint rejects the request with HTTP 403 Forbidden (`AAL2_REQUIRED`) and clear security guidance.
3. Clean Initial Enrollment Preserved:
   - Accounts without active MFA factors can enroll their first TOTP factor using an AAL1 authenticated session as intended during onboarding.

---

## 2. Requirement-to-Evidence Verification Matrix

| Requirement | Implementation Artifacts | Verification Tests | Verdict |
| :--- | :--- | :--- | :--- |
| **Deny TOTP re-enrollment from AAL1 / MFA-pending session** | `kanban/api/v1/auth_mfa.py` (`enroll_totp`), `kanban/auth/mfa/totp.py` | `kanban/tests/security/test_totp_re_enrollment_protection.py::test_aal1_session_cannot_re_enroll_totp_when_mfa_active` | PASS |
| **Enforce AAL2 requirement for factor replacement** | `kanban/api/v1/auth_mfa.py` | `kanban/tests/security/test_totp_re_enrollment_protection.py::test_aal2_session_can_re_enroll_totp_when_mfa_active` | PASS |
| **Preserve first-time enrollment for new users** | `kanban/auth/mfa/totp.py` | `kanban/tests/security/test_totp_re_enrollment_protection.py::test_first_time_totp_enrollment_allowed_with_aal1`, `kanban/tests/auth/test_totp.py` (all tests pass) | PASS |
| **Zero Em/En-Dashes Rule** | All touched files use plain ASCII hyphens | `uv run python -m scripts.check_no_dashes --all` exits 0 | PASS |
| **>=95% Test Coverage** | MFA TOTP service and security suite | 96% coverage on `kanban/auth/mfa/totp.py`, 4/4 security tests pass, 10/10 auth tests pass | PASS |

---

## 3. Specialist Verdict

The TOTP re-enrollment and factor overwrite vulnerability is fully mitigated. AAL1 sessions cannot overwrite or replace active factors, closing the account takeover path while preserving clean first-time onboarding.

STATUS: APPROVED

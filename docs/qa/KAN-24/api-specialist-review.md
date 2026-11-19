# API Specialist Security & Architecture Audit Review: KAN-24

## Audit Metadata
- Ticket ID: KAN-24 ([KB-P3-AUDIT-18])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan24-5cab4be9`
- Target Branch: feat/KAN-24
- Base Commit: 31aca8e
- Head Commit: ee98d2d
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the backend architecture, cryptographic security controls, API contract schemas, and authorization guards introduced in ticket KAN-24. The implementation resolves four critical WebAuthn, FIDO2, and MFA vulnerabilities without adding external dependencies, degrading test performance, or weakening security invariants.

All changes have been validated against authoritative security specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Hardware FIDO2 Compatibility & Attachment Hint
- Files: `kanban/auth/mfa/webauthn.py`, `kanban/api/v1/auth_webauthn.py`
- Invariant & Problem: Previously, hardcoded `UserVerificationRequirement.REQUIRED` rejected cross-platform USB/NFC hardware security keys (e.g., YubiKey 5 without a PIN configured) despite valid User Presence (`UP=True`).
- Audit Findings:
  - `WebauthnService.registration_options` and `authentication_options` now configure `UserVerificationRequirement.PREFERRED` and `ResidentKeyRequirement.PREFERRED`.
  - `verify_registration` and `verify_authentication` configure `require_user_verification=False`.
  - Mandatory security properties remain intact: User Presence (`UP=True`), `rp.name = "👍kanban"`, strict ASCII FQDN `rp.id`, origin check against configured origin, single-use 300s challenge, and `sign_count` clone detection.
  - `WebauthnRegisterOptionsRequest` correctly models optional `authenticator_attachment: Literal["platform", "cross-platform"] | None = None`.
  - Principal's `display_name` is passed into `user_display_name` during options generation.

### 2. First-Factor Enrollment Deadlock & AAL2 Freshness Enforcement
- Files: `kanban/api/v1/auth_webauthn.py`
- Invariant & Problem: Previously, `_assert_can_register` rejected authenticated users with zero MFA factors with `403 AAL2_REQUIRED`, making it impossible for standard users to register their first WebAuthn factor.
- Audit Findings:
  - Users with `not has_totp and webauthn_count == 0` are permitted to initiate and complete first-factor registration.
  - On successful registration verification (`POST /api/v1/auth/webauthn/register/verify`), the session is elevated to AAL2 (`aal_level = 2`, `aal2_verified_at = now()`).
  - Users with existing factors (`has_totp or webauthn_count > 0`) must possess fresh AAL2 credentials (`aal_level >= 2` within `AAL2_MAX_AGE_SECONDS = 900`), failing with RFC 7807 `AAL2_REQUIRED` or `AAL2_STALE` with populated discovery `methods`.

### 3. Last-Factor Lockout Prevention Across Admin Tiers
- Files: `kanban/api/v1/auth_webauthn.py`, `kanban/api/v1/auth_mfa.py`
- Invariant & Problem: Deletion endpoints checked only `role IN ('SERVER_ADMIN', 'PROJECT_ADMIN')`, omitting `WORKSPACE_ADMIN` and `principal.is_server_admin`.
- Audit Findings:
  - `DELETE /api/v1/auth/webauthn/credentials/{credential_id}` and `DELETE /api/v1/auth/mfa/totp` now evaluate `is_server_admin` and query for roles in `('SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN')`.
  - When the credential being deleted is the administrator's last active factor, the endpoint raises HTTP 409 `LAST_FACTOR` with clear error detail, preventing administrative account lockout.
  - Non-administrative members (`WORKSPACE_MEMBER`) can remove credentials without lockout restrictions.

### 4. Credential Metadata & Step-Up Methods Discovery
- Files: `kanban/api/v1/auth_webauthn.py`, `kanban/auth/mfa/policy.py`, `kanban/api/problems.py`
- Audit Findings:
  - `GET /api/v1/auth/webauthn/credentials` and `PATCH /api/v1/auth/webauthn/credentials/{credential_id}` responses serialize `aaguid`, `transports`, and `suspect_clone_at`.
  - Signature counter regressions during authentication properly flag `suspect_clone_at` and log security warnings.
  - `Problem` schema and `ProblemException` support `methods: list[str] | None`. Step-up exceptions (`AAL2_REQUIRED` and `AAL2_STALE`) dynamically return enrolled methods from `["totp", "webauthn", "recovery"]`.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No modifications to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: `test_aal2_policy.py::test_case_10_assert_admin_routes_protected` passes cleanly. All `/api/v1/admin/*` endpoints remain protected by `Depends(require_admin_aal2)`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - `kanban/api/v1/auth_webauthn.py`: 98% line and branch coverage
   - `kanban/auth/mfa/policy.py`: 97% line and branch coverage
   - `kanban/auth/mfa/webauthn.py`: 98% line and branch coverage
   - Total touched modules: 98% (comfortably exceeds >= 95.10% threshold).
   - All 37 pytest tests passing in 16.67s.
5. [x] Static Analysis: `ruff check`, `ruff format --check`, and `mypy` (1072 files) pass with 0 errors.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `artifacts/webauthn-openapi-schemas.json`, and `message-to-reality-checker.md` verified in `docs/qa/KAN-24/`.

---

## Verdict & Handoff
STATUS: APPROVED

The backend API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for API-to-UI contract verification (backend-only ticket; no UI screenshots expected).

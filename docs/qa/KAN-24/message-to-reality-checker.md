# Forensic Verification Proof Packet: KAN-24

## Ticket Identification
- **Ticket ID:** KAN-24
- **Title:** [KB-P3-AUDIT-18] Fix WebAuthn & FIDO2 Backend Enrollment Policy, Hardware Security Key UV Compatibility, and Admin Lockout Guards
- **Branch:** `feat/KAN-24`
- **Scope Classification:** `N/A - Non-UI Ticket` (Backend-only WebAuthn/FIDO2 & MFA policy; frontend Passkey/FIDO2 UI is delivered in KAN-25).

---

## 1. Executive Summary & Problem Resolutions

Ticket KAN-24 resolves four critical architectural and security defects in the WebAuthn, FIDO2, and MFA backend subsystems:

### Problem 1: Hardware FIDO2 Security Key Compatibility & Attachment Hint
- **Root Cause:** `kanban/auth/mfa/webauthn.py` previously hardcoded `UserVerificationRequirement.REQUIRED` and `require_user_verification=True`, rejecting standard cross-platform USB/NFC FIDO2 security keys (such as YubiKey 5 / Security Key series without an active user PIN).
- **Resolution:** Updated `WebauthnService.registration_options` and `authentication_options` to configure `UserVerificationRequirement.PREFERRED` and `ResidentKeyRequirement.PREFERRED`.
- Updated `verify_registration` and `verify_authentication` to pass `require_user_verification=False`, preserving mandatory User Presence (`UP=True`), `rp.name = "👍kanban"`, strict ASCII FQDN `rp.id`, origin validation, single-use 300s challenge, and `sign_count` clone detection.
- Updated `WebauthnRegisterOptionsRequest` in `kanban/api/v1/auth_webauthn.py` to accept an optional `authenticator_attachment` (`"platform" | "cross-platform" | null`) and populated the principal's `display_name` into `user_display_name`.

### Problem 2: First-Factor Enrollment Deadlock & 900s AAL2 Freshness Enforcement
- **Root Cause:** `_assert_can_register` in `kanban/api/v1/auth_webauthn.py` rejected authenticated AAL1 users who possessed zero MFA factors with HTTP 403 `AAL2_REQUIRED`, creating an enrollment deadlock for users attempting to register their first WebAuthn credential.
- **Resolution:** Re-architected `_assert_can_register` to permit authenticated principals with `not has_totp and webauthn_count == 0` to register their initial WebAuthn factor directly from an AAL1 session.
- Upon successful `POST /api/v1/auth/webauthn/register/verify`, the user's active session is elevated to AAL2 (`aal_level = 2`, `aal2_verified_at = now()`).
- When additional factors exist (`has_totp or webauthn_count > 0`), fresh AAL2 verification is enforced (`aal_level >= 2` and `aal2_verified_at` within `AAL2_MAX_AGE_SECONDS = 900`), raising RFC 7807 `AAL2_REQUIRED` or `AAL2_STALE` with populated discovery `methods`.

### Problem 3: Lockout Guards Across Admin Roles (`is_server_admin` & `WORKSPACE_ADMIN`)
- **Root Cause:** `DELETE /api/v1/auth/webauthn/credentials/{credential_id}` and `DELETE /api/v1/auth/mfa/totp` previously checked only `role IN ('SERVER_ADMIN', 'PROJECT_ADMIN')`, omitting `WORKSPACE_ADMIN` and `principal.is_server_admin`.
- **Resolution:** Enforced the `LAST_FACTOR` lockout guard across all administrative tiers: `SERVER_ADMIN`, `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, and `principal.is_server_admin`. Any administrator attempting to delete their sole remaining MFA factor receives HTTP 409 `LAST_FACTOR`. Non-admin members (`WORKSPACE_MEMBER`) retain the ability to remove their credentials without lockout.

### Problem 4: Complete Credential Metadata & Step-Up `methods` Discovery
- **Root Cause:** `GET /api/v1/auth/webauthn/credentials` and `PATCH /api/v1/auth/webauthn/credentials/{credential_id}` omitted `aaguid`, `transports`, and `suspect_clone_at`. Problem responses for `AAL2_REQUIRED` and `AAL2_STALE` omitted available authentication methods.
- **Resolution:** Enriched credential serialization with `aaguid` (UUID string), `transports` (`list[str]`), and `suspect_clone_at` (ISO timestamp). When a signature counter regression occurs during authentication, `suspect_clone_at` is flagged and logged.
- Added `_get_enrolled_methods` helper to inspect active factors (`totp`, `webauthn`, `recovery`) and dynamically populate `methods: list[str]` on `AAL2_REQUIRED` and `AAL2_STALE` problem details (`kanban/auth/mfa/policy.py`, `kanban/api/problems.py`).

---

## 2. Forensic Proof Inventory & Evidence Mapping

| Requirement | Primary Evidence File | Description |
| :--- | :--- | :--- |
| **1. Unit & Integration Test Suite** | `docs/qa/KAN-24/unit-test-results.txt` | 37 passed tests across 4 test suites with 98% line and branch coverage on touched modules. Zero failures. |
| **2. Build, Types & Linter Verification** | `docs/qa/KAN-24/build-or-typecheck.txt` | Complete clean output from `ruff check`, `ruff format --check`, `mypy` (1072 files), `lint-imports` (2 kept), and `check_no_dashes --all`. |
| **3. OpenAPI & Contract Schemas** | `docs/qa/KAN-24/artifacts/webauthn-openapi-schemas.json` | Extracted OpenAPI paths and schemas for `/api/v1/auth/webauthn/*` and `/api/v1/auth/mfa/*`. |
| **4. Git Diff Patch** | `docs/qa/KAN-24/git-diff.patch` | Exact diff against `origin/main`. |
| **5. Changed Files Manifest** | `docs/qa/KAN-24/changed-files-manifest.txt` | Exact list of modified and newly created files. |
| **6. Non-UI Ticket Declaration** | This document | Declares `N/A - Non-UI Ticket` confirming backend-only implementation; UI screenshots are handled in KAN-25. |

---

## 3. Coverage Analysis on Touched Modules

```
Name                             Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------------
kanban/api/v1/auth_webauthn.py     256      4     74      3    98%   151, 155, 287-288, 681->693
kanban/auth/mfa/policy.py          103      2     50      3    97%   97, 193->195, 232
kanban/auth/mfa/webauthn.py        194      6     48      0    98%   368-369, 536-537, 561-562
----------------------------------------------------------------------------
TOTAL                              553     12    172      6    98%
```
Achieved **98% line and branch coverage**, comfortably surpassing the mandatory `>=95.10%` threshold.

---

## 4. Invariant Compliance Checklist

- [x] Zero `\u2014` em-dashes or `\u2013` en-dashes (`python3 -m scripts.check_no_dashes --all` passed).
- [x] Zero new external dependencies added.
- [x] All `/api/v1/admin/*` routes untouched or preserve `Depends(require_admin_aal2)`.
- [x] Strict ASCII FQDN `rp.id` and `rp.name = "👍kanban"` retained.
- [x] Clean database isolation with PostgreSQL savepoints / session rollbacks; zero touches to production / test kanban instances.
- [x] Backend-only ticket: zero frontend React modifications in `kanban/web/src/`.

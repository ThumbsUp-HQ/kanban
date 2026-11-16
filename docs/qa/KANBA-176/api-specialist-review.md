# Backend Architect / API Specialist Review: KANBA-176

- **Reviewer:** Backend Architect / API Specialist (`arch-reviewer`)
- **Date:** 2026-11-16
- **Ticket:** KANBA-176 ([KB-UX-06] Simplify Admin Auth Studio: Mandatory vs Optional Sections, OAuth/LDAP/AD Presets, Local User Creation, and Permission Grants UI)
- **Scope Inspected:**
  - `kanban/api/v1/admin/auth_cards.py`
  - `kanban/api/v1/admin/principals.py`
  - `kanban/admin/principal_service.py`
  - `kanban/auth/oidc/config.py`
  - `kanban/auth/oidc/flow.py`
  - `kanban/auth/ldap/config.py`
  - `kanban/auth/ldap/service.py`
  - `kanban/auth/local/service.py`
  - `kanban/auth/identity_service.py`
  - `kanban/tests/auth/test_auth_use_cases.py`
  - `docs/qa/KANBA-176/changed-files-manifest.txt`
  - `docs/qa/KANBA-176/git-diff.patch`
  - `docs/qa/KANBA-176/unit-test-results.txt`
  - `docs/qa/KANBA-176/build-check.txt`
  - `docs/qa/KANBA-176/message-to-reality-checker.md`

---

## 1. Architectural & Security Evaluation

### A. Auth Card Schemas, Presets & Secret Masking
- **OIDC & OAuth 2.0 Hardening (`kanban/auth/oidc/`):**
  - Verified client secret write-only masking on read/edit responses; plaintext secrets are never leaked back to the client.
  - Verified mandatory `S256` PKCE enforcement across all authorization code exchange flows.
  - Verified robust GitHub OAuth provider handling: integer `id` from GitHub user profile API is cleanly coerced to string `sub`, and primary verified emails are resolved from `/user/emails` or defaulted to `{login}@users.noreply.github.com` with `email_verified=True`.
- **LDAP & Active Directory Hardening (`kanban/auth/ldap/`):**
  - Verified Bind DN password masking and TLS enforcement (`ldaps://` or `StartTLS` with certificate pinning / CA bundle validation).
  - Verified Active Directory preset support: `sAMAccountName` username filtering, `objectGUID` binary identifier decoding, and fallback email generation (`{clean_username}@ldap.local`).
  - Strict directory group access evaluation: `access_mode = "group_restricted"` cleanly rejects unlisted directory members with HTTP 403 `IDENTITY_NOT_PROVISIONED`.

### B. Local User Provisioning & MFA Policy Security
- **Admin Principals & Role Binding API (`kanban/api/v1/admin/principals.py`):**
  - Route dependencies strictly enforce `Depends(require_admin_aal2)` across `/api/v1/admin/principals` and `/api/v1/admin/auth-cards`.
  - `POST /api/v1/admin/principals` now accepts `password` and initial `role` (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `WORKSPACE_MEMBER`, `WORKSPACE_GUEST`), provisioning the principal, registering the user object, hashing the password with Argon2id, and committing the role binding atomically.
- **Selective MFA Step-Up Policy (`kanban/auth/local/service.py`):**
  - Enforces MFA step-up (`mfa_pending=True`) for principals holding `SERVER_ADMIN` or having an enrolled MFA factor. Standard members without enrolled factors log in cleanly without an unconfigured MFA lockout block.

### C. Import Boundaries & Code Hygiene
- `uv run lint-imports` confirmed that all module layering rules are preserved (2 kept, 0 broken).
- `uv run ruff check` confirmed zero lint or formatting issues.
- `scripts.check_no_dashes` confirmed strict adherence to plain ASCII hyphens across all documentation and comments.

---

## 2. Test Suite & Coverage Verification
- Executed `uv run pytest kanban/tests/auth/test_auth_use_cases.py -v`:
  - 10/10 backend unit tests passed in 0.21s covering all 7 auth use cases:
    - Use Case 1: LDAP Any User defaults and standard member provisioning.
    - Use Case 2: LDAP Admin Group (`SERVER_ADMIN`) and User Group (`WORKSPACE_MEMBER`) grants, with rejection of unlisted accounts.
    - Use Case 3: Active Directory preset and fallback email resolution.
    - Use Case 4: GitHub OAuth claims and string subject coercion.
    - Use Case 5: OAuth admin and user email allowlists.
    - Use Case 6: Local user provisioning and MFA policy enforcement.
    - Use Case 7: Principal role mutation and secure password resets.
- Vitest frontend tests:
  - 49/49 tests passed in `AuthCardEditorDrawer.test.tsx` and `AuthStudioPage.test.tsx`.
- Production Vite build succeeded in 1.40s.

---

## 3. Findings & Defect Summary
- **Critical Defects:** 0
- **Security Vulnerabilities:** 0
- **Schema / Invariant Violations:** 0
- **Regressions:** 0

All backend, identity, API security, and access control invariants for KANBA-176 are satisfied.

---

**Verdict:** APPROVED

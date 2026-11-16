# KANBA-176 (`KB-UX-06`) - Verification Proof & Reality Checker Dossier

## Task Overview
- **Ticket:** KANBA-176 (`[KB-UX-06] Simplify Admin Auth Studio: Mandatory vs Optional Sections, OAuth/LDAP/AD Presets, Local User Creation, and Permission Grants UI`)
- **Status:** Complete, all 7 use cases validated and verified against project requirements.

---

## 1. Scope & Implementation Summary

### A. Simplified Admin Auth Studio & Drawer (`AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `adminAuth.css`, `adminAuthApi.ts`)
1. **1-Click Provider Presets:**
   - Pre-fills forms with hardened defaults for:
     - `Google (OAuth 2.0)`: OIDC, `https://accounts.google.com`, scopes `openid, profile, email`
     - `GitHub (OAuth 2.0)`: OAuth 2.0, `https://github.com`, endpoints, scopes `read:user, user:email`
     - `Active Directory (sAMAccountName)`: LDAP, `ldaps://ad.corp.local:636`, `(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))`, `objectGUID`
     - `Standard LDAP (OpenLDAP)`: LDAP, `ldaps://ldap.corp.local:636`, `(&(objectClass=person)(uid={username}))`, `entryUUID`
     - `Custom OAuth 2.0 / OIDC`: OIDC, `oauth1` default slug, custom scopes
2. **Mandatory vs Collapsed Optional / Advanced Sections:**
   - **Mandatory Settings:**
     - OAuth/OIDC: Client ID, Client Secret (write-only masking with Replace checkbox on edit), Access Policy Mode.
     - LDAP/AD: Server URL, Bind DN, Bind DN Password (write-only masking with Replace checkbox on edit), Base DN, Access Policy Mode.
   - **Optional / Advanced Settings Accordion (collapsed by default):**
     - Slug identifier (auto-derived), display name, button subtext, icon preset, auto-provision toggle, allowed email domains, CA certificate PEM, SPKI SHA-256 TLS pins, token auth method, custom user/subject/email/name attributes.
     - PKCE hidden from UI (auto-enforced `S256`).
3. **Strict CSP & Design Token Alignment:**
   - Zero inline styles (`style-src 'self'`). All styling powered by CSS classes in `adminAuth.css` using theme variables.

### B. End-to-End Implementation of All 7 Auth Use Cases
1. **Use Case 1 (LDAP Any User):**
   - `LdapCardConfig.access_mode = "any_user"` provisions valid directory users as `WORKSPACE_MEMBER`.
2. **Use Case 2 (LDAP + Admin Group + User Group):**
   - `LdapCardConfig.admin_groups` grants `SERVER_ADMIN`.
   - `LdapCardConfig.user_groups` grants `WORKSPACE_MEMBER`.
   - `access_mode = "group_restricted"` strictly rejects unlisted directory users with 403 `IDENTITY_NOT_PROVISIONED`.
3. **Use Case 3 (LDAP Active Directory):**
   - Active Directory `sAMAccountName` filter assertion preset.
   - `subject_attribute="objectGUID"`.
   - Fallback to `{clean_username}@ldap.local` when directory entry omits `mail`.
4. **Use Case 4 (OAuth Any User - Google/GitHub):**
   - Coerces integer `id` from GitHub API to string `sub`.
   - Queries `/user/emails` for primary verified email or falls back to `{login}@users.noreply.github.com` with `email_verified=True`.
5. **Use Case 5 (OAuth + Admin List + User List):**
   - `OidcCardConfig.admin_allowlist` grants `SERVER_ADMIN`.
   - `OidcCardConfig.user_allowlist` grants `WORKSPACE_MEMBER`.
   - Unlisted email addresses raise 403 `IDENTITY_NOT_PROVISIONED`.
6. **Use Case 6 (Local User Creation & MFA Login Rules):**
   - `POST /api/v1/admin/principals` extended to accept `password` and `role`, provisioning user object, `local_credentials` row, and initial `RoleBinding`.
   - In `LocalAdminLoginService.login`, only require MFA step-up (`mfa_pending=True`) if user holds `SERVER_ADMIN` or has an enrolled MFA factor.
7. **Use Case 7 (Users & Permissions Management UI):**
   - Tab bar in `AuthStudioPage.tsx` switching between `[Auth Provider Cards]` and `[Users & Permissions]`.
   - Users table rendering principal handle, display name, email, provider badge (`LOCAL`, `GOOGLE`, `GITHUB`, `ACTIVE DIRECTORY`, `LDAP`), inline role selector (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `WORKSPACE_MEMBER`, `WORKSPACE_GUEST`), and "Reset Password" action.
   - "+ Add Local User" modal dialog and "Reset Password" modal dialog.

---

## 2. Verification Evidence

### Automated Test Results
- **Backend Tests:** `kanban/tests/auth/test_auth_use_cases.py`
  - 10/10 test cases passed in 0.22s.
- **Frontend Tests:** `kanban/web/src/features/admin-auth/AuthStudioPage.test.tsx` and `AuthCardEditorDrawer.test.tsx`
  - 49/49 test cases passed in 3.80s.
- **Total Tests Passing:** 59/59.

### Quality & Build Checks
- **Backend Ruff Lint:** `uv run ruff check ...` -> `All checks passed!`
- **Web ESLint:** `cd kanban/web && npx eslint ...` -> `0 errors, 0 warnings`
- **Web Production Build:** `cd kanban/web && pnpm run build` -> `built in 1.40s` (exit code 0)

### Visual Artifacts
- `docs/qa/KANBA-176/screenshots/auth-studio-simplified-and-users.png`: Full screenshot of Authentication Studio showing the "Users & Permissions" tab, provider badges, inline role grants, and action buttons.
- `docs/qa/KANBA-176/screenshots/auth-studio-presets-drawer.png`: Screenshot of the simplified Drawer with 1-click provider presets, Mandatory Settings section, and collapsed Optional/Advanced Accordion.

---

## 3. Dossier Manifest
- `docs/qa/KANBA-176/git-diff.patch`
- `docs/qa/KANBA-176/changed-files-manifest.txt`
- `docs/qa/KANBA-176/unit-test-results.txt`
- `docs/qa/KANBA-176/build-check.txt`
- `docs/qa/KANBA-176/screenshots/auth-studio-simplified-and-users.png`
- `docs/qa/KANBA-176/screenshots/auth-studio-presets-drawer.png`
- `docs/qa/KANBA-176/message-to-reality-checker.md`

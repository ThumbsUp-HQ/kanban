# API Specialist Review & Verification: KAN-367

- **Ticket ID:** KAN-367
- **Title:** [KB-ADVANCED-DISCLOSURE-01] Auth Card Studio Inverted Advanced Section Refactor and Auto-Derived Slug UX
- **Reviewer Persona:** Clean-Room Backend / API / Security Specialist (`@api-spec`)
- **Target Surfaces:** `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`, `adminAuthApi.ts`, `AuthCardEditorDrawer.test.tsx`
- **Audit Date:** 2026-11-23
- **Verdict:** APPROVED (Grade-A)

---

## 1. Security & API Contract Verification

### A. Payload Schema & Normalization
The payload constructor in `AuthCardEditorDrawer.tsx` (`constructPayload()`) was audited against backend expectations:
1. **OIDC / OAuth2 Payloads:**
   - Correctly formats `public_config` with `kind`, `client_id`, `scopes` (defaulting to `['openid', 'profile', 'email']`), and `client_auth` (`client_secret_basic` vs `private_key_jwt`).
   - Conditionally attaches `issuer`, `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint` only when populated.
   - Enforces HTTPS URL scheme on `issuer_url`.
   - Access policies: `admin_allowlist` and `user_allowlist` arrays are sanitized and serialized only when `accessPolicyMode === 'restricted'`.
2. **LDAP Payloads:**
   - Validates server URL protocol: rejects plain HTTP or invalid schemes. Enforces `ldaps://` or `ldap://` with forced `starttls: true`.
   - Normalizes directory attributes: `subject_attribute` (default `objectGUID`), `email_attribute` (default `mail`), and `display_name_attribute` (default `displayName`).
   - Pins SPKI SHA-256 fingerprint: strict validation against 64-hex regex (`/^[a-f0-9]{64}$/i`).
   - Transport certificates: preserves CA PEM formatting for self-signed or enterprise PKI chains.
3. **Secret Write-Only Masking:**
   - On edit mode, stored secrets are never exposed to the frontend DOM. Placeholder displays active `dek_kid`.
   - Secret payload field is omitted on submission unless the `Replace Stored Secret` checkbox is explicitly checked and a non-empty secret is entered.

### B. Slug Sanitization & Invariants
- Enforces slug regex: 3 to 48 lowercase alphanumeric characters or hyphens (`/^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$/`).
- Auto-derivation logic handles aggressive input sanitization, stripping invalid characters, collapsing multiple hyphens, and trimming leading/trailing hyphens.
- Prevents tampering: slug input is disabled on edit, preserving cryptographic callback URI bindings (`/api/v1/auth/oidc/{slug}/callback`).

### C. Handshake & Test Connection Safety
- Supports testing draft connection configs (`testDraftAuthCardHandshake`) and existing saved cards (`testAuthCardHandshake`) with appropriate error containment, ensuring transient network errors do not crash the admin studio.

---

## 2. Test Coverage & Code Quality

- **Test Suite:** `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.test.tsx` expanded to 55 comprehensive unit tests.
- **V8 Coverage Metrics:**
  - Statements: 99.79% (exceeds >=95% gate)
  - Branches: 95.92% (exceeds >=95% gate)
  - Functions: 100.00% (exceeds >=95% gate)
  - Lines: 100.00% (exceeds >=95% gate)
- **Static Analysis:**
  - TypeScript: 0 errors (`pnpm typecheck` passed cleanly)
  - ESLint: 0 warnings, 0 errors (`pnpm lint --max-warnings 0` passed cleanly)
  - ASCII dashes enforcement: 0 errors (`scripts.check_no_dashes` passed cleanly)

---

## 3. Verdict

The implementation adheres to all security invariants, API specifications, and contract requirements.
- **Verdict:** APPROVED (Grade-A)

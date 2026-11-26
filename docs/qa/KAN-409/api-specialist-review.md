# API Specialist Review: KAN-409 (Slice 1 Phase 4 Publish Verified Multi-Card Auth, AD/LDAP, OIDC & RBAC Wiki + In-App Docs Guides)

**Ticket:** KAN-409 (`[SLICE-1-P4][KB-AUTH-DOCS]`)  
**Parent Epic:** KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan409-6ed6f24d`  
**Target Commit:** `f54c855c` (branch `docs/KAN-409-slice1-auth-docs`)  
**Wiki Commit:** `4452a11` (branch `docs/KAN-409-slice1-auth-docs` in `./thumbs-up-kanban.wiki`)  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the technical accuracy, schema fidelity, protocol specifications, API contracts, and security documentation delivered in **KAN-409: Phase 4 Publish Verified Multi-Card Auth, AD/LDAP, OIDC & RBAC Wiki + In-App Docs Guides**.

The documentation covers the entire Slice-1 subsystem across authoritative wiki chapters (`Multi-Card-Authentication-Studio.md`, `Role-and-Permission-Matrix.md`, and Slice-1 sections of `Studio-Configuration-Reference.md`) and the compiled offline in-app DocsCenter bundle (`wikiManifest.ts`, 612,452 bytes, 106 images). Every setting, data type, protocol parameter, error code, and security invariant was verified against the backend API routers and React studio components:
1. **Multi-Card Authentication Studio & Anti-Lockout Safeguards**:
   - Live credential testing routes: `POST /api/v1/admin/auth-cards/test-handshake` (drafts) and `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake` (saved).
   - Critical anti-lockout invariant accurately distinguished: test handshakes update connectivity/health status only and **NEVER** satisfy `handshake_probe_15m` (`last_admin_handshake_at`). Disabling `LOCAL_ADMIN` requires an active, verified interactive `SERVER_ADMIN` login via an external auth card within the last 15 minutes (`record_external_admin_handshake`), returning HTTP 409 `LOCKOUT_PREVENTED` (`code: "LOCKOUT_PREVENTED"`, `layer: "handshake_probe_15m"`) if violated.
   - Ordering and card enable/disable controls verified with fractional-index `sort_rank` (computed via `midpoint_rank()`, e.g. `"V00V"`), with zero cleartext secrets in responses.
2. **Active Directory & LDAPS / StartTLS Handshakes**:
   - Authentication route: `POST /api/v1/auth/ldap/{slug}/login`.
   - Protocol negotiation: StartTLS on standard port 389 vs direct LDAPS on port 636 with pinned CA PEM validation.
   - Schema parity for `LdapCardConfig`: accurately documents actual fields (`url`, `transport_mode`, `service_bind_dn`, `base_dn`, `user_search_filter`, `subject_attribute`, `email_attribute`, `display_name_attribute`, `member_of_attribute`, `group_dn_map`, `access_mode`, `admin_groups`, `user_groups`, `ca_cert_pem`, `spki_sha256_pins`). `spki_sha256_pins` documented strictly as an administrative API parameter.
   - Nested group synchronization: recursive `memberOf` filter mapped to canonical roles.
3. **OIDC Federation & Verified-Claim Account Linking**:
   - Authorization flow routes: `GET /api/v1/auth/oidc/{slug}/start` and `GET /api/v1/auth/oidc/{slug}/callback`.
   - Scopes documented as `list[str]` in backend API (`["openid", "email", "profile"]`) and comma-separated in drawer UI.
   - Security invariant: unverified email claims (`email_verified: false`) strictly rejected with HTTP 403 `EMAIL_NOT_VERIFIED` to eliminate account takeover risks.
4. **WebAuthn / Passkeys & AAL2 MFA**:
   - WebAuthn Relying Party configuration: display string `rp.name = "👍kanban"` with strict ASCII FQDN `rp.id`.
   - Multi-factor enrollment routes: `/totp/enroll`, `/totp/confirm`, `/mfa/verify`, and `/mfa/recovery/regenerate`.
   - Recovery code count strictly documented as **10** single-use recovery codes (`RECOVERY_CODE_COUNT = 10` in `kanban/auth/mfa/recovery.py`).
5. **Granular RBAC Policy Builder & 30-Permission Engine**:
   - 30 canonical permissions partitioned across Workspace (8), Issue (10), and Field (12) tiers matching `kanban/security/granular_permissions.py` and `RbacPolicyBuilder.tsx`.
   - Capability bitmask matches `Capability(IntFlag)`: `NONE=0`, `VIEW=1`, `COMMENT=2`, `EDIT=4`, `TRANSITION=8`, `LINK=16`, `SHARE=32`, `ADMIN=64`, `DELETE=128`, `ALL=255`.
   - Absolute DENY precedence rule enforced: `effective = allow & (~deny)`.
   - UI mechanics clarified: indeterminate checkbox represents partial grant across multiple roles (auto-saving via permissions API), and custom role authoring uses `*create new*` selector.
6. **In-App Heading Anchors & DocsCenter Verification**:
   - Exact heading slugs generated via `slugifyAnchor()` resolve all in-app `docHref` targets: `#aal2-step-up`, `#mfa-enrollment`, `#lockout-prevention`, `#password-security`, `#system-roles`, `#workspace-level-roles`, `#granular-rbac-policy-builder`, `#30-permission-granular-engine`, and `#workspace-studio`.

**Verdict: APPROVED.** All API contracts, schemas, security bounds, and operator procedures in KAN-409 are thoroughly verified and approved.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Verified REST Endpoints
- **Multi-Card Auth:**
  - `POST /api/v1/admin/auth-cards`
  - `PATCH /api/v1/admin/auth-cards/{id}`
  - `POST /api/v1/admin/auth-cards/test-handshake`
  - `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake`
- **Active Directory / LDAP:**
  - `POST /api/v1/auth/ldap/{slug}/login`
- **OIDC Federation:**
  - `GET /api/v1/auth/oidc/{slug}/start`
  - `GET /api/v1/auth/oidc/{slug}/callback`
- **Passkeys & MFA:**
  - `POST /api/v1/auth/mfa/totp/enroll`
  - `POST /api/v1/auth/mfa/totp/confirm`
  - `POST /api/v1/auth/mfa/verify`
  - `POST /api/v1/auth/mfa/recovery/regenerate`
  - `POST /api/v1/auth/aal2/drop`
  - `POST /api/v1/auth/webauthn/register/options`
- **Granular RBAC:**
  - `GET/POST /api/v1/admin/rbac/roles`
  - `PATCH/DELETE /api/v1/admin/rbac/roles/{id}`
  - `PUT /api/v1/admin/rbac/roles/permissions:batch`
  - `PUT /api/v1/admin/rbac/roles/{id}/permissions`

### 2.2 Security Invariants Verified
- **Hostile Wire Invariant:** Egress and certificate pinning strictly verified; StartTLS downgrade strictly rejected.
- **Walled Component Garden:** Multi-tenant RLS isolation verified (`FORCE ROW LEVEL SECURITY`).
- **Volatile State Sanitization:** Recovery codes single-use; session elevation dropped past 900s idle.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Pytest Suite (`kanban/tests/auth/`)**:
   - **113/113 passed in 35.07s**.
   - Coverage on touched modules: `cards/service.py` 98%, `cards/handshake.py` 96%, `cards/schemas.py` 100%, `ldap/service.py` 99%, `ldap/client.py` 97%, `ldap/sync.py` 100%.

2. **Frontend Vitest Suite**:
   - **193/193 passed in 9.36s** across all Slice-1 components.
   - Branch coverage: **95.85%** (`AuthCardEditorDrawer.tsx` 95.57%, `AuthStudioPage.tsx` 95.68%, `RbacPolicyBuilder.tsx` 97.59%, `DocsCenterPage.tsx` 95.12%, `DocMarkdownViewer.tsx` 95.95%).
   - Verified 71/71 DocsCenter tests with 96.15% branch coverage.

3. **Build & Quality Pipeline**:
   - `scripts/check_no_dashes.py`: 0 Unicode dashes repository-wide and across all wiki chapters.
   - `tsc -b --noEmit`: 0 TypeScript errors.
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
   - `vite build`: Clean production bundle in 1.25s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-409/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: Exit code 0 across sync, dashes, typecheck, lint, and build.
  - `unit-test-results.txt`: Documents 113 Pytest and 193 Vitest tests with >=95% branch coverage.
  - `screenshots/`: 16 multi-viewport PNG captures visually verified.

The documentation, endpoint schemas, and security controls for KAN-409 are robust, verified, and approved for release.

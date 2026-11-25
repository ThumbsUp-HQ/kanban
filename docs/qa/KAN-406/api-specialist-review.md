# API Specialist Review & Verification: KAN-406

- **Ticket ID:** KAN-406 (`[SLICE-1-P1][KB-AUTH-AUDIT] Multi-Card Auth, AD/LDAP, OIDC, MFA and RBAC Setting Inventory and Simplification Audit`)
- **Reviewer Persona:** Senior Backend & API Security Architect (`@api-spec`)
- **Target Surfaces:** Slice 1 Backend Wiring & Setting Inventory Audit (`docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md`)
- **Audit Date:** 2026-11-25
- **Verdict:** APPROVED (Zero REST or Auth Contract Regressions; 100% Backend Wiring Traceability Verified)

---

## 1. Scope & Backend Topology Audit

A comprehensive forensic audit of the Slice 1 setting inventory and simplification audit document (`docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md`) was performed against all relevant backend routers, authentication services, and data models:
- `kanban/api/v1/admin/auth_cards.py`:
  - `GET /api/v1/admin/auth-cards`: Correctly inventoried; verifies caller possesses `require_admin_aal2` and returns public card metadata with masked secrets.
  - `POST /api/v1/admin/auth-cards`: Correctly mapped; verifies provider kind, schema validation, and anti-lockout rules.
  - `POST /api/v1/admin/auth-cards/{card_ref}/enable` & `disable`: Correctly mapped; enforces minimum active card rules so admins cannot disable the final auth card.
  - `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake`: Correctly mapped; executes live LDAPS/OIDC/OAuth2 reachability check with strict 8.0s timeout.
  - `POST /api/v1/admin/auth-cards/{card_ref}/reorder`: Correctly mapped; validates contiguous ordering.
  - `DELETE /api/v1/admin/auth-cards/{card_ref}`: Correctly mapped; requires explicit confirmation slug and blocks deletion of the last surviving administrative auth mechanism.
- `kanban/api/v1/admin/principals.py`:
  - `GET /api/v1/admin/principals`: Correctly mapped; lists users, groups, and service accounts with role bindings and account states.
  - `POST /api/v1/admin/principals`: Correctly mapped; provisions local accounts or service bots with strict handle validation.
  - `POST /api/v1/admin/principals/{id}/reset-password`: Correctly mapped; resets local password with zero credential leakage in logs.
- `kanban/api/v1/admin/rbac.py`:
  - `GET /api/v1/admin/rbac/roles` & `POST /api/v1/admin/rbac/roles`: Correctly mapped; manages custom RBAC roles.
  - `PUT /api/v1/admin/rbac/roles/{role_id}/permissions`: Correctly mapped; updates granular permission bitmasks.
- `kanban/api/v1/auth_ldap.py` & `kanban/auth/ldap/`:
  - Enforces StartTLS or LDAPS on port 636/389, certificate trust validation, and service account bind DN authentication.
- `kanban/api/v1/auth_oidc.py` & `kanban/auth/oidc/`:
  - Enforces PKCE S256, nonce validation, state HMAC binding, and token exchange.
- `kanban/api/v1/auth_local.py`:
  - Constant-time password hashing via Argon2id with server-side pepper.
- `kanban/api/v1/auth_mfa.py` & `kanban/api/v1/auth_webauthn.py`:
  - TOTP enrollment, verification, and recovery code regeneration.
  - WebAuthn registration, challenge signing, and user verification.
- `kanban/api/v1/auth_identities.py`:
  - Explicit multi-card identity linking preventing accidental account collisions or privilege escalation.

---

## 2. API Contract & Security Invariant Verification

1. **Setting-by-Setting Mapping Parity:**
   Every UI control identified in the inventory table maps to an authentic backend endpoint or database model attribute. No phantom endpoints or unmapped fields exist in the specification.
2. **Security & Boundary Invariants:**
   - Anti-lockout guardrails are documented and enforced across all mutating card operations.
   - AAL2 requirement on all administrative routes (`require_admin_aal2`) is maintained without bypass.
   - Credential write-only behavior is maintained; secrets and private keys are never returned in GET payloads.
   - Clear distinction maintained between Slice-1 scope and KAN-404 (WebSudo), KAN-398 (Server-Admin RBAC check), and KAN-400 (Password manager auto-fill fixes).

---

## 3. Verdict

**APPROVED.** The Slice 1 audit document is technically exhaustive, security-hardened, and provides an authoritative foundation for Phase 2 implementation.

# Integration Reality-Checker Briefing: KAN-406

- **Ticket**: KAN-406 (`[SLICE-1-P1][KB-AUTH-AUDIT]` Phase 1: Multi-Card Auth, AD/LDAP, OIDC, MFA & RBAC Setting Inventory & Simplification Audit)
- **Parent Epic**: KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)
- **Branch**: `docs/KAN-406-slice1-audit`
- **Review Status**: Pending Dual Specialist Review (`api-spec` and `ui-spec`)
- **Deliverable Path**: `docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md`

## Summary of Completed Technical Actions

1. **Comprehensive Setting-by-Setting Inventory Table**:
   - Inspected 100% of UI controls, labels, options, defaults, validation rules, and backend bindings across all Slice-1 files:
     - Frontend: `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, `kanban/web/src/features/admin-auth/AuthCardEditorDrawer.tsx`, `kanban/web/src/features/rbac/RbacPolicyBuilder.tsx`, `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
     - Backend: `kanban/api/v1/admin/auth_cards.py`, `kanban/api/v1/admin/principals.py`, `kanban/api/v1/admin/rbac.py`, `kanban/api/v1/auth_ldap.py` (and `kanban/auth/ldap/router.py`), `kanban/api/v1/auth_oidc.py`, `kanban/api/v1/auth_local.py`, `kanban/api/v1/auth_mfa.py`, `kanban/api/v1/auth_webauthn.py`, `kanban/api/v1/auth_identities.py`
   - Structured table with columns: `Screen/Drawer | Setting Label & Key | Options / Type | 1-Sentence Plain-English Meaning | Backend Wiring Status | Disposition (KEEP | SIMPLIFY | MERGE | MOVE_TO_ADVANCED | CUT)`.

2. **Simplification Proposals & Focus Areas**:
   - **Active Directory vs OpenLDAP 1-Click Presets**: Auto-fills canonical search filters and attributes (`objectGUID`/`sAMAccountName`/`displayName` for AD vs `entryUUID`/`uid`/`cn` for OpenLDAP) to eliminate configuration mistakes.
   - **`sort_rank` and Fractional Indexing**: Encapsulates raw fractional index strings behind accessible Up/Down buttons and drag handles.
   - **SPKI SHA-256 Pin vs CA PEM**: Moves both into a collapsible Advanced TLS Security section with clear guidance on root CA bundles vs key pinning.
   - **Copyable OIDC Redirect URI**: Dynamically renders `${origin}/api/v1/auth/oidc/${slug}/callback` with 1-click copy button and origin warning.
   - **Anti-Lockout Safeguards**: Warns administrators before disabling or deleting the sole remaining administrative authentication card to prevent lockout.
   - **Password-Manager Suppression**: Mandates suppression attributes (`autoComplete="off"`, `data-1p-ignore="true"`, `data-lpignore="true"`, `data-bwignore="true"`, `data-form-type="other"`) on administrative bind passwords and client secret inputs.

3. **Phase 2 (`KAN-407`) Action Checklist & Phase 3 (`KAN-408`) Staging Checklist**:
   - File-scoped implementation tasks for Phase 2, deduplicated against `KAN-404` (Gate 0 WebSudo) and `KAN-398` (`/admin/auth` access fix).
   - Local OpenLDAP (`dc=planetexpress,dc=com`) and Keycloak/Mock OIDC container staging checklist for offline, hermetic workouts in Phase 3 without external secrets or internet access.
   - Reiteration of strict non-destructive policy protecting `https://k.hackedyour.info` / `192.168.1.101`.

4. **Forensic Verification**:
   - Zero Unicode em/en-dashes verified: `python3 scripts/check_no_dashes.py --all docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md` exits 0 (`docs/qa/KAN-406/build-check.txt`).
   - 100% of cited repository file paths verified to exist on disk (`docs/qa/KAN-406/unit-test-results.txt`).
   - Screenshots: `N/A - Read-Only Audit & Specification Handoff Ticket (UI screenshots captured in KAN-407 and KAN-408)`.

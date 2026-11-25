# API Specialist Review: KAN-398 Server Admin Auth Access Fix

- **Ticket**: KAN-398 (`[KB-ADMIN-AUTH-ACCESS-FIX] Server-Admin Auth Card Access Matrix & Subnav Filter`)
- **Reviewer**: API Specialist (`@api-spec`)
- **Status**: APPROVED
- **Date**: 2026-11-25

---

## 1. Executive Summary

This audit validates the backend database migration and API access control changes introduced for ticket KAN-398. The changes resolve an authorization bug where `SERVER_ADMIN` principals could not be resolved when querying project/server scope without an active `app.workspace_id` session setting. The migration updates `app_principal_has_role(p_project_id uuid, p_roles text[])` to decouple server-scoped `SERVER_ADMIN` checks from workspace scoping, while preserving strict workspace isolation for `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, and `VIEWER` roles.

---

## 2. Database Migration Audit

### 2.1 Migration Topology and Linearity
- **Revision ID**: `p6_17_server_admin_role_access`
- **Down Revision**: `p6_16_credential_project_scoping`
- **Chain Verification**: Verified linear chain with `uv run kanban-ctl db check-migrations --static-only`. Total 79 migrations tracked, exactly 1 head.
- **SQL Source Files**:
  - `database/migrations/sql/p6_17_server_admin_role_access.up.sql`
  - `database/migrations/sql/p6_17_server_admin_role_access.down.sql`

### 2.2 Security Definer and Search Path Invariants
- Function definition enforces:
  - `STABLE SECURITY DEFINER`
  - `SET search_path = pg_catalog, public`
- This ensures execution runs under database owner privileges without risk of search-path hijacking attacks.

### 2.3 SQL Logic Analysis
The updated `app_principal_has_role` implementation evaluates principal roles using two distinct scopes:
1. **Server-Scoped Role Check**:
   ```sql
   IF 'SERVER_ADMIN' = ANY(p_roles) THEN
       IF EXISTS (
           SELECT 1 FROM role_bindings rb
           WHERE rb.principal_id = ANY (v_pset)
             AND rb.role = 'SERVER_ADMIN'
             AND rb.scope_type = 'server'
       ) THEN
           RETURN true;
       END IF;
   END IF;
   ```
   - Matches if the principal has a `SERVER_ADMIN` binding with `scope_type = 'server'`, regardless of whether `v_ws` (`app.workspace_id`) is NULL or set.
2. **Workspace and Project-Scoped Role Check**:
   ```sql
   IF v_ws IS NOT NULL THEN
       RETURN EXISTS (
           SELECT 1 FROM role_bindings rb
           WHERE rb.principal_id = ANY (v_pset)
             AND rb.role = ANY (p_roles)
             AND rb.workspace_id = v_ws
             AND (
                 (rb.scope_type = 'workspace')
                 OR (
                     rb.scope_type = 'project'
                     AND p_project_id IS NOT NULL
                     AND rb.project_id = p_project_id
                     AND (v_cred_projs IS NULL OR p_project_id = ANY (v_cred_projs))
                 )
             )
       );
   END IF;
   ```
   - Retains strict workspace isolation: `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, and `VIEWER` role bindings MUST have `rb.workspace_id = v_ws`.
   - If `v_ws` is NULL, non-server roles return `false`.

### 2.4 Reversibility / Downgrade Safety
- The downgrade script `p6_17_server_admin_role_access.down.sql` restores the exact `p6_04` / `p6_16` definition.
- Automated migration cycle test in `database/tests/migrations/test_p6_17_server_admin_role_access_migration.py` validates upgrade -> downgrade -> upgrade in clean database without errors (0.65s).

---

## 3. API Route Guard and Access Matrix Verification

### 3.1 Endpoint Audited
- `GET /api/v1/admin/auth-cards`
- Route declaration:
  - Router dependency: `Depends(require_admin_aal2)`
  - Endpoint capability check: `require_admin_capability(auth.ADMIN_CAP_SYSTEM_SETTINGS)`

### 3.2 Access Matrix Test Results
The test suite in `kanban/tests/auth/test_admin_auth_cards_access.py` validates the complete authorization matrix:
- **Unauthenticated (No token / session)**: Returns HTTP 401 Unauthorized.
- **Server Administrator (AAL2 verified)**: Returns HTTP 200 OK with list of configured auth cards.
- **Workspace Administrator (AAL2 verified)**: Returns HTTP 403 Forbidden with error code `INSUFFICIENT_CAPABILITY`. Workspace admins cannot manage global auth provider cards.
- **Project Administrator (AAL2 verified)**: Returns HTTP 403 Forbidden with error code `INSUFFICIENT_CAPABILITY`.
- **Standard Member / Viewer**: Returns HTTP 403 Forbidden with error code `FORBIDDEN` (blocked at the router-level `require_admin_aal2` guard).

### 3.3 Direct SQL Role Validation Tests
- `test_app_principal_has_role_sql_server_admin_without_workspace`:
  - Validates `app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])` returns `true` when `app.workspace_id` is NULL.
- `test_app_principal_has_role_sql_workspace_and_project_scoping`:
  - Validates `WORKSPACE_ADMIN` and `PROJECT_ADMIN` return `true` only when `app.workspace_id` matches the binding's workspace.
  - Validates cross-workspace tampering returns `false`.
  - Validates NULL workspace with non-server roles returns `false`.

---

## 4. Problem Details and Error Codes
In `kanban/web/src/api/problem.ts`:
- Added helper `isMfaEnrollmentRequiredCode(code: unknown): boolean` recognizing:
  - `'MFA_ENROLLMENT_REQUIRED'`
  - `'mfa_enrollment_required'`
- Ensures parity with existing `isAal2StepUpCode` pattern.

---

## 5. Specialist Sign-Off
All backend security invariants, SQL search-path protections, and access control matrices meet the zero-tolerance quality standard.

**Verdict**: APPROVED

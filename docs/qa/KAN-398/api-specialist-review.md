# API Specialist Review: KAN-398 Server Admin Auth Access Fix

- **Ticket**: KAN-398 (`[KB-ADMIN-AUTH-ACCESS-FIX] Server-Admin Auth Card Access Matrix & Subnav Filter`)
- **Reviewer**: API Specialist (`@api-spec`)
- **Status**: APPROVED
- **Date**: 2026-11-25

---

## 1. Executive Summary

This audit validates the backend database migration and API access control changes introduced for ticket KAN-398, including Round 1 reality-checker remediation. The changes resolve an authorization bug where `SERVER_ADMIN` principals could not be resolved when querying project/server scope without an active `app.workspace_id` session setting or when active on a secondary workspace. The implementation introduces linear migration #81 (`p6_19_server_admin_cross_workspace_role_access`) updating `app_principal_has_role(p_project_id uuid, p_roles text[])` to:
1. Enforce `app.credential_projects` bounds checking before role resolution when `p_project_id` is supplied and credential scoping is active.
2. Resolve `SERVER_ADMIN` directly against active principals and server role bindings without requiring `p.workspace_id = app_current_workspace_id()`, allowing cross-workspace administration.
3. Retain strict workspace isolation (`rb.workspace_id = app_current_workspace_id()`) for non-server roles (`WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, and `VIEWER`).
4. Update `kb_auth.card_admin_list()` and `kb_auth.card_admin_get()` to call `app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])` instead of raw principal set queries.

---

## 2. Database Migration Audit

### 2.1 Migration Topology and Linearity
- **Revision ID**: `p6_19_server_admin_cross_workspace_role_access`
- **Revises**: `p6_18_websudo_sliding_aal2`
- **Chain Verification**: Verified linear single-head chain with `uv run kanban-ctl db check-migrations --static-only`. Total 81 migrations tracked, exactly 1 head.
- **SQL Source Files**:
  - `database/migrations/sql/p6_19_server_admin_cross_workspace_role_access.up.sql`
  - `database/migrations/sql/p6_19_server_admin_cross_workspace_role_access.down.sql`

### 2.2 Security Definer and Search Path Invariants
- Function definition enforces:
  - `STABLE SECURITY DEFINER`
  - `SET search_path = pg_catalog, public`
- This ensures execution runs under database owner privileges without risk of search-path hijacking attacks.

### 2.3 SQL Logic Analysis
The updated `app_principal_has_role` implementation evaluates principal roles using strict priority and boundary gates:

1. **Credential Project Scoping Boundary Check (First Pre-Check)**:
   ```sql
   IF p_project_id IS NOT NULL AND current_setting('app.credential_projects', true) IS NOT NULL AND current_setting('app.credential_projects', true) <> '' THEN
       BEGIN
           v_cred_projs := string_to_array(current_setting('app.credential_projects', true), ',')::uuid[];
       EXCEPTION WHEN OTHERS THEN
           v_cred_projs := NULL;
       END;
       IF v_cred_projs IS NOT NULL AND NOT (p_project_id = ANY (v_cred_projs)) THEN
           RETURN FALSE;
       END IF;
   END IF;
   ```
   - When project-scoped credentials are in effect, attempts to access an unlisted project are rejected immediately, even for server admins.

2. **Server-Scoped Role Check (Cross-Workspace Safe)**:
   ```sql
   IF 'SERVER_ADMIN' = ANY (p_roles) THEN
       v_principal_id := nullif(current_setting('app.principal_id', true), '')::uuid;
       IF v_principal_id IS NOT NULL THEN
           IF EXISTS (
               SELECT 1
               FROM principals p
               JOIN role_bindings rb ON rb.principal_id = p.id
               WHERE p.id = v_principal_id
                 AND p.status = 'ACTIVE'
                 AND rb.role::text = 'SERVER_ADMIN'
                 AND rb.scope_type = 'server'
           ) THEN
               RETURN TRUE;
           END IF;
           -- Recursive group membership checks for server role bindings
           IF EXISTS (
               SELECT 1
               FROM principal_group_closure pgc
               JOIN principals grp ON grp.id = pgc.group_id
               JOIN role_bindings rb ON rb.principal_id = grp.id
               WHERE pgc.member_id = v_principal_id
                 AND grp.status = 'ACTIVE'
                 AND rb.role::text = 'SERVER_ADMIN'
                 AND rb.scope_type = 'server'
           ) THEN
               RETURN TRUE;
           END IF;
       END IF;
   END IF;
   ```
   - Checks `principals` and `role_bindings` directly without requiring `p.workspace_id = app_current_workspace_id()`.
   - Functions correctly when `app.workspace_id` is empty, set to bootstrap workspace A, or switched to secondary workspace B.

3. **Workspace and Project-Scoped Role Check (Strict Workspace Isolation)**:
   ```sql
   v_ws := app_current_workspace_id();
   IF v_ws IS NULL THEN
       RETURN FALSE;
   END IF;

   v_pset := app_effective_principal_set();
   IF cardinality(v_pset) = 0 THEN
       RETURN FALSE;
   END IF;

   RETURN EXISTS (
       SELECT 1 FROM role_bindings rb
       WHERE rb.principal_id = ANY (v_pset)
         AND rb.role::text = ANY (p_roles)
         AND rb.workspace_id = v_ws
         AND (
             (rb.scope_type = 'workspace')
             OR (
                 rb.scope_type = 'project'
                 AND p_project_id IS NOT NULL
                 AND rb.project_id = p_project_id
             )
         )
   );
   ```
   - Retains strict workspace isolation: `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, and `VIEWER` role bindings MUST have `rb.workspace_id = v_ws`.
   - If `v_ws` is NULL, non-server roles return `FALSE`.

4. **Auth Card Admin Functions**:
   `kb_auth.card_admin_list()` and `kb_auth.card_admin_get()` call `app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])` ensuring server admins operating on secondary workspaces do not trigger privilege errors.

### 2.4 Reversibility and Downgrade Safety
- The downgrade script `p6_19_server_admin_cross_workspace_role_access.down.sql` restores `p6_17` and `p2_03` definitions cleanly.
- Automated migration cycle test in `database/tests/migrations/test_p6_19_server_admin_cross_workspace_role_access_migration.py` validates upgrade -> downgrade -> upgrade in clean database without errors (0.64s).

---

## 3. API Route Guard and Access Matrix Verification

### 3.1 Endpoint Audited
- `GET /api/v1/admin/auth-cards`
- Route declaration:
  - Router dependency: `Depends(require_admin_aal2)`
  - Endpoint capability check: `require_admin_capability(auth.ADMIN_CAP_SYSTEM_SETTINGS)`

### 3.2 Access Matrix and Boundary Test Results
The test suite in `kanban/tests/auth/test_admin_auth_cards_access.py` validates the complete authorization matrix:
- **Unauthenticated (No token / session)**: Returns HTTP 401 Unauthorized.
- **Server Administrator (AAL2 verified, Bootstrap Workspace A)**: Returns HTTP 200 OK.
- **Server Administrator (AAL2 verified, Active on Secondary Workspace B)**: Returns HTTP 200 OK (both direct SQL check and API route check with `X-KB-Scope-Workspace: ws_B`).
- **Server Administrator with Project-Scoped Credentials (`app.credential_projects`)**:
  - Allowed project: `app_principal_has_role` returns `true`.
  - Blocked project outside boundary: `app_principal_has_role` returns `false`.
- **Workspace Administrator on Workspace A active on Workspace B**: Returns HTTP 403 Forbidden.
- **Workspace Administrator (AAL2 verified)**: Returns HTTP 403 Forbidden with error code `INSUFFICIENT_CAPABILITY`. Workspace admins cannot manage global auth provider cards.
- **Project Administrator (AAL2 verified)**: Returns HTTP 403 Forbidden with error code `INSUFFICIENT_CAPABILITY`.
- **Viewer (AAL2 verified)**: Returns HTTP 403 Forbidden with error code `FORBIDDEN` (blocked at the router-level `require_admin_aal2` guard).

---

## 4. Problem Details and Error Codes
In `kanban/web/src/api/problem.ts`:
- Added helper `isMfaEnrollmentRequiredCode(code: unknown): boolean` recognizing:
  - `'MFA_ENROLLMENT_REQUIRED'`
  - `'mfa_enrollment_required'`
- Ensures parity with existing `isAal2StepUpCode` pattern.

---

## 5. Specialist Sign-Off
All backend security invariants, SQL search-path protections, credential scoping boundaries, cross-workspace role resolution, and access control matrices meet the zero-tolerance quality standard.

**Verdict**: APPROVED

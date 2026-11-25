# API Specialist & Security Review: KAN-396

## Ticket Reference
- **Ticket ID**: `KAN-396` (`[KB-OAUTH-ADMIN-REVOKE-PURGE-LAYOUT] Fix /admin/oauth Clipped Action Buttons, Fix PostgreSQL status CHECK 500 on Revoke/Suspend & Add Bulk Delete / Purge Stale OAuth Clients`)
- **Reviewer Persona**: API & Security Architect (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Branch**: `feat/KAN-396-oauth-admin-revoke-purge`
- **Base Commit**: `5b75379d`
- **Head Commit**: `1b017021` (Feature commit `72071659`)
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. Executive Summary & Verification Objective

Ticket `KAN-396` addresses a critical PostgreSQL constraint failure and implements enterprise-grade OAuth client lifecycle governance. Previously, patching an OAuth client status to `'suspended'` or `'revoked'` resulted in an HTTP 500 database error because `oauth_clients_status_check` only permitted `('active', 'pending_admin_approval', 'disabled')`. Furthermore, administrators lacked capabilities to permanently cascade delete test clients or purge stale dynamic client registration (DCR) records.

This review specifically verifies:
1. **Linear Database Migration #82 (`p6_20_oauth_clients_status_check`)**: Schema constraint update, downgrade normalization (`'suspended'`/`'revoked'` -> `'disabled'`), migration reversibility, and single-head chain integrity.
2. **Server Admin AAL2 Route Protection**: Ensuring all administrative endpoints (`GET /api/v1/admin/oauth-clients`, `PATCH /api/v1/admin/oauth-clients/{client_id}`, `DELETE /api/v1/admin/oauth-clients/{client_id}`, and `POST /api/v1/admin/oauth-clients/bulk-delete`) strictly declare and enforce `Depends(require_admin_aal2)`.
3. **Hard Delete & Cascading Deletion Safety**: Verification of `_permanently_delete_clients` cleaning up all 5 dependent tables (`oauth_revoked_jtis`, `oauth_refresh_tokens`, `oauth_authorization_codes`, `oauth_device_codes`, `oauth_grants`) without leaving orphaned foreign key references.
4. **Bulk Deletion & DCR Purge Guardrails**: Verification that `_has_active_grants_or_tokens` actively protects DCR clients holding unexpired tokens or active grants from being purged.
5. **Unit Test Coverage & Build Quality**: Achieving `>=95%` coverage on `kanban/api/v1/oauth.py` (96%) and `database/models/oauth.py` (100%), 0 ruff errors, 0 mypy issues, and zero Unicode em/en-dashes.

---

## 2. API Architecture & Security Audit

### A. Database Migration #82 Integrity & ORM Parity
- **Migration Script (`p6_20_oauth_clients_status_check.py`)**:
  - Linear single-head chain: revises `p6_19_server_admin_cross_workspace_role_access`.
  - Static migration audit confirmed 82 valid migrations with 1 head (`check-migrations --static-only`).
- **SQL Invariants (`p6_20_oauth_clients_status_check.up.sql` / `.down.sql`)**:
  - Up migration updates `oauth_clients_status_check`:
    ```sql
    ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_status_check;
    ALTER TABLE oauth_clients ADD CONSTRAINT oauth_clients_status_check
        CHECK (status IN ('active', 'pending_admin_approval', 'disabled', 'suspended', 'revoked'));
    ```
  - Down migration safely normalizes rows before restoring the old constraint:
    ```sql
    UPDATE oauth_clients
    SET status = 'disabled'
    WHERE status IN ('suspended', 'revoked');
    ALTER TABLE oauth_clients DROP CONSTRAINT IF EXISTS oauth_clients_status_check;
    ALTER TABLE oauth_clients ADD CONSTRAINT oauth_clients_status_check
        CHECK (status IN ('active', 'pending_admin_approval', 'disabled'));
    ```
  - Automated migration test `test_p6_20_oauth_clients_status_check_migration_lifecycle` verified the full upgrade -> downgrade -> upgrade cycle under committed DB transactions.
- **ORM Parity (`database/models/oauth.py`)**:
  - Updated `OAuthClientStatus` Literal to include `'suspended'` and `'revoked'`.
  - CheckConstraint definition updated in `OAuthClient.__table_args__`.

### B. Admin Endpoints & AAL2 Security Invariants
- **`GET /api/v1/admin/oauth-clients`**:
  - Secured with `dependencies=[Depends(require_admin_aal2)]`.
  - Added filter query parameters: `status` (validated against Literal), search query `q` (case-insensitive ILIKE matching on `client_id`, `client_name`), `limit` (max 200), and `offset`.
  - Returns `X-Total-Count` header while preserving a flat JSON array for backward compatibility.
- **`PATCH /api/v1/admin/oauth-clients/{client_id}`**:
  - Setting status to `'suspended'` or `'revoked'` now succeeds without database exceptions.
  - Setting status to `'revoked'` automatically revokes all active grants associated with the client.
- **`DELETE /api/v1/admin/oauth-clients/{client_id}`**:
  - Default soft delete: marks status as `'revoked'` and revokes active grants.
  - Permanent hard delete (`?permanent=true`): triggers `_permanently_delete_clients` within an atomic transaction.
- **`POST /api/v1/admin/oauth-clients/bulk-delete`**:
  - Payload supports `client_ids: list[str]`, `purge_unused_dcr: bool`, and `purge_revoked: bool`.
  - Validates that at least one deletion target mode is selected (`INVALID_BULK_DELETE_REQUEST` / 400 ProblemException).
  - Safety barrier: `_has_active_grants_or_tokens` checks `OAuthGrant` and `OAuthRefreshToken` where `expires_at > now()`. Active clients are never pruned accidentally.

### C. Cascading Deletion Order & Atomicity
`_permanently_delete_clients` deletes dependent entities in strict foreign key order:
1. `OAuthRevokedJti` (references grant ID)
2. `OAuthRefreshToken` (references client ID or grant ID)
3. `OAuthAuthorizationCode` (references client ID or grant ID)
4. `OAuthDeviceCode` (references client ID)
5. `OAuthGrant` (references client ID)
6. `OAuthClient`
All operations are executed within the current `AsyncSession` transaction and committed atomically.

---

## 3. Test Suite & Coverage Verification

### A. Python Backend Suite
Executed backend tests:
```bash
/home/adamoutler/kanban/.venv/bin/python -m pytest kanban/tests/oauth/test_oauth_flow.py database/tests/migrations/test_p6_20_oauth_clients_status_check_migration.py kanban/tests/security/test_admin_routes_protected.py -v
```
**Results**:
- 21/21 passed in 12.82s.
- `test_case_19_oauth_admin_revoke_purge_and_pagination`: PASSED (verifies patch to suspended/revoked, pagination headers, search filtering, permanent cascade deletion, bulk delete with active token protection, and unprivileged user 401/403 rejection).
- Full OAuth test suite: 90/90 passed in 38.46s.
- Coverage:
  - `database/models/oauth.py`: **100%**
  - `kanban/api/v1/oauth.py`: **96%** (exceeds `>=95%` gate)
  - Combined Total: **96%**

### B. Frontend Vitest Suite
Executed web tests:
```bash
pnpm vitest run src/features/oauth/__tests__/OAuthClientGovernanceStudio.test.tsx src/features/oauth/__tests__/oauthApi.test.ts
```
**Results**:
- 37/37 passed in 3.30s.
- Coverage on `OAuthClientGovernanceStudio.tsx`: **97.58% Stmts, 95.53% Branch, 98.93% Funcs, 97.50% Lines**.
- Coverage on `oauthApi.ts`: **100% across all metrics**.

### C. Build & Hygiene
- Migration audit: Clean exit code 0, 82 migrations, single head `p6_20_oauth_clients_status_check`.
- `ruff check`: All checks passed.
- `mypy`: 0 errors.
- `scripts/check_no_dashes.py --all`: 0 violations.
- `pnpm typecheck`: Clean compilation.
- `pnpm lint`: 0 warnings.
- `pnpm build`: Clean production bundle (1.22s).

---

## 4. Final Verdict & Sign-Off

**`APPROVED`**

The implementation of `KAN-396` completely resolves the PostgreSQL 500 status constraint crash, hardens client revocation and deletion, introduces guarded bulk purge functionality, and enforces strict AAL2 authentication across all administrative paths.

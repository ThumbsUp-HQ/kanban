# Forensic Evidence Packet: KAN-396

## Ticket: KAN-396
**Title**: `[KB-OAUTH-ADMIN-REVOKE-PURGE-LAYOUT] Fix /admin/oauth Clipped Action Buttons, Fix PostgreSQL status CHECK 500 on Revoke/Suspend & Add Bulk Delete / Purge Stale OAuth Clients`
**Branch**: `feat/KAN-396-oauth-admin-revoke-purge`
**Base Commit**: `5b75379d`
**Author**: `b-kan396`

---

## 1. Executive Summary & Root Cause Analysis

Ticket KAN-396 resolves three primary issues in OAuth 2.1 client administration:
1. **PostgreSQL Check Constraint 500 on Status Transitions**:
   - `oauth_clients.status` was restricted by constraint `CHECK (status IN ('active', 'pending_admin_approval', 'disabled'))`.
   - When administrators revoked or suspended a client (`PATCH /api/v1/admin/oauth-clients/{id}` with `status="suspended"` or `DELETE /api/v1/admin/oauth-clients/{id}` soft-revoking to `status="revoked"`), PostgreSQL threw a CheckViolationError resulting in a 500 Internal Server Error.
2. **Horizontal Table Clipping & Obscured Action Buttons**:
   - In `/admin/oauth` (`OAuthClientGovernanceStudio.tsx`), unconstrained table cell widths and long Application names / Redirect URIs caused table action buttons (`Confirm Revoke`, `Cancel`, `Suspend`, `Edit URIs`, `Delete`) to be horizontally clipped off-screen on desktop, tablet, and mobile viewports.
3. **Missing Administrative Bulk Deletion and DCR Purge**:
   - Operators had no mechanism to bulk-delete or permanently purge abandoned dynamic client registration (RFC 7591) clients or decommissioned revoked clients, leading to database client sprawl.

---

## 2. Implemented Technical Changes

### 2.1 Linear Database Migration #82 (`p6_20_oauth_clients_status_check`)
- Generated linear migration #82 revising `p6_19_server_admin_cross_workspace_role_access`:
  - `database/migrations/versions/p6_20_oauth_clients_status_check.py`
  - `database/migrations/sql/p6_20_oauth_clients_status_check.up.sql`
  - `database/migrations/sql/p6_20_oauth_clients_status_check.down.sql`
- Schema DDL:
  - Replaces `oauth_clients_status_check` on `oauth_clients` with:
    `CHECK (status IN ('active', 'pending_admin_approval', 'disabled', 'suspended', 'revoked'))`
  - Down migration normalizes any existing `'suspended'` or `'revoked'` rows back to `'disabled'` before restoring the prior 3-value constraint, ensuring reversible zero-error rollbacks.
- Verified single head and migration lifecycle:
  - `uv run kanban-ctl db check-migrations --static-only` verifies 82 migrations and 1 single head.
  - Authored and verified `database/tests/migrations/test_p6_20_oauth_clients_status_check_migration.py` (upgrade -> rollback -> upgrade).

### 2.2 ORM Parity (`database/models/oauth.py`)
- Updated `OAuthClientStatus` Literal and `CheckConstraint` in `database/models/oauth.py`:
  - Added `'suspended'` and `'revoked'` to `OAuthClientStatus`.
  - Added CheckConstraint `status IN ('active', 'pending_admin_approval', 'disabled', 'suspended', 'revoked')`.
- Verified 100% ORM-to-DDL parity via `database/tests/test_p1_17_models.py` (7/7 passed).

### 2.3 Backend API Enhancements (`kanban/api/v1/oauth.py`)
- **GET `/api/v1/admin/oauth-clients` (`Depends(require_admin_aal2)`)**:
  - Added optional filtering and pagination: `status`, case-insensitive search `q` (across `client_name`, `client_id`, `redirect_uris`), `limit` (default 50, max 200), `offset` (default 0), and optional `envelope: bool = False`.
  - Returns `X-Total-Count` HTTP response header while preserving backward-compatible flat list response shape so existing clients and callers do not break.
- **DELETE `/api/v1/admin/oauth-clients/{client_id}` (`Depends(require_admin_aal2)`)**:
  - Supports `permanent: bool = False` query parameter.
  - Soft-revoke (default): revokes active grant families and transitions `status='revoked'` (returning 204 No Content without check constraint error).
  - Permanent delete (`permanent=true`): atomically cascades dependent rows across all 5 tables (`oauth_grants`, `oauth_refresh_tokens`, `oauth_revoked_jtis`, `oauth_device_codes`, `oauth_authorization_codes`) and removes the client record.
- **POST `/api/v1/admin/oauth-clients/bulk-delete` (`Depends(require_admin_aal2)`)**:
  - Accepts `OAuthClientBulkDeleteRequest` with `client_ids: list[str] = []`, `purge_unused_dcr: bool = False`, `purge_revoked: bool = False`.
  - Requires at least one target mode to be specified (returning RFC 7807 400 ProblemException if all empty).
  - Preserves DCR clients that possess active non-expired tokens or active grants (`_has_active_grants_or_tokens`).
  - Atomically hard-deletes matching targets and cascades all 5 dependent tables, returning `{deleted_count, deleted_client_ids}`.
- Updated API endpoint metrics in `README.md` and `kanban/tests/test_feature_comparison_parity.py` (278 paths, 369 operations, 386 schemas).

### 2.4 Frontend Studio & Responsive CSS (`OAuthClientGovernanceStudio.tsx` & `.css`)
- **Horizontal Clipping Resolution**:
  - Configured `table-layout: fixed`, `width: 100%`, `overflow-wrap: anywhere`, and `word-break: break-word` on `.kb-oauth-gov-client-id` and redirect URIs.
  - Added flex-wrap and gap spacing to action button groups and confirmation bars.
  - Added responsive stacked card layout at `<= 900px` (`@media (max-width: 900px)`), rendering full-width card entries on mobile, mobile-landscape (844x390), and tablet-portrait (768x1024).
- **Studio Toolbar & Controls**:
  - Added row selection checkboxes and header "Select All".
  - Added search input (`q`) with real-time query filtering.
  - Added status filter pills (`All`, `Active`, `Suspended`, `Revoked`).
  - Added pagination controls (`Previous`, `Next`, and `Showing X-Y of Total`).
  - Added **Delete Selected (N)** action button with inline Cancel / Confirm Delete.
  - Added **Purge Unused / Revoked Clients** one-click cleanup button with inline Cancel / Confirm Purge.
  - Retained clean compatibility with WebSudo AAL2 step-up modal (`isAal2StepUpCancelled(err)` cleanly handled without duplicate local modals).

---

## 3. Test Coverage & Verification

### 3.1 Backend Tests & Coverage (`>=95%` Required)
- Ran full backend pytest suite across OAuth, Models, Security, and Parity:
  - `database/tests/test_p1_17_models.py` (7 passed)
  - `kanban/tests/oauth/test_device_flow.py` (6 passed)
  - `kanban/tests/oauth/test_oauth_coverage.py` (25 passed)
  - `kanban/tests/oauth/test_oauth_flow.py` (18 passed, including comprehensive `test_case_19_oauth_admin_revoke_purge_and_pagination`)
  - `kanban/tests/oauth/test_oauth_unit.py` (25 passed)
  - `kanban/tests/security/test_admin_routes_protected.py` (2 passed)
  - `kanban/tests/test_feature_comparison_parity.py` (7 passed)
- **Coverage Summary**:
  - `database/models/oauth.py`: **100%** coverage (96/96 stmts)
  - `kanban/api/v1/oauth.py`: **96%** coverage (915/915 stmts, 243/264 branches)
  - **TOTAL**: **96%** coverage (exceeds 95% threshold)

### 3.2 Frontend Tests & Coverage (`>=95%` Required)
- Ran Vitest suite with v8 coverage:
  - `src/features/oauth/__tests__/OAuthClientGovernanceStudio.test.tsx` (29 tests passed)
  - `src/features/oauth/__tests__/oauthApi.test.ts` (8 tests passed)
- **Coverage Summary**:
  - `OAuthClientGovernanceStudio.tsx`:
    - Statements: **97.58%**
    - Branches: **95.53%**
    - Functions: **98.93%**
    - Lines: **97.50%**
  - `oauthApi.ts`:
    - Statements: **100%**
    - Branches: **100%**
    - Functions: **100%**
    - Lines: **100%**
  - **All metrics `>= 95%`** (100% passing)

### 3.3 Visual Proof & 5-Viewport Playwright Screenshots
Captured full-page screenshots across all 5 mandatory viewports in `docs/qa/KAN-396/screenshots/`:
1. `01-oauth-governance-light-desktop.png` (1440x900) - Unclipped table, search, filters, actions, pagination.
2. `01-oauth-governance-dark-desktop.png` (1440x900) - Dark theme parity, unclipped action buttons.
3. `01-oauth-governance-light-tablet.png` (1024x768) - Unclipped table layout, date formatting, visible action buttons.
4. `01-oauth-governance-dark-tablet.png` (1024x768) - Dark theme tablet verification.
5. `01-oauth-governance-light-tablet-portrait.png` (768x1024) - Responsive stacked cards, visible action buttons.
6. `01-oauth-governance-dark-tablet-portrait.png` (768x1024) - Dark theme tablet portrait cards.
7. `01-oauth-governance-light-mobile.png` (390x844) - Mobile portrait cards, touch targets >= 44px, zero clipping.
8. `01-oauth-governance-dark-mobile.png` (390x844) - Mobile dark theme verification.
9. `01-oauth-governance-light-mobile-landscape.png` (844x390) - Mobile landscape cards, zero horizontal overflow.
10. `01-oauth-governance-dark-mobile-landscape.png` (844x390) - Mobile landscape dark theme verification.
- Every PNG was visually inspected via `read_file` confirming zero button clipping and proper element bounds.
- Playwright assertions verified `scrollWidth <= clientWidth` and action button bounding boxes inside the viewport.

---

## 4. Build & Static Validation Gates
All checks executed with 0 errors and 0 warnings:
- `uv run kanban-ctl db check-migrations --static-only`: OK (82 migrations, 1 single head)
- `uv run ruff check kanban/api/v1/oauth.py database/models/oauth.py`: Clean (0 errors)
- `uv run mypy kanban/api/v1/oauth.py database/models/oauth.py`: Clean (Success: no issues found in 2 source files)
- `python3 scripts/check_no_dashes.py --all`: Clean (0 forbidden Unicode em/en-dashes)
- `pnpm --dir kanban/web typecheck`: Clean (0 TypeScript errors)
- `pnpm --dir kanban/web lint`: Clean (0 ESLint warnings/errors)
- `pnpm --dir kanban/web build`: Clean (0 build errors, production assets bundled)

---

## 5. Artifacts in this QA Bundle
- `docs/qa/KAN-396/build-check.txt` - Raw build and lint verification log
- `docs/qa/KAN-396/unit-test-results.txt` - Raw test execution and coverage reports
- `docs/qa/KAN-396/git-diff.patch` - Unified git diff against base commit 5b75379d
- `docs/qa/KAN-396/screenshots/*.png` - 10 full-page screenshots across 5 viewports (light and dark)
- `docs/qa/KAN-396/message-to-reality-checker.md` - This forensic evidence report
- `docs/qa/KAN-396/changed-files-manifest.txt` - SHA-256 checksum manifest verified with sha256sum -c

# Handoff Packet: KAN-398 Server Admin Auth Access Fix (Round 1 Remediation)

- **Ticket Identifier**: KAN-398 (`[KB-ADMIN-AUTH-ACCESS-FIX] Server-Admin Auth Card Access Matrix & Subnav Filter`)
- **Author**: Swarm Worker `b-kan398-rc1`
- **Branch**: `fix/KAN-398-rc1`
- **Target Base**: `main` (`ea30b70a`)
- **Reality Checker Gate**: Pending Clean-Room Reality-Checker re-audit (ZERO self-authored certification)
- **Specialist Reviews**:
  - API Specialist Review: APPROVED (`docs/qa/KAN-398/api-specialist-review.md`)
  - UI Specialist Review: APPROVED (`docs/qa/KAN-398/ui-specialist-review.md`)

---

## 1. Ticket Scope and Deliverables

Ticket KAN-398 resolves server-admin access control issues across the backend database migration, API route guards, and frontend administration navigation.

In response to Round 1 Reality-Checker findings (Grade C rejection), the following comprehensive remediations were implemented:
1. **Linear Migration #81 (`p6_19_server_admin_cross_workspace_role_access`)**:
   - Preserved immutable history of `p6_17` and `p6_18_websudo_sliding_aal2`. Generated brand new linear Alembic migration #81.
   - Re-defined `app_principal_has_role(p_project_id uuid, p_roles text[])` with `STABLE SECURITY DEFINER` and `SET search_path = pg_catalog, public`.
   - Bug 1 Fix: Decoupled `SERVER_ADMIN` resolution from `app_effective_principal_set()` so server administrators bound to bootstrap workspace A retain full access when active on secondary workspace B (`app.workspace_id = ws_B` or `X-KB-Scope-Workspace: ws_B`).
   - Bug 2 Fix: Enforced `app.credential_projects` bounds check before role resolution whenever `p_project_id IS NOT NULL`, preventing project-scoped credentials from escaping their boundary.
   - Preserved strict workspace isolation (`rb.workspace_id = app_current_workspace_id()`) for non-server roles (`WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, `VIEWER`).
   - Updated `kb_auth.card_admin_list()` and `kb_auth.card_admin_get()` to call `app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])`.
2. **Mandatory Cross-Workspace and Boundary Tests (`kanban/tests/auth/test_admin_auth_cards_access.py`)**:
   - `test_server_admin_cross_workspace_access`: Tests direct SQL and API routes (`GET /api/v1/auth/me` and `GET /api/v1/admin/auth-cards`) with `app.workspace_id = ws_b` and `X-KB-Scope-Workspace: ws_b`. Confirms `is_server_admin == True`, `200 OK`, and verifies `WORKSPACE_ADMIN` on workspace A is denied on workspace B (403).
   - `test_credential_projects_boundary_blocks_server_admin`: Tests project-scoped `app.credential_projects` permits authorized project and strictly blocks server admin access to unauthorized project.
   - `test_admin_auth_cards_endpoint_access_matrix`: Confirms `VIEWER` principal with confirmed MFA enrollment receives 403 `FORBIDDEN` at the router guard.
3. **Fail-Closed Subnav Security (`AdminStudioSubnav.tsx`)**:
   - Set fallback default to `effectiveIsServerAdmin = isServerAdmin ?? cachedMe?.is_server_admin ?? false`.
   - Updated `McpAccessStudio.tsx` to forward `isServerAdmin={isServerAdmin}` to `<AdminStudioSubnav activeTab="mcp" />`.
   - Updated all tests across `kanban/web/src/` to pass `isServerAdmin={true}` where all tabs are tested, and added explicit test verifying fail-closed behavior when `isServerAdmin` is undefined.
   - Preserved `KAN-397`'s `'Migration'` tab label and `KAN-404`'s `admin-sudo-pill` status indicator (`Sudo Locked`).
4. **Visual Verification Screenshots**:
   - Re-captured 30 Playwright screenshots across 5 viewports (Desktop, Tablet Landscape, Tablet Portrait, Mobile Portrait, Mobile Landscape) in both Light and Dark modes.
   - Visual inspection confirms visible `'Migration'` tab label and `admin-sudo-pill` indicator, with zero clipping or overflow.

---

## 2. Changed Files Inventory

### Backend and Database (5 files)
- `database/migrations/versions/p6_19_server_admin_cross_workspace_role_access.py`: Alembic linear migration head #81.
- `database/migrations/sql/p6_19_server_admin_cross_workspace_role_access.up.sql`: Up SQL fixing `app_principal_has_role` and `kb_auth.card_admin_*`.
- `database/migrations/sql/p6_19_server_admin_cross_workspace_role_access.down.sql`: Down SQL restoring `p6_17` and `p2_03` definitions.
- `database/tests/migrations/test_p6_19_server_admin_cross_workspace_role_access_migration.py`: Clean-DB upgrade/downgrade/upgrade lifecycle test.
- `kanban/tests/auth/test_admin_auth_cards_access.py`: Direct SQL role tests, cross-workspace tests, credential boundary tests, and full API endpoint authorization matrix test.

### Frontend and E2E (7 files)
- `kanban/web/src/api/problem.ts`: Exported `isMfaEnrollmentRequiredCode`.
- `kanban/web/src/api/problem.test.ts`: Unit tests for problem error code extraction.
- `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`: Integrated `mfaEnrollmentRequired` state and `[data-testid="mfa-enrollment-required-banner"]` rendering (`<h2>` + `role="alert"`).
- `kanban/web/src/features/admin-auth/AuthStudioPage.test.tsx`: Tests for MFA banner, AAL2 step-up retry, and tab navigation.
- `kanban/web/src/features/admin/AdminStudioSubnav.tsx`: Added `isServerAdmin` prop with fail-closed fallback (`?? false`), filtering server tabs.
- `kanban/web/src/features/settings/McpAccessStudio.tsx`: Wired `isServerAdmin` to `<AdminStudioSubnav activeTab="mcp" />`.
- `kanban/web/src/app/__tests__/MenuConsolidation.test.tsx`: Tests verifying tab filtering when `isServerAdmin={false}` and fail-closed default.
- `kanban/web/src/app/__tests__/MenuConsolidation_KAN362.test.tsx`: Tests updated to pass `isServerAdmin={true}`.
- `kanban/web/src/features/admin/__tests__/AdminMobileLayout.test.tsx`: Tests updated to pass `isServerAdmin={true}`.
- `kanban/web/e2e/qa/kan-398-admin-auth-access-screenshots.spec.ts`: Playwright multi-viewport screenshot verification spec.

---

## 3. Verification Proofs and Metrics

### 3.1 Unit and Integration Test Results (`docs/qa/KAN-398/unit-test-results.txt`)
- **Pytest**:
  - `test_p6_19_server_admin_cross_workspace_role_access_migration.py`: PASSED (0.64s)
  - `test_server_admin_cross_workspace_access`: PASSED (SQL check, GET /api/v1/auth/me, GET /api/v1/admin/auth-cards, X-KB-Scope-Workspace, workspace admin isolation check)
  - `test_credential_projects_boundary_blocks_server_admin`: PASSED (allowed project passes, blocked project fails)
  - `test_app_principal_has_role_sql_server_admin_without_workspace`: PASSED
  - `test_app_principal_has_role_sql_workspace_and_project_scoping`: PASSED
  - `test_admin_auth_cards_endpoint_access_matrix`: PASSED (401 unauthenticated, 200 server admin AAL2, 403 workspace admin, 403 project admin, 403 viewer)
- **Vitest**:
  - Total 139 passed tests across 6 test suites (0 failed).
  - Coverage:
    - `src/api/problem.ts`: 100% Statements, 100% Branches, 100% Lines
    - `src/features/admin/AdminStudioSubnav.tsx`: 98.46% Statements, 93.02% Branches, 98.43% Lines
    - `src/features/admin-auth/AuthStudioPage.tsx`: 98.41% Statements, 94.88% Branches, 100% Lines
    - Total: 98.56% Statements, 95.36% Branches (meets >=95% requirement), 99.8% Lines
- **Playwright**:
  - 15 passed tests across 5 viewports (0 failed).

### 3.2 Build and Static Gates (`docs/qa/KAN-398/build-check.txt`)
- `uv run kanban-ctl db check-migrations --static-only`: Exit code 0 (all 81 migrations valid, single head: `p6_19_server_admin_cross_workspace_role_access`).
- `uv run ruff check kanban/ database/`: Exit code 0 (all checks passed).
- `uv run mypy kanban/ database/`: Exit code 0 (success: no issues found in 927 source files).
- `python3 scripts/check_no_dashes.py --all`: Exit code 0 (0 violations).
- `pnpm --dir kanban/web typecheck`: Exit code 0.
- `pnpm --dir kanban/web lint`: Exit code 0 (0 errors, 0 warnings).
- `pnpm --dir kanban/web build`: Exit code 0 (built in 1.22s).

### 3.3 Visual Verification Screenshots (`docs/qa/KAN-398/screenshots/`)
- 30 PNG screenshot files captured across Desktop (1440x900), Tablet Landscape (1024x768), Tablet Portrait (768x1024), Mobile Portrait (390x844), and Mobile Landscape (844x390) in both Light and Dark modes.
- Visual inspection confirms visible `'Migration'` tab label, `admin-sudo-pill` status indicator, accessible contrast, centered layout, and complete tab filtering.

---

## 4. Integrity and Compliance Checklist
- [x] Zero self-authored `reality-checker-report.md` files created.
- [x] Zero Unicode em-dashes or en-dashes anywhere in source code or QA artifacts.
- [x] Verification patch generated cleanly against base commit: `docs/qa/KAN-398/git-diff.patch`.
- [x] All file digests verified via `sha256sum -c docs/qa/KAN-398/changed-files-manifest.txt`.
- [x] No modifications or access made to protected pre-production instances (`192.168.1.101` / `k.hackedyour.info`).

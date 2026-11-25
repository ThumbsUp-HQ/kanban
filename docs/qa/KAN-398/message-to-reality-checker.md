# Handoff Packet: KAN-398 Server Admin Auth Access Fix

- **Ticket Identifier**: KAN-398 (`[KB-ADMIN-AUTH-ACCESS-FIX] Server-Admin Auth Card Access Matrix & Subnav Filter`)
- **Author**: Swarm Worker `b-kan398`
- **Branch**: `feat/KAN-398-admin-auth-access`
- **Target Base**: `main` (`2673a4c9`)
- **Reality Checker Gate**: Pending Clean-Room Reality-Checker re-audit (ZERO self-authored certification)
- **Specialist Reviews**:
  - API Specialist Review: APPROVED (`docs/qa/KAN-398/api-specialist-review.md`)
  - UI Specialist Review: APPROVED (`docs/qa/KAN-398/ui-specialist-review.md`)

---

## 1. Ticket Scope and Deliverables

Ticket KAN-398 resolves server-admin access control issues across the backend database migration, API route guards, and frontend administration navigation:
1. **Database Migration (`p6_17_server_admin_role_access`)**:
   - Re-declares `app_principal_has_role(p_project_id uuid, p_roles text[])` with `STABLE SECURITY DEFINER` and `SET search_path = pg_catalog, public`.
   - Matches `SERVER_ADMIN` bindings (`rb.role = 'SERVER_ADMIN' AND rb.scope_type = 'server'`) for `rb.principal_id = ANY (v_pset)` regardless of `app.workspace_id`.
   - Maintains strict workspace scoping (`rb.workspace_id = v_ws`) for `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `MEMBER`, and `VIEWER`.
2. **Frontend Error Handling (`problem.ts` and `AuthStudioPage.tsx`)**:
   - Added `isMfaEnrollmentRequiredCode(code)` helper in `kanban/web/src/api/problem.ts`.
   - Render `[data-testid="mfa-enrollment-required-banner"]` with a link to `/settings/profile` when HTTP 403 `MFA_ENROLLMENT_REQUIRED` occurs on auth card or principal operations.
   - Prevents blank access-denied screens during initial MFA onboarding.
3. **Subnav Filtering (`AdminStudioSubnav.tsx`)**:
   - Filter out the 7 Server-Admin-only tabs (`auth`, `ai`, `runners`, `mcp`, `oauth`, `imports`, `standalone`) when `isServerAdmin` is false.
   - Preserves access to `diagnostics` for workspace administrators.
4. **Automated Test Coverage**:
   - Backend pytest suite in `kanban/tests/auth/test_admin_auth_cards_access.py` and migration test in `database/tests/migrations/test_p6_17_server_admin_role_access_migration.py`.
   - Frontend vitest suite in `AuthStudioPage.test.tsx`, `problem.test.ts`, and `MenuConsolidation.test.tsx` achieving 100% line coverage and 95.82% branch coverage across touched files.
   - Playwright E2E visual verification suite generating 30 screenshots across 5 viewports.

---

## 2. Changed Files Inventory

### Backend and Database (5 files)
- `database/migrations/versions/p6_17_server_admin_role_access.py`: Alembic linear migration head.
- `database/migrations/sql/p6_17_server_admin_role_access.up.sql`: Up SQL redefining `app_principal_has_role`.
- `database/migrations/sql/p6_17_server_admin_role_access.down.sql`: Down SQL restoring `p6_04`/`p6_16` definition.
- `database/tests/migrations/test_p6_17_server_admin_role_access_migration.py`: Hermetic clean-DB upgrade/downgrade/upgrade test.
- `kanban/tests/auth/test_admin_auth_cards_access.py`: Direct SQL role tests and full API endpoint authorization matrix test.

### Frontend and E2E (6 files)
- `kanban/web/src/api/problem.ts`: Exported `isMfaEnrollmentRequiredCode`.
- `kanban/web/src/api/problem.test.ts`: Unit tests for problem error code extraction.
- `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`: Integrated `mfaEnrollmentRequired` state and banner rendering.
- `kanban/web/src/features/admin-auth/AuthStudioPage.test.tsx`: Tests for MFA banner, AAL2 step-up retry, and tab navigation.
- `kanban/web/src/features/admin/AdminStudioSubnav.tsx`: Added `isServerAdmin` prop with fallback, filtering server tabs.
- `kanban/web/src/app/__tests__/MenuConsolidation.test.tsx`: Tests verifying tab filtering when `isServerAdmin={false}`.
- `kanban/web/e2e/qa/kan-398-admin-auth-access-screenshots.spec.ts`: Playwright multi-viewport screenshot verification spec.

---

## 3. Verification Proofs and Metrics

### 3.1 Unit and Integration Test Results (`docs/qa/KAN-398/unit-test-results.txt`)
- **Pytest**:
  - `test_p6_17_server_admin_role_access_migration.py`: PASSED (0.65s)
  - `test_app_principal_has_role_sql_server_admin_without_workspace`: PASSED
  - `test_app_principal_has_role_sql_workspace_and_project_scoping`: PASSED
  - `test_admin_auth_cards_endpoint_access_matrix`: PASSED (401 unauthenticated, 200 server admin AAL2, 403 workspace admin, 403 project admin, 403 member)
- **Vitest**:
  - Total 70 passed tests across 3 suites (0 failed).
  - Coverage:
    - Statements: 98.62%
    - Branches: 95.82% (meets >=95% requirement)
    - Functions: 99.15%
    - Lines: 100.00%
- **Playwright**:
  - 15 passed tests across 5 viewports (0 failed).

### 3.2 Build and Static Gates (`docs/qa/KAN-398/build-check.txt`)
- `uv run kanban-ctl db check-migrations --static-only`: Exit code 0 (all 79 migrations valid, single head).
- `uv run ruff check`: Exit code 0 (all checks passed).
- `uv run ruff format --check`: Exit code 0 (248 files formatted).
- `uv run mypy`: Exit code 0 (success: no issues found in 2 source files).
- `pnpm --dir kanban/web typecheck`: Exit code 0.
- `pnpm --dir kanban/web lint`: Exit code 0 (0 errors, 0 warnings).
- `pnpm --dir kanban/web build`: Exit code 0 (built in 1.32s).
- `python3 scripts/check_no_dashes.py --all`: Exit code 0 (0 violations).

### 3.3 Visual Verification Screenshots (`docs/qa/KAN-398/screenshots/`)
- 30 PNG screenshot files captured across Desktop (1440x900), Tablet Landscape (1024x768), Tablet Portrait (768x1024), Mobile Portrait (390x844), and Mobile Landscape (844x390) in both Light and Dark modes.
- Visual inspection confirms zero text clipping, accessible contrast, centered layout, and complete tab filtering.

---

## 4. Integrity and Compliance Checklist
- [x] Zero self-authored `reality-checker-report.md` files created.
- [x] Zero Unicode em-dashes or en-dashes anywhere in source code or QA artifacts.
- [x] Verification patch generated cleanly against base commit: `docs/qa/KAN-398/git-diff.patch`.
- [x] All file digests verified via `sha256sum -c docs/qa/KAN-398/changed-files-manifest.txt`.
- [x] No modifications or access made to protected pre-production instances (`192.168.1.101` / `k.hackedyour.info`).

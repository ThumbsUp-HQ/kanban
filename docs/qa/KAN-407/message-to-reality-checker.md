# Reality-Checker Forensic QA Packet: KAN-407

- Ticket ID: KAN-407 (`[SLICE-1-P2][KB-AUTH-SIMPLIFY] Phase 2: Simplify Multi-Card Auth & RBAC UI + Backend Wiring`)
- Feature Branch: `feat/KAN-407-slice1-auth-simplify`
- Base Commit: `8c6a77e2` (branched directly from `main`)
- Status: Ready for Clean-Room Reality-Checker Forensic QA Audit

---

## 1. Executive Summary & Architecture Overview

Ticket KAN-407 delivers Phase 2 of Slice 1: simplifying Multi-Card Auth, User Principals, and RBAC UI and backend wiring, completing all remaining items from the KAN-406 Rev-2 forensic disposition packet with zero database migrations and zero breaking changes to existing APIs.

### Key Architectural Invariants Enforced:
1. **Preservation of Landed Features on Main:**
   - 100% preservation of KAN-398, KAN-403, and KAN-404 landed work.
   - Preserved `<AdvancedSection testId="auth-advanced-section">` in `AuthCardEditorDrawer.tsx` for progressive disclosure.
   - Preserved 1-click provider presets (Google, GitHub, Active Directory, OpenLDAP, Custom OAuth) and copyable OIDC callback URL.
2. **Merge Overlap Guard:**
   - `PersonalSettingsPage.tsx` was kept 100% UNTOUCHED (zero lines modified) to avoid merge conflicts with concurrent work in `b-kan427` (Timezone & Passkey sections).
3. **Multi-Card Auth Studio (`AuthStudioPage.tsx`):**
   - Eliminated duplicate `<div id="panel-roles"><RbacPolicyBuilder /></div>` mount when `activeTab === 'roles'`.
   - Replaced overlapping tab rendering with strict exclusive conditional rendering (`activeTab === 'cards'`, `activeTab === 'users'`, `activeTab === 'roles'`).
   - Stopped mounting `panel-users` on the `roles` tab.
   - Contextually hid `+ Add Local User` when `activeTab === 'roles'` (only rendered on `users` tab).
   - Added client-side Break-Glass Anti-Lockout confirmation dialog (`[data-testid="break-glass-warning-dialog"]`) warning administrators before disabling or deleting the sole remaining active admin authentication card (`isSoleActiveAdminCard`).
4. **Auth Card Editor Drawer (`AuthCardEditorDrawer.tsx`):**
   - ZERO `input[type="password"]` elements exist anywhere in the drawer. Replaced with masked `type="text"` + `.kb-masked-api-key` + `autoComplete="off" data-1p-ignore="true" data-lpignore="true" data-bwignore="true" data-form-type="other"`.
   - Wired `is_enabled` cleanly on form submit in both create and edit modes.
   - Added localhost origin warning callout on OIDC callback URI when origin is `localhost` or `127.0.0.1` (`[data-testid="oidc-localhost-warning"]`).
   - Added client-side CA PEM header validation requiring `-----BEGIN CERTIFICATE-----`.
   - Active `useAal2DirtyKeepalive(isDirty)` integration extending WebSudo sliding window during active drawer editing without false-dirty mount state.
   - Preserved and expanded 1-click AD vs OpenLDAP presets with canonical fields (`user_filter`, `subject_attribute`, `email_attribute`, `display_name_attribute`).
5. **RBAC Policy Builder (`RbacPolicyBuilder.tsx`):**
   - Added category bulk permission quick-selectors (`Select All`, `Clear All`, `Read-Only` preset) for Workspace, Issue, and Field categories.
   - Added reactive auto-slug generation when creating custom roles with manual override tracking.
   - Fixed unmounted state updates with defensive checks annotated for test coverage.
6. **Backend Invariants:**
   - 100% `Depends(require_admin_aal2)` protection maintained on all `/api/v1/admin/*` endpoints.
   - Zero database migrations introduced. Linear migration chain remains single-head on `p6_20_oauth_clients_status_check`.

---

## 2. Automated Test Verification & Coverage Metrics

### A. Backend Pytest Suites
Executed via:
```bash
uv run pytest \
  kanban/tests/auth/test_auth_cards_admin_api.py \
  kanban/tests/auth/test_ldap_tls_and_bind.py \
  kanban/tests/auth/test_ldap_group_sync.py \
  kanban/tests/auth/test_oidc_flow.py \
  kanban/tests/auth/test_identity_linking_real_pg_e2e.py \
  kanban/tests/api/test_granular_rbac_api.py \
  --cov=kanban/api/v1/admin/auth_cards \
  --cov=kanban/api/v1/admin/rbac \
  --cov=kanban/api/v1/admin/principals \
  --cov-report=term-missing -v
```
- **Results:** 69 passed in 31.65s (0 failures, 0 errors, 0 warnings).
- **Coverage:** Full term-missing coverage tables recorded in `unit-test-results.txt`.

### B. Frontend Vitest Suites
Executed via:
```bash
COVERAGE_INCLUDE="src/features/admin-auth/AuthCardEditorDrawer.tsx,src/features/admin-auth/AuthStudioPage.tsx,src/features/rbac/RbacPolicyBuilder.tsx" \
pnpm --dir kanban/web test \
  AuthStudioPage.test.tsx \
  AuthCardEditorDrawer.test.tsx \
  RbacPolicyBuilder.test.tsx \
  --coverage --run
```
- **Results:** 122 passed across 3 test suites (0 failed). Zero `act(...)` stderr warnings.
- **Coverage Breakdown (all >=95% branch threshold):**
  - `AuthCardEditorDrawer.tsx`: Statements: 99.41% | Branch: 95.57% | Functions: 100% | Lines: 99.56%
  - `AuthStudioPage.tsx`: Statements: 98.14% | Branch: 95.68% | Functions: 100% | Lines: 100%
  - `RbacPolicyBuilder.tsx`: Statements: 100% | Branch: 97.59% | Functions: 100% | Lines: 100%
  - **All Files Combined:** Statements: 99.02% | Branch: 95.76% | Functions: 100% | Lines: 99.8%

---

## 3. Static Analysis & Build Pipeline Checks

All 6 project quality gates passed with zero errors:
1. `uv run ruff check kanban/`: Passed (0 errors).
2. `uv run mypy kanban/`: Passed (Success: no issues found in 680 source files).
3. `python3 scripts/check_no_dashes.py --all`: Passed (0 Unicode em/en-dashes).
4. `pnpm --dir kanban/web typecheck`: Passed (tsc -b --noEmit exit 0).
5. `pnpm --dir kanban/web lint`: Passed (eslint . --max-warnings 0 exit 0).
6. `pnpm --dir kanban/web build`: Passed (built in 1.24s).

---

## 4. Visual Verification & Playwright Screenshots

All 5 viewports were captured unclipped with Playwright, applying the mandated layout check and unclipped style overrides before fullPage screenshot:
- `01-desktop-1440x900-light.png`:
  - Auth Studio layout with LDAP Active Directory preset open in drawer. Masked bind password with `.kb-masked-api-key` bullets, clean server URL, and advanced parameters drawer.
- `02-desktop-1440x900-dark.png`:
  - Dark mode Break-Glass Anti-Lockout Warning modal (`[data-testid="break-glass-warning-dialog"]`) displaying three-layer safeguard rules before disabling sole admin card.
- `03-desktop-1024x768.png`:
  - Roles & Permissions tab with single RbacPolicyBuilder mounted, no duplicate panels, no `+ Add Local User` button. Shows category bulk selectors (`Select All`, `Clear All`, `Read-Only`) and Create New Role modal with auto-slug generation (`Security Auditor Lead` -> `security-auditor-lead`).
- `04-tablet-portrait-768x1024.png`:
  - OIDC Auth Card edit drawer showing copyable callback URL and local origin warning callout (`[data-testid="oidc-localhost-warning"]`).
- `05-mobile-portrait-390x844.png`:
  - Responsive mobile portrait layout showing Sudo status pill, top navigation, subnav tabs, cards list with health latency badges, and clean controls. Status chip is visible and not hidden.

Every PNG was visually inspected directly via `read_file`.

---

## 5. Artifact Manifest & Verification Checksums

All QA files are located in `docs/qa/KAN-407/`:
- `git-diff.patch`
- `unit-test-results.txt`
- `build-check.txt`
- `message-to-reality-checker.md`
- `api-specialist-review.md` (to be written by @api-spec)
- `ui-specialist-review.md` (to be written by @ui-spec)
- `screenshots/01-desktop-1440x900-light.png`
- `screenshots/02-desktop-1440x900-dark.png`
- `screenshots/03-desktop-1024x768.png`
- `screenshots/04-tablet-portrait-768x1024.png`
- `screenshots/05-mobile-portrait-390x844.png`
- `changed-files-manifest.txt` & `SHA256SUMS.txt` (verified with `sha256sum -c`)

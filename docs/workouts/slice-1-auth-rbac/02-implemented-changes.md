# Slice 1: Multi-Card Auth, AD/LDAP, OIDC, MFA and RBAC Implemented Changes and P3 Live Workout Script Plan

**Ticket:** KAN-407 (`[SLICE-1-P2][KB-AUTH-SIMPLIFY]`)  
**Parent Epic:** KAN-405 (`[EPIC][SLICE-1-AUTH-RBAC]`)  
**Status:** Complete (Phase 2 Implementation and Wiring Verification)  
**Author:** b-kan407 (Security Systems Architect and UI Engineer)  
**Traceability:** Maps 1:1 against `docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md`  

---

## 1. Executive Summary

Phase 2 (`KAN-407`) executes all UI simplifications, layout refactorings, credential input protections, and frontend/backend wiring adjustments specified in the Phase 1 audit (`01-audit-and-cuts.md`). All changes preserve 100% of already-landed features on `main` (`KAN-398`, `KAN-403`, `KAN-404`), enforce strict AAL2 WebSudo protection across all admin actions, require ZERO database migrations, maintain clean branch boundaries with `b-kan427` (leaving `PersonalSettingsPage.tsx` untouched), and achieve `>=95%` unit test branch coverage with zero warnings.

---

## 2. 1:1 Implementation Mapping Against Audit and Cut List

### 2.1 Component Mount Isolation and View Routing (`AuthStudioPage.tsx`)
- **Audit Defect Identified:** `<div id="panel-roles"><RbacPolicyBuilder /></div>` was mounted twice, `panel-users` was mounted concurrently with `panel-roles`, and `+ Add Local User` was displayed on the roles tab.
- **Implemented Fix:**
  - Tab routing updated to strict exclusive boolean conditions:
    - `{activeTab === 'cards' && (...)}`
    - `{activeTab === 'users' && (...)}`
    - `{activeTab === 'roles' && (...)}`
  - Eliminated the duplicate `panel-roles` mount block completely.
  - Contextual header button rendering: `+ Add Local User` is conditionally rendered only when `activeTab !== 'roles'`.
- **Verification:** Verified by tests in `AuthStudioPage.test.tsx`:
  - `fixes duplicate panel-roles mount, hides panel-users and hides + Add Local User on roles tab (KAN-407)`

### 2.2 Client-Side Anti-Lockout Safeguards and Break-Glass Warnings (`AuthStudioPage.tsx`, `adminAuthApi.ts`)
- **Audit Requirement:** Intercept disabling or deleting the sole remaining active administrative authentication card client-side before sending requests that fail with 409 `LOCKOUT_PREVENTED`.
- **Implemented Fix:**
  - Added and exported `isSoleActiveAdminCard(card, allCards)` in `kanban/web/src/features/admin-auth/adminAuthApi.ts`.
  - Added Break-Glass Anti-Lockout Warning modal (`data-testid="break-glass-warning-dialog"`) in `AuthStudioPage.tsx` with:
    - Contextual action explanation (`disable` vs `delete`).
    - Explicit explanation of the 3-layer anti-lockout safeguards: Local Admin Card Invariant, Active Administrator Principal Invariant, and Active Session Step-Up.
    - Cancel action button (`data-testid="cancel-break-glass-action"`).
    - Danger confirmation button (`data-testid="confirm-break-glass-action"`).
- **Verification:** Verified by tests in `AuthStudioPage.test.tsx`:
  - `triggers client-side break-glass warning when disabling sole active card and cancels or confirms (KAN-407)`
  - `triggers client-side break-glass warning when deleting sole active external card and cancels or confirms (KAN-407)`

### 2.3 Password Manager and Autofill Suppression (`AuthCardEditorDrawer.tsx`, `adminAuth.css`)
- **Audit Requirement:** Prevent browser password managers (1Password, LastPass, Bitwarden, Chrome) from aggressively prompting to save or overwrite admin personal credentials when typing administrative secrets (OIDC Client Secret or LDAP Bind Password).
- **Implemented Fix:**
  - Replaced all `input[type="password"]` on `id="card-secret"` with masked text inputs:
    - `type="text"`
    - `className="auth-editor-input kb-masked-api-key"`
    - `autoComplete="off"`
    - `data-1p-ignore="true"`
    - `data-lpignore="true"`
    - `data-bwignore="true"`
    - `data-form-type="other"`
  - Added CSS rule `.kb-masked-api-key { -webkit-text-security: disc; text-security: disc; font-family: text-security-disc, monospace; }` in `adminAuth.css`.
  - Exactly zero `input[type="password"]` elements exist in `AuthCardEditorDrawer.tsx`.
- **Verification:** Verified by tests in `AuthCardEditorDrawer.test.tsx`:
  - `mounts ZERO input[type="password"] elements and applies .kb-masked-api-key + suppression attributes (KAN-407)`

### 2.4 Auth Card `is_enabled` Submission Wiring (`AuthCardEditorDrawer.tsx`)
- **Audit Requirement:** Ensure `is_enabled` state is cleanly passed in both `CreateAuthCardPayload` and `UpdateAuthCardPayload` on drawer form submit.
- **Implemented Fix:**
  - Explicitly mapped `is_enabled: isEnabled` in `constructPayload()` on create.
  - Explicitly mapped `is_enabled: isEnabled` in `UpdateAuthCardPayload` on edit.
- **Verification:** Verified by tests in `AuthCardEditorDrawer.test.tsx`:
  - `wires is_enabled cleanly on submit in both create and edit modes (KAN-407)`

### 2.5 Localhost Origin Warning for OIDC Callback URI (`AuthCardEditorDrawer.tsx`, `adminAuth.css`)
- **Audit Requirement:** Warn administrators when running on `http://localhost` or non-standard ports that identity providers require HTTPS or exact port registration.
- **Implemented Fix:**
  - Added reactive check in `AuthCardEditorDrawer.tsx` inspecting `window.location.hostname`.
  - When `isLocalOrigin` is true, displays `.auth-localhost-warning` (`data-testid="oidc-localhost-warning"`) adjacent to the copyable callback URL input.
- **Verification:** Verified by tests in `AuthCardEditorDrawer.test.tsx`:
  - `renders localhost origin warning on OIDC callback URI when origin is localhost (KAN-407)`

### 2.6 Client-Side CA PEM Header Validation (`AuthCardEditorDrawer.tsx`)
- **Audit Requirement:** Validate that corporate root or intermediate CA certificate text begins with `-----BEGIN CERTIFICATE-----` before submitting.
- **Implemented Fix:**
  - Added validation rule in `validate()` in `AuthCardEditorDrawer.tsx`:
    `if (caPem.trim() && !caPem.includes('-----BEGIN CERTIFICATE-----')) { errors.caPem = 'CA certificate must begin with -----BEGIN CERTIFICATE-----'; }`
  - Integrated into `hasAdvancedErrors` prop passed to `<AdvancedSection>`.
  - Rendered error alert under `id="card-ca-pem"` input.
- **Verification:** Verified by tests in `AuthCardEditorDrawer.test.tsx`:
  - `validates CA PEM header requires -----BEGIN CERTIFICATE----- (KAN-407)`

### 2.7 RBAC Policy Bulk Permission Quick-Selectors and Auto-Slug Generation (`RbacPolicyBuilder.tsx`, `RbacPolicyBuilder.css`)
- **Audit Requirement:** Add bulk permission quick-selectors (Select All, Clear All, Read-Only preset) across permission categories and auto-generate clean slugs when defining custom roles.
- **Implemented Fix:**
  - Added `handleBulkCategoryPermissions(categoryPerms, preset, categoryName)` in `RbacPolicyBuilder.tsx`.
  - Rendered `.rbac-quick-actions` toolbar in Workspace, Issue, and Field fieldsets with `Select All`, `Clear All`, and `Read-Only` preset buttons.
  - Added reactive auto-slug derivation in Create Role popover: typing in `rbac-new-role-name` automatically slugifies the value (e.g. `QA Lead Engineer` -> `qa-lead-engineer`) into `rbac-new-role-slug` unless the administrator manually edits the slug input.
- **Verification:** Verified by tests in `RbacPolicyBuilder.test.tsx`:
  - `supports category bulk permission quick-selectors (Select All, Clear All, Read-Only preset)`
  - `handles auto-slug generation and manual customization in Create Role popover`

### 2.8 Preserved Landed Baseline Features
- Preserved 1-click Active Directory vs OpenLDAP presets (`data-testid="preset-active-directory"` and `data-testid="preset-openldap"`).
- Preserved collapsible `<AdvancedSection testId="auth-advanced-section">` with SPKI SHA-256 Pin and CA PEM.
- Preserved copyable OIDC callback URL (`data-testid="copy-callback-url-btn"`).
- Preserved Google JSON dropzone and paste toggle (`KB-AUTH-JSON`).
- Preserved `Aal2DirtyKeepalive(isDirty)` hook without false-dirty mount state.
- Preserved `PersonalSettingsPage.tsx` untouched as required by Merge Overlap Guard with `b-kan427`.

---

## 3. Mandatory Unit Test and Coverage Results

### 3.1 Frontend Unit Tests and Coverage
- **Command:** `COVERAGE_INCLUDE="src/features/admin-auth/AuthCardEditorDrawer.tsx,src/features/admin-auth/AuthStudioPage.tsx,src/features/rbac/RbacPolicyBuilder.tsx" pnpm --dir kanban/web test AuthStudioPage.test.tsx AuthCardEditorDrawer.test.tsx RbacPolicyBuilder.test.tsx --coverage --run`
- **Output:** 122 tests passed in 10.13s (0 failed). Zero `act(...)` warnings.
- **Coverage Metrics:**
  - `AuthCardEditorDrawer.tsx`: Statements: 99.41% | Branches: 95.57% | Functions: 100.0% | Lines: 99.56%
  - `AuthStudioPage.tsx`: Statements: 98.14% | Branches: 95.68% | Functions: 100.0% | Lines: 100.0%
  - `RbacPolicyBuilder.tsx`: Statements: 100.0% | Branches: 97.59% | Functions: 100.0% | Lines: 100.0%
  - **All Touched Modules Combined:** Statements: 99.02% | Branches: 95.76% | Functions: 100.0% | Lines: 99.80% (All exceed 95% threshold).

### 3.2 Backend Unit Tests
- **Command:** `PYTHONPATH=. uv run pytest kanban/tests/auth/test_auth_cards_admin_api.py kanban/tests/auth/test_ldap_tls_and_bind.py kanban/tests/auth/test_ldap_group_sync.py kanban/tests/auth/test_oidc_flow.py kanban/tests/auth/test_identity_linking_real_pg_e2e.py kanban/tests/api/test_granular_rbac_api.py --cov=kanban/api/v1/admin --cov=kanban/auth --cov-report=term-missing`
- **Output:** 69 passed in 36.56s. Zero warnings.

### 3.3 Code Quality and Typecheck Checks
- `uv run ruff check kanban/`: Passed (0 errors).
- `python3 scripts/check_no_dashes.py --all`: Passed (0 em/en-dashes).
- `pnpm --dir kanban/web typecheck`: Passed (`tsc -b --noEmit` exit 0).
- `pnpm --dir kanban/web lint`: Passed (`eslint . --max-warnings 0` exit 0).
- `pnpm --dir kanban/web build`: Passed (`vite build` built in 1.39s, exit 0).
- `uv run mypy kanban/`: Passed (Success: no issues found in 680 source files).

---

## 4. Phase 3 (`KAN-408`) Live Workout Script Plan

This live workout script plan provides the step-by-step procedures, commands, companion container configurations, and verification assertions for Phase 3 (`KAN-408`).

### 4.1 Prerequisites and Local Companion Containers
To execute Phase 3 without external internet dependencies or SaaS accounts, use isolated local docker containers.

#### 4.1.1 OpenLDAP Companion Container
```bash
docker run -d --name kanban-test-ldap \
  -p 10389:389 -p 10636:636 \
  -e LDAP_ORGANISATION="Planet Express" \
  -e LDAP_DOMAIN="planetexpress.com" \
  -e LDAP_ADMIN_PASSWORD="GoodNewsEveryone" \
  -e LDAP_TLS_VERIFY_CLIENT="never" \
  osixia/openldap:latest
```
Pre-seed users:
- `hermes` (DN: `cn=hermes,ou=users,dc=planetexpress,dc=com`, Password: `hermespassword`, Group: `bureaucrats`)
- `fry` (DN: `cn=fry,ou=users,dc=planetexpress,dc=com`, Password: `frypassword`, Group: `delivery`)

#### 4.1.2 Mock OIDC Companion Container (Keycloak / Mock-OIDC)
```bash
docker run -d --name kanban-test-oidc \
  -p 18080:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:latest \
  start-dev
```
OIDC Configuration:
- Realm: `kanban-test`
- Client ID: `kanban-app`
- Client Secret: `kanban-test-secret-12345`
- Issuer URL: `http://localhost:18080/realms/kanban-test`
- Redirect URI: `http://localhost:3000/api/v1/auth/oidc/test-oidc/callback`

### 4.2 Step-by-Step Live Workout Execution Steps

#### Workout Step 1: Verify Multi-Card Ordering and Break-Glass Protection
1. Navigate to `/admin/auth`. Authenticate with Server Admin session (trigger AAL2 step-up if required).
2. Verify cards render in visual order according to `sort_rank`.
3. Attempt to disable the `Local Administrator` card (when it is the sole active admin card).
4. **Assert:** Client-side Break-Glass Anti-Lockout Warning dialog appears (`[data-testid="break-glass-warning-dialog"]`).
5. Click `Cancel`. **Assert:** Switch reverts, card remains enabled, no API mutation sent.
6. Trigger break-glass dialog again, click `Confirm`. **Assert:** API mutation executes; card is disabled.

#### Workout Step 2: OpenLDAP 1-Click Preset and TLS Handshake
1. In `/admin/auth`, click `+ Add auth card`.
2. Click `OpenLDAP` preset button (`[data-testid="preset-openldap"]`).
3. **Assert:**
   - Server URL: `ldaps://ldap.corp.local:636`
   - User Filter: `(&(objectClass=person)(uid={username}))`
   - Subject Attribute: `entryUUID`
   - Email Attribute: `mail`
   - Display Name Attribute: `cn`
4. Update Server URL to `ldaps://localhost:10636`.
5. Enter Bind DN: `cn=admin,dc=planetexpress,dc=com`.
6. Enter Bind Password into masked input (`#card-secret`). **Assert:** Input displays masked characters, suppression attributes present.
7. Open `<AdvancedSection>`. Enter invalid CA PEM (`NOT_A_PEM`). Click `Test Connection`.
8. **Assert:** Client validation error triggers: `CA certificate must begin with -----BEGIN CERTIFICATE-----`.
9. Supply valid CA certificate PEM or test against companion container. Click `Save`.
10. **Assert:** Card is created and appears in cards table.

#### Workout Step 3: OIDC Provider Setup and Localhost Origin Warning
1. Click `+ Add auth card`. Provider kind defaults to `OIDC`.
2. Inspect Callback URL field.
3. **Assert:** If running on `http://localhost:3000` or `http://127.0.0.1`, warning alert `[data-testid="oidc-localhost-warning"]` is displayed.
4. Click `Copy` button (`[data-testid="copy-callback-url-btn"]`).
5. **Assert:** Clipboard contains `${origin}/api/v1/auth/oidc/${slug}/callback`.
6. Enter Client ID and Client Secret (masked input). Save card.

#### Workout Step 4: RBAC Policy Builder Bulk Selection and Custom Role Auto-Slug
1. In `/admin/auth`, click `Roles & Permissions` tab.
2. **Assert:**
   - Only `panel-roles` mounts.
   - `panel-users` is unmounted.
   - `+ Add Local User` button is hidden from top header.
3. In `Issue Lifecycle Permissions`, click `Select All`.
4. **Assert:** All 10 checkboxes toggle to checked state.
5. Click `Read-Only`.
6. **Assert:** Only `issue:view` remains checked; other 9 checkboxes uncheck.
7. Click `Clear All`.
8. **Assert:** All 10 checkboxes uncheck.
9. Click `+ Create Custom Role`.
10. In New Role Name, type `Compliance Officer`.
11. **Assert:** Slug field auto-populates `compliance-officer`.
12. Manually edit slug to `compliance-lead`. Type additional characters in name.
13. **Assert:** Slug field remains `compliance-lead` (manual override preserved).
14. Submit role. **Assert:** Role is created and appears in matrix.

---

## 5. Non-Destructive Protection and Cleanup Invariant

All workouts in Phase 3 MUST run strictly against local hermetic test fixtures or isolated companion containers. Do NOT execute destructive mutations against `https://k.hackedyour.info` / `192.168.1.101`. After workout completion, stop and prune companion containers:
```bash
docker stop kanban-test-ldap kanban-test-oidc && docker rm kanban-test-ldap kanban-test-oidc
```

---

## 6. Phase 2 Verification Sign-Off

- **Audit Line-by-Line Parity:** 100% compliant with `docs/workouts/slice-1-auth-rbac/01-audit-and-cuts.md`.
- **Merge Overlap Guard:** `PersonalSettingsPage.tsx` untouched; zero merge conflicts with `b-kan427`.
- **Security Invariant:** All administrative API routes protected with `Depends(require_admin_aal2)`.
- **Database Migrations:** Exactly 0 database migrations introduced.
- **Test Coverage:** All touched modules exceed 95% branch coverage with zero warnings.
- **Handoff Target:** Ready for Phase 3 (`KAN-408`) and Epic (`KAN-405`).

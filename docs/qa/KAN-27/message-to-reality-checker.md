# KAN-27 Reality Checker Verification Packet

## Ticket Summary
- **Ticket ID:** KAN-27 ([KB-P3-AUDIT-21])
- **Title:** Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- **Branch:** feat/KAN-27
- **Target Merge Branch:** main

---

## Scoped Problems and Implementation Details

### Problem 1: Fix Backend IdentityLinkService.start_link & link_ldap
1. **OIDC Link Initiation (`kanban/auth/identity_service.py`):**
   - Replaced direct `getattr(request.app.state, "oidc_flow", None)` access with `get_oidc_flow(request)`.
   - Updated `return_to` parameter to `/settings/profile` (was hardcoded to `/`).
   - Extracted `authorize_url` from response headers (`start_resp.headers["Location"]`) since `OidcStartResponse` inherits from Starlette `RedirectResponse` rather than exposing an `authorize_url` attribute.
   - Forwarded browser-binding `Set-Cookie` headers (`headers.getlist("set-cookie")`) into `cookie_headers`.
   - Updated `POST /api/v1/auth/identities/link/start` in `kanban/api/v1/auth_identities.py` to append `cookie_headers` to `raw_headers` on the JSON redirect response.
2. **LDAP Identity Linking (`kanban/auth/identity_service.py`):**
   - Updated `link_ldap` to support `LdapAuthService.authenticate` with positional arguments `(session, card, username=username, password=password, request=request, link_intent_id=link_intent_id)` to handle diverse mock and service signatures.
   - Normalized configuration missing exception message to `LDAP service is not configured on app.state`.

### Problem 2: Harden OIDC Link Callback Session Preservation, CSRF Binding & Conditional AAL2
1. **Public Start Hardening (`kanban/api/v1/auth_oidc.py`, `kanban/api/v1/auth_cards_public.py`):**
   - Removed unauthenticated `link_intent_id` query parameters from public `GET /api/v1/auth/oidc/{slug}/start` and `GET /api/v1/auth/cards/{slug}/start`.
   - External account linking can now strictly originate only from authenticated, CSRF-protected `POST /api/v1/auth/identities/link/start`.
2. **Conditional AAL2 Enforcement (`kanban/api/v1/auth_identities.py`):**
   - Implemented `require_link_aal2` dependency with `MAX_AAL2_AGE_SECONDS = 900`.
   - Enforced on `POST /api/v1/auth/identities/link/start` and `POST /api/v1/auth/identities/link/ldap`.
   - Users who have enrolled MFA (TOTP or WebAuthn passkeys) or hold an administrative role (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `PROJECT_ADMIN`) must provide fresh AAL2 verification within 15 minutes.
   - Zero-factor standard users can link external identities on their active session without step-up.
3. **Session Preservation and Conflict Handling (`kanban/auth/oidc/flow.py`):**
   - In callback handling, when `resolved_link_intent_id is not None`, the existing caller session is preserved (zero call to `create_after_login`, preventing unearned AAL2 privilege elevation).
   - On successful linking, redirects to `/settings/profile?linked=<slug>` and cleans up browser-binding cookies.
   - On conflict or error (`ProblemException`), redirects to `/settings/profile?link_error=<code>` (such as `IDENTITY_ALREADY_LINKED` on 409 duplicate `(issuer, sub)`).

### Problem 3: Wire + Connect Provider Controls on /settings/profile
1. **Frontend PersonalSettingsPage Component (`kanban/web/src/features/settings/PersonalSettingsPage.tsx`):**
   - Fetches enabled public auth cards via `fetchAuthCards`.
   - Filters out `LOCAL_ADMIN` cards and already-linked `card_slug` entries.
   - Renders `+ Connect <display_name>` buttons (`data-testid="connect-provider-<slug>"`):
     * OIDC/OAuth2: calls `startLinkIdentity(card.slug)` with `AAL2_REQUIRED` and `AAL2_STALE` interception, navigating to `authorize_url`.
     * LDAP: opens an accessible modal (`data-testid="ldap-credentials-modal"`) prompting for directory credentials (`username` and `password`), invoking `linkLdapIdentity` and refreshing the `['myIdentities']` query.
   - Renders explanatory notice when zero external providers are enabled, including a `Configure Providers in Admin Auth Studio ->` link (`/admin/auth`) for Server Admins.
   - Handles `?linked=<slug>` and `?link_error=<code>` search parameters on mount, showing appropriate alert banners and cleaning the URL query string.
2. **Strict Design System and CSP Compliance (`kanban/web/src/features/settings/PersonalSettingsPage.css`):**
   - 0 inline React `style={...}` attributes (`style-src 'self'`).
   - 100% canonical CSS custom property tokens from `theme.css`.
   - Accessible keyboard focus and touch target dimensions.

---

## Automated Verification and Test Coverage

1. **Unit Test Coverage:**
   - **Backend Pytest (`43 passed in 4.25s`):**
     * `kanban/api/v1/auth_identities.py`: 95% statement coverage.
     * Comprehensive unit tests covering OIDC link start with `Set-Cookie` forwarding, callback session preservation without unearned AAL2 elevation, duplicate `(issuer, sub)` conflict handling, unauthenticated `link_intent_id` rejection, conditional AAL2 enforcement, and LDAP linking.
   - **Frontend Vitest (`66 passed in 7.28s`):**
     * `src/features/settings/PersonalSettingsPage.tsx`:
       - Statements: 98.39% (threshold >= 95%)
       - Branches: 95.43% (threshold >= 95%)
       - Functions: 99.00% (threshold >= 95%)
       - Lines: 100.00% (threshold >= 95%)
     * `cssTokensAudit.test.ts`: 4/4 passed (100% valid tokens, 0 undefined variables).

2. **Static Gate Verifications:**
   - `ruff check .`: 0 errors.
   - `mypy`: Success (0 issues found across 1091 source files).
   - `lint-imports`: 2 contracts kept, 0 broken.
   - `pnpm --dir kanban/web exec tsc -b`: 0 errors.
   - `pnpm --dir kanban/web exec eslint .`: 0 errors.
   - `python3 -m scripts.check_no_dashes --all`: 0 em-dashes and 0 en-dashes.

---

## Verbatim Artifacts Manifest in docs/qa/KAN-27/
- `unit-test-results.txt`: Verbatim Pytest and Vitest test runs with coverage reports.
- `build-or-typecheck.txt`: Verbatim output of ruff, mypy, lint-imports, check_no_dashes, tsc -b, eslint, and cssTokensAudit.
- `changed-files-manifest.txt`: List of touched working tree files.
- `git-diff.patch`: Complete git diff against HEAD commit 53f7b6eb.
- `message-to-reality-checker.md`: This comprehensive verification report.

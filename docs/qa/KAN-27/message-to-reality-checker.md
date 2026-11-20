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


---

## Live Full-Stack Verification (Zero-Mock Against Standalone Container, Commit 5998e9ab)

- **Target:** `http://localhost:18951` (`kanban-liveqa-1`, PostgreSQL 16 with `FORCE ROW LEVEL SECURITY`)
- **Proof Log:** `docs/qa/KAN-27/live-fullstack-proof.txt`
- **LIVE_STACK_VERDICT: FAIL**
- **Summary of Live Checks:**
  - Empty external providers view (`/settings/profile` prior to external cards) renders explanation and Server Admin `Configure Providers in Admin Auth Studio ->` (`/admin/auth`) link (`live-kan27-empty-providers-desktop-light.png`).
  - Unauthenticated `GET /api/v1/auth/oidc/corp-sso/start?link_intent_id=...` and `GET /api/v1/auth/cards/corp-sso/start?link_intent_id=...` ignore `link_intent_id` (login-only flow).
  - `@projadmin` (`PROJECT_ADMIN`, `aal_level=1`) calling `POST /api/v1/auth/identities/link/start` receives `403 AAL2_REQUIRED`.
  - `+ Connect Corp SSO` / `+ Connect Corp LDAP` buttons (Desktop Light/Dark + Mobile `390x844`, `scrollWidth=390`) and `ldap-credentials-modal` (Desktop Light/Dark) render cleanly.
  - **CRITICAL BLOCKER (RESOLVED IN RC1):** `POST /api/v1/auth/identities/link/start` for OIDC (`corp-sso`) failed with **`HTTP 500 INTERNAL_ERROR`** both via API and via browser UI click (`live-kan27-link-start-500-failure-desktop-light.png`). PostgreSQL 16 raised `ForeignKeyViolationError` on `oidc_auth_requests_link_intent_id_fkey` because `database/migrations/sql/p2_06_oidc_auth_requests.up.sql:12` defined `oidc_auth_requests.link_intent_id REFERENCES principals(id)` instead of `REFERENCES identity_link_intents(id)`, while `IdentityLinkService.start_link` passes `identity_link_intents.id`.
  - Downstream OIDC callback, session preservation, `?linked=` confirmation banner, and duplicate `(issuer, sub)` `IDENTITY_ALREADY_LINKED` conflict checks were blocked until this schema FK bug was fixed.

---

## 6. Live QA Remediation (fix/KAN-27-rc1)

### Root Cause Analysis & Schema Migration
- In `p2_06_oidc_auth_requests.up.sql:12`, column `link_intent_id` was defined with `REFERENCES principals(id) ON DELETE SET NULL` because `identity_link_intents` was introduced in a later migration (`p2_08_user_identities.up.sql:42`).
- When `IdentityLinkService.start_link` generated an intent via `kb_auth.identity_link_intent_create(...)` and forwarded the resulting `intent_id` into `oidc_flow.start(...)`, PostgreSQL 16 rejected the insertion with `ForeignKeyViolationError` on `oidc_auth_requests_link_intent_id_fkey` (`Key is not present in table "principals"`).

### Resolution Implemented
1. **Linear Database Migration (`p4_23_oidc_link_intent_fk`):**
   - Created single-head migration `database/migrations/versions/p4_23_oidc_link_intent_fk.py` following `database/GEMINI.md`.
   - `p4_23_oidc_link_intent_fk.up.sql`: Drops `oidc_auth_requests_link_intent_id_fkey` and adds `CONSTRAINT oidc_auth_requests_link_intent_id_fkey FOREIGN KEY (link_intent_id) REFERENCES identity_link_intents(id) ON DELETE SET NULL`.
   - `p4_23_oidc_link_intent_fk.down.sql`: Restores foreign key constraint referencing `principals(id)`.
   - Validated: `uv run kanban-ctl db check-migrations` reports `OK: All 62 migrations valid. Single head: p4_23_oidc_link_intent_fk`.
2. **SQLAlchemy ORM Parity (`database/models/auth.py`):**
   - Updated `OidcAuthRequest.link_intent_id` annotation to `ForeignKey("identity_link_intents.id", ondelete="SET NULL")`.
   - Verified schema parity test `database/tests/test_p1_17_models.py::test_orm_schema_parity` passes 100%.
3. **Migration Lifecycle Validation (`database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py`):**
   - Executes real upgrade -> downgrade -> upgrade cycle on PostgreSQL 16.
   - Verifies target table shifts from `identity_link_intents` to `principals` and back to `identity_link_intents`.
4. **Real PostgreSQL E2E ASGI Lifecycle Test (`kanban/tests/auth/test_identity_linking_real_pg_e2e.py`):**
   - Zero mocking of core auth services: uses real PostgreSQL tables, real `kb_auth.*` SQL routines, real `SessionService`, and real `RLSSessionFactory`. Outbound HTTP to IdP mocked solely via `FakeIdP` / `MockTransport`.
   - Proves zero-factor `WORKSPACE_MEMBER` `@alice` (`aal_level=1`) calls `POST /api/v1/auth/identities/link/start` (HTTP 200, sets `kb_oidc` cookie, inserts real row into `oidc_auth_requests` and `identity_link_intents` with zero FK error).
   - Proves IdP callback `GET /api/v1/auth/oidc/corp-sso/callback?code=...&state=...` redirects 302 to `/settings/profile?linked=corp-sso`, binds identity in `user_identities`, and preserves `@alice` exact `session_id` and `aal_level == 1`.
   - Proves second user `@admin` attempting to link the same `(issuer, sub)` redirects to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED` with zero duplicate rows in PostgreSQL.
5. **Existing Suite Alignment (`kanban/tests/auth/test_oidc_flow.py`):**
   - Corrected test cases `test_oidc_callback_link_flow_preserves_session_and_redirects` and `test_oidc_callback_link_flow_conflict_redirects_error` to use the generated `intent_id` rather than principal ID.

### Verification Summary
- `check-migrations`: OK (62 migrations valid, single head).
- Migration lifecycle test: PASSED (1/1).
- ORM parity and RLS tests: PASSED (6/6).
- Real PG E2E test: PASSED (1/1).
- Full Auth test suite: PASSED (292/292).
- Frontend Vitest: PASSED (66/66).
- Static quality checks (Ruff, MyPy, lint-imports, check_no_dashes, tsc, eslint): 100% clean, 0 errors, 0 em/en-dashes.

---

## 7. Live Full-Stack Verification R2 (Zero-Mock Against Standalone Container, Commit 23ae056d)

- **Target:** `http://localhost:18951` (`kanban-liveqa-1`, PostgreSQL 16 with `FORCE ROW LEVEL SECURITY`, migration head `p4_23_oidc_link_intent_fk`)
- **Proof Log:** `docs/qa/KAN-27/live-fullstack-proof.txt`
- **LIVE_STACK_VERDICT: PASS**
- **Verified Live Flows (0 mocks, 0 `page.route`, 0 `context.route`, 0 console/page errors):**
  - Empty external providers notice + Server Admin `Configure Providers in Admin Auth Studio ->` (`/admin/auth`) link (`live-kan27-empty-providers-desktop-light.png`).
  - Real HTTPS OIDC provider on `172.17.0.1:40085` (RS256 JWKS + PKCE S256 + strict TLS CA verification) with enabled `corp-sso` (`OIDC`) and `corp-ldap` (`LDAP`) cards.
  - Unauthenticated `GET /api/v1/auth/oidc/corp-sso/start?link_intent_id=...` and `GET /api/v1/auth/cards/corp-sso/start?link_intent_id=...` ignore `link_intent_id` (`oidc_auth_requests.link_intent_id` remains `NULL`).
  - `@projadmin` (`PROJECT_ADMIN`, `aal_level=1`) calling `POST /api/v1/auth/identities/link/start` receives `403 AAL2_REQUIRED`.
  - Zero-factor `WORKSPACE_MEMBER` (`@alice_33yuf`, `aal_level=1`) clicking `+ Connect Corp SSO` succeeds: `POST /api/v1/auth/identities/link/start` returns `HTTP 200` with `Set-Cookie` forwarded (0 FK errors), real IdP `/authorize` + `/token` + `/jwks` + `/api/v1/auth/oidc/corp-sso/callback` returns `302` to `/settings/profile?linked=corp-sso`, preserves exact `session_id` and `aal_level === 1`, and displays the confirmation banner and `corp-sso (OIDC)` row in `GET /api/v1/auth/identities` and UI.
  - `@admin` (`AAL2`) attempting to link the same `(issuer, sub)` via real OIDC callback redirects cleanly (`302`) to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED`.
  - Screenshots verified via `read_file` across Desktop `1440x900` Light/Dark, Tablet `768x1024` Light, Mobile `390x844` Light (`scrollWidth=390`), LDAP credentials modal Light/Dark, and linked confirmation banner + OIDC row Light/Dark (`docs/qa/KAN-27/screenshots/live-kan27-*.png`).

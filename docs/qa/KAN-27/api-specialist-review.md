# API Specialist Review: KAN-27 (KB-P3-AUDIT-21)

- Ticket: KAN-27
- Title: [KB-P3-AUDIT-21] Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-27`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-27 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack R3 verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves three primary problems across authentication, identity linking, session management, and responsive profile settings:
1. Self-Service Identity Linking Flow: Implementing `IdentityLinkService.start_link` for OIDC and OAuth2 providers, emitting valid redirect URLs with state, PKCE code challenge (`S256`), and forwarding secure `Set-Cookie: kb_oidc` cookies to the browser.
2. Identity Linking Callback & Security Boundaries: Validating link intents, handling IdP callbacks without creating orphaned records, enforcing strict AAL2 authentication requirements for admin principals, preserving non-admin session integrity (`session_id` and `aal_level=1`) without granting unearned AAL2 escalation, and rejecting duplicate `(issuer, sub)` collisions with redirect to `IDENTITY_ALREADY_LINKED`.
3. Self-Service Settings Frontend: Providing an intuitive, responsive external identity management UI on `/settings/profile`, with active provider connect cards, LDAP credential binding modals with in-modal error handling and Escape key focus restoration, linked identity tables with unlink actions, and empty provider notices linking to Admin Auth Studio.

All API contracts, security invariants, database migrations, session preservation guarantees, and test coverage requirements are verified and certified:
- Schema Migration & ORM Parity: Migration `p4_23_oidc_link_intent_fk` establishes `FOREIGN KEY (link_intent_id) REFERENCES identity_link_intents(id) ON DELETE SET NULL`. SQLAlchemy model `OidcAuthRequest.link_intent_id` in `database/models/auth.py` maintains exact parity. Migration chain is linear with 62 valid migrations and single head `p4_23_oidc_link_intent_fk`.
- Zero-Mock Live Full-Stack R3 Proof: Verified on container `kanban-liveqa-2` (`http://localhost:18962`) with real HTTPS OIDC provider (`https://172.17.0.1:40185`, RS256 JWKS, PKCE S256), real LDAPS BER server (`ldaps://172.17.0.1:40636`, RFC 4511), and PostgreSQL 16 with FORCE ROW LEVEL SECURITY. All flows passed with zero console errors, zero page errors, and zero 5xx responses.
- Session Preservation & Security Invariants: Caller session ID and authentication assurance level (`aal_level=1`) preserved for `@alice` after successful OIDC linking. Unauthenticated link probes rejected with 0 DB insertions. Unearned AAL2 escalation prevented. `@projadmin` (`PROJECT_ADMIN`, AAL1) link attempt rejected with HTTP 403 `AAL2_REQUIRED`. Duplicate `(issuer, sub)` collision cleanly rejected with redirect to `link_error=IDENTITY_ALREADY_LINKED` and browser alert banner.
- High Test Coverage: 319/319 Pytest tests passed with 98% overall coverage on touched auth modules (`database/models/auth.py` 100%, `auth_identities.py` 100%, `identity_service.py` 98%, `oidc/flow.py` 97%). 72/72 Vitest frontend tests passed with `PersonalSettingsPage.tsx` achieving 98.49% statements, 95.25% branch, and 100% lines coverage.
- Zero New External Dependencies: Zero new runtime packages added (`Apache-2.0` stack only). Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter`.
- Style & Quality: Clean across static analyzers, zero compiler/linter warnings, zero inline JSX style props, and strict zero em-dashes and en-dashes.

---

## 2. Detailed Contract & Security Verification

### 2.1 Schema Migration & Constraint Integrity (`p4_23_oidc_link_intent_fk`)
- Migration Files:
  - `database/migrations/sql/p4_23_oidc_link_intent_fk.up.sql`
  - `database/migrations/sql/p4_23_oidc_link_intent_fk.down.sql`
  - `database/migrations/versions/p4_23_oidc_link_intent_fk.py` (down_revision: `p4_22_outbox_replay_reader`)
- DDL Invariant:
  ```sql
  ALTER TABLE oidc_auth_requests
      DROP CONSTRAINT IF EXISTS oidc_auth_requests_link_intent_id_fkey;

  ALTER TABLE oidc_auth_requests
      ADD CONSTRAINT oidc_auth_requests_link_intent_id_fkey
      FOREIGN KEY (link_intent_id)
      REFERENCES identity_link_intents(id)
      ON DELETE SET NULL;
  ```
- Verification:
  - Migration check: `kanban-ctl db check-migrations` validates all 62 migrations with single head `p4_23_oidc_link_intent_fk`.
  - Reversibility test: `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py` executes full upgrade -> downgrade -> upgrade cycle, verifying `information_schema.table_constraints` and `constraint_column_usage`.
  - SQLAlchemy model `OidcAuthRequest.link_intent_id` in `database/models/auth.py` specifies `ForeignKey("identity_link_intents.id", ondelete="SET NULL")`, maintaining 100% schema parity.

### 2.2 In-Modal LDAP Error Handling, Modal Controls & Focus Restoration
- Client Source: `kanban/web/src/features/settings/PersonalSettingsPage.tsx` and `PersonalSettingsPage.css`
- Behavior Verification:
  - When submitting invalid LDAP credentials, the server returns HTTP 401.
  - The resulting error message is rendered directly inside the open modal dialog via `data-testid="ldap-modal-error"`, rather than being hidden behind the backdrop or displayed as an unassociated global toast.
  - Modal footer provides exactly one Cancel button (`cancelButtonCount=1`) alongside a header Close button.
  - Pressing the `Escape` key dismisses the modal and restores focus back to the initiating trigger button (`[data-testid="connect-provider-corp-ldap"]`).
  - Submitting valid LDAP credentials performs a successful bind (resultCode=0) and links the account via `POST /api/v1/auth/identities/link/ldap` -> HTTP 200.

### 2.3 Mobile 390x844 Responsive Card Table
- Client Source: `PersonalSettingsPage.css`
- Verification:
  - On viewports <= 640px, the linked identities table switches to a responsive card layout utilizing `td[data-label]` pseudo-elements.
  - Viewport metrics at 390x844 confirm `scrollWidth=390` and `innerWidth=390`.
  - Card cards render cleanly within the viewport; long email values (e.g., `alice.sso.r3@corp.example.test`) truncate with an ellipsis or wrap within the single-line flex row inside `.kb-table-scroll-container`.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R3)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-27/live-fullstack-proof.txt` on target container `kanban-liveqa-2` (`http://localhost:18962`) at commit `b3b0f4ba`:
1. Setup & Admin AAL2 Bootstrap:
   - Claimed initial workspace via `POST /api/v1/setup/claim`, enrolled TOTP AAL2, elevated session.
   - Created enabled OIDC card `corp-sso` (HTTP 201) and LDAPS card `corp-ldap` (HTTP 201, `transport_mode=ldaps`).
2. Backend Security Invariants:
   - Probed `GET /api/v1/auth/oidc/corp-sso/start` and `GET /api/v1/auth/cards/corp-sso/start` with unauthenticated requests; DB query confirmed 0 `oidc_auth_requests` with non-null `link_intent_id` created.
   - User `@projadmin` (`PROJECT_ADMIN`, AAL1) attempted `POST /api/v1/auth/identities/link/start` -> returned HTTP 403 `AAL2_REQUIRED` ("This operation requires multi-factor authentication (AAL2).").
3. Zero-Factor Member OIDC Link Flow:
   - Logged in as `@alice` (zero-factor, AAL1): `session_id=0c6b0d7d-8e6c-489a-b038-83226b31bcbe`, `aal_level=1`.
   - Clicked `[data-testid="connect-provider-corp-sso"]` -> real HTTPS OIDC authorize -> callback 302 to `/settings/profile?linked=corp-sso`.
   - Post-link session: `session_id=0c6b0d7d-8e6c-489a-b038-83226b31bcbe`, `aal_level=1` (session preserved; zero unearned AAL2 escalation).
   - Mobile 390x844 metrics: `scrollWidth=390`, `innerWidth=390`, `td[data-label]` cards rendered cleanly. Screenshot: `screenshots/live-kan27-linked-identities-mobile-light.png`.
4. LDAP Modal Error, Single Cancel, Escape Focus Restore & Valid Link:
   - Opened `[data-testid="ldap-credentials-modal"]` at 1440x900 Light.
   - Submitted invalid credentials (username=alice, password=WrongLdapPassword!): LDAPS bind returned resultCode=49 (invalidCredentials), HTTP 401.
   - Verified `data-testid="ldap-modal-error"` visible INSIDE open modal ("Invalid credentials"), `cancelButtonCount=1`, `hasCloseButton=true`. Screenshot: `screenshots/live-kan27-ldap-modal-error-desktop-light.png`.
   - Pressed Escape key: modal dismissed and focus restored to `[data-testid="connect-provider-corp-ldap"]`.
   - Reopened modal and submitted valid credentials (username=alice, password=AliceLdapPass123!): LDAPS bind returned resultCode=0, HTTP 200.
   - Linked identities table text displays both `corp-sso (OIDC)` and `corp-ldap (LDAP)`.
5. Duplicate (Issuer, Sub) Conflict Banner:
   - User `@admin` (AAL2) initiated link against the same OIDC subject (`sub=oidc-alice-sub-r3`).
   - Callback detected pre-existing binding and redirected 302 to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED`.
   - Rendered alert banner: "External identity is already linked to another account.\nDismiss". Screenshot: `screenshots/live-kan27-conflict-banner-desktop-light.png`.
6. Stability Diagnostics: Console errors: 0, Page errors: 0, Server 5xx errors: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suites (`unit-test-results.txt`):
  - `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py`: 1 passed in 0.62s.
  - `database/tests/test_p1_17_models.py` & `test_p1_14_rls_catalog.py`: 6 passed in 0.50s.
  - `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`: 1 passed in 0.39s (real PostgreSQL lifecycle).
  - Full Auth Test Suite: 319 passed in 76.71s across 35 test files.
  - Coverage: `database/models/auth.py` (100%), `kanban/api/v1/auth_identities.py` (100%), `kanban/auth/identity_service.py` (98%), `kanban/auth/oidc/flow.py` (97%). Total statements: 1019, Miss: 4, Total coverage: 98%.
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed.
  - `src/features/settings/__tests__/PersonalSettingsPage.test.tsx`: 68 passed.
  - Total: 72 passed in 7.81s across 2 test suites.
  - Coverage: `PersonalSettingsPage.tsx` achieves 98.49% statements, 95.25% branch, 99.05% functions, 100% lines.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run ruff format --check .`: Clean (1926 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1107 source files).
  - `uv run kanban-ctl db check-migrations`: Clean (All 62 migrations valid, single head: `p4_23_oidc_link_intent_fk`).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.26s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Foreign Key Integrity | `link_intent_id` FK to `identity_link_intents(id)` | Migration `p4_23_oidc_link_intent_fk` + ORM model | PASS |
| Single-Head Migration | Linear migration chain without branching | 62 valid migrations, single head `p4_23_oidc_link_intent_fk` | PASS |
| Session Preservation | Caller session retained post-link without elevation | `@alice` session preserved, `aal_level=1` maintained | PASS |
| Admin AAL2 Gate | Project/Server Admin link requires AAL2 | Probed `@projadmin` AAL1 rejected with HTTP 403 | PASS |
| Duplicate Collision | Duplicate `(issuer, sub)` binding rejected | Redirects to `link_error=IDENTITY_ALREADY_LINKED` | PASS |
| In-Modal LDAP Error | 401 error shown inside modal, not behind backdrop | `data-testid="ldap-modal-error"` visible in modal | PASS |
| Focus Restoration | Escape dismisses modal and restores trigger focus | Focus restored to `connect-provider-corp-ldap` | PASS |
| Mobile Card Table | 390x844 responsive layout with `td[data-label]` | `scrollWidth=390`, `innerWidth=390` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, identity linking handshakes, session preservation guards, in-modal error handlers, database migrations, and unit test suites for KAN-27 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `kanban-liveqa-2`, and certified. Ready for Clean-Room Reality-Checker QA.

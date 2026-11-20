# API Specialist Review: KAN-27 (KB-P3-AUDIT-21)

- Ticket: KAN-27
- Title: [KB-P3-AUDIT-21] Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-27`
- Branch: `main`
- Commit: `837f657d079ebcb8ee88eec86ad2f6df41c1eb33` (short: `837f657d`)
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-27 on `main` at commit `837f657d`, incorporating verified evidence from the R4 zero-mock live container execution (`live-fullstack-proof.txt` run on `http://127.0.0.1:18961`, container `kanban-liveqa-1`), all 13 live visual screenshots in `docs/qa/KAN-27/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves three primary problems across authentication, identity linking, session management, and responsive profile settings:
1. Self-Service Identity Linking Flow: Implementing `IdentityLinkService.start_link` for OIDC and OAuth2 providers, emitting valid redirect URLs with state, PKCE code challenge (`S256`), and forwarding secure `Set-Cookie: kb_oidc` cookies to the browser.
2. Identity Linking Callback & Security Boundaries: Validating link intents, handling IdP callbacks without creating orphaned records, enforcing strict AAL2 authentication requirements for admin principals, preserving non-admin session integrity (`session_id` and `aal_level=1`) without granting unearned AAL2 escalation, and rejecting duplicate `(issuer, sub)` collisions with redirect to `IDENTITY_ALREADY_LINKED`.
3. Self-Service Settings Frontend: Providing an intuitive, responsive external identity management UI on `/settings/profile`, with active provider connect cards, LDAP credential binding modals with in-modal error handling and Escape key focus restoration, linked identity tables with unlink actions, and empty provider notices linking to Admin Auth Studio.

All API contracts, security invariants, database migrations, session preservation guarantees, and test coverage requirements are verified and certified:
- Schema Migration & ORM Parity: Migration `p4_23_oidc_link_intent_fk` establishes `FOREIGN KEY (link_intent_id) REFERENCES identity_link_intents(id) ON DELETE SET NULL`. SQLAlchemy model `OidcAuthRequest.link_intent_id` in `database/models/auth.py` maintains exact parity. Migration chain is linear with 62 valid migrations and single head `p4_23_oidc_link_intent_fk`.
- Zero-Mock Live Full-Stack R4 Proof: Verified on container `kanban-liveqa-1` (`http://127.0.0.1:18961`) with real HTTPS OIDC provider (`https://172.17.0.1:40185`, RS256 JWKS, PKCE S256), real LDAPS BER server (`ldaps://172.17.0.1:40636`, RFC 4511), and PostgreSQL 16 with FORCE ROW LEVEL SECURITY. All flows passed with zero unexpected console errors, zero page errors, and zero 5xx responses.
- Session Preservation & Security Invariants: Caller session ID and authentication assurance level (`aal_level=1`) preserved for `@alice_r4_24513` after successful OIDC linking. Unauthenticated link probes rejected with 0 DB insertions. Unearned AAL2 escalation prevented. `@projadmin` (`PROJECT_ADMIN`, AAL1) link attempt rejected with HTTP 403 `AAL2_REQUIRED`. Duplicate `(issuer, sub)` collision cleanly rejected with redirect to `link_error=IDENTITY_ALREADY_LINKED` and browser alert banner.
- Live Unlink Verification: Identity unlink executed via `DELETE /api/v1/auth/identities/{id}` returning HTTP 200 `{"unlinked":true}` (72ms), immediately updating the table while preserving account access.
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
  - Modal footer provides exactly one Cancel button (`cancelCount=1`) alongside a header Close button (`closeBtnCount=1`).
  - Pressing the `Escape` key dismisses the modal and restores focus back to the initiating trigger button (`[data-testid="connect-provider-corp-ldap"]`).
  - Submitting valid LDAP credentials performs a successful bind (resultCode=0) and links the account via `POST /api/v1/auth/identities/link/ldap` -> HTTP 200.

### 2.3 Mobile 390x844 Responsive Card Table
- Client Source: `PersonalSettingsPage.css`
- Verification:
  - On viewports <= 640px, the linked identities table switches to a responsive card layout utilizing `td[data-label]` pseudo-elements.
  - Viewport metrics at 390x844 confirm `docScrollWidth=390` and `innerWidth=390` (`overflows=false`).
  - Table cells wrap cleanly: `alice.sso.r4@corp.example.test` and `alice.ldap.r4@corp.example.test` measure `scrollWidth=186, clientWidth=186, height=78` with zero horizontal clipping.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R4)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-27/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://127.0.0.1:18961`) at commit `837f657d`:
1. Setup & Admin AAL2 Bootstrap:
   - Claimed initial workspace via `POST /api/v1/setup/claim`, enrolled TOTP AAL2, confirmed session.
   - Configured & enabled real OIDC (`corp-sso-r4`) and LDAPS (`corp-ldap`) auth cards via AAL2 `@admin`:
     * `PATCH /api/v1/admin/auth-cards` (corp-sso-r4) -> HTTP 200 (16ms)
     * `PATCH /api/v1/admin/auth-cards` (corp-ldap) -> HTTP 200 (21ms)
2. Empty Providers Notice:
   - Verified `[data-testid="no-external-providers-notice"]` renders when external cards are disabled.
   - Screenshot: `screenshots/live-kan27-empty-providers-desktop-light.png`.
3. Backend Security Invariants:
   - Probed `GET /api/v1/auth/oidc/corp-sso-r4/start` with unauthenticated link intent id -> HTTP 302 with PKCE S256 code challenge (`code_challenge_method=S256`), zero DB link records inserted.
   - User `@projadmin` (`PROJECT_ADMIN`, AAL1) attempted `POST /api/v1/auth/identities/link/start` -> returned HTTP 403 `AAL2_REQUIRED` (request_id: `c8996d6d06d0446281b5806839632fc5`).
4. Zero-Factor Member OIDC Link Flow:
   - Logged in as `@alice_r4_24513` (zero-factor, AAL1): `session_id=c8fdfc04-5fea-4094-a90a-d4d7c02c3840`, `aal_level=1`.
   - Clicked `[data-testid="connect-provider-corp-sso-r4"]` -> real HTTPS OIDC authorize -> callback 302 to `/settings/profile?linked=corp-sso-r4` (477ms flow).
   - Post-link session: `session_id=c8fdfc04-5fea-4094-a90a-d4d7c02c3840`, `aal_level=1` (session preserved; zero unearned AAL2 escalation).
   - Linked identities table populated with `alice.sso.r4@corp.example.test`.
   - Screenshots: `live-kan27-linked-banner-desktop-light.png`, `live-kan27-linked-banner-desktop-dark.png`.
5. LDAP Modal Error, Single Cancel, Escape Focus Restore & Valid Link:
   - Opened `[data-testid="ldap-credentials-modal"]` at 1440x900 Light (`cancelCount=1`, `closeBtnCount=1`).
   - Submitted invalid credentials (username=alice, password=WrongLdapPassword!): LDAPS bind returned resultCode=49 (invalidCredentials), HTTP 401 (126ms).
   - Verified `data-testid="ldap-modal-error"` visible INSIDE open modal ("Invalid credentials"). Screenshot: `live-kan27-ldap-modal-error-desktop-light.png`.
   - Pressed Escape key: modal dismissed and focus restored to `[data-testid="connect-provider-corp-ldap"]`.
   - Reopened modal and submitted valid credentials (username=alice, password=AliceLdapPass123!): LDAPS bind returned resultCode=0, HTTP 200 (145ms).
   - Linked identities table text displays both `corp-sso-r4 (OIDC)` and `corp-ldap (LDAP)`.
   - Mobile 390x844 metrics: `docScrollWidth=390`, `innerWidth=390`, table cells wrap cleanly without clipping (`scrollWidth=186, clientWidth=186, height=78`). Screenshot: `live-kan27-linked-identities-mobile-light.png`.
6. Duplicate (Issuer, Sub) Conflict Banner:
   - User `@admin` (AAL2, session `01a1fa5c-68ae-7361-ad99-572942e6bb7d`) initiated link against the same OIDC subject (`sub=oidc-alice-sub-r4-v4`).
   - Callback detected pre-existing binding and redirected 302 to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED`.
   - Rendered alert banner: "External identity is already linked to another account.\nDismiss". Screenshot: `live-kan27-conflict-banner-desktop-light.png`.
7. Live Identity Unlink Journey:
   - Elevated `@alice_r4_24513` to AAL2 via TOTP (`POST /api/v1/auth/mfa/totp/confirm -> HTTP 200`).
   - Accepted confirm dialog and clicked Unlink on `corp-ldap` row:
     * `DELETE /api/v1/auth/identities/{id}` -> HTTP 200 `{"unlinked":true}` (72ms).
     * Table updated immediately from 2 rows to 1 row (`corp-sso-r4` preserved).
     * Screenshot: `live-kan27-unlink-desktop-light.png`.
8. All 13 Live Screenshots Verified on Disk:
   - `live-kan27-conflict-banner-desktop-light.png`
   - `live-kan27-connect-buttons-desktop-dark.png`
   - `live-kan27-connect-buttons-desktop-light.png`
   - `live-kan27-connect-buttons-mobile-light.png`
   - `live-kan27-connect-buttons-tablet-light.png`
   - `live-kan27-empty-providers-desktop-light.png`
   - `live-kan27-ldap-modal-desktop-dark.png`
   - `live-kan27-ldap-modal-desktop-light.png`
   - `live-kan27-ldap-modal-error-desktop-light.png`
   - `live-kan27-linked-banner-desktop-dark.png`
   - `live-kan27-linked-banner-desktop-light.png`
   - `live-kan27-linked-identities-mobile-light.png`
   - `live-kan27-unlink-desktop-light.png`
9. Stability Diagnostics: Unexpected console errors: 0, Page errors: 0, Server 5xx errors: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suites (`unit-test-results.txt`):
  - `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py`: 1 passed in 0.69s.
  - `database/tests/test_p1_17_models.py` & `test_p1_14_rls_catalog.py`: 6 passed in 0.65s.
  - `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`: 1 passed in 0.39s (real PostgreSQL lifecycle).
  - Full Auth Test Suite: 319 passed in 87.14s across 35 test files.
  - Coverage: `database/models/auth.py` (100%), `kanban/api/v1/auth_identities.py` (100%), `kanban/auth/identity_service.py` (98%), `kanban/auth/oidc/flow.py` (97%). Total statements: 1019, Miss: 4, Total coverage: 98%.
- Frontend Vitest Suite (`unit-test-results.txt`):
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed in 18ms.
  - `src/features/settings/__tests__/PersonalSettingsPage.test.tsx`: 68 passed in 7054ms.
  - Total: 72 passed in 8.45s across 2 test suites.
  - Coverage: `PersonalSettingsPage.tsx` achieves 98.49% statements, 95.25% branch, 99.05% functions, 100% lines.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run ruff format --check .`: Clean (1963 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1165 source files).
  - `uv run kanban-ctl db check-migrations`: Clean (All 62 migrations valid, single head: `p4_23_oidc_link_intent_fk`).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean (0 errors).
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
| Live Identity Unlink | Safely unlinks provider when >=1 factor remains | `DELETE /api/v1/auth/identities/{id}` returns 200 | PASS |
| Mobile Card Table | 390x844 responsive layout with `td[data-label]` | `docScrollWidth=390`, `innerWidth=390` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, identity linking handshakes, session preservation guards, in-modal error handlers, live unlink journeys, database migrations, and unit test suites for KAN-27 on `main` at commit `837f657d` have been thoroughly audited, verified against live container `kanban-liveqa-1` (R4 execution), and certified. All 13 live visual screenshots in `docs/qa/KAN-27/screenshots/` are verified. Ready for Clean-Room Reality-Checker QA.

# API Specialist Review: KAN-27 (KB-P3-AUDIT-21)

- Ticket: KAN-27
- Title: [KB-P3-AUDIT-21] Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-27`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-27 on `main` (commit `23ae056d`), incorporating concrete evidence from zero-mock live full-stack verification (`docs/qa/KAN-27/live-fullstack-proof.txt`).

The ticket resolves three primary problems:
1. Self-Service Identity Linking Flow: Implementing `IdentityLinkService.start_link` for OIDC and OAuth2 providers, emitting valid redirect URLs with state, PKCE code challenge (`S256`), and forwarding secure `Set-Cookie: kb_oidc` cookies to the browser.
2. Identity Linking Callback & Security Boundaries: Validating link intents, handling IdP callbacks without creating orphaned records, enforcing strict AAL2 authentication requirements for admin principals, preserving non-admin session integrity (`session_id` and `aal_level=1`) without granting unearned AAL2 escalation, and rejecting duplicate `(issuer, sub)` collisions with redirect to `IDENTITY_ALREADY_LINKED`.
3. Self-Service Settings Frontend: Providing an intuitive, responsive external identity management UI on `/settings/profile`, with active provider connect cards, LDAP credential binding modals, linked identity tables with unlink actions, and empty provider notices linking to Admin Auth Studio.

During live-QA round 1 validation, database foreign key constraint errors occurred during link initiation because `oidc_auth_requests.link_intent_id` erroneously referenced `principals(id)` instead of `identity_link_intents(id)`. The remediation in `fix/KAN-27-rc1` (merged into `main` at `23ae056d`) introduced migration `p4_23_oidc_link_intent_fk`, updated SQLAlchemy ORM models, and verified full downgrade/upgrade reversibility.

All API contracts, security invariants, database migrations, session preservation guarantees, and test coverage requirements are verified and approved:
- Schema Migration & ORM Parity: Migration `p4_23_oidc_link_intent_fk` drops the invalid constraint and establishes `FOREIGN KEY (link_intent_id) REFERENCES identity_link_intents(id) ON DELETE SET NULL`. SQLAlchemy model `OidcAuthRequest.link_intent_id` in `database/models/auth.py` maintains exact parity. Migration chain is linear with 62 valid migrations and single head `p4_23_oidc_link_intent_fk`.
- Zero-Mock Live Full-Stack Proof: Verified on container `kanban-liveqa-1` (`http://localhost:18951`) with real HTTPS OIDC provider (`https://172.17.0.1:40085`, RS256 JWKS, PKCE S256) and PostgreSQL 16 with FORCE ROW LEVEL SECURITY. All flows passed with zero console errors and zero page errors.
- Session Preservation & Security Invariants: Caller session ID and authentication assurance level (`aal_level=1`) preserved for `@alice_33yuf` after successful OIDC linking. Unauthenticated link probes rejected with 0 DB insertions. Unearned AAL2 escalation prevented. `@projadmin` (`PROJECT_ADMIN`, AAL1) link attempt rejected with HTTP 403 `AAL2_REQUIRED`. Duplicate `(issuer, sub)` collision cleanly rejected with redirect to `link_error=IDENTITY_ALREADY_LINKED`.
- Test Suites: 34/34 tests in auth identity linking suite passed, with `kanban/api/v1/auth_identities.py` achieving 95% statement coverage. 66/66 Vitest tests passed on `PersonalSettingsPage.test.tsx`.
- Zero External Dependencies & Clean Layering: Zero external dependencies added (`Apache-2.0` compliant). Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter`.
- Style & Formatting: Zero compiler/linter warnings, zero inline JSX style props, and strict zero em-dashes and en-dashes.

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

### 2.2 Live Full-Stack Proof Audit (`live-fullstack-proof.txt` - R2)
- Environment: Container `kanban-liveqa-1` (`http://localhost:18951`), commit `23ae056d`, OIDC IdP `https://172.17.0.1:40085`.
- Audit Results:
  - Setup & Admin Bootstrap: Completed setup wizard via `/setup/claim`, enrolled TOTP AAL2, and landed on `/settings/profile` as `@admin`.
  - Empty Providers View: `/settings/profile` before adding external cards displays clear notice: "No external identity providers (OIDC, OAuth2, LDAP) are currently enabled in this workspace." with link to `/admin/auth`. Captured in `live-kan27-empty-providers-desktop-light.png`.
  - Provider Creation: Created enabled OIDC card `corp-sso` (HTTP 201) and LDAP card `corp-ldap` (HTTP 201) via `POST /api/v1/admin/auth-cards`.
  - Security Invariants:
    - Probed `GET /api/v1/auth/oidc/corp-sso/start` and `GET /api/v1/auth/cards/corp-sso/start` with unauthenticated requests; DB check confirmed 0 `oidc_auth_requests` with non-null `link_intent_id` created.
    - User `@projadmin` (`PROJECT_ADMIN`, AAL1) attempted `POST /api/v1/auth/identities/link/start` -> returned HTTP 403 `AAL2_REQUIRED` ("This operation requires multi-factor authentication (AAL2).").
  - Member OIDC Link Flow:
    - User `@alice_33yuf` (`WORKSPACE_MEMBER`, AAL1) visited `/settings/profile` (verified across desktop light, dark, tablet, and mobile 390x844 with `scrollWidth = 390`).
    - Clicked "+ Connect Corp SSO" -> `POST /api/v1/auth/identities/link/start` returned HTTP 200 with `Set-Cookie: kb_oidc`.
    - Real OIDC provider performed authorization (`/authorize` -> `/callback` with PKCE S256 and RS256 `id_token` exchange).
    - Callback redirected 302 to `/settings/profile?linked=corp-sso`.
    - Profile rendered success banner: "Account successfully linked (corp-sso)." and table row showing `corp-sso (OIDC)` linked to `alice.sso.33yuf@corp.example.test`.
    - Session preserved: `@alice_33yuf` retained active `session_id=aa3e4bf5-ac21-45b1-80f3-8463152fb24c` with `aal_level=1` (zero unearned AAL2 privilege elevation).
  - Collision & Duplicate Rejection:
    - User `@admin` initiated link against the same IdP subject (`sub=oidc-alice-sub-33yuf`).
    - Callback detected pre-existing `(issuer, sub)` binding in `user_identities` and redirected 302 to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED`.
  - Browser Diagnostics: Console errors = 0, page errors = 0.

### 2.3 Test Suites and Coverage
- Backend Pytest Suites:
  - `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py`: 1/1 passed.
  - `database/tests/test_p1_17_models.py` & `test_p1_14_rls_catalog.py`: 6/6 passed (ORM parity and RLS catalog gate).
  - `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`: 1/1 passed against real PostgreSQL.
  - `kanban/tests/auth/test_identity_linking.py` and `test_oidc_flow.py`: 33/33 passed.
  - Statement coverage: `kanban/api/v1/auth_identities.py` achieves 95% coverage.
- Frontend Vitest Suite:
  - `src/features/settings/__tests__/PersonalSettingsPage.test.tsx`: 66/66 passed.

---

## 3. Specialist Checklist

1. [x] Foreign key constraint `oidc_auth_requests_link_intent_id_fkey` references `identity_link_intents(id)`
2. [x] Linear single-head migration chain verified via `kanban-ctl db check-migrations` (62 migrations valid)
3. [x] Migration upgrade, downgrade, and re-upgrade verified against PostgreSQL catalog
4. [x] SQLAlchemy ORM model `OidcAuthRequest.link_intent_id` parity verified
5. [x] Zero-mock real PostgreSQL ASGI E2E test passes without foreign key errors
6. [x] Live container verification confirms 200 OK link start and clean OIDC callback redirect
7. [x] Session preservation verified: caller session retained without unearned AAL2 escalation
8. [x] Admin AAL2 gate verified: project/server admin link initiation rejects AAL1 callers with 403 AAL2_REQUIRED
9. [x] Duplicate subject collision cleanly redirected to `link_error=IDENTITY_ALREADY_LINKED`
10. [x] Empty external providers state verified on `/settings/profile` with link to `/admin/auth`
11. [x] All 34 auth identity backend tests passing with 95% coverage on `auth_identities.py`
12. [x] All 66 frontend Vitest tests passing on `PersonalSettingsPage.test.tsx`
13. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
14. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-27 is verified and approved on `main` at commit `23ae056d`. The implementation establishes a secure, reversible foreign key constraint, preserves caller sessions without privilege elevation, enforces admin AAL2 boundaries, and successfully executes full-stack external identity linking on live containerized infrastructure. Ready for Clean-Room Reality-Checker QA.

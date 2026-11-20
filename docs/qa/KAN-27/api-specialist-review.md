# API Specialist Review: KAN-27-rc1 (KB-P3-AUDIT-21)

- Ticket: KAN-27
- Title: [KB-P3-AUDIT-21] Wire Self-Service External Identity Linking (OIDC, OAuth2, LDAP) on /settings/profile and Fix Backend Link Initiation & Session Preservation (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan27-rc1-0fa848cb`
- Target Branch: `fix/KAN-27-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `d61b35d0`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-27 remediation on branch `fix/KAN-27-rc1` (commit `d61b35d0`). The ticket addresses live-QA validation feedback by correcting a schema foreign key constraint definition on `oidc_auth_requests.link_intent_id`, ensuring atomic database migrations with full downgrade/upgrade reversibility, updating SQLAlchemy ORM models to maintain strict schema parity, and providing an end-to-end zero-mock ASGI integration test running against real PostgreSQL 16.

All API contracts, security invariants, session preservation behaviors, database migration invariants, and test coverage requirements are verified and approved:
1. Root Cause Resolution: In `database/migrations/sql/p2_06_oidc_auth_requests.up.sql:12`, `oidc_auth_requests.link_intent_id` was erroneously defined as `REFERENCES principals(id) ON DELETE SET NULL` rather than `REFERENCES identity_link_intents(id) ON DELETE SET NULL`. Migration `p4_23_oidc_link_intent_fk` cleanly drops the invalid constraint and establishes the correct foreign key reference to `identity_link_intents(id)`.
2. Linear Single-Head Chain: `kanban-ctl db check-migrations` confirms all 62 migrations are valid with a single head: `p4_23_oidc_link_intent_fk`.
3. SQLAlchemy ORM Parity: `OidcAuthRequest.link_intent_id` in `database/models/auth.py` is updated to `ForeignKey("identity_link_intents.id", ondelete="SET NULL")`, aligning ORM and DDL schemas.
4. Migration Reversibility: `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py` validates the complete upgrade -> downgrade -> upgrade cycle directly against PostgreSQL `information_schema.table_constraints`.
5. Real PostgreSQL ASGI E2E Verification: `kanban/tests/auth/test_identity_linking_real_pg_e2e.py` exercises the complete lifecycle against live PostgreSQL with zero database or service mocking, verifying zero FK errors on `POST /api/v1/auth/identities/link/start`, cookie forwarding, session preservation (@alice, aal_level=1), and duplicate subject collision rejection (@admin, IDENTITY_ALREADY_LINKED).
6. Security Boundaries & Zero Privilege Escalation: Caller session IDs and authentication assurance levels (`aal_level=1`) are preserved upon link completion without invoking unearned AAL2 escalation. Ephemeral cookies are cleared on conflict redirects.
7. Strict Style and Quality: Zero em-dashes and zero en-dashes (`check_no_dashes` clean). Zero linter or mypy warnings across 1099 source files.

---

## 2. Detailed Verification

### 2.1 Database Schema Migration & Constraint Integrity (`p4_23_oidc_link_intent_fk`)
- Source: `database/migrations/sql/p4_23_oidc_link_intent_fk.up.sql` and `.down.sql`
- Version: `database/migrations/versions/p4_23_oidc_link_intent_fk.py` (down_revision: `p4_22_outbox_replay_reader`)
- DDL Operations:
  ```sql
  ALTER TABLE oidc_auth_requests
      DROP CONSTRAINT IF EXISTS oidc_auth_requests_link_intent_id_fkey;

  ALTER TABLE oidc_auth_requests
      ADD CONSTRAINT oidc_auth_requests_link_intent_id_fkey
      FOREIGN KEY (link_intent_id)
      REFERENCES identity_link_intents(id)
      ON DELETE SET NULL;
  ```
- Reversibility: The downgrade script restores the prior constraint to `principals(id)`.
- Test Verification: `test_p4_23_oidc_link_intent_fk_migration_lifecycle` passes in 0.83s, querying `information_schema.table_constraints` and `constraint_column_usage` across upgrade, downgrade, and re-upgrade transitions.
- Catalog Check: `uv run kanban-ctl db check-migrations` reports: `OK: All 62 migrations valid. Single head: p4_23_oidc_link_intent_fk`.

### 2.2 SQLAlchemy ORM Model Parity (`database/models/auth.py`)
- In `OidcAuthRequest`:
  ```python
  link_intent_id: Mapped[uuid.UUID | None] = mapped_column(
      ForeignKey("identity_link_intents.id", ondelete="SET NULL"), nullable=True
  )
  ```
- Maintains 100% parity between Alembic migration DDL and declarative SQLAlchemy metadata.

### 2.3 Real PostgreSQL ASGI E2E Lifecycle (`test_identity_linking_real_pg_e2e.py`)
- Test: `test_oidc_identity_linking_real_pg_lifecycle` in `kanban/tests/auth/test_identity_linking_real_pg_e2e.py`
- Setup: Real PostgreSQL engine (`pg_worker_db`), real `RLSSessionFactory`, real `SessionService`, real `OidcFlow`, real `DatabaseIdentityResolver`, and outbound HTTP redirected via `FakeIdP` / `MockTransport`. Zero mock objects for internal services or databases.
- Execution Path 1 (Link Start & Foreign Key Validation):
  - Zero-factor user `@alice` with active session (`aal_level=1`) calls `POST /api/v1/auth/identities/link/start` with payload `{"provider_card_slug": "corp-sso"}`.
  - Generates `intent_id = uuid.uuid4()` and inserts rows into `identity_link_intents` and `oidc_auth_requests`.
  - Proves zero Postgres foreign key violation error (200 OK returned with `mode: "redirect"`, `authorize_url`, and `Set-Cookie: kb_oidc`).
- Execution Path 2 (OIDC Callback & Session Preservation):
  - Request to `GET /api/v1/auth/oidc/corp-sso/callback?code=...&state=...` with browser cookie `kb_oidc`.
  - Database resolves state and bound `link_intent_id`.
  - Exchanges code against FakeIdP, stores linked identity row in `user_identities`, and redirects 302 to `/settings/profile?linked=corp-sso`.
  - Database assertions prove `@alice`'s session record in PostgreSQL retains the exact same `session_id` and remains at `aal_level == 1`.
- Execution Path 3 (Collision & Duplicate Subject Rejection):
  - User `@admin` initiates link against the same IdP subject.
  - Callback detects pre-existing `(issuer, sub)` binding in `user_identities`.
  - Redirects 302 to `/settings/profile?link_error=IDENTITY_ALREADY_LINKED` without throwing 500 exceptions or creating orphaned rows.

### 2.4 Test Suite & Coverage Verification
- Migration Lifecycle: `database/tests/migrations/test_p4_23_oidc_link_intent_fk_migration.py` PASSED (1/1).
- Real PG ASGI E2E: `kanban/tests/auth/test_identity_linking_real_pg_e2e.py` PASSED (1/1).
- Auth Integration Suite: `kanban/tests/auth/test_identity_linking.py` and `kanban/tests/auth/test_oidc_flow.py` PASSED (33/33).
- Full Auth Suite: 292/292 tests passing across `kanban/tests/auth/`.
- Coverage: `kanban/api/v1/auth_identities.py` maintains 95% test coverage.

### 2.5 Security, Boundary, and Code Style Compliance
- Dependency Check: Zero new external packages added. All code uses native Python and project dependencies (`Apache-2.0` compliant).
- Punctuation Standard: Zero em-dashes and zero en-dashes (`check_no_dashes` passed cleanly).
- Static Analysis: `ruff check` (0 errors), `ruff format --check` (clean), `mypy` (clean across 1099 source files), `lint-imports` (2 kept, 0 broken).

---

## 3. Specialist Checklist

1. [x] Foreign key constraint `oidc_auth_requests_link_intent_id_fkey` references `identity_link_intents(id)`
2. [x] Single-head migration chain verified via `kanban-ctl db check-migrations` (62 migrations valid)
3. [x] Migration upgrade, downgrade, and re-upgrade verified against PostgreSQL catalog
4. [x] SQLAlchemy ORM model `OidcAuthRequest.link_intent_id` parity verified
5. [x] Zero-mock real PostgreSQL ASGI E2E test passes without foreign key errors
6. [x] Session preservation verified: caller session retained without unearned AAL2 escalation
7. [x] Duplicate subject collision cleanly redirected to `link_error=IDENTITY_ALREADY_LINKED`
8. [x] All 292 authentication tests passing in `kanban/tests/auth/`
9. [x] Static typecheck and linting clean (`mypy`, `ruff`, `lint-imports`)
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

The KAN-27 RC1 remediation on branch `fix/KAN-27-rc1` (commit `d61b35d0`) fully resolves the foreign key reference issue, provides rock-solid migration reversibility, and validates the entire identity linking and collision flow against live PostgreSQL. Ready for dual specialist signoff and merge into `main`.

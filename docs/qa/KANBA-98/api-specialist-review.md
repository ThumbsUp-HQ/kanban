# API Specialist Gate Review: KANBA-98 (KB-P2-08)

- **Ticket**: `KANBA-98` (`KB-P2-08`: `[Phase 2 / Auth] Identity linking without email auto-merge: (auth_card_id, immutable_subject_id), explicit AAL2 link flow & pre-hijack defense`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-98`
- **Worktree**: `/tmp/kb-wt-KANBA-98`
- **Scope**:
  - `database/migrations/versions/p2_08_user_identities.py`
  - `database/migrations/sql/p2_08_user_identities.up.sql`
  - `database/migrations/sql/p2_08_user_identities.down.sql`
  - `database/models/auth.py`
  - `kanban/auth/identity_service.py`
  - `kanban/api/v1/auth_identities.py`
  - `kanban/app.py`
  - `kanban/services/activity.py`

---

### 1. Architectural & Security Evaluation

#### A. Zero Cross-Card Email Auto-Merge & Pre-Hijack Invariants (S4.2 / S4.1 / S3.1)
- Authentication resolution in `DatabaseIdentityResolver` strictly resolves external subjects using the composite tuple `(auth_card_id, immutable_subject_id)`.
- Zero database query or application code path maps an incoming `assertion.email` to an existing `principal_id`.
- Pre-hijacking defense: when an unlinked external assertion matches the email of an existing user in the workspace (`lower(email) = lower(assertion.email)`), the system refuses to auto-attach the credential. Instead, it records `IDENTITY_AUTO_MERGE_BLOCKED` in `activity_records` and raises RFC 7807 HTTP 409 `IDENTITY_LINK_REQUIRED`.
- Subject stability: changing an IdP email post-link does not break authentication or detach the user, because resolution keys solely on the immutable subject identifier.

#### B. Explicit AAL2 Link Flow & Intent Hardening (S4.2)
- Account linking is exposed via `POST /api/v1/auth/identities/link/start` and requires an active session with fresh AAL2 (`require_aal2(max_age_seconds=900)`) plus CSRF protection.
- Link intents in `identity_link_intents` are cryptographically isolated:
  - Bound to `(principal_id, session_id, target_card_id)`.
  - Enforce a strict 300s TTL (`expires_at`).
  - Single-use: consumed atomically via `kb_auth.identity_link_consume_and_bind` with `consumed_at IS NULL` validation.
- Cross-session link CSRF, session mismatch, card mismatch, expired intents, and intent replays fail closed with RFC 7807 HTTP 400 `LINK_INTENT_INVALID`.
- Attempting to link an identity already bound to another principal fails closed with RFC 7807 HTTP 409 `IDENTITY_ALREADY_LINKED`.

#### C. Minimum Authentication Method Safeguards (S4.3)
- Identity removal via `DELETE /api/v1/auth/identities/{identity_id}` requires fresh AAL2 (`require_aal2(max_age_seconds=900)`) and CSRF validation.
- Sole credential guard: if a principal attempts to unlink their sole remaining `user_identities` row and lacks active `local_admin_credentials`, the operation is blocked with RFC 7807 HTTP 409 `LAST_AUTH_METHOD`.
- Removal atomically unlinks the row and records `IDENTITY_UNLINKED` in the immutable activity ledger.

#### D. Administrator Session Elevation Gate
- When an external login resolves for a principal holding `SERVER_ADMIN` or `PROJECT_ADMIN` roles, `SessionService.create_after_login` issues a session with `aal=1, mfa_pending=True`.
- This enforces that administrative accounts cannot access `/api/v1/admin/*` endpoints until they satisfy second-factor verification (AAL2).

#### E. Privilege Boundary & Storage Isolation
- Tables `user_identities` and `identity_link_intents` are created under `FORCE ROW LEVEL SECURITY`, owned by `kb_auth_owner`, and explicitly revoked from `PUBLIC`, `kanban_app`, and `app_rls_reader`.
- Direct queries from application role `kanban_app` are rejected by PostgreSQL with SQLSTATE 42501 (`insufficient_privilege`).
- Access is mediated exclusively through `SECURITY DEFINER` functions in schema `kb_auth` with fixed `search_path = pg_catalog, public`.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 15/15 tests passing across `test_identity_resolution.py` and `test_identity_linking.py` covering all 10 mandatory ticket test cases.
- **Coverage**: Total 96.61% line and branch coverage across touched modules:
  - `kanban/api/v1/auth_identities.py`: 100%
  - `kanban/auth/identity_service.py`: 96% (204 statements, 10 missed)
- **Static Analysis & Linters**:
  - `ruff check .`: PASS (0 errors)
  - `ruff format --check .`: PASS (947 files clean)
  - `mypy --strict kanban database`: PASS (444 source files clean)
  - `lint-imports`: PASS (2 contracts kept, 0 broken)
  - `make license`: PASS (115 python files, 0 violations)
  - `check_no_dashes.py`: PASS (0 unpermitted dashes)
- **Migration Reversibility**: `test_p2_08_user_identities_migration_lifecycle` verified clean upgrade and downgrade in 0.40s.

---

### 3. Gate Verdict

The identity linking and pre-hijack defense implementation satisfies all security invariants, database privilege walls, and architectural requirements.

**VERDICT: APPROVED**

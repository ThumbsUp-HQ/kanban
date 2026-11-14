# Message to Reality-Checker: KANBA-98 (KB-P2-08)

## Overview & Executive Summary

- **Ticket**: `KANBA-98` (`KB-P2-08`: `[Phase 2 / Auth] Identity linking without email auto-merge: (auth_card_id, immutable_subject_id), explicit AAL2 link flow & pre-hijack defense`)
- **Worktree**: `/tmp/kb-wt-KANBA-98`
- **Branch**: `feat/KANBA-98`
- **Target Modules**:
  - `database/migrations/versions/p2_08_user_identities.py`
  - `database/migrations/sql/p2_08_user_identities.up.sql`
  - `database/migrations/sql/p2_08_user_identities.down.sql`
  - `database/models/auth.py`
  - `kanban/auth/identity_service.py`
  - `kanban/api/v1/auth_identities.py`
  - `kanban/app.py`
  - `kanban/services/activity.py`

This implementation delivers hardened external identity resolution and explicit account linking. The architecture prevents account pre-hijacking and cross-provider identity impersonation by enforcing strict `(auth_card_id, immutable_subject_id)` binding with zero email auto-merge across providers. Linking an additional identity mandates an active, fresh AAL2 session in the same browser context, live authentication against the target provider, and atomic consumption of single-use link intents.

---

## Mandates, Invariants & Security Architecture

### 1. Zero Cross-Card Email Auto-Merge Invariant (S4.2 Item 4)
- **Principle**: Identity resolution never queries users by email when binding an external assertion.
- **Pre-Hijack Defense**: When an unlinked external provider asserts an email that matches an existing workspace user (`lower(email) = lower(assertion.email)`), the system halts auto-provisioning, logs `IDENTITY_AUTO_MERGE_BLOCKED` to the audit ledger, and raises RFC 7807 HTTP 409 `IDENTITY_LINK_REQUIRED`.
- **Subject Stability**: Resolution relies solely on the immutable subject identifier. Subsequent IdP email changes do not detach or disrupt the user's account.

### 2. Database Privilege Wall & Storage Isolation (S4.2 / S15.1)
- Tables `user_identities` and `identity_link_intents` are owned by `kb_auth_owner` with `FORCE ROW LEVEL SECURITY`.
- Permissions are strictly revoked: `REVOKE ALL ON user_identities, identity_link_intents FROM PUBLIC, kanban_app, app_rls_reader`.
- Direct queries from the application role `kanban_app` raise PostgreSQL error 42501 (`insufficient_privilege`).
- Access is mediated exclusively through 9 `SECURITY DEFINER` functions in the `kb_auth` schema with fixed `SET search_path = pg_catalog, public`:
  - `kb_auth.card_get_by_id`
  - `kb_auth.identity_lookup`
  - `kb_auth.identity_record_login`
  - `kb_auth.identity_provision_new_user`
  - `kb_auth.identity_list_for_principal`
  - `kb_auth.identity_link_intent_create`
  - `kb_auth.identity_link_intent_get`
  - `kb_auth.identity_link_consume_and_bind`
  - `kb_auth.identity_unlink`

### 3. Explicit AAL2 Link Flow & Cryptographic Intent Binding
- Initiating a link (`POST /api/v1/auth/identities/link/start`) requires an active session with fresh AAL2 (`require_aal2(max_age_seconds=900)`) plus CSRF protection.
- Link intents enforce a 300s TTL (`expires_at`), are tied to `(principal_id, session_id, target_card_id)`, and can only be consumed once.
- Cross-session CSRF, intent expiration, card mismatch, or reuse raises RFC 7807 HTTP 400 `LINK_INTENT_INVALID`.
- Attempting to link an identity already bound to another principal raises RFC 7807 HTTP 409 `IDENTITY_ALREADY_LINKED`.

### 4. Admin Session Elevation & Last Auth Method Safeguards
- Administrative external logins: users holding `SERVER_ADMIN` or `PROJECT_ADMIN` roles signing in via external providers receive sessions with `aal=1, mfa_pending=True`, requiring second-factor verification before accessing administrative routes.
- Minimum authentication method guard: attempting to unlink a principal's sole remaining `user_identities` row when no local credentials exist raises RFC 7807 HTTP 409 `LAST_AUTH_METHOD`.

---

## Verification & Test Results

### 1. Mandatory Test Cases (All 10 Pass)
- **Case 1 (Positive auto-provision & subsequent login)**: Verified in `test_identity_resolution.py::test_case_01_auto_provision_and_subsequent_login_subject_stability`.
- **Case 2 (Security - pre-hijack duplicate email block)**: Verified in `test_identity_resolution.py::test_case_02_pre_hijack_blocks_auto_merge_and_records_audit`.
- **Case 3 (Security - same subject across two cards)**: Verified in `test_identity_resolution.py::test_case_03_same_subject_across_different_cards_resolves_independently`.
- **Case 4 (Security - unverified email & domain allowlist)**: Verified in `test_identity_resolution.py::test_case_04_unverified_email_and_domain_allowlist_and_unprovisioned`.
- **Case 5 (Positive - explicit AAL2 link OIDC & LDAP)**: Verified in `test_identity_linking.py::test_case_05_explicit_aal2_link_oidc_and_ldap`.
- **Case 6 (Security - AAL1 & stale AAL2 link blocked)**: Verified in `test_identity_linking.py::test_case_06_link_start_blocked_without_fresh_aal2`.
- **Case 7 (Security - cross-session link CSRF & intent replay)**: Verified in `test_identity_linking.py::test_case_07_cross_session_replay_expired_card_mismatch_intent_invalid`.
- **Case 8 (Security - already linked subject conflict)**: Verified in `test_identity_linking.py::test_case_08_already_linked_subject_conflict`.
- **Case 9 (Security - admin MFA gate on external login)**: Verified in `test_identity_resolution.py::test_case_09_admin_role_requires_mfa_pending_session`.
- **Case 10 (Unlink & privilege boundary enforcement)**: Verified in `test_identity_linking.py::test_case_10_unlink_flow_last_auth_method_guard_and_privilege_wall`.

### 2. Test Execution & Coverage
- Command:
  `KB_TEST_PGHOST=/tmp/kb-pgsock-17 uv run pytest kanban/tests/auth/test_identity_resolution.py kanban/tests/auth/test_identity_linking.py -q --cov=kanban.auth.identity_service --cov=kanban.api.v1.auth_identities --cov-branch --cov-report=term-missing --cov-fail-under=95`
- Result: **15 passed in 0.92s**
- Line and branch coverage:
  - `kanban/api/v1/auth_identities.py`: 100%
  - `kanban/auth/identity_service.py`: 96%
  - Combined coverage: **96.61%** (exceeds >=95% gate)

### 3. Static Analysis & Linters
- `uv run ruff check .`: Clean (0 errors)
- `uv run ruff format --check .`: Clean (947 files formatted)
- `uv run mypy --strict kanban database`: Clean (444 source files)
- `uv run lint-imports`: Clean (2 contracts kept, 0 broken)
- `make license`: Clean (115 files, 0 violations)
- `python3 scripts/check_no_dashes.py --all`: Clean (0 unpermitted dashes)

### 4. Migration Lifecycle
- `database/tests/migrations/test_p2_08_migration.py`: Passed in 0.40s.
- Verifies upgrade creates tables and functions with `FORCE RLS` and downgrade cleanly removes all objects.

---

## Forensic Proof Inventory

The following proof artifacts have been populated in `docs/qa/KANBA-98/`:
1. `git-diff.patch`: Clean unified diff from `origin/main` excluding build artifacts.
2. `unit-test-results.txt`: Pytest execution log showing 15 passed tests, branch coverage report, and exit code 0.
3. `build-check.txt`: Linters, static analysis, type checking, license, and typography check results.
4. `schema-dump.sql`: Complete DDL, constraints, grants, and `kb_auth` functions dump from migration test run.
5. `contract-sample.json`: Representative JSON request and response payloads for all error and success conditions.
6. `api-specialist-review.md`: Signed review from `@arch-reviewer` (APPROVED).
7. `ui-specialist-review.md`: Signed review from `@ui-specialist` (APPROVED).
8. `message-to-reality-checker.md`: This comprehensive verification brief.
9. Screenshots: N/A - Non-UI Ticket (per ticket specification).

Ready for forensic evaluation by `@reality-checker`.

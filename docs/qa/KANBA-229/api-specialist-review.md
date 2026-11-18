# API Specialist Review: KANBA-229

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-229 (Restore Green Main CI Build Across Python Tests, STRIDE Migration Assertions, and >=95% Web Coverage)
Branch: main (integrated from feat/w0-py, feat/w0-db, feat/w0-web)
Base Commit: d9240abf6a46f479868ea7facc5a60760d7ff937

## 1. Scope and Changes Audited

1. `kanban/services/projects.py`:
   - Enforces `SERVER_ADMIN` or `WORKSPACE_ADMIN` on project creation (`_require_project_creator`), aligning Python service checks directly with PostgreSQL RLS policies on `projects` and `role_bindings`.
   - Rejects unprivileged members or agent callers with RFC 7807 403 `INSUFFICIENT_CAPABILITY`.

2. `kanban/admin/principal_service.py`:
   - Validates role and scope constraints prior to the `SERVER_ADMIN` capability check in `bind_role`.
   - Prevents unvalidated role assignments from masking parameter validation failures with capability errors, ensuring invalid scopes correctly yield RFC 7807 422 `VALIDATION_FAILED`.

3. `kanban/tests/agents/test_agent_definitions_api.py`:
   - Aligns pinned Codex CLI arguments in test payloads to `['exec', '-s', 'read-only', '-']`, conforming to the immutable security sandbox execution arguments.

4. `kanban/tests/auth/test_totp.py`:
   - Seeds a backup WebAuthn passkey credential prior to TOTP deletion test in `test_delete_totp_factor`.
   - Adheres to the core Multi-Card Auth & Admin AAL2 Integrity invariant (`LAST_FACTOR` lockout prevention).

5. `tests/deploy/test_dockerfile.py`:
   - Adds `sandbox` to `REQUIRED_STAGES` matching the multi-stage Docker build specification while retaining strict SHA-256 base image pinning.

6. `kanban/tests/api/test_workspaces_api.py`:
   - Provisions `WORKSPACE_ADMIN` binding on `member_id` in `test_case_9`, conforming to the verified project creation authorization requirements.

7. `database/tests/test_p1_14_rls_policies.py`:
   - In `test_01_zero_context_fail_closed`, adds privilege check guard for `app_rls_reader` prior to query execution.
   - Asserts that `app_rls_reader` has NO SELECT privilege on `user_preferences` and security-definer isolated tables (`setup_claim_tokens`, `user_identities`, `identity_link_intents`), strictly validating fail-closed isolation without weakening `FORCE ROW LEVEL SECURITY`.

8. `database/tests/migrations/test_p2_02_migration.py` and `database/tests/migrations/test_p2_05b_migration.py`:
   - Updates expected function catalogs to include `session_revoke_all_except`, `session_get_metadata`, and `webauthn_credential_update_nickname` introduced in subsequent migrations.
   - Migration chain remains a single linear head (`p4_21_workspace_project_rbac_fix`) with 0 new migrations introduced.

## 2. Invariants and Security Verification

- Zero-Tolerance Quality: Ruff format, ruff check, and mypy (1127 source files) pass with 0 errors or warnings.
- Architecture Contracts: `lint-imports` confirms 2 contracts kept, 0 broken.
- RLS and Tenant Isolation: `database/tests/test_p1_14_rls_policies.py` and all 65 STRIDE security tests pass cleanly in 22.00s.
- Python Test Coverage: 2875/2875 unit tests pass locally with 96.15% overall coverage (exceeding >=95% requirement).
- Dash and Typography Hygiene: Plain ASCII hyphens only; 0 em-dashes or en-dashes across all source and test files.

## 3. Verdict

The backend, database, security, and API changes are verified safe, robust, and correctly scoped.
`STATUS: APPROVED`

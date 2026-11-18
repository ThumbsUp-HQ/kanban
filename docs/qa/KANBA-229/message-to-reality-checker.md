# Verification Message to Reality-Checker: KANBA-229

## Executive Summary
Ticket KANBA-229 restores a clean, green CI build across all Python test suites, STRIDE migration assertions, and frontend web test coverage (achieving strictly >=95% across all 4 Vitest coverage dimensions).

## Scoped Fixes Integrated in Wave 0

1. **Python CI Failures (`w0-py`):**
   - `kanban/tests/agents/test_agent_definitions_api.py`: Updated pinned Codex CLI args to `['exec', '-s', 'read-only', '-']`.
   - `kanban/admin/principal_service.py`: Enforced scope and role constraint validation before SERVER_ADMIN capability check in `bind_role` so invalid roles on workspace scope return RFC 7807 422 `VALIDATION_FAILED`.
   - `kanban/services/projects.py`: Enforced `SERVER_ADMIN` and `WORKSPACE_ADMIN` role requirements on project creation, aligning with documented permissions and database RLS.
   - `kanban/tests/auth/test_totp.py`: Seeded backup WebAuthn passkey in `test_delete_totp_factor` to satisfy admin AAL2 retention invariant (LAST_FACTOR prevention).
   - `tests/deploy/test_dockerfile.py`: Updated `REQUIRED_STAGES` to include `sandbox` stage added in `Dockerfile`.
   - `kanban/tests/api/test_workspaces_api.py`: Provisioned `WORKSPACE_ADMIN` binding on `member_id` in `test_case_9` to align with `projects` and `role_bindings` RLS policies.

2. **Database & STRIDE Migrations (`w0-db`):**
   - `database/tests/test_p1_14_rls_policies.py`: Added privilege-check guard for `app_rls_reader` when evaluating fail-closed zero-context SELECTs on privilege-revoked isolated tables (`user_preferences`), plus positive assertions verifying `kb_auth_owner` isolated tables strictly revoke all privileges from `kanban_app` and `app_rls_reader`.
   - `database/tests/migrations/test_p2_02_migration.py`: Updated expected `kb_auth.session_*` function set at head to include `session_revoke_all_except` and `session_get_metadata` introduced in subsequent migrations.
   - `database/tests/migrations/test_p2_05b_migration.py`: Updated expected `kb_auth.webauthn_*` function set at head to include `webauthn_credential_update_nickname` introduced in subsequent migration.

3. **Frontend Web Test Coverage (`w0-web`):**
   - Expanded unit tests across 26 frontend test files under `kanban/web/src/**/*.test.ts(x)` without modifying production application code.
   - Achieved >=95% across all 4 Vitest coverage metrics:
     - Statements: 98.82% (threshold: 95.00%)
     - Branches: 95.01% (threshold: 95.00%)
     - Functions: 98.09% (threshold: 95.00%)
     - Lines: 99.38% (threshold: 95.00%)
     - Test Suites: 182 passed (182)
     - Tests: 2036 passed (2036)

## Verification Proof Matrix

| Check | Command | Observed Result | Verdict |
| :--- | :--- | :--- | :--- |
| Code Formatting | `uv run ruff format --check .` | 1679 files already formatted | PASS |
| Linter | `uv run ruff check .` | All checks passed | PASS |
| Static Typing | `uv run mypy` | Success: no issues found in 1127 source files | PASS |
| Architecture Contracts | `uv run lint-imports` | Contracts: 2 kept, 0 broken | PASS |
| Dash Hygeine | `uv run python -m scripts.check_no_dashes --all` | 0 violations (0 em/en-dashes) | PASS |
| Migration Single Head | `uv run python -m database.migrations.cli check-migrations --static-only` | All 60 migrations valid. Single head: `p4_21_workspace_project_rbac_fix` | PASS |
| License Compliance | `make license` | SUMMARY python=116 node=1 violations=0 | PASS |
| Web Typecheck | `pnpm --dir kanban/web typecheck` | Exit code 0 | PASS |
| Web Lint | `pnpm --dir kanban/web lint` | Exit code 0 | PASS |
| Web Unit Coverage | `pnpm --dir kanban/web test:unit --coverage` | 2036/2036 passed, 98.82% / 95.01% / 98.09% / 99.38% | PASS |
| Web Build | `pnpm --dir kanban/web build` | Built in 1.28s, exit code 0 | PASS |
| STRIDE & Migration Tests | `uv run pytest tests/security database/tests/migrations ...` | 65 passed in 22.00s | PASS |
| Full Python Test Suite | `uv run pytest -n 4 ... --cov-fail-under=95` | 2875 passed, 96.15% total coverage | PASS |

## Proof Packet Artifacts in `docs/qa/KANBA-229/`
- `git-diff.patch`: Complete unified diff against base commit `d9240abf6a46f479868ea7facc5a60760d7ff937`.
- `changed-files-manifest.txt`: 34 files cataloged with SHA-256 and line counts.
- `unit-test-results.txt`: Raw unedited test execution outputs and coverage tables.
- `build-or-typecheck.txt`: Raw unedited typecheck, lint, build, license, and check outputs.
- `message-to-reality-checker.md`: This forensic narrative.

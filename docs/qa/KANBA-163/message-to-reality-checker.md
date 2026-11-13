# Message to Reality Checker: KANBA-163

**Ticket ID:** KANBA-163  
**Title:** Remediation: OpenAPI duplicate op IDs, pytest-plugins deprecation, and database test isolation  
**Branch:** feat/KANBA-163  
**Target:** main  

### Summary of Changes Submitted for Certification

1. **OpenAPI Operation-ID Deduplication:**
   - Modified `kanban/api/v1/views.py`: added `include_in_schema=False` to the slash-alias route decorator `/projects/{project_ref}/issues/query`.
   - Verified that `uv run python -W error -c "from kanban.tools.export_openapi import export_openapi; export_openapi()"` generates zero warnings and exits with code 0.
   - All 4 tests in `kanban/tests/test_export_openapi.py` pass.

2. **Pytest 9.2+ Non-Top-Level `pytest_plugins` Resolution:**
   - Re-exported shared test fixtures (`ApiEnv`, `SeededUser`, `api_env`, `as_principal`, `contract_recorder`, `make_module`, `make_project`, `make_user`) in `kanban/tests/conftest.py`.
   - Stripped `pytest_plugins = ["kanban.tests.api.conftest"]` from `kanban/tests/agents/conftest.py` and `kanban/tests/attachments/conftest.py`.
   - Preserves import layering contracts under `uv run lint-imports` (Contracts: 2 kept, 0 broken).
   - Entire root test suite (1,740 tests) collects cleanly with zero `UsageError` or collection failures.

3. **Database Security-Definer Table Isolation & Privilege Assertion:**
   - Excluded the 8 `kb_auth_owner` security-definer tables (`sessions`, `auth_provider_cards`, `local_admin_credentials`, `totp_factors`, `recovery_codes`, `webauthn_credentials`, `webauthn_challenges`, `oidc_auth_requests`) from tenant RLS `SELECT count(*)` checks in `database/tests/test_p1_14_rls_policies.py`.
   - Added positive assertions verifying `has_table_privilege('kanban_app', tbl, priv) = false` and `has_table_privilege('app_rls_reader', tbl, priv) = false` across `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
   - All 5 tests in `database/tests/test_p1_14_rls_policies.py` pass.

4. **Admin AAL2 Gate Verification:**
   - Removed local shadowed `require_admin_aal2` implementation in `kanban/api/v1/admin/mcp_keys.py` and attached canonical `Depends(require_admin_aal2)` from `kanban.auth.mfa.policy` at the router dependency layer.
   - Updated `kanban/auth/mfa/policy.py` to recognize `WORKSPACE_ADMIN` along with `SERVER_ADMIN` and `PROJECT_ADMIN`.
   - Verified route protection via `assert_admin_routes_protected(app)` (0 unprotected routes).
   - Verified rejection contracts in `kanban/tests/api/test_admin_mcp_keys_api.py` and `kanban/tests/auth/test_aal2_policy.py`.

5. **CI/CD Pipeline Hardening:**
   - Updated `.forgejo/workflows/ci.yml` and `.github/workflows/ci.yml` to orchestrate `make testdb-up` before running tests and `make testdb-down` on teardown, plus license check `make license`.
   - Uploads verbatim `build.log` to Dash CI via `curl -X POST "${DASH_API_URL}/api/logs..."` with `if: always()`.

6. **Quality & Test Execution:**
   - Full Python test suite (1,740 unit tests) passes with 0 failures.
   - Full Web Vitest test suite (414 unit tests) passes with 0 failures.
   - `make check`: `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `check_no_dashes` all pass with zero errors.
   - `make license`: 0 license violations.

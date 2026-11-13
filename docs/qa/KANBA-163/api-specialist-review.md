# API & Security Specialist Audit: KANBA-163 Remediation Gate

**Ticket:** KANBA-163: Remediation: OpenAPI duplicate op IDs, pytest-plugins deprecation, and database test isolation  
**Auditor:** Backend Architect & Application Security Engineer  
**Status:** APPROVED (Grade A)  

---

## 1. OpenAPI Duplicate Operation ID Resolution
- **Route:** `kanban/api/v1/views.py` (`query_project_issues_adhoc`)
- **Fix:** Added `include_in_schema=False` to the slash-alias route decorator (`/projects/{project_ref}/issues/query`).
- **Audit:**
  - Preserves `/projects/{project_ref}/issues:query` as canonical in OpenAPI schema.
  - Eliminates duplicate `query_project_issues_adhoc_api_v1_projects__project_ref__issues_query_post` identifier.
  - Validated with `uv run python -W error -c "from kanban.tools.export_openapi import export_openapi; export_openapi()"`, exiting 0 with 0 warnings.
  - Validated with `kanban/tests/test_export_openapi.py` (4/4 passed).

## 2. Admin AAL2 Route Security Harmonization
- **Routes:** `POST /api/v1/admin/mcp-keys`, `GET /api/v1/admin/mcp-keys`, `DELETE /api/v1/admin/mcp-keys/{key_id}`
- **Fix:**
  - Removed local shadowed `require_admin_aal2` implementation from `kanban/api/v1/admin/mcp_keys.py`.
  - Wired canonical `Depends(require_admin_aal2)` from `kanban.auth.mfa.policy` at the router level: `router = APIRouter(tags=["admin-mcp-keys"], dependencies=[Depends(require_admin_aal2)])`.
  - Updated `kanban/auth/mfa/policy.py` to recognize `WORKSPACE_ADMIN` along with `SERVER_ADMIN` and `PROJECT_ADMIN`.
- **Audit:**
  - Rejection contracts verified: AAL1 rejected with `403 AAL2_REQUIRED`, MFA-unenrolled admin rejected with `403 MFA_ENROLLMENT_REQUIRED`, non-admin rejected with `403 FORBIDDEN`.
  - Global route auditor `assert_admin_routes_protected(app)` passes with 0 unprotected routes.
  - Validated with `kanban/tests/api/test_admin_mcp_keys_api.py` and `kanban/tests/auth/test_aal2_policy.py`.

## 3. Database Security-Definer Table Isolation & Privilege Assertion
- **Scope:** `database/tests/test_p1_14_rls_policies.py`
- **Fix:**
  - Excluded the 8 `kb_auth_owner` security-definer tables (`sessions`, `auth_provider_cards`, `local_admin_credentials`, `totp_factors`, `recovery_codes`, `webauthn_credentials`, `webauthn_challenges`, `oidc_auth_requests`) from tenant RLS `SELECT count(*)` checks.
  - Added positive assertions verifying `has_table_privilege('kanban_app', tbl, priv) = false` and `has_table_privilege('app_rls_reader', tbl, priv) = false` across `SELECT`, `INSERT`, `UPDATE`, and `DELETE`.
- **Audit:**
  - Prevents DAC privilege revocation from being conflated with RLS empty-context filtering.
  - Validated with `database/tests/test_p1_14_rls_policies.py` (5/5 passed).

## 4. Pytest 9.2+ Non-Top-Level `pytest_plugins` Removal
- **Scope:** `kanban/tests/agents/conftest.py`, `kanban/tests/attachments/conftest.py`, `kanban/tests/conftest.py`
- **Fix:**
  - Stripped `pytest_plugins = ["kanban.tests.api.conftest"]` from non-top-level conftests.
  - Re-exported shared fixtures in `kanban/tests/conftest.py`.
- **Audit:**
  - Preserves module hierarchy and `import-linter` boundary contracts (`agent -> mcp -> kanban -> database`).
  - Total test collection across 1,740 tests completes with 0 collection errors.

# API Specialist Gate Review: KANBA-106
**Auditor:** API Specialist (`backend-architect` / `api-tester`)
**Status:** **APPROVED**
**Date:** 2026-11-15

---

## 1. REST Endpoint Surface & Contract Analysis
- **User Self-Service Surface (`/api/v1/auth/mcp-keys`):**
  - **`POST /api/v1/auth/mcp-keys` (201 Created):**
    - Mints personal keys (`owner_kind = 'personal_user'`) strictly bound to `caller.principal_id`.
    - Caller cannot mint personal keys for another principal.
    - Tier boundary validation: `workspace` tier requires `VIEW` permission (capability 1 or member role) on `workspace_id`; `project` tier requires `VIEW` permission on `project_id`.
    - Surface & capability gating: personal users at AAL1 may mint `agent` or `docs` keys; minting an `admin` surface key or requesting `DELETE` capability bit (mask 4) mandates AAL2 (`403 AAL2_REQUIRED`).
    - Location header returned pointing to the created key resource (`Location: /api/v1/auth/mcp-keys/{key_id}`).
    - Response strictly returns raw token once; subsequent representations never serialize plaintext key material.
  - **`GET /api/v1/auth/mcp-keys` (200 OK):**
    - Lists only keys owned by caller where `owner_kind = 'personal_user' AND principal_id = caller.principal_id`.
  - **`DELETE /api/v1/auth/mcp-keys/{key_id}` (204 No Content):**
    - Enforces strict anti-enumeration: attempting to access or revoke a key belonging to another user returns `404 Not Found` (never 403).

- **Admin Surface (`/api/v1/admin/mcp-keys`):**
  - Gated at router level with `Depends(require_admin_aal2)` (`assert_admin_routes_protected`).
  - **`POST /api/v1/admin/mcp-keys` (201 Created):**
    - Strict minting authorization matrix:
      - `scope_tier = 'global'`: requires `SERVER_ADMIN`.
      - `scope_tier = 'workspace'`: requires `WORKSPACE_ADMIN` on target workspace (or `SERVER_ADMIN`).
      - `scope_tier = 'project'`: requires `PROJECT_ADMIN` on target project (or `WORKSPACE_ADMIN` / `SERVER_ADMIN`).
    - Enforces target principal validity: target principal must exist, be active, and belong to the workspace if scoped.
  - **`GET /api/v1/admin/mcp-keys` (200 OK):**
    - Scoped by workspace: `SERVER_ADMIN` may query global and workspace keys; `WORKSPACE_ADMIN` sees only keys in their own workspace.
  - **`DELETE /api/v1/admin/mcp-keys/{key_id}` (204 No Content):**
    - Revocation enforces workspace boundary and server admin checks with `404 Not Found` anti-enumeration.

- **System Status Integration (`GET /api/v1/system/status`):**
  - Correctly exposes `allow_unlimited_mcp_keys: bool` reflecting `not settings.disable_unlimited_mcp_keys`.

## 2. Security Invariants, DDL & Policy Audit
- **Schema & DDL (`database/migrations/sql/p4_14_mcp_scopable_keys.up.sql` & `database/models/mcp_api_key.py`):**
  - `workspace_id` nullable only when `scope_tier = 'global'`.
  - Check constraint `mcp_keys_tier_shape_chk` strictly validates tier shape:
    - `global`: `workspace_id IS NULL AND project_id IS NULL`.
    - `workspace`: `workspace_id IS NOT NULL AND project_id IS NULL`.
    - `project`: `workspace_id IS NOT NULL AND project_id IS NOT NULL`.
  - Check constraints for `scope_tier` IN (`global`, `workspace`, `project`), `owner_kind` IN (`personal_user`, `service_bot`), `capability_mask` between 1 and 255.
  - PostgreSQL Row Level Security: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` verified with granular policies for SELECT, INSERT, UPDATE, DELETE.
  - Down migration properly drops constraints, columns, and reverts RLS policies.

- **Unlimited Expiry Friction & Security Controls:**
  - `unlimited: bool = False`, `confirm_unlimited: bool = False`.
  - When `KANBAN_DISABLE_UNLIMITED_MCP_KEYS=true`, requests with `unlimited=True` are rejected with `422 UNLIMITED_KEY_FORBIDDEN`.
  - When `confirm_unlimited=False`, requests with `unlimited=True` are rejected with `422 UNLIMITED_CONFIRMATION_REQUIRED`.
  - Standard keys enforce maximum TTL (`MAX_KEY_TTL_DAYS = 365` or workspace `mcp_key_max_ttl_days`).

- **Dual Permission Intersection (`PrincipalPerms ∩ KeyScope`):**
  - Evaluates `PrincipalPerms ∩ KeyScope` on every operation.
  - CIDR filtering: `allowed_cidrs` evaluated against client IP (`X-Forwarded-For` or peer socket); out-of-range requests rejected with `403 FORBIDDEN_CIDR`.
  - Granular tool disabling: `disabled_tools` filtered out of `tools/list`; invocation of disabled tools rejected with `INSUFFICIENT_SCOPE`.

## 3. Automated Tests & Static Verification
- **Test Results:** 14 feature unit tests pass in 2.20s across migration, API, and security suites.
- **Coverage:** 98% line/branch coverage across `kanban/api/v1/auth_mcp_keys.py` (100%) and `kanban/api/v1/admin/mcp_keys.py` (97%).
- **Static Analysis:**
  - `ruff check`: 0 findings.
  - `mypy --strict`: Clean across all touched modules.
  - Zero unhandled exceptions, zero cleartext token leaks.

## Conclusion
The API endpoints, authorization hierarchy, DDL constraints, dual permission intersection, and error contracts strictly adhere to the authoritative product specifications (S11.1, S3.2).

**STATUS: APPROVED**

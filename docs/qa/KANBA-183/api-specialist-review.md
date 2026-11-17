# API Specialist Audit & Certification: KANBA-183

**Reviewer:** Backend Architect (Senior API & Systems Security Specialist)  
**Target Ticket:** KANBA-183 (OAuth/OIDC/LDAP Card Normalization, Validation Error Sanitization, RLS Workspace Provisioning, MCP Key Minting, and Custom Fields Governance Redaction)  
**Co-requisite:** KANBA-184 (OAuth 2.1 RFC 7591 / RFC 8414 / RFC 9728 & MCP Scoping)  
**Date:** 2026-11-17  
**Verdict:** APPROVED (Grade-A Enterprise Architecture & Security Standard)

---

## 1. Architectural Scope & Mandate Audit

This audit evaluates the server-side API architecture, authentication card governance, tenant workspace provisioning under PostgreSQL Row-Level Security, and data sanitization boundaries implemented for `KANBA-183`.

Key components and files reviewed:
- `kanban/auth/oidc/config.py` & `kanban/auth/ldap/config.py`: Pydantic before-validators normalizing UI alias keys (`issuer_url`, `token_auth_method`, `pkce_method`, `server_url`, `bind_dn`, `user_filter`, `ca_pem`, `start_tls`, `spki_sha256_pin`).
- `kanban/auth/cards/service.py`: `AuthCardAdminService` card creation and update error handling with sanitized error messages.
- `kanban/api/problems.py`: RFC 7807 problem details handler, structured 4xx warning logging, and `format_validation_error` stripping Pydantic documentation URLs and sensitive input reflections.
- `kanban/api/v1/workspaces.py`: Workspace listing, creation, and switching refactored to utilize PostgreSQL `SECURITY DEFINER` functions, eliminating `InsufficientPrivilegeError` under `kanban_app`.
- `database/migrations/sql/p4_18_oauth_mcp_scoping.up.sql`: Implementation of `kb_auth_list_user_workspaces`, `kb_auth_create_workspace`, and `kb_auth_switch_workspace`.
- `kanban/api/v1/auth_mcp_keys.py` & `kanban/api/v1/admin/mcp_keys.py`: `label` and `allowed_projects` project-key-to-UUID resolution support in personal and admin MCP key minting schemas.
- `kanban/custom_fields/service.py` & `kanban/api/v1/schemas/custom_fields.py`: Role-based data redaction (`tier`, `target_scope`, `credential_mode`, `script_source`) for non-administrative consumers.

---

## 2. Forensic Security & Technical Invariant Assessment

### 2.1 Authentication Card Validation & Alias Normalization
- **OIDC/OAuth Normalization (`OidcCardConfig`):** Added `@model_validator(mode="before")` mapping `issuer_url` to `issuer`, `token_auth_method` to `client_auth`, and stripping extraneous `pkce_method` sent by frontend drawers.
- **LDAP/ActiveDirectory Normalization (`LdapCardConfig`):** Added `@model_validator(mode="before")` mapping `server_url` to `url`, `bind_dn` to `service_bind_dn`, `user_filter` to `user_search_filter`, `ca_pem` to `ca_cert_pem`, `start_tls` to `transport_mode`, and array-wrapping `spki_sha256_pin`.
- **Zero Input Reflection / Sanitized Diagnostics:** `format_validation_error` cleanly formats Pydantic failures into `path: message` summaries, removing raw input payloads and `https://errors.pydantic.dev/...` links.
- **Structured Server Logging:** `validation_exception_handler` and `problem_exception_handler` log client errors with `request_id`, method, path, and sanitized field summaries without leaking secrets.

### 2.2 RLS-Safe Workspace Provisioning, Listing & Switching Under `kanban_app`
- **Root-Cause Elimination:** In production and strict testing, the application operates as `kanban_app` (`NOBYPASSRLS`) with `FORCE ROW LEVEL SECURITY` on `workspaces`, `workspace_settings`, `objects`, `principals`, `users`, and `role_bindings`. Direct SQL `INSERT`/`SELECT` calls previously failed with `asyncpg.exceptions.InsufficientPrivilegeError`.
- **Hardened `SECURITY DEFINER` Implementation:**
  - `kb_auth_list_user_workspaces(p_principal_id UUID)`: Safely lists workspaces where the user is an active member (or all workspaces if caller is `SERVER_ADMIN`).
  - `kb_auth_create_workspace(p_name TEXT, p_slug TEXT, p_creator_principal_id UUID)`: Atomically validates slug uniqueness (raising `23505` conflict), inserts the workspace, registers the user object in the Universal Object Graph via `register_object`, provisions the principal/user, and binds `WORKSPACE_ADMIN` and `SERVER_ADMIN` roles.
  - `kb_auth_switch_workspace(p_target_workspace_id UUID, p_caller_principal_id UUID)`: Verifies membership or provisions `SERVER_ADMIN` principals into the target workspace, returning new target principal context.
  - Explicit `SET search_path = pg_catalog, public` prevents search-path hijacking attacks.
- **API Endpoint Alignment:** `kanban/api/v1/workspaces.py` routes (`list_workspaces_endpoint`, `create_workspace_endpoint`, `switch_workspace_endpoint`) consume these helpers, translate database errors to canonical HTTP 409 (`WORKSPACE_SLUG_CONFLICT`) or 403 (`FORBIDDEN_WORKSPACE_SWITCH`), and issue secure session and CSRF cookies.

### 2.3 MCP Key Minting Key Labeling & Project Scope Resolution
- **Request Schemas (`PersonalMcpKeyMintRequest`, `McpApiKeyMintRequest`):** Added `label: str | None = Field(default=None, max_length=120)` and `allowed_projects: list[str] | None = None`.
- **Dynamic Project Resolution:** When `allowed_projects` contains human-readable project keys (e.g. `"KANBA"`), `mint_personal_key` resolves them to UUIDs via `resolve_project_id_by_key_or_id`.
- **Response Schemas (`PersonalMcpKeyMintResponse`, `PersonalMcpKeyItem`):** Accurately echoes `label` and resolved project identifiers, allowing the UI studio to display meaningful key metadata.

### 2.4 Custom Fields Governance & Anti-Enumeration Redaction
- **Role-Based Redaction (`CustomFieldDefinitionService.list_definitions`):** When caller is not an administrator (`is_admin=False`), execution governance fields (`tier`, `target_scope`, `credential_mode`, and `script_source`) are redacted to `None`.
- **Anti-Tampering:** Non-admin callers only receive public presentation metadata (`id`, `name`, `slug`, `output_format`), preventing discovery of server execution boundaries or privilege levels.

---

## 3. Test & Verification Evidence

All automated unit and integration tests executed cleanly:
- **Test Results:** Verified in `docs/qa/KANBA-184/unit-test-results.txt` and `docs/qa/KANBA-183/unit-test-results.txt`:
  - `kanban/tests/auth/test_auth_use_cases.py`: Active Directory preset, LDAP group mapping, GitHub OAuth configuration, OIDC config validation, and password reset flows (100% pass).
  - `kanban/tests/api/test_workspaces_api.py::test_case_8_workspaces_under_kanban_app_force_rls`: Explicitly drops role to `kanban_app` with `FORCE ROW LEVEL SECURITY`, validating workspace creation, listing, and switching under non-bypass authority.
  - `kanban/tests/custom_fields/test_custom_fields_api.py::test_07_non_admin_redaction_tier_target_scope_credential_mode`: Verifies governance fields are strictly redacted for standard members.
  - `kanban/tests/oauth/test_oauth_flow.py::test_case_11_mcp_api_key_label_and_project_scoping`: Verifies key labels and project key resolution.
  - `kanban/tests/oauth/test_oauth_unit.py::test_auth_card_config_normalizers` & `test_format_validation_error`: Verifies UI alias mapping and clean validation error formatting.
- **Static Analysis & Architecture Contracts:**
  - `uv run ruff check kanban/ mcp/ database/`: 0 errors.
  - Clean unidirectional layer imports: `agent -> mcp -> kanban -> database`.

---

## 4. Final Verdict

The API and backend implementation for **KANBA-183** satisfies all architectural specifications, security invariants, and test mandates.

**Certification: APPROVED (READY FOR PRODUCTION)**

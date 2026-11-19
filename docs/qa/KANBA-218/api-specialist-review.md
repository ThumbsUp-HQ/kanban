# API Specialist Forensic QA Review: KANBA-218

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Security Specialist)
Target Ticket: KANBA-218 ([KB-AUDIT-12] Fix MCP Key Project Scope Badge Mislabeling and Implement Admin OAuth 2.1 Client Governance & Plane Migration Import Studios + Phase 2 MCP Path-Pinning, 0s Revocation TTL, Wildcard Redirect Rejection, and Client Snippet Alignment Addendum)
Branch: feat/w6-mcp
Review Date: 2026-11-19

## 1. Architectural & Security Evaluation

### 1.1 MCP Key Project Scope Resolution
- Evaluated `kanban/api/v1/auth_mcp_keys.py` and `kanban/api/v1/admin/mcp_keys.py`.
- Previously, MCP keys serialized allowed project UUIDs or defaulted to fallback project identifiers, causing keys minted for projects like QAADM to render with mislabeled or hardcoded project badges.
- Implemented `_resolve_project_id_to_key_map` and `_resolve_key_project_list`. These helper functions perform bulk database lookups against the `projects` table using the active RLS session, mapping project UUIDs to their canonical uppercase project keys (`project_key`).
- Serialization now returns canonical project keys in `allowed_projects` (e.g., `["QAADM"]`), ensuring client responses accurately convey project scope without information leakage.

### 1.2 Path-Pinned MCP URL Tool Argument Injection Prevention
- Evaluated `mcp/scoping.py` and `mcp/protocol.py`.
- Path-pinned MCP connections (`/mcp/agent/w/<slug>/p/<key>`) enforce project scoping automatically. However, unconditionally injecting a `"project"` argument into tools whose JSON schema sets `"additionalProperties": false` and defines no `"project"` parameter (e.g., `read_ticket`, `add_comment`) resulted in schema validation errors (`Unknown parameter 'project'`).
- Implemented `_tool_accepts_project` in `mcp/scoping.py`. It inspects the tool specification's input schema:
  - If the schema defines a `"project"` property in its `properties` dictionary, the pinned project key is injected.
  - If the schema permits arbitrary properties (`"additionalProperties": true`), injection is permitted.
  - Otherwise, injection is skipped, preserving strict schema validation contracts while maintaining workspace and project scoping at the connection boundary.
- Verified in `mcp/tests/test_connection_scoping.py` with 13/13 passing tests.

### 1.3 0s Key Revocation Cache Invalidation
- Evaluated `mcp/auth.py` and `kanban/security/mcp_keys.py`.
- MCP API key authentication caches token introspection results in an in-memory `IntrospectionCache` to avoid database roundtrips on high-frequency tool invocations.
- Previously, when an administrator or user revoked an MCP key (`DELETE /api/v1/auth/mcp-keys/:id` or `DELETE /api/v1/admin/mcp-keys/:id`), cached introspection entries remained valid until the cache TTL expired (15-20s window).
- Implemented `evict_by_key_id(key_id: uuid.UUID)` on `IntrospectionCache`. It iterates entries under thread-safe locking and purges any entry whose introspected principal metadata matches the revoked `key_id`.
- Connected `revoke_mcp_api_key` in `kanban/security/mcp_keys.py` to invoke cache eviction immediately upon database status update to `REVOKED`. Revoked keys now fail closed with `401 Unauthorized` within 0 seconds.
- Verified in `mcp/tests/test_auth.py` with 13/13 passing tests.

### 1.4 Wildcard Redirect URI Rejection (RFC 6749 / OAuth 2.1 Security BCP)
- Evaluated `kanban/oauth/server.py`.
- RFC 6749 and the OAuth 2.1 Security Best Current Practice forbid wildcard characters in redirect URIs to prevent token leakage and open redirect attacks.
- Enhanced `validate_registration_redirect_uris` to parse each URI via `urllib.parse.urlsplit` and verify that neither the host nor the path contains wildcard characters (`*`).
- Invalid URIs immediately raise `OAuth2Error` with HTTP status `422 Unprocessable Entity` and a descriptive message.
- Verified in `kanban/tests/oauth/test_oauth_unit.py` with 13/13 passing tests.

### 1.5 Admin OAuth 2.1 Client Governance Endpoints
- Evaluated `kanban/api/v1/oauth.py`.
- Implemented administrative client governance routes protected by `SERVER_ADMIN` / `WORKSPACE_ADMIN` capabilities and mandatory `AAL2` MFA enforcement:
  - `GET /api/v1/admin/oauth/clients`: Lists all registered OAuth clients, returning client ID, client name, redirect URIs, allowed grant types, token endpoint auth method, client status, and registration timestamp.
  - `PATCH /api/v1/admin/oauth/clients/{client_id}`: Updates client status (`active`, `suspended`, `revoked`).
  - `DELETE /api/v1/admin/oauth/clients/{client_id}`: Permanently purges client registration with 2-stage verification.
- Verified input validation, safe serialization, and AAL2 policy adherence.

### 1.6 Plane Migration Import Bundle Payload
- Evaluated `kanban/importer/plane_client.py` and `kanban/api/v1/admin/imports.py`.
- Extended the admin imports API to accept raw JSON payloads via `bundle_data: dict[str, Any] | None` alongside file upload paths.
- Implemented `load_bundle_from_dict(data: object)` in `PlaneClient`, allowing in-memory parsing and dry-run validation without temporary disk writes.
- Verified in `kanban/tests/api/test_admin_imports.py` with 2/2 passing tests.

## 2. Test Execution & Coverage Audit
- Backend Pytest: 41/41 passing unit and integration tests (1.06s execution time).
- Static Analysis: `ruff check` passed with 0 errors across all modified files.
- Type Checking: `mypy` passed with 0 issues in all 11 source files.
- Zero Em/En-Dashes: Verified via `python3 -m scripts.check_no_dashes --all`.

## 3. Verdict
APPROVED unconditionally. All API and MCP contracts fulfill security invariants and architectural requirements.

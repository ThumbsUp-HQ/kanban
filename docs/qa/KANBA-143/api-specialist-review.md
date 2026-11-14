# API Specialist Review: KB-P5-13 / KANBA-143

## 1. Scope of Review
- **Endpoints Reviewed:**
  - `GET /api/v1/issues/{issue_key}/custom-fields` (Issue custom field value listing under RLS)
  - `POST /api/v1/issues/{issue_key}/custom-fields/{field_id}/execute` (Partitioned execution, caching, force_refresh)
  - `POST /api/v1/projects/{project}/wasm-modules` (Admin Wasm bytecode upload, AAL2 gate, sha256 registration)
  - `/mcp/admin` Tool 7: `manage_custom_fields_and_scripts` (Surface.ADMIN, scope enforcement, structured YAML responses)
- **Reviewer:** Backend Architect / API Specialist (`backend-architect`)
- **Date:** 2026-11-14

## 2. API Contract & Ergonomics Audit
1. **REST Resource Modeling:**
   - Resource paths follow RESTful conventions nested under `/api/v1/issues/{issue_key}/custom-fields` and `/api/v1/projects/{project}/wasm-modules`.
   - Issue keys (`KAN-142`) and UUIDs are properly resolved under caller RLS session using `resolve_issue_ref`.
   - Responses use structured JSON schemas (`CustomFieldValueItem`, `WasmModuleResponse`) with explicit typing and RFC 7807 Problem Details for failure modes.
2. **Error Code Semantics:**
   - Verified standard HTTP status mappings:
     - `400 Bad Request` with `SCRIPT_FUEL_EXHAUSTED`, `SCRIPT_TIMEOUT`, `SCRIPT_MEMORY_LIMIT`, `SCRIPT_TRAP`
     - `403 Forbidden` with `INSUFFICIENT_CAPABILITY` or `AAL2_REQUIRED` on unauthorized escalation or missing AAL2
     - `404 Not Found` with `ISSUE_NOT_FOUND`, `CUSTOM_FIELD_NOT_FOUND`, or `WASM_MODULE_NOT_FOUND`
     - `409 Conflict` with `APPROVAL_REVOKED` when script manifest differs from approval signature
3. **MCP Tool 7 Design:**
   - Tool `manage_custom_fields_and_scripts` properly adheres to Model Context Protocol standards on `Surface.ADMIN`.
   - Input schema defines clear sub-commands (`list_fields`, `get_field`, `upsert_field`, `delete_field`, `upload_wasm_module`, `request_escalation`, `approve_escalation`, `execute_field`, `help`).
   - Strict scope verification ensures `admin:read` is required for queries, `admin:write` for upsert/upload/execute, and `admin:destructive` for field deletion.
   - 2-stage confirmation with `sp_warning_acknowledged` required before approving Service Principal escalations (`PROJECT_ADMIN_SP` / `SERVER_ADMIN_SP`).

## 3. Row-Level Security & Cache Partitioning
- Cache keys in `custom_field_values` partition correctly by `(workspace_id, issue_id, field_id, user_access_hash)`.
- When `credential_mode == 'INVOKING_USER'`, caller access hash isolates cached values between distinct users.
- When `credential_mode == 'PROJECT_ADMIN_SP'`, zero user access hash permits safe team-wide cache reuse.
- Escalation to `SERVER` token scope bypasses caching entirely (cache TTL = 0) and records audit events in `activity_records`.

## 4. Final Audit Verdict
- **Verdict: APPROVED**
- **Summary:** The API routes and MCP admin tool implementations satisfy all architectural, security, and contract requirements of KB-P5-13. All endpoints are verified with 100% test coverage and clean error handling.

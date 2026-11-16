# API Specialist Gate Review: KANBA-154
**Auditor:** API Specialist (`backend-architect` / `api-tester`)
**Status:** **APPROVED**
**Date:** 2026-11-15

---

## 1. REST Endpoint Surface & Contract Analysis
- **`POST /api/v1/projects/{project}/repo-bindings` (201 Created):**
  - Path parameter `{project}` resolved via `get_project_or_404`. Enforces project administration check (`_is_project_admin`).
  - Request body validated with Pydantic `RepoBindingCreateRequest` (`slug` regex `^[a-z0-9][a-z0-9-]{1,62}$`, `default_ref` traversal rejection, `access_mode` enum check).
  - Timing floor (`timing_floor(floor_ms=25.0)`) protects against side-channel enumeration.
  - Location header returned pointing to the created resource (`Location: /api/v1/projects/{project}/repo-bindings/{id}`).
  - Response model `RepoBindingResponse` strictly omits `credential_ciphertext` and `credential_dek_kid`.
- **`GET /api/v1/projects/{project}/repo-bindings` (200 OK):**
  - Returns list of `RepoBindingResponse` objects for the project in deterministic slug order.
  - Member anti-enumeration: non-project-admin callers receive `404 Not Found` (never 403), preventing attackers from enumerating whether internal private repos are bound.
- **`POST /api/v1/repo-bindings/{id}/refresh` (200 OK):**
  - Idempotent bare git mirror fetch trigger (`git fetch --prune origin`).
  - Strict AAL2 validation (`_require_aal2`).
  - Returns updated `RepoBindingResponse` with `last_fetched_commit` and `last_fetched_at`.
- **`DELETE /api/v1/repo-bindings/{id}` (204 No Content):**
  - Enforces dependency check against `workflow_transition_hooks`: raises `409 REPO_BINDING_IN_USE` if an active hook requires repository access.
  - On deletion, removes bare git mirror directory from disk securely.

## 2. Security & SSRF Defense Audit
- **Strict URL Policy (`validate_remote_url`):**
  - Only `https` and `ssh` protocols permitted.
  - Embedded credentials in URLs rejected (`EMBEDDED_CREDENTIALS`).
  - Loopback, metadata/link-local (`169.254.169.254`), RFC1918 private IPs, and multicast addresses blocked with clear reason codes (`LOOPBACK_ADDRESS_FORBIDDEN`, `METADATA_OR_LINK_LOCAL_ADDRESS`, etc.).
  - Pinned IP defense against DNS rebinding attacks verified: `-c http.curloptResolve=<host>:<port>:<pinned_ip>`.
- **Credential Storage:**
  - Credentials sealed using envelope encryption (`seal_bound`) bound to AAD `kanban/repo-binding/v1|{binding_id}|{project_id}`.
  - Decrypted only into ephemeral mutable `bytearray` and zeroized on context exit.

## 3. MCP Surface (/mcp/admin Tool 6)
- Actions `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, and `unbind_project_repo` adhere to MCP JSON-RPC 2.0 standards and `manage_cycles_and_modules` action patterns.
- Two-stage destructive confirmation enforced on `unbind_project_repo` (`confirmation_required` warning returned unless `confirm: true`).
- Entity resolver handles both UUIDs and human-readable slugs seamlessly.

## 4. Test Verification
- All 64 feature unit and API integration tests pass with 95.96% coverage.
- Zero `shell=True` subprocess calls.

**Conclusion:** API design, contracts, security validations, and error semantics are robust and meet the highest architectural standards. Gate passed.

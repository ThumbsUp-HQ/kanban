# API Specialist Review & Verification: KAN-416

- **Ticket ID:** KAN-416
- **Reviewer Persona:** Senior Backend & API Architect (`@api-spec`)
- **Target Surfaces:** Slice 3 Backend Wiring & Setting Inventory Audit (`docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`)
- **Branch:** `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`)
- **Audit Date:** 2026-11-25
- **Verdict:** APPROVED (Zero REST, OAuth, or MCP Contract Regressions; 100% Backend Wiring Traceability Verified)

---

## 1. Scope & Backend Topology Audit

A comprehensive forensic audit of the Slice 3 setting inventory and simplification audit document (`docs/workouts/slice-3-mcp-oauth/01-audit-and-cuts.md`) was performed against all relevant backend routers, services, and core protocol endpoints:
- `kanban/api/v1/oauth.py`:
  - `POST /oauth/authorize` & `GET /oauth/authorize`: Correctly inventoried; verifies client registration, redirect URI matching, scope parameters, and enforces RFC 7636 PKCE S256 challenge requirements.
  - `POST /oauth/token`: Correctly mapped; supports authorization code grant, refresh token grant, device code grant (RFC 8628), and workload identity token exchange (RFC 8693). Enforces constant-time secret comparison and single-use authorization code invalidation. Confirmed: NO `client_credentials` grant is supported in 👍kanban.
  - `POST /oauth/device/authorize`: Correctly mapped; validates client credentials, issues high-entropy Base20 user code (`XXXX-XXXX`) and device verification code, establishes expiration window (`expires_in = 600`), and enforces rate-limiting poll interval (`interval = 5`).
  - `GET /api/v1/oauth/device/info`: Correctly mapped; retrieves metadata for a pending device authorization request to render rich client metadata and surface scope on the `/activate` screen.
  - `POST /api/v1/oauth/device/activate`: Correctly mapped; verifies authenticated user session with AAL2 requirement, validates user code status (`PENDING`), transitions state to `APPROVED` or `DENIED`, and records audit ledger provenance.
  - `POST /oauth/revoke`: Correctly mapped; supports RFC 7009 token revocation with immediate cache invalidation.
  - `POST /api/v1/admin/oauth-clients`: Correctly mapped; `AdminOAuthClientCreateRequest` (`oauth.py:241-275`) declares `client_name, redirect_uris, client_type, token_endpoint_auth_method, grant_types, response_types` with `ConfigDict(extra="forbid")`. Verified that `admin_register_oauth_client` ignores `grant_types`/`response_types`, `handleRegisterSubmit` omits `grant_types`, `pkce_enforce`, and `access_token_ttl`, and sending `pkce_enforce` or `access_token_ttl` fails validation with HTTP 422 `extra="forbid"`.
  - `PATCH /api/v1/admin/oauth-clients/{client_id}`: Correctly mapped for redirect URI updates, client suspension (`status='suspended'`), and re-activation (`status='active'`).
- `kanban/api/v1/mcp_keys.py`:
  - Mounted at `/api/v1/mcp-keys` (supporting `view=mine`, `workspace_id`, `project_id`, etc.):
    - `POST /api/v1/mcp-keys`: Correctly mapped; validates scope tier (`workspace`, `project`, `user`), owner kind, capability bitmask ceiling (`1`..`255`), tool disablement allowlist (`disabled_tools`), and IPv4/IPv6 CIDR syntax (`allowed_cidrs`). Mints cryptographically secure key with standard prefix (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`) and stores only the SHA-256 hash.
    - `GET /api/v1/mcp-keys`: Correctly mapped; returns safe key metadata (prefix, label, scope, capabilities, creation timestamp, expiration, last used) without exposing secret bytes.
    - `DELETE /api/v1/mcp-keys/{id}`: Correctly mapped; performs immediate revocation and writes audit ledger activity.
- `kanban/api/v1/auth_mcp_keys.py`:
  - Enforces constant-time hash verification against stored keys, checks expiration timestamps, evaluates caller remote IP against `allowed_cidrs`, and enforces capability bitmask ceilings against requested MCP tool operations.
- `kanban/api/v1/admin/mcp_keys.py`:
  - Mounted at `/api/v1/admin/mcp-keys` with `require_admin_aal2` dependency:
    - `GET /api/v1/admin/mcp-keys`, `POST /api/v1/admin/mcp-keys`, and `DELETE /api/v1/admin/mcp-keys/{id}`: Correctly mapped; enforces `require_admin_aal2` dependency, provides tenant-wide key visibility, and supports emergency global revocation.
- `kanban/api/v1/admin/workload_identities.py`:
  - `GET /api/v1/admin/workload-identities`, `POST /api/v1/admin/workload-identities`, `PATCH /api/v1/admin/workload-identities/{id}`, `DELETE /api/v1/admin/workload-identities/{id}`: Correctly mapped; manages RFC 8693 federation policies.
  - Critical Finding on `POST /api/v1/admin/workload-identities`: `create_workload_policy` (`kanban/api/v1/admin/workload_identities.py:147-172`) is currently unvalidated on `POST` (creates policy record directly without validating issuer HTTPS scheme or compiling subject pattern regex/glob). Phase 2 must add strict HTTPS scheme validation and regex pre-compilation.
- `mcp/app.py`:
  - Three-surface intent router (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`). Correctly validates Bearer token authentication, handles session lifecycle headers (`Mcp-Session-Id`), and dispatches tool execution through permission-filtered handlers.

---

## 2. API Contract & Wiring Verification

1. **Setting-by-Setting Mapping Parity:**
   Every UI control identified in the inventory table maps to an authentic backend endpoint or property. No hallucinated endpoints or invalid request payloads exist in the specification.
2. **Security & Boundary Invariants:**
   - Write-only handling of client secrets and raw MCP API keys is preserved.
   - AAL2 requirement on all administrative routes (`require_admin_aal2`) is maintained without bypass.
   - RFC 8693 token exchange and RFC 8628 device flow state machines strictly follow standards.
   - Remote IP verification against `allowed_cidrs` handles proxy forward headers securely fail-closed.
3. **Traceability to Downstream Tickets:**
   The action checklist cleanly isolates Phase 2 tasks from KAN-404 (WebSudo), KAN-390 (Admin MCP subnav), KAN-395 (Admin AAL2 routes), and KAN-396 (OAuth client registration).

---

## 3. Verdict

**APPROVED.** The audit document is technically precise, forensically verified, and provides an authoritative foundation for Phase 2 implementation.

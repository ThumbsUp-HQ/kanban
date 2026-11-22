# API & Security Specialist Review: KAN-63 (`[KB-SEC-CODEX-01]`)

- **Reviewer Persona:** `security-engineer` / `backend-architect` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-63` (`[KB-SEC-CODEX-01] De-Expose Public /api/v1/internal MCP Routes, Enforce Role-Bound HMAC Service Auth, & Bind Ephemeral Minting to Active Executions (CWE-290/345/862)`)
- **Audited Commit (`HEAD`):** `fb3b87ae996bc49b57b2faa7321074321dfb7b93` (`fb3b87ae`)
- **Audited Branch:** `feat/KAN-63-internal-service-auth`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-63/git-diff.patch`
  - `docs/qa/KAN-63/contract-sample.json`
  - `docs/qa/KAN-63/unit-test-results.txt`
  - `docs/qa/KAN-63/build-check.txt`
  - `docs/qa/KAN-63/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `kanban/api/v1/__init__.py`
  - `kanban/app.py`
  - `kanban/security/service_auth.py`
  - `kanban/api/internal/mcp_ephemeral.py`
  - `kanban/api/internal/mcp_introspect.py`
  - `kanban/security/ephemeral_mcp_tokens.py`
  - `kanban/security/read_taint.py`
  - `mcp/internal_client.py`
  - `kanban/web/openapi.json`
  - `kanban/web/src/api/schema.gen.ts`
  - `kanban/tests/security/test_internal_route_isolation.py`
  - `kanban/tests/security/test_ephemeral_mcp_tokens.py`
  - `mcp/tests/test_ephemeral_auth.py`
  - `kanban/tests/api/test_admin_mcp_keys_api.py`
  - `kanban/tests/security/test_read_taint.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-63` delivers a critical, comprehensive hardening of the internal MCP and agent service boundaries, systematically eliminating vulnerabilities associated with CWE-290 (Authentication Bypass by Spoofing), CWE-345 (Insufficient Verification of Data Authenticity), and CWE-862 (Missing Authorization).

Key security achievements:
1. **Zero Public Route Exposure & Clean OpenAPI Schema:** Public `/api/v1/internal/*` and `/internal/*` routes are removed from the public router tree and now unconditionally return HTTP `404 Not Found`. Internal services run strictly via an isolated sub-application (`create_internal_app`), mounted via an internal ASGI dispatcher. The public OpenAPI spec (`kanban/web/openapi.json`) and generated TypeScript schema (`schema.gen.ts`) contain zero `/internal/` endpoints.
2. **Cryptographic Role-Bound Service Authentication:** All unverified and spoofable identity headers (`X-KB-Service-Principal`, `X-SSL-Client-Cert`, `X-Client-Cert-CN`) have been completely deleted. Authentication now strictly requires role-bound HKDF-SHA256 subkeys derived from `master_kek` (`derive_subkey(km.master_kek, f"internal-service-v2/{principal}")`) signing `ts + principal + method + path + sha256(body)` via `X-KB-Internal-Auth` (with <= 300s clock drift tolerance) or verified ASGI TLS client certificates (`scope["client_cert"]`).
3. **Strict Least-Privilege Principal Segregation:** Endpoint authorizations enforce exact role boundaries. `mcp-gateway` is authorized for `introspect` (200) and `revoke` (200), but is strictly forbidden (`403 FORBIDDEN`) from calling the ephemeral token minting endpoint. Ephemeral token minting is restricted strictly to `agent-runtime` and `kanban-api`.
4. **Active Workflow Execution Cryptographic Binding:** `mint_ephemeral_token()` validates via `_verify_active_execution_binding` that `execution_id` exists in `workflow_transition_executions`, is in active status (`running_sync` or `pending_async`), matches `(workspace_id, invoking_principal_id, project_id)`, and is bound to an attached hook whose `agent_definition` owns the `agent_principal_id`. Fabricated or inactive executions are rejected with `422`, and scope/agent mismatches are rejected with `403`.
5. **Coverage & Quality Verification:** 42 Pytest tests across 5 test suites pass with 97% overall coverage (each touched module >= 95%). `make check`, `pnpm check:api`, `pnpm build`, and repository-wide dash checks passed cleanly with 0 errors.

---

## 2. Threat Modeling & Vulnerability Remediation Analysis

### 2.1 CWE-290 & CWE-345 Remediation: Header Spoofing Elimination
- **Vulnerability:** Previously, internal endpoints accepted unverified client-supplied headers such as `X-KB-Service-Principal: agent-runtime` or unverified `X-SSL-Client-Cert`, allowing any client on the wire to impersonate high-privilege service principals.
- **Remediation (`kanban/security/service_auth.py`):**
  - Subkey derivation uses HKDF-SHA256 with distinct role separation info strings: `f"internal-service-v2/{principal}"`.
  - Signature verification canonicalizes `f"{ts_int}\n{principal}\n{method}\n{path}\n{sha256(body_bytes)}"` and performs constant-time `hmac.compare_digest`.
  - Replay and drift protection enforces `abs(now - ts) <= 300`.
  - ASGI client certificate checking inspects `request.scope.get("client_cert")` directly from the TLS layer (X.509 ASN.1 parsed Subject CN and SAN DNS/URI), rejecting any mismatch between certificate identity and HMAC principal.
  - All fallback branches in `mcp_ephemeral.py`, `mcp_introspect.py`, and `read_taint.py` to unverified headers have been purged.

### 2.2 CWE-862 Remediation: Role Separation & Least Privilege
- **Vulnerability:** In previous versions, any authenticated service principal could invoke any internal endpoint, including token minting.
- **Remediation (`kanban/api/internal/mcp_ephemeral.py`, `mcp_introspect.py`):**
  - `POST /internal/v1/mcp/ephemeral-tokens`: Restricted strictly to `{"agent-runtime", "kanban-api"}`. Requests signed by `mcp-gateway` return `403 FORBIDDEN`.
  - `POST /internal/v1/mcp/introspect` & `POST /internal/v1/mcp/ephemeral-tokens/by-execution/{id}/revoke`: Permitted for `{"mcp-gateway", "agent-runtime", "kanban-api"}`.
  - Verified via recorded exchanges in `contract-sample.json` and unit tests in `test_case_3_edge_cross_role_escalation_tampering_and_fabricated_execution`.

### 2.3 Execution Context Binding Integrity (`kanban/security/ephemeral_mcp_tokens.py`)
- **Vulnerability:** Attackers with access to internal minting could fabricate arbitrary `execution_id` values or mint tokens outside their assigned project/agent boundaries.
- **Remediation (`_verify_active_execution_binding`):**
  - Validates `execution_id` existence in `workflow_transition_executions` (`422 INVALID_EXECUTION` if not found).
  - Validates `status in ("running_sync", "pending_async")` (`422 INACTIVE_EXECUTION` if completed/failed).
  - Validates `(workspace_id, project_id, invoking_principal_id)` tuple parity (`403 EXECUTION_SCOPE_MISMATCH`).
  - Verifies database link to `workflow_transition_hooks` and `agent_definitions` confirming `ad.principal_id == agent_principal_id` (`403 AGENT_NOT_BOUND_TO_EXECUTION`).

---

## 3. Wire Contract & API Boundary Verification

Audited `contract-sample.json` exchanges:
- `1_public_api_v1_internal_404`: Public `POST /api/v1/internal/v1/mcp/ephemeral-tokens` returns `404 Not Found`.
- `2_public_root_internal_404`: Public root `POST /internal/v1/mcp/ephemeral-tokens` returns `404 Not Found`.
- `3_internal_spoofed_headers_401`: Request with spoofed `X-KB-Service-Principal` returns `401 AUTHENTICATION_REQUIRED`.
- `4_internal_mcp_gateway_mint_403`: `mcp-gateway` attempting to mint tokens returns `403 FORBIDDEN`.
- `5_internal_fabricated_execution_422`: Non-existent `execution_id` returns `422 INVALID_EXECUTION`.
- `6_internal_agent_runtime_mint_201`: Valid `agent-runtime` request mints scoped ephemeral token (`201 Created`).
- `7_internal_mcp_gateway_introspect_200`: `mcp-gateway` introspects valid ephemeral token (`200 OK`).
- `8_internal_mcp_gateway_revoke_200`: `mcp-gateway` revokes execution tokens (`200 OK`, `revoked_count: 1`).

---

## 4. Test Verification & Code Coverage

- **Pytest Suite Results (`42 passed in 14.41s`):**
  - `kanban/tests/security/test_internal_route_isolation.py`: 4 passed
  - `kanban/tests/security/test_ephemeral_mcp_tokens.py`: 7 passed
  - `mcp/tests/test_ephemeral_auth.py`: 20 passed
  - `kanban/tests/api/test_admin_mcp_keys_api.py`: 4 passed
  - `kanban/tests/security/test_read_taint.py`: 7 passed
- **Coverage by Module (All >= 95% threshold):**
  - `kanban/security/service_auth.py`: **99%**
  - `kanban/api/v1/__init__.py`: **100%**
  - `kanban/api/internal/mcp_introspect.py`: **99%**
  - `kanban/security/ephemeral_mcp_tokens.py`: **97%**
  - `kanban/api/internal/mcp_ephemeral.py`: **96%**
  - `kanban/security/read_taint.py`: **95%**
  - `mcp/internal_client.py`: **95%**
  - Combined total coverage: **97%**
- **Static Checks & API Parity:**
  - `make check`: 0 errors
  - `pnpm --dir kanban/web run check:api`: 0 errors (0 diffs between OpenAPI spec and generated TypeScript code)
  - `pnpm --dir kanban/web run build`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 5. Review Sign-Off

The internal route isolation, cryptographic service authentication, role boundaries, and active execution binding for `KAN-63` are rigorously verified and approved.

**STATUS: APPROVED**

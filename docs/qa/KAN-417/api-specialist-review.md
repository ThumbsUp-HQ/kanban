# API Specialist Review: KAN-417 (Slice 3 Phase 2 MCP & OAuth Simplification)

**Ticket:** KAN-417 (`[SLICE-3-P2][KB-MCP-OAUTH-SIMPLIFY]`)  
**Parent Epic:** KAN-415 (`[EPIC][SLICE-3-MCP-OAUTH]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan417-b61a8c15`  
**Target Commit:** `feat/KAN-417-slice3-mcp-simplify`  

---

## 1. Executive Summary & Verdict

This API Specialist Review evaluates the backend implementation, endpoint contracts, schema models, network/CIDR validation logic, workload identity federation invariants, and OAuth 2.1 protocol security controls introduced in **KAN-417: Simplify MCP Access, Workload OIDC & OAuth 2.1 Governance**.

The backend changes in this branch directly implement and enforce critical security and protocol invariants:
1. **RFC 6749 / RFC 9700 OAuth 2.1 Grant Type Hardening**:
   - Explicitly rejects `client_credentials` grant type attempts with HTTP 400 `UNSUPPORTED_GRANT_TYPE`. This strictly upholds the thumbs-up-kanban architecture invariant that machine-to-machine integrations must leverage cryptographically bounded MCP API keys or federated Workload Identity OIDC tokens rather than ambient client credential escalation without user identity.
2. **RFC 7636 PKCE S256 Enforcement on Public Clients**:
   - Enforces PKCE S256 (`payload.client_type == "public" and not payload.pkce_enforce` -> HTTP 400 `INVALID_CLIENT_METADATA`). Public OAuth clients (desktop agents, single-page apps, CLI runners) cannot register or execute authorization flows without S256 code challenge verification.
3. **Pydantic CIDR Ingress Validation**:
   - Added `validate_allowed_cidrs` validators on `McpApiKeyMintRequest` and `UnifiedMcpKeyMintRequest` using `ipaddress.ip_network(..., strict=False)`. Invalid CIDR notations fail immediately at the schema serialization boundary before database interaction.
4. **Workload Identity Issuer & Subject Pattern Invariants**:
   - `validate_issuer_https` validates that OIDC workload identity issuers mandate the `https://` URI scheme.
   - `validate_subject_pattern` compiles subject patterns through `fnmatch.translate` and `re.compile` at request validation time, rejecting malformed patterns with actionable HTTP 422 errors.
5. **Capability Mask Range Bounds**:
   - Expanded capability bitmask ceiling to allow `0` (read-only / zero-tool execution keys) up through `255`, aligning both API request schemas and `mint_mcp_api_key` security layer validation.

**Verdict: APPROVED.** The backend code adheres strictly to zero-trust security invariants, includes comprehensive regression tests, maintains 100% clean typing and linting, and exhibits zero architectural regressions.

---

## 2. API Contract & Security Invariant Audit

### 2.1 OAuth 2.1 Client Registration & Protocol Enforcement (`kanban/api/v1/oauth.py`)
- **Route:** `POST /api/v1/admin/oauth/clients` (`admin_register_oauth_client`)
- **Access Control:** Enforces admin session with AAL2 verification requirement (`Depends(require_admin_aal2)`).
- **Prohibited Grant Check:**
  ```python
  if payload.grant_types and "client_credentials" in payload.grant_types:
      raise ProblemException(
          code="UNSUPPORTED_GRANT_TYPE",
          status=400,
          title="Unsupported Grant Type",
          detail="The client_credentials grant type is strictly prohibited in 👍kanban.",
      )
  ```
- **Public Client PKCE Check:**
  ```python
  if payload.client_type == "public" and not payload.pkce_enforce:
      raise ProblemException(
          code="INVALID_CLIENT_METADATA",
          status=400,
          title="Invalid Client Metadata",
          detail="Public OAuth 2.1 clients must enforce PKCE S256.",
      )
  ```
- **Response Model Parity:** Metadata fields (`pkce_enforce`, `access_token_ttl`, `grant_types`) are explicitly included in registration responses.

### 2.2 Unified MCP API Key Management (`kanban/api/v1/admin/mcp_keys.py` & `kanban/api/v1/mcp_keys.py`)
- **Routes:**
  - `POST /api/v1/admin/mcp/keys` (`admin_mint_key`)
  - `POST /api/v1/mcp/keys` (`mint_unified_key`)
- **Capability Mask:** `capability_mask: int = Field(default=7, ge=0, le=255)` supports bitmask `0` for zero-tool / inspection-only credentials.
- **CIDR Network Validation:**
  ```python
  @field_validator("allowed_cidrs")
  @classmethod
  def validate_allowed_cidrs(cls, v: list[str] | None) -> list[str] | None:
      if v is not None:
          for c in v:
              try:
                  ipaddress.ip_network(c.strip(), strict=False)
              except ValueError as exc:
                  raise ValueError(f"Invalid CIDR block: {c}") from exc
      return v
  ```
- **Core Security Engine:** `kanban/security/mcp_keys.py` updated to check `0 <= capability_mask <= MAX_CAPABILITY_MASK` and properly evaluate ingress request IP against CIDR subnets using `ipaddress.ip_address`.

### 2.3 Workload Identity Federation (`kanban/api/v1/admin/workload_identities.py`)
- **Routes:**
  - `POST /api/v1/admin/workload-identities/policies`
  - `PATCH /api/v1/admin/workload-identities/policies/{policy_id}`
- **Scheme Validation:** Issuer must start with `https://`.
- **Subject Pattern Compilation:**
  ```python
  @field_validator("subject_pattern")
  @classmethod
  def validate_subject_pattern(cls, v: str) -> str:
      v_strip = v.strip()
      try:
          re.compile(fnmatch.translate(v_strip))
      except Exception as e:
          raise ValueError(f"Invalid subject pattern: {e}") from e
      return v_strip
  ```
- **TTL Bounds:** `max_ttl_seconds` constrained to `ge=60, le=86400` (1 minute to 24 hours).

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Test Suite (Pytest)**:
   - 114 tests passed across OAuth flows, unified MCP key management, admin MCP endpoints, workload OIDC token exchange, and JWT authentication:
     - `kanban/tests/oauth/test_device_flow.py`: 6 passed
     - `kanban/tests/oauth/test_oauth_coverage.py`: 25 passed
     - `kanban/tests/oauth/test_oauth_flow.py`: 18 passed
     - `kanban/tests/oauth/test_oauth_unit.py`: 25 passed
     - `kanban/tests/api/test_unified_mcp_keys_api.py`: 9 passed
     - `kanban/tests/api/test_admin_mcp_keys_api.py`: 4 passed
     - `kanban/tests/auth/test_workload_oidc_exchange.py`: 7 passed
     - `mcp/tests/test_workload_jwt_auth.py`: 7 passed
     - `mcp/tests/test_mcp_capability_mask_and_cidr.py`: 6 passed
     - `kanban/tests/test_feature_comparison_parity.py`: 7 passed
   - Total runtime: 53.69s, 0 failures, 0 errors.

2. **Frontend Test Suite (Vitest)**:
   - 130 tests passed across 5 test suites (`ConnectOAuthAppModal`, `DeviceActivatePage`, `OAuthClientGovernanceStudio`, `McpUnifiedStudio`, `McpAccessStudio`).
   - Branch coverage: 95.04% (exceeds >=95% requirement).

3. **Static Analysis & Linting Pipeline**:
   - `ruff check`: All checks passed.
   - `mypy`: Success, 0 issues found in 808 source files.
   - `tsc -b --noEmit`: 0 errors.
   - `eslint`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.41s.
   - `check_no_dashes.py`: 0 forbidden Unicode dashes found.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-417/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: All 5 build tools pass cleanly.
  - `unit-test-results.txt`: Documents 114 backend and 130 frontend passing tests.
  - `git-diff.patch`: Fully captured without dirty tracking files.
  - `screenshots/`: 5 multi-viewport unclipped PNG captures.
  - `changed-files-manifest.txt` and `SHA256SUMS.txt`: Verified with `sha256sum -c`.

The API architecture and security hardening for KAN-417 are complete, robust, and approved for integration.

# API & Security Specialist Review: KAN-66 (`[KB-SEC-04]`)

- **Reviewer Persona:** `security-engineer` / `backend-architect` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-66` (`[KB-SEC-04] Enforce Immutable CredentialBoundary Across REST Bearer Auth, Workspace/Project Allowlists, CIDR, Capability Mask, & Tool Scope`)
- **Audited Commit (`HEAD`):** `ea104737b3071af8b0d7331325dad31425cdff5c` (`ea104737`, merging `a5d23fb913ca87601c20d93b39a3a103d237c0df`)
- **Audited Branch:** `main` (merged from `feat/KAN-66-rest-credential-boundary`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-66/git-diff.patch`
  - `docs/qa/KAN-66/contract-sample.json`
  - `docs/qa/KAN-66/unit-test-results.txt`
  - `docs/qa/KAN-66/build-check.txt`
  - `docs/qa/KAN-66/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `kanban/security/boundary.py`
  - `kanban/security/mcp_keys.py`
  - `kanban/security/permissions.py`
  - `kanban/api/deps.py`
  - `kanban/auth/sessions/resolver.py`
  - `kanban/auth/mfa/policy.py`
  - `kanban/tests/security/test_credential_boundary_rest.py`
  - `kanban/tests/security/test_mcp_keys.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-66` establishes an immutable, defense-in-depth credential scoping architecture across the REST API layer, preventing privilege escalation and lateral movement across workspaces, projects, network boundaries, and administrative surfaces.

Previously, API keys (`kb_pat_*`) and ephemeral agent tokens (`kb_eat_*`) possessed scoping rules within the MCP server layer, but REST Bearer authentication resolvers did not uniformly enforce network CIDR restrictions, project allowlists, surface boundaries, or administrative AAL2 elevation policies.

The implementation introduces `CredentialBoundary` (`kanban/security/boundary.py`) as a frozen, slotted immutable dataclass attached to `PrincipalContext`, rigorously enforcing:
1. **Network CIDR Allowlists:** Client IPs outside `boundary.allowed_cidrs` are immediately rejected with HTTP `403 CIDR_NOT_ALLOWED`.
2. **Workspace & Project Boundary Enforcement:** Requests targeting workspaces outside `workspace_allowlist` return HTTP `403 CREDENTIAL_SCOPE_VIOLATION`. Project access checks in `evaluate_capabilities` and `compute_effective_capabilities` return `Capability.NONE` for unallowed projects, ensuring anti-enumeration via HTTP `404 Not Found` at object boundaries.
3. **Surface & Method Segregation:** Credentials minted with `surface == "docs"` are restricted from executing state-mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) on non-doc resources (`/api/v1/issues`), returning HTTP `403 INSUFFICIENT_SCOPE`. Credentials without `surface == "admin"` attempting administrative endpoints (`/api/v1/admin/*`) return HTTP `403 AAL2_REQUIRED`.
4. **Headless Admin AAL2 Protection:** `require_admin_aal2` rejects headless tokens unless the credential explicitly carries `surface == "admin"` and verified AAL2 provenance, preventing non-admin API keys from bypassing MFA requirements.
5. **Code Coverage & Quality:** `kanban/security/boundary.py` achieved **100% statement and 100% branch coverage**. All 20 targeted tests and 443 total security/auth tests passed cleanly. Static analysis (`make check`) and repository-wide dash checks passed with 0 errors.

---

## 2. Architecture & Wire Contract Verification

### 2.1 Immutable Boundary Model (`kanban/security/boundary.py`)
- `@dataclass(frozen=True, slots=True) class CredentialBoundary`:
  - Attributes: `scope_tier`, `surface`, `workspace_allowlist`, `project_allowlist`, `capability_mask`, `allowed_tools`, `allowed_cidrs`, `execution_id`, and `has_aal2_provenance`.
  - In `__post_init__`, defensively freezes collections into immutable types (`frozenset`, `tuple`, `uuid.UUID`).
  - `from_introspection` parses active token introspection records from `McpIntrospectionResult`.
  - `EmptyCapabilitySet`: customized empty set comparing equal to `0`, `Capability.NONE`, and empty sets, ensuring compatibility with integer bitmasks and set operations.

### 2.2 Wire Frame Contracts (`docs/qa/KAN-66/contract-sample.json`)
The wire interactions were validated across normal and adversarial scenarios:
- `200_OK_AGENT_REQUEST`: Valid agent token within CIDR allowlist (`192.168.1.50` in `192.168.1.0/24`) and project allowlist creates issue successfully (`200 OK`).
- `200_OK_DOCS_MUTATION`: Docs surface credential mutates `/api/v1/docs` successfully (`200 OK`).
- `403_CIDR_NOT_ALLOWED`: Request from `10.0.0.50` outside `192.168.1.0/24` blocked with `403 CIDR_NOT_ALLOWED`.
- `403_CREDENTIAL_SCOPE_VIOLATION`: Scope header specifying unallowed workspace blocked with `403 CREDENTIAL_SCOPE_VIOLATION`.
- `403_INSUFFICIENT_SCOPE_DOCS_SURFACE`: Docs credential attempting `POST /api/v1/issues` blocked with `403 INSUFFICIENT_SCOPE`.
- `403_AAL2_REQUIRED_HEADLESS_ADMIN`: Headless agent credential attempting `/api/v1/admin/*` blocked with `403 AAL2_REQUIRED`.

---

## 3. Security Analysis & Threat Mitigation

### 3.1 Network Boundary & Anti-Spoofing (Action 2)
- `resolve_client_ip(request.scope)` safely resolves the connecting client IP.
- `boundary.allows_ip` parses IP networks using standard library `ipaddress.ip_network(cidr, strict=False)`.
- Rejects non-matching or malformed client IPs prior to entering application business logic.

### 3.2 Anti-Enumeration & Capability Intersection (Action 3)
- `evaluate_capabilities` checks `_check_boundary_project_allowlist`. If the object or target project is outside `project_allowlist`, returns `Capability.NONE`.
- Downstream `require_capability` raises HTTP `404 NOT_FOUND` rather than `403`, preventing attackers from enumerating issues in other projects.
- `compute_effective_capabilities` intersects RBAC capabilities with `boundary.capability_mask`, ensuring that tokens with restricted masks (e.g. read-only VIEW) cannot execute EDIT or DELETE operations regardless of caller role.

### 3.3 Admin AAL2 Policy Enforcement (Action 4)
- `require_admin_aal2` (`kanban/auth/mfa/policy.py`) inspects `principal.credential_boundary`.
- Only API keys with `surface == "admin"` and `has_aal2_provenance == True` are permitted through headless administrative flows. Any standard agent or docs token is rejected with `403 AAL2_REQUIRED`.

---

## 4. Test Verification & Code Coverage

- **Targeted Test Results (`20 passed in 0.38s`):**
  - `kanban/tests/security/test_credential_boundary_rest.py`: 11 passed
    - Boundary immutability and defensive freezing
    - CIDR allowlist enforcement (positive and negative)
    - Workspace allowlist enforcement
    - Project allowlist anti-enumeration
    - Capability mask bitwise intersection
    - Docs surface mutation denial on non-docs
    - Admin AAL2 headless key rejection
  - `kanban/tests/security/test_mcp_keys.py`: 9 passed
    - Ephemeral and PAT token introspection boundary construction
- **Full Security & Auth Test Suites:**
  - 443 passed in 53.16s (`uv run pytest kanban/tests/security/ kanban/tests/auth/`)
- **Coverage Metrics:**
  - `kanban/security/boundary.py`: **100% statement, 100% branch** (120/120 statements, 56/56 branches)
- **Static Analysis & Build Verification:**
  - `make check`: 0 errors (ruff check, ruff format, mypy, lint-imports, check-migrations)
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (0 em/en-dashes)

---

## 5. Review Sign-Off

The REST credential boundary implementation satisfies all requirements for KB-SEC-04 with zero regressions and complete coverage.

**STATUS: APPROVED**

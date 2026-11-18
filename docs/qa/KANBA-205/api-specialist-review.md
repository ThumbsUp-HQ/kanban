# QA API Specialist Review: KANBA-205

## Review Metadata
- **Ticket ID:** KANBA-205 ([KB-QA-MCP] Multi-Tenant MCP Scoping Matrix Verification: User Agent vs Project Agent (agy & codex))
- **Reviewer:** api-specialist (Independent API & Security Architecture Swarm Reviewer)
- **Review Date:** 2026-11-18
- **Target Surfaces:** Model Context Protocol (MCP) endpoints (`/mcp/agent`, `/mcp/agent/w/{workspace_slug}`, `/mcp/agent/w/{workspace_slug}/p/{project_key}`, `/mcp/docs`, `/mcp/admin`), McpAuthMiddleware, IntrospectionCache, TaintGuard, and upstream REST contracts
- **Status:** APPROVED

---

## 1. Executive Summary
This independent review audits the multi-tenant scoping matrix, authentication, authorization, and protocol preconditions for the Model Context Protocol (MCP) subsystem under KANBA-205. The test suite (`tests/mcp/test_mcp_scoping_qa_matrix.py`) deterministically validates all six conditions (Conditions A through F) specified in the product architecture:
- User Agent (`personal_user`) vs Project Agent (`service_bot`) identity handling.
- Unscoped vs project-pinned Personal Access Token (`kb_agt_`) semantics.
- Connection path routing vs dynamic request-level scoping headers.
- Hard surface separation (`kb_agt_`, `kb_doc_`, `kb_adm_`, `kb_agt_eph_`).
- Admin RBAC capability checks and 2-stage destructive action lifecycle.
- Protocol compliance (RFC 9728 resource metadata, session binding, TaintGuard taint confirmation, and 15-second TTL cache eviction).

All 6 test matrix conditions execute cleanly in 1.32 seconds, with complete coverage across the MCP surface tree (13,351 statements at 95.67% test coverage, passing 328 unit tests with zero regressions).

---

## 2. Condition-by-Condition Architectural Audit

### Condition A: User Agent Unscoped Global Key
- **Token Class:** `personal_user` with global scope tier (`kb_agt_*`).
- **Surface Endpoint:** `/mcp/agent` (unscoped).
- **Tool Listing:** Exposes exactly the 9 registered agent tools (`create_ticket`, `read_ticket`, `update_ticket`, `transition_ticket`, `begin_work`, `complete_work`, `add_comment`, `link_objects`, `search_tickets`).
- **Execution & Scope Behavior:** Explicit parameters (`project: "QAUSR1"`) are passed to upstream API routes without forced header injection.
- **Tenant Isolation & Anti-Enumeration:** Requests targeting unauthorized workspaces or projects correctly yield HTTP 404 (`NOT_FOUND`), preventing tenant and resource enumeration attacks.

### Condition B: User Agent Unscoped Key to Scoped Endpoints
- **Surface Endpoints:** `/mcp/agent/w/kanban` (workspace-scoped) and `/mcp/agent/w/kanban/p/QAUSR1` (project-scoped).
- **Auto-Fill Behavior:** When calling `create_ticket` or other project-bound tools without specifying `project`, the scoped endpoint context auto-fills `project="QAUSR1"`.
- **Cross-Project Injection Defense:** Attempting to mutate a foreign project (e.g., `project="QAADM"`) while connected to `/mcp/agent/w/kanban/p/QAUSR1` is rejected with HTTP 403 `CONNECTION_SCOPE_VIOLATION`.

### Condition C: User Agent Project-Pinned Key
- **Token Class:** `personal_user` with `scope_tier="project"`, pinned to `workspace_slug="kanban"` and `allowed_projects=["QAUSR1"]`.
- **Narrowing Behavior:** Connecting to unscoped `/mcp/agent` with this key safely narrows effective operations to `QAUSR1`.
- **Forbidden Route Rejection:** Connecting to foreign project endpoints (e.g., `/mcp/agent/w/kanban/p/QAADM`) or broad workspace endpoints (`/mcp/agent/w/kanban`) is blocked with HTTP 403 `KEY_SCOPE_VIOLATION`.
- **Read-Only Capability Defense:** Keys configured with read-only scopes or capability mask 1 correctly reject mutations (`create_ticket`, `update_ticket`) with HTTP 403 `INSUFFICIENT_SCOPE`.

### Condition D: Project Agent (Service Bot)
- **Token Class:** `service_bot` (`kb_agt_*`) bound to project `QAADM`.
- **Allowed Connections:** Connects successfully to `/mcp/agent/w/kanban/p/QAADM` or `/mcp/agent` paired with valid `X-Workspace-Slug` and `X-Project-Key` headers matching `QAADM`.
- **Cross-Project Connection Rejection:** Connecting to `/mcp/agent/w/kanban/p/QAUSR1` is blocked with HTTP 403 `KEY_SCOPE_VIOLATION`.
- **Tool Allowlist & Denylist Enforcement:** `allowed_tools` and `disabled_tools` filters are strictly enforced: denylisted or unlisted tools are excluded from `tools/list` and rejected at `tools/call` with HTTP 404 `TOOL_NOT_FOUND`.
- **View-Only Capability Mask:** `capability_mask=1` (View only) enforces read-only access, rejecting write attempts with HTTP 403 `INSUFFICIENT_CAPABILITY`.

### Condition E: Surface Isolation & Admin RBAC Parity
- **Cryptographic Surface Isolation:**
  - `kb_agt_*` tokens presented to `/mcp/docs` or `/mcp/admin` yield HTTP 403 `SURFACE_KEY_MISMATCH`.
  - `kb_doc_*` tokens presented to `/mcp/agent` or `/mcp/admin` yield HTTP 403 `SURFACE_KEY_MISMATCH`.
  - `kb_adm_*` tokens presented to `/mcp/agent` or `/mcp/docs` yield HTTP 403 `SURFACE_KEY_MISMATCH`.
  - Ephemeral script tokens (`kb_agt_eph_*`) presented to `/mcp/admin` yield HTTP 403 `SURFACE_KEY_MISMATCH`.
- **Admin Granular Scopes:** Read-only admin keys (`admin:read`) cannot execute modifying tools (`configure_workspace`, `architect_project`), returning HTTP 403 `INSUFFICIENT_SCOPE`.
- **Two-Stage Destructive Confirmation:** Destructive lifecycle operations (`purge_project`, `purge_workspace`) require a two-stage pattern: `request_delete` returns an ephemeral confirmation token, and `execute_delete` requires the token, an exact `confirm_phrase`, and a non-empty audit reason.

### Condition F: Protocol Preconditions, TaintGuard, and Revocation
- **RFC 9728 Compliance:** Unauthenticated requests return HTTP 401 with a `WWW-Authenticate` header containing `Bearer realm="kanban-mcp"` and `resource_metadata` URI pointing to RFC 9728 JSON discovery documents.
- **Header Precondition Checks:**
  - Conflicting headers (e.g., path specifying `w/kanban` while header specifies `X-Workspace-Slug: acme`) return HTTP 400 `CONFLICTING_SCOPE_HEADERS`.
  - Specifying `X-Project-Key` without `X-Workspace-Slug` returns HTTP 400 `VALIDATION_FAILED`.
- **Session Replay Immunity:** Ephemeral sessions or unknown session IDs return HTTP 404 `SESSION_NOT_FOUND`.
- **TaintGuard Cross-Scope Defense:** Attempting cross-scope mutations after reading tainted context returns HTTP 409 `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.
- **Introspection Cache TTL Evocation:** Revoked tokens or expired cache entries (15-second TTL) immediately fall back to fresh upstream validation, returning HTTP 401 on revocation.

---

## 3. Hostile Input, Sanitization & Secret Scrubbing
- **Secret Scrubbing:** Token prefixes (`kb_agt_`, `kb_doc_`, `kb_adm_`) in error responses and logs are masked or scrubbed. No raw bearer secrets are reflected back to clients or committed in plaintext.
- **Character Encoding & Punctuation:** Checked with `scripts.check_no_dashes --all`. All documents adhere strictly to plain ASCII hyphens (`-`).

---

## 4. Verification Proof Summary
- **Matrix Unit Tests:** `tests/mcp/test_mcp_scoping_qa_matrix.py` (6 passed in 1.32s).
- **Subsystem Test Suite:** 328 tests passed, 95.67% total branch coverage.
- **Integrity Logs:** Pre-run and post-run configuration SHA-256 baseline verification matches bit-for-bit with zero residual probe entries.
- **Contract Recordings:** Comprehensive contract capture recorded in `docs/qa/KANBA-205/contract-sample.json`.

---

## 5. Specialist Verdict
The multi-tenant MCP scoping implementation satisfies all security invariants, tenant boundaries, and protocol contracts. **APPROVED** without reservations.

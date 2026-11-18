# API Specialist Forensic QA Review: KANBA-205

## Metadata
- **Ticket ID:** KANBA-205
- **Title:** [KB-QA-MCP] CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Branch:** `feat/kanba-205`
- **Review Date:** 2026-11-18
- **Verdict:** APPROVED

---

## 1. Architectural & Protocol Assessment

### 1.1 MCP Multi-Surface Isolation & Scoping Matrix
- **Condition A (User Agent Unscoped Global Key):**
  - Confirmed `tools/list` on `/mcp/agent` returns exactly the 9 official agent tools (`search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`).
  - Disposable CRUD operations on `QAUSR1` execute cleanly with appropriate serialization.
  - Anti-enumeration invariant verified: querying unauthorized or nonexistent issues (e.g. `SECRET-99`) returns indistinguishable RFC 7807 `404 NOT_FOUND`.

### 1.2 Monotonic Scoping & Connection Narrowing
- **Condition B (Unscoped Key to Scoped Endpoints):**
  - Connecting an unscoped global key to `/mcp/agent/w/kanban` resolves workspace-scoped tickets cleanly.
  - Connecting to `/mcp/agent/w/kanban/p/QAUSR1` correctly auto-populates `project="QAUSR1"` on mutations when omitted.
  - Cross-project mutation attempts (e.g. `create_ticket(project="QAADM")` or `update_ticket(identifier="QAADM-1")`) fail-closed with `CONNECTION_SCOPE_VIOLATION`.
- **Condition C (User Agent Project-Pinned Key):**
  - Project-pinned key (`scope_tier="project"`, `QAUSR1`) connecting to unscoped `/mcp/agent` monotonically narrows effective scope to `QAUSR1`.
  - Presenting this key to foreign workspace `/mcp/agent/w/kanban` or foreign project `/mcp/agent/w/kanban/p/QAADM` is rejected with HTTP 403 `KEY_SCOPE_VIOLATION`.
  - Key carrying `agent:read`-only scope rejects write mutations with `INSUFFICIENT_SCOPE`.

### 1.3 Service Bot & Capability Controls
- **Condition D (Project Agent Service Bot):**
  - Service bot pinned to `QAADM` operates properly via `/mcp/agent/w/kanban/p/QAADM` and `/mcp/agent` with `X-Workspace-Slug: kanban` and `X-Project-Key: QAADM`.
  - Foreign scope connections are rejected with 403 `KEY_SCOPE_VIOLATION`.
  - `allowed_tools` and `disabled_tools` filters are enforced at both discovery (`tools/list`) and invocation (`tools/call`), returning `INSUFFICIENT_SCOPE` upon violation.
  - Read-only capability mask (`capability_mask=1`) blocks write mutations, returning `INSUFFICIENT_CAPABILITY` / `INSUFFICIENT_PERMISSION`.

### 1.4 Surface Cross-Isolation & Downstream Admin RBAC Parity
- **Condition E (Surface Cross-Isolation):**
  - Presenting `kb_agt_` on `/mcp/docs` or `/mcp/admin` -> 403 `SURFACE_KEY_MISMATCH`.
  - Presenting `kb_doc_` on `/mcp/agent` or `/mcp/admin` -> 403 `SURFACE_KEY_MISMATCH`.
  - Presenting `kb_adm_` on `/mcp/agent` or `/mcp/docs` -> 403 `SURFACE_KEY_MISMATCH`.
  - Presenting ephemeral `kb_agt_eph_` on `/mcp/admin` -> 403 `SURFACE_KEY_MISMATCH`.
  - Admin RBAC parity verified: `admin:read`-only keys are denied on mutating actions (`configure_workspace(action="update")`), and workspace admins lacking server administrator role are rejected with `INSUFFICIENT_CAPABILITY` on `manage_auth_cards`.
  - Two-stage confirmation on `destructive_lifecycle` (`request_delete` -> `execute_delete`) verified with single-use confirmation token, uppercase confirmation phrase, and audit reason.

### 1.5 Protocol Invariants, Session Fingerprinting, and TaintGuard
- **Condition F (Protocol & Security Invariants):**
  - Unauthenticated requests return HTTP 401 with `WWW-Authenticate` header containing RFC 9728 `resource_metadata` URI.
  - RFC 9728 metadata endpoint returns 200 with resource FQDN, authorization servers, and supported scopes.
  - Conflicting header vs URL path returns 400 `CONFLICTING_SCOPE_HEADERS`.
  - Project key supplied without workspace returns 400 `VALIDATION_FAILED`.
  - Session replay across scopes or across different API keys is rejected with HTTP 404.
  - `TaintGuard` blocks cross-scope writes targeting broader audiences with HTTP 409 `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.
  - Cache TTL expiry (15s) and token revocation correctly transition active tokens to 401 Unauthorized.

---

## 2. Test Execution & Evidence Verification

- **Automated Matrix Suite:** `tests/mcp/test_mcp_scoping_qa_matrix.py` executed with 6 passed tests, 0 failures, 0 skipped.
- **Combined Test Coverage:** Full `mcp` test suite achieves 95.67% branch coverage (exceeding the >=95% gate requirement).
- **HTTP/JSON-RPC Transcript:** `docs/qa/KANBA-205/mcp-transcript.txt` records all wire exchanges with zero unredacted secrets.
- **Contract Sample:** `docs/qa/KANBA-205/contract-sample.json` captures structured matrix summary and RFC 9728 metadata samples.

---

## 3. Specialist Verdict

The test suite and scoping contracts for KANBA-205 demonstrate strict fail-closed enforcement, monotonic scope narrowing, and complete protocol compliance.

**Verdict: APPROVED**

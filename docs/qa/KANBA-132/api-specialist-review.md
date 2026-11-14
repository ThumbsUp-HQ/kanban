# API Specialist Gate Review: KANBA-132 (KB-P4-13)

- **Ticket**: `KANBA-132` (`KB-P4-13`: `[Phase 4 / MCP] Ephemeral kb_agt_eph_* read-only MCP tokens (execution_id, Invoker ∩ Agent ∩ Project, TTL<=120s, max_calls<=25)`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-132`
- **Branch**: `feat/KANBA-132`
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have performed an exhaustive architectural and API wire contract review of the implementation for `KANBA-132` (`KB-P4-13`), implementing Ephemeral `kb_agt_eph_*` read-only MCP tokens according to `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 14.3, 11.1, 3.2), `AGENTS.md`, and `docs/tickets/KB-P4-13.md`.

The implementation satisfies all architectural, cryptographic, and security invariant requirements:
- **Cryptographic Token Lifecycle**: Ephemeral tokens use high-entropy random secrets (`secrets.token_urlsafe(32)`) prefixed with `kb_agt_eph_`, stored strictly as SHA-256 digests (`token_sha256 = hashlib.sha256(token.encode('ascii')).digest()`). Raw secrets exist only in transit and are returned strictly once upon minting.
- **Strict Database Invariants & Constraints**: Table `mcp_ephemeral_tokens` enforces check constraints on `allowed_tools` (cardinality 1..4, subset of `search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`), `max_calls` (1..25), `calls_used` (0..max_calls), and `expires_at` (created_at < expires_at <= created_at + 120s). Row-Level Security (`FORCE RLS`) is enabled with workspace isolation policies.
- **mTLS & Internal Service Boundary**: `POST /internal/v1/mcp/ephemeral-tokens` strictly validates caller identity via client certificates or HMAC headers and enforces service principal authorization: only `agent-runtime` and `kanban-api` may mint ephemeral tokens; `mcp-gateway` is explicitly rejected with HTTP 403.
- **Atomic Call-Budget & Surface Enforcement**: `POST /internal/v1/mcp/introspect` supports `consume_call` and `tool_name` parameters. When `consume_call=true`, an atomic single-statement SQL `UPDATE ... SET calls_used = calls_used + 1 ... RETURNING ...` guarantees zero race conditions under concurrent load. Unknown tools return `EPHEMERAL_TOOL_FORBIDDEN` and exhausted budgets return `EPHEMERAL_CALL_BUDGET_EXCEEDED`.
- **Zero-Cache Window & Immediate Revocation**: `mcp/auth.py` explicitly bypasses the 15-second positive introspection cache for `kb_agt_eph_*` tokens. Every `tools/call` evaluates live state in PostgreSQL, ensuring `POST /internal/v1/mcp/ephemeral-tokens/by-execution/{id}/revoke` takes effect on the immediate next request (0s stale window).
- **Triple-Intersection Confinement (`Invoker ∩ Agent ∩ Project`)**: Requests executed under ephemeral tokens establish PostgreSQL session context with `SET LOCAL app.principal_id`, `SET LOCAL app.agent_principal_id`, `SET LOCAL app.token_scopes = 'agent:read,docs:read'`, `SET LOCAL app.ephemeral_project_id`, and `SET LOCAL TRANSACTION READ ONLY`. Object access requires `VIEW` granted to both invoker and agent, confined strictly to the designated project.
- **Protocol & Surface Isolation**: Presenting a `kb_agt_eph_*` token on `/mcp/admin` is rejected with `403 SURFACE_KEY_MISMATCH` before network dispatch. `tools/list` on `/mcp/agent` exposes only read tools (`search_tickets`, `read_ticket`) and omits all write tools.
- **Zero Unicode Dashes**: All documentation and code use standard ASCII hyphens `-` with zero `U+2014` or `U+2013` characters.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Token Prefix & Entropy** | `kb_agt_eph_*` with 256-bit entropy | `secrets.token_urlsafe(32)` with SHA-256 storage | PASS |
| **Tool Allowlist Check** | Subset of 4 read tools | Enforced by DB CHECK and Pydantic validation | PASS |
| **Max TTL & Calls** | TTL <= 120s, max_calls <= 25 | Enforced by DB CHECK and Pydantic validation | PASS |
| **mTLS Mint Boundary** | mcp-gateway rejected 403 | Validated in test_case_5 (`assert res.status_code == 403`) | PASS |
| **Atomic Concurrency** | Exactly N calls succeed out of M | 10 concurrent requests on max_calls=5: 5 pass, 5 fail | PASS |
| **Cache Bypass** | 0s cache window for ephemeral | Bypasses IntrospectionCache in `mcp/auth.py` | PASS |
| **Immediate Revoke** | Revoke by execution_id | Immediate 401 on next call | PASS |
| **Surface Isolation** | /mcp/admin rejected 403 | `SURFACE_KEY_MISMATCH` returned prior to introspect | PASS |
| **Triple Intersection** | Invoker ∩ Agent ∩ Project | Confined to KAN project, cross-project SEC-1 returns 404 | PASS |
| **Kernel Read-Only** | TRANSACTION READ ONLY | Set on connection session; blocks SQL mutations | PASS |
| **Test Coverage** | >= 95% on touched modules | **97.64%** total coverage across touched modules | PASS |
| **Build & Type Clean** | Zero errors across ruff/mypy/lint | All checks passed cleanly with 0 errors | PASS |

---

## 2. Technical Audit Details

### 2.1 Schema & Migrations (`database/migrations/sql/p4_13_mcp_ephemeral_tokens.up.sql`)
The migration cleanly defines table `mcp_ephemeral_tokens`, the necessary partial index on `(execution_id) WHERE revoked_at IS NULL`, the unique index on `(token_sha256)`, workspace RLS policies, and grants to `kanban_app` and `app_rls_reader`. Helper functions `app_effective_principal_set_for` and `app_has_object_capability` correctly support dual-principal OBO evaluation and project-pin confinement.

### 2.2 Security Service (`kanban/security/ephemeral_mcp_tokens.py`)
Functions `generate_ephemeral_mcp_token`, `mint_ephemeral_token`, `revoke_ephemeral_tokens_by_execution`, and `introspect_and_consume_ephemeral_token` are implemented defensively with explicit bounds checking, input sanitization, and structured error responses. The atomic decrement executes cleanly in a single SQL statement preventing concurrency anomalies.

### 2.3 Internal API Routes (`kanban/api/internal/mcp_ephemeral.py`, `kanban/api/internal/mcp_introspect.py`)
Routes enforce mTLS / HMAC authentication dependencies. The minting endpoint verifies caller credentials and rejects unauthorized service principals. Introspection returns full principal context and filtered tool allowlists based on the requested surface.

### 2.4 MCP Middleware & Protocol (`mcp/auth.py`, `mcp/protocol.py`)
`McpAuthMiddleware` correctly recognizes the `kb_agt_eph_` prefix, skips cache lookup, enforces surface boundaries, and passes budget exhaustion results to `McpProtocolHandler` for proper JSON-RPC error formatting with canonical YAML error payloads.

---

## 3. Verdict

The implementation of `KANBA-132` (`KB-P4-13`) is architecturally sound, thoroughly tested, and adheres to all security invariants.

**Verdict: APPROVED**

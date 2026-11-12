# API Specialist Gate Independent Forensic Audit: KANBA-62 (KB-P4-01)

- Ticket: `KANBA-62` (`KB-P4-01`)
- Title: MCP server skeleton: 3 isolated Streamable HTTP mounts + internal kanban-api client
- Epic: `KB-E4` (Phase 4 Model Context Protocol)
- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Date: 2026-11-12
- Worktree: `/tmp/kb-wt-KANBA-62` on branch `feat/KANBA-62` (commit `b17d5d2`)
- Scope: Independent forensic audit of the Streamable HTTP JSON-RPC 2.0 wire protocol (`2025-06-18`), 3-surface registry isolation (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`), internal HTTP/2 mTLS client (`KanbanApiClient`), RFC 7807 problem details mapping to canonical `McpErrorCode`, body/response limit guards, transcript token redaction, and import linter boundaries.

---

### 1. Executive Summary & Verification Matrix

An independent forensic API and systems architecture audit of `KANBA-62` (`KB-P4-01`) was conducted across `mcp/` source code, configuration settings, test suites, live HTTP exchange transcripts, and dependency supply chains.

The implementation satisfies all architectural, security, and protocol requirements of `docs/tickets/KB-P4-01.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (S11.1, S2.3, S2.4, S2.1).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Streamable HTTP Spec** | `MCP-Protocol-Version: 2025-06-18` | Implemented in `mcp/protocol.py`; unsupported versions rejected with HTTP 400 | PASS |
| **Surface Mount Isolation** | 3 independent mounts: `/mcp/agent`, `/mcp/docs`, `/mcp/admin` | Discrete `ToolRegistry` instances per mount; startup `freeze()`; cross-surface tool discovery/call blocked | PASS |
| **JSON-RPC Methods** | `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call` | All 5 standard methods handled; unknown methods return `-32601`; notifications return HTTP 204 | PASS |
| **Negative Constraints** | Standalone SSE streams (HTTP 405), batching (HTTP 400) | GET returns HTTP 405 with `Allow: POST, DELETE`; array batching returns HTTP 400 | PASS |
| **Request Body Guard** | Max 1 MiB (`1,048,576` bytes) | Capped at 1 MiB; bodies >= 1,048,577 bytes return HTTP 413 | PASS |
| **Session Lifecycle & Store** | `Mcp-Session-Id` header, idle TTL 3600s, max 10,000 sessions | `InMemorySessionStore` with LRU eviction and idle expiration; DELETE returns HTTP 204; stale/unknown ID returns HTTP 404 | PASS |
| **DNS-Rebinding Defense** | Origin header validation | Checks incoming `Origin` against `allowed_origins`; HTTP 403 on disallowed origin | PASS |
| **Internal Client Transport** | `KanbanApiClient` (HTTP/2 mTLS + standalone ASGITransport) | mTLS verification with client cert/key; plaintext `http://` strictly rejected in mTLS mode | PASS |
| **Client Timeout Budgets** | Connect 2.0s, read 10.0s, write 10.0s, pool 2.0s | Enforced via `httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)` | PASS |
| **Response Size Guard** | Max 8 MiB streamed response | Streamed chunks tracked; aborted with `UPSTREAM_ERROR` if > 8 MiB | PASS |
| **Identity Forwarding** | `X-KB-Subject-Token` and `X-KB-MCP-Session` headers | Propagated on every outbound call to `kanban-api`; no forged principal assertion | PASS |
| **RFC 7807 Error Mapping** | Upstream problems mapped to canonical `McpErrorCode`s | 404 -> NOT_FOUND, 409 -> CONFLICT_ETAG / VALIDATION_FAILED, 412 -> CONFLICT_ETAG, 422 -> VALIDATION_FAILED, 429 -> RATE_LIMITED, 5xx -> UPSTREAM_UNAVAILABLE | PASS |
| **Structured Tool Error** | `{"content": [{"type": "text", "text": "<yaml>"}], "isError": true}` | Emits `error: {code: <McpErrorCode>, message: ..., hint: ...}`; zero traceback disclosure | PASS |
| **Transcript Redaction** | Redact `Authorization`, `X-KB-Subject-Token`, `kb_*` tokens | `conftest.py` regex replaces tokens with `<prefix>***REDACTED***`; verified in `mcp-transcript.txt` | PASS |
| **Zero PyPI MCP SDK** | Exclude PyPI `mcp` SDK to avoid namespace collision | Verified: zero `mcp` package in `uv.lock`; pure-native protocol engine | PASS |
| **Import Boundary Gate** | `mcp/` forbidden from importing `database/` | `lint-imports` contract KEPT (2 kept, 0 broken); zero database imports | PASS |
| **Test Coverage & Quality** | Mandatory Feature Tests (>=95% coverage) | 19/19 tests passing in 1.00s; 98% line+branch coverage across `mcp`; zero lint/type errors | PASS |

---

### 2. Detailed Wire Contract & Architectural Review

#### A. Protocol Engine (`mcp/protocol.py`)
1. **JSON-RPC 2.0 Conformance:**
   - Validates `jsonrpc == "2.0"`. Malformed JSON returns `-32700 Parse error`. Missing method or invalid request returns `-32600 Invalid Request`.
   - Batch requests (`isinstance(payload, list)`) are rejected immediately with HTTP 400 per Streamable HTTP 2025-06-18 specifications.
   - Handled methods:
     - `initialize`: Returns `protocolVersion: "2025-06-18"`, `capabilities: {tools: {listChanged: false}}`, `serverInfo: {name: "kanban-mcp-<surface>", version: "0.0.0"}`, and sets header `Mcp-Session-Id: <32-byte-token-urlsafe>`. Note: name adheres strictly to ASCII identifiers per brand directive.
     - `notifications/initialized`: Notification (null `id`) returns HTTP 204.
     - `ping`: Returns empty result `{}` with request `id`.
     - `tools/list`: Returns registered tools (`name`, `description`, `inputSchema`) for the surface.
     - `tools/call`: Validates `name` and `arguments` object. Resolves tool from the frozen surface registry. Formats successful output as YAML text inside `content: [{type: "text", text: ...}]` with `isError: false`. Captures exceptions and formats them as structured `KbMcpError` YAML payloads with `isError: true`.
2. **Session Store (`InMemorySessionStore`):**
   - Cryptographically random session IDs via `secrets.token_urlsafe(32)`.
   - LRU eviction: capacity capped at `10,000` sessions using `collections.OrderedDict`. On 10,001st session, oldest inactive session is popped.
   - Idle TTL expiration: default `3600.0s`. Tested with frozen clock at `3600s + 1` confirming expired sessions return None.
   - Session termination: `DELETE /mcp/{surface}` with valid `Mcp-Session-Id` removes session and returns HTTP 204. Re-invocation returns HTTP 404.

#### B. Surface Isolation & Registry (`mcp/registry.py` & `mcp/app.py`)
1. **Physical Surface Separation:**
   - Three separate mounts: `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`.
   - Three separate `ToolRegistry` instances bound to `Surface.AGENT`, `Surface.DOCS`, and `Surface.ADMIN`.
   - `ToolRegistry.register` strictly validates `spec.surface == self.surface`, raising `ValueError` on cross-surface registration.
   - `ToolRegistry.freeze()` locks each registry during `create_mcp_app` startup; mutations after freeze raise `RuntimeError`.
   - Cross-surface invocation: invoking `ping_admin` on `/mcp/agent` returns `isError: true` with `McpErrorCode.NOT_FOUND` and a helpful suggestion to use the proper surface mount.

#### C. Internal Client (`mcp/internal_client.py`)
1. **Security & Transport Guards:**
   - Evaluates base URL: in `mtls` mode, any plaintext `http://` URL raises `ValueError` at client instantiation.
   - mTLS configured with client certificate, client private key, and internal CA bundle.
   - In `standalone_inprocess` mode, leverages `httpx.ASGITransport(app=kanban_app)` avoiding local TCP sockets and cleartext loopback exposure.
   - Strict connection and read timeouts: connect `2.0s`, read `10.0s`, write `10.0s`, pool `2.0s`.
   - Response streaming limit: buffers response chunks iteratively and aborts with `KbMcpError(McpErrorCode.UPSTREAM_ERROR)` if accumulated size exceeds 8 MiB (`8,388,608` bytes).
2. **Error Translation:**
   - Correctly maps RFC 7807 problem payloads and HTTP statuses to canonical `McpErrorCode` enum members:
     - `404` -> `McpErrorCode.NOT_FOUND`
     - `409` (with type ending in `etag-mismatch`) -> `McpErrorCode.CONFLICT_ETAG`
     - `409` (other) -> `McpErrorCode.VALIDATION_FAILED`
     - `412` -> `McpErrorCode.CONFLICT_ETAG`
     - `422` -> `McpErrorCode.VALIDATION_FAILED`
     - `429` -> `McpErrorCode.RATE_LIMITED`
     - `>= 500` / `httpx.TransportError` -> `McpErrorCode.UPSTREAM_UNAVAILABLE`

#### D. Supply Chain & Module Boundaries
1. **No PyPI `mcp` SDK Collision:**
   - `uv.lock` contains zero `mcp` package entries. Workspace package `mcp` is cleanly preserved.
   - `httpx` (`0.28.1`, BSD-3-Clause) and `h2` (`4.4.1`, MIT) are cryptographically pinned with sha256 hashes.
   - `make license` passes with 0 violations.
2. **Zero Database Exposure:**
   - `mcp/` contains zero database connections, zero PostgreSQL credentials, and zero direct imports from `database/`.
   - `uv run lint-imports` validates the forbidden contract `mcp -> database` with 0 broken contracts.

---

### 3. Verdict

The implementation of `KANBA-62` (`KB-P4-01`) is robust, security-hardened, fully compliant with Streamable HTTP JSON-RPC 2.0 standards, and completely meets all criteria set forth in the ticket specification.

**Gate Verdict:** **`APPROVED`**

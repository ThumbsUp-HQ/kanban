# MCP Module Manifest (`kanban-mcp`)

## Responsibility
Three-surface Model Context Protocol server exposing isolated mounts `/mcp/agent`, `/mcp/docs`, and `/mcp/admin` adhering to the Streamable HTTP JSON-RPC 2.0 specification (`MCP-Protocol-Version: 2025-06-18`). Provides surface registry isolation, streamable JSON-RPC handling, and an authenticated internal HTTP/2 mTLS client (`KanbanApiClient`) connecting the MCP server to `kanban-api`. Holds zero direct PostgreSQL credentials, forbids importing `database/`, and interacts exclusively with `kanban-api` over internal HTTP/2 mTLS or in-process ASGI transport.

## Topology & Submodules
- `mcp/app.py`: Starlette application factory `create_mcp_app` mounting the 3 isolated surfaces and wiring registry/protocol handlers.
- `mcp/protocol.py`: Streamable HTTP JSON-RPC 2.0 protocol engine, session lifecycle store (`InMemorySessionStore`), 1 MiB body limiting, DNS rebinding origin checks, and batch rejection.
- `mcp/registry.py`: Surface enum (`AGENT`, `DOCS`, `ADMIN`), `ToolSpec`, and immutable `ToolRegistry` enforcing cross-surface isolation and freeze semantics.
- `mcp/internal_client.py`: Internal authenticated HTTP/2 client (`KanbanApiClient`) with mTLS certificate authentication, RFC 7807 problem details mapping to typed MCP errors, and 8 MiB response limits.
- `mcp/errors.py`: Canonical `McpErrorCode` string enum (11 exact codes) and `KbMcpError` with inline YAML serialization.
- `mcp/settings.py`: Pydantic settings loading runtime configuration, mTLS certificates, origin allowlists, and timeouts.

## Depends On
- `kanban` (`kanban-core` package for shared models and in-process ASGI wiring).

## Depended On By
- `agent` (`kanban-agent` package for AI agent tool execution against MCP endpoints).
- External MCP clients (IDE extensions, agent runners, administrative automation).

## Inbound Contracts
- Streamable HTTP JSON-RPC 2.0 requests over POST on `/mcp/agent`, `/mcp/docs`, and `/mcp/admin`.
- Supported JSON-RPC methods: `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`.
- DELETE request on `/mcp/{surface}` with `MCP-Session-Id` header terminates active session (HTTP 204).
- Optional `MCP-Protocol-Version: 2025-06-18` header validation.
- Enforced body size limit of 1 MiB per JSON-RPC request.
- Batch requests strictly rejected with HTTP 400.

## Outbound Contracts
- Internal HTTP/2 communication to `kanban-api` over mTLS (or in-process ASGI in `standalone_inprocess` mode).
- Identity forwarding headers: `X-KB-Subject-Token` (caller subject credential) and `X-KB-MCP-Session`.
- RFC 7807 problem details responses mapped to typed `KbMcpError` error codes.
- Response body limit of 8 MiB aborted with `UPSTREAM_ERROR`.

## Architectural Invariants & Security Boundaries
- **Zero Database Imports:** `mcp/` is strictly forbidden from importing `database/` directly, verified by Import Linter contract.
- **Surface Isolation:** Each surface mount has its own distinct `ToolRegistry`. Tools registered on `/mcp/admin` cannot be discovered or executed on `/mcp/agent` or `/mcp/docs`.
- **DNS Rebinding Protection:** Validates incoming `Origin` against `allowed_origins` when configured (HTTP 403 on mismatch).
- **Session Isolation:** MCP sessions are tied to a specific surface; session lookup rejects cross-surface usage.

## Performance Budgets
- MCP JSON-RPC protocol overhead < 5ms excluding downstream API calls.
- Internal HTTP/2 client connect timeout: 2.0s, read/write timeout: 10.0s, pool timeout: 2.0s.
- In-memory session store LRU eviction cap: 10,000 active sessions; idle TTL: 3600 seconds.
- Zero PostgreSQL connection pool overhead (proxy architecture).

## Failure Modes
- `INVALID_REQUEST`: Malformed JSON or JSON-RPC batch request (HTTP 400).
- `METHOD_NOT_FOUND`: Unrecognized JSON-RPC method (JSON-RPC error -32601).
- `SESSION_EXPIRED`: Missing, unknown, or expired `MCP-Session-Id` header (HTTP 404).
- `NOT_FOUND`: Tool not found on target surface registry (YAML error in tool content).
- `RATE_LIMITED`: Upstream HTTP 429 received from `kanban-api`.
- `UPSTREAM_UNAVAILABLE`: Network failure, connection drop, or upstream 503 from `kanban-api`.
- `UPSTREAM_ERROR`: Non-parseable or unmapped HTTP error or response body exceeding 8 MiB.

# Backend Architect / API Specialist Review: KANBA-179

## Review Scope
Audit of live MCP server mounting in `kanban/app.py`, standalone in-process client loopback hardening in `mcp/internal_client.py`, and RFC 9728 protected-resource metadata routing and Bearer token parsing in `mcp/auth.py` and `mcp/protocol.py`.

## Verification Findings

### 1. Live MCP Mounting & Route Precedence (`kanban/app.py`)
- Removed the 501 Not Implemented placeholder on `/mcp/{surface:path}`.
- Replaced with live proxy mounting via `_McpProxyApp` mounted at:
  - `/.well-known/oauth-protected-resource/mcp`
  - `/mcp`
- Mount occurs BEFORE root SPA static asset handler (`/`), ensuring all live MCP JSON-RPC calls and RFC 9728 discovery requests are accurately matched and not swallowed by the SPA HTML fallback.
- `_McpProxyApp` cleanly resets `scope["root_path"] = ""` on intercepted requests, preserving the exact URI paths required by `mcp_app` route matching.
- Supports dynamic fallback and state injection (`app.state.mcp_app`), allowing isolated unit testing with custom mock clients without requiring a full live database connection.

### 2. Standalone In-Process Loopback Hardening (`mcp/internal_client.py`)
- Updated `base_url` in standalone in-process mode from `http://kanban.local` to `http://localhost`.
- Under the production `SecurityHeadersMiddleware`, requests to `http://kanban.local` were blocked due to strict Host header enforcement (`standalone_cleartext_hosts`). Connecting via `http://localhost` adheres strictly to loopback security invariants.
- Guaranteed that `X-KB-Service-Principal: mcp-gateway` is always populated on internal requests to bypass CSRF and pass internal service principal validation gates.

### 3. RFC 9728 Discovery & Token Whitespace Parsing (`mcp/auth.py`, `mcp/protocol.py`)
- RFC 9728 endpoint `/.well-known/oauth-protected-resource/mcp/{surface}` is explicitly exempted from Bearer authentication in `McpAuthMiddleware._resolve_surface`, returning `200 OK` with JSON discovery metadata even when `auth_enabled=True`.
- Tolerant header token parsing: handles arbitrary leading/trailing whitespace, tabs, and multi-space separators between `Bearer` and the token value (e.g. `   Bearer    <token>   `), while rejecting missing, empty, or non-Bearer schemes with RFC 6750 `401 Unauthorized` and `WWW-Authenticate` challenge headers.

### 4. Architectural Boundaries (`pyproject.toml`, `lint-imports`)
- Confirmed unidirectional module hierarchy `agent -> mcp -> kanban -> database` remains intact and passes `uv run lint-imports` with 0 contract violations.

## Verdict
**APPROVED**: Security invariants, RFC compliance, and clean architectural boundaries verified.

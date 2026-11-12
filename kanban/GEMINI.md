# Kanban Core Module Manifest (`kanban-core`)

## Responsibility
Core web application and API service layer for the Kanban platform. Implements FastAPI HTTP REST, WebSocket, and SSE endpoints, Multi-Card Authentication (OAuth2/OIDC, LDAPS, Local Admin), session lifecycle, nh3 server-side content sanitization, state machine workflow transitions, Markdown conversion, Project Stickies with Doc promotion, and static SPA serving.

## Depends On
- `database` (`kanban-database` package for PostgreSQL data layer and models).

## Depended On By
- `mcp` (`kanban-mcp` gateway via internal HTTP API endpoints).

## Inbound Contracts
- HTTP/1.1, HTTP/2, WebSocket, and SSE connections from clients and reverse proxy (Caddy).
- Authenticated internal API requests from MCP gateway over application network.

## Outbound Contracts
- Clean JSON REST payloads, WebSocket event broadcasts, and SSE change streams.
- Database access executed under kanban_app role with SET LOCAL principal session variables.

## Performance Budgets
- Standard REST API read endpoint latency < 50ms (p95).
- Realtime WebSocket and SSE broadcast latency < 25ms from trigger event.
- Content sanitization and Markdown conversion < 10ms for payloads up to 100KB.

## Failure Modes
- Authentication failure returning 401 Unauthorized or 404 Not Found (anti-enumeration).
- Invalid payload schemas returning RFC 7807 Problem Details.
- Database connection pool exhaustion returning HTTP 503 Service Unavailable.
- Sanitizer rejection for disallowed HTML tags, scripts, or dangerous URI schemes.

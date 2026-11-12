# Kanban Core Module Manifest (`kanban-core`)

## Responsibility
Core web application, static asset server, and API service layer for the Kanban platform. Implements:
- Single ASGI application factory (`create_app`) mounting `/api`, `/ws`, `/sse`, `/mcp` placeholders, and static SPA.
- Configuration management (`kanban.settings.Settings`) with `KB_` environment prefix.
- Hardened static file delivery (`kanban.web_static.PrecompressedSPAStaticApp`) with Brotli/Gzip content negotiation, SPA fallback, 50 MiB file limits, 64 KiB streaming, path traversal prevention, and strong ETags.
- Security headers middleware (`kanban.security.headers.SecurityHeadersMiddleware`) enforcing Section 5.4 Content-Security-Policy, anti-framing, nosniff, permissions policy, and standalone cleartext host protection.
- Outbound secret scrubber (`kanban.security.scrubber`) preventing sensitive credential egress.

## Depends On
- `database` (`kanban-database` package for PostgreSQL data layer and models).

## Depended On By
- `mcp` (`kanban-mcp` gateway via internal HTTP API endpoints).
- Root deployment harnesses (Docker standalone and runtime-slim images).

## Inbound Contracts
- ASGI 3.0 protocol interface via Uvicorn.
- HTTP/1.1, HTTP/2, WebSocket, and SSE connections from clients and reverse proxy (Caddy).
- Standalone cleartext requests restricted to loopback hosts (`localhost`, `127.0.0.1`, `[::1]`) unless overridden via `KB_STANDALONE_CLEARTEXT_HOSTS`.

## Outbound Contracts
- Hardened HTTP response headers on 100% of responses, including error responses and static files.
- Byte-identical Section 5.4 Content-Security-Policy on every response.
- RFC 9457 Problem Details JSON format for error responses.
- Database access executed under `kanban_app` role with `SET LOCAL` principal session variables.

## Performance Budgets
- Static asset delivery latency <= 5ms for pre-compressed Brotli and Gzip assets.
- Scrubber execution latency <= 1.0ms median on 2,000-char text windows.
- Standard REST API read endpoint latency < 50ms (p95).
- Realtime WebSocket and SSE broadcast latency < 25ms from trigger event.

## Failure Modes
- Standalone cleartext HTTP on external host returns HTTP 403 `CLEARTEXT_HTTP_BLOCKED` problem JSON.
- Missing Host header in standalone mode returns HTTP 400 Bad Request.
- Static file traversal attempts or symlink escapes return HTTP 404 Not Found.
- Static files exceeding 50 MiB return HTTP 404 Not Found.
- WebSocket access to `/ws` returns policy violation closure code 1008.
- Placeholder routes `/sse` and `/mcp/*` return HTTP 501 Not Implemented problem JSON.

# Kanban Core Module Manifest (`kanban-core`)

## Responsibility
Core web application, static asset server, and API service layer for the Kanban platform. Implements:
- Single ASGI application factory (`create_app`) mounting canonical `/api/v1` router, legacy `/api` fallback, `/ws`, `/sse`, `/mcp` placeholders, and static SPA.
- Configuration management (`kanban.settings.Settings`) with `KB_` environment prefix.
- Hardened static file delivery (`kanban.web_static.PrecompressedSPAStaticApp`) with Brotli/Gzip content negotiation, SPA fallback, 50 MiB file limits, 64 KiB streaming, path traversal prevention, and strong ETags.
- Security headers middleware (`kanban.security.headers.SecurityHeadersMiddleware`) enforcing Section 5.4 Content-Security-Policy, anti-framing, nosniff, permissions policy, and standalone cleartext host protection.
- Outbound secret scrubber (`kanban.security.scrubber`) preventing sensitive credential egress.
- Pure ASGI Request-ID middleware (`kanban.api.request_id.RequestIdMiddleware`) validating inbound `^[A-Za-z0-9-]{8,64}$` identifiers or generating 32-hex UUIDv4 tokens, with logging filter injection.
- Canonical RFC 7807 problem details model (`kanban.api.problems.Problem`, `ProblemException`, `not_found`, and non-leaking exception handlers for 422, Starlette HTTP, and 500 errors).
- Cryptographic key material provider (`kanban.security.keys.KeyMaterial`, `load_key_material`, `derive_subkey`) enforcing mode 0600 keyring files, symlink rejection, 32-byte key boundaries, and purpose-separated HKDF-SHA256 derivations.
- Principal identity and RLS session dependencies (`kanban.api.deps.PrincipalContext`, `PrincipalResolver`, `DenyAllResolver`, `get_principal`, `get_rls_session`) rejecting client-supplied headers and binding context inside transactions.
- Timing equalization engine (`kanban.api.timing.TimingFloor`, `timing_floor`, `load_or_404`) enforcing a 25.0ms timing floor and indistinguishable 404 responses for non-existent and RLS-hidden objects.
- Multi-Card Auth Studio envelope encryption (`kanban.security.envelope`) using AES-256-GCM, per-card DEK wrapping, and AAD context binding.
- Multi-Card Auth repository and schemas (`kanban.auth.cards`) interacting with `kb_auth` database boundary.
- Permission evaluator, OBO intersection and anti-enumeration access manifest (`kanban.security.permissions`, `kanban.security.access_manifest`, `GET /api/v1/objects/{id}/access`).
- Shared activity helper (`kanban.services.activity`): `record_activity` (16384 byte payload cap, hash-chained `append_activity`, SAVEPOINT-scoped fail-closed listeners), `ActivityEventType` + `EVENT_CATEGORY`, `emit_ephemeral_event`. Payloads carry `sha256` digests, never Markdown bodies.
- Project API (`kanban.api.v1.projects`, `kanban.services.projects`, `kanban.api.v1.schemas.projects`): create/list/get/patch projects and `PUT .../module-defaults`, all under the RLS request transaction with jitter-equalized 404s.
- Custom field definitions and execution configuration (`kanban.custom_fields`, `kanban.api.v1.custom_fields`, `kanban.api.v1.schemas.custom_fields`): admin-only definition gate across RBAC, API, and Postgres `WITH CHECK` RLS; 7-format output schema (`text`, `number`, `badge`, `markdown_snippet`, `url`, `json_table`, `severity_pill`), zero raw HTML, deterministic `manifest_sha256`, and partitioned `user_access_hash` cache isolation.
- Custom field cryptographic escalation approvals (`kanban.custom_fields.approvals`, `kanban.api.v1.custom_field_approvals`): S13.2 Scope x Principal matrix enforcement, AAL2 freshness gate (<= 900s), dual-control `SERVER_ADMIN` distinct approvals, HKDF-derived HMAC-SHA256 signatures, single-byte tamper auto-revocation trigger, and fail-closed `assert_execution_authorized` gate.
- Typed object links API and canonical URL helper (`kanban.api.v1.links`, `kanban.services.links`, `kanban.api.v1.schemas.links`, `kanban.services.object_ref`): create/list/delete typed links between registered objects with restricted-target masking and server-authoritative canonical URLs.
- Test harness: `kanban.tests.contract.ContractRecorder` (`KB_CONTRACT_OUT`, `KB_TICKET_ID`, credential header redaction) and `kanban/tests/api/conftest.py` fixtures `api_env`, `as_principal`, `make_user`, `make_project`, `make_module`, `contract_recorder`.

## Depends On
- `database` (`kanban-database` package for PostgreSQL data layer, ORM models, and `RLSSessionFactory`).

## Depended On By
- `mcp` (`kanban-mcp` gateway via internal HTTP API endpoints).
- Root deployment harnesses (Docker standalone and runtime-slim images).

## Inbound Contracts
- ASGI 3.0 protocol interface via Uvicorn.
- HTTP/1.1, HTTP/2, WebSocket, and SSE connections from clients and reverse proxy (Caddy).
- Standalone cleartext requests restricted to loopback hosts (`localhost`, `127.0.0.1`, `[::1]`) unless overridden via `KB_STANDALONE_CLEARTEXT_HOSTS`.
- Authenticated requests must resolve identity via server-side `PrincipalResolver`; client headers (`X-Principal-Id`, `X-Workspace-Id`) are strictly ignored.

## Outbound Contracts
- Hardened HTTP response headers on 100% of responses, including error responses and static files.
- Byte-identical Section 5.4 Content-Security-Policy on every response.
- `X-Request-ID` response header echoed on 100% of HTTP responses.
- RFC 7807 Problem Details JSON format (`application/problem+json`, `urn:kanban:problem:<code>`) for error responses.
- Database access executed under `kanban_app` role with `SET LOCAL` principal session variables.

## Performance Budgets
- Static asset delivery latency <= 5ms for pre-compressed Brotli and Gzip assets.
- Scrubber execution latency <= 1.0ms median on 2,000-char text windows.
- Standard REST API read endpoint latency < 50ms (p95).
- Timing floor on object retrieval endpoints = 25.0ms (statistical jitter delta <= 5.0ms).
- Realtime WebSocket and SSE broadcast latency < 25ms from trigger event.

## Failure Modes
- Standalone cleartext HTTP on external host returns HTTP 403 `CLEARTEXT_HTTP_BLOCKED` problem JSON.
- Missing Host header in standalone mode returns HTTP 400 Bad Request.
- Static file traversal attempts or symlink escapes return HTTP 404 Not Found.
- Static files exceeding 50 MiB return HTTP 404 Not Found.
- Missing or unverified credentials return HTTP 401 `AUTHENTICATION_REQUIRED`.
- Non-existent objects and RLS-hidden objects return identical HTTP 404 `NOT_FOUND` problem documents.
- Validation failures return HTTP 422 `VALIDATION_FAILED` with stripped user input.
- Missing or permissive keyring files fail closed at startup with `KeyMaterialError`.
- Unhandled server exceptions return HTTP 500 `INTERNAL_ERROR` with server-side correlation logging and zero trace leakage.
- WebSocket access to `/ws` returns policy violation closure code 1008.
- Placeholder routes `/sse` and `/mcp/*` return HTTP 501 Not Implemented problem JSON.

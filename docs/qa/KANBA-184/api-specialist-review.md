# API Specialist Audit & Certification: KANBA-184

**Reviewer:** Backend Architect (Senior API & Systems Security Specialist)  
**Target Ticket:** KANBA-184 (RFC 7591 Dynamic Registration, RFC 8414/9728 Metadata, Scoped Resource Routing & RLS-Safe Identity Resolution)  
**Co-requisite:** KANBA-183 (OAuth/LDAP Aliasing, Custom Fields Governance Redaction, RLS Workspace Management)  
**Date:** 2026-11-17  
**Verdict:** APPROVED (Grade-A Enterprise Architecture & Security Standard)

---

## 1. Architectural Scope & Mandate Audit

This audit evaluates the server-side API architecture, Model Context Protocol (MCP) authentication pipeline, PostgreSQL Universal Object Graph integration, and OAuth 2.1 authorization server compliance implemented for `KANBA-184`.

Key components and files reviewed:
- `kanban/api/v1/oauth.py`: RFC 7591 Dynamic Client Registration, RFC 8414 / OIDC discovery routers, interactive consent screen RLS binding, and public base URL derivation.
- `kanban/oauth/server.py`: PKCE S256 verification, strict URI validation, hierarchical resource target parsing, route-specific CSP generation, and accessible consent screen rendering.
- `kanban/security/mcp_keys.py`: MCP token introspection, audience/surface verification, nested savepoint schema tolerance, `SECURITY DEFINER` workspace/project resolution, and key labeling.
- `mcp/scoping.py`: Monotonic connection narrowing, workspace slug vs. UUID matching, and project key array containment.
- `mcp/app.py`: Bare `/mcp` route resolution, scoped `/mcp/w/{workspace}[/p/{project}]` endpoints, and RFC 9728 protected-resource metadata routes.
- `mcp/auth.py`: Dynamic reverse-proxy public origin derivation (`Host` + `X-Forwarded-Proto` tolerance without `X-Forwarded-Host`), scoped `WWW-Authenticate` challenge preservation, and `McpAuthContext` propagation.
- `kanban/web_static.py`: Hardened SPA fallback routing boundary excluding `/.well-known`, `/oauth`, `/internal`, `/api`, `/ws`, `/sse`, and `/mcp`.
- `kanban/api/deps.py`: `get_rls_session` non-UUID `x-kb-scope-workspace` header slug-to-UUID resolution under RLS.
- `kanban/auth/sessions/resolver.py`: `SessionCookieResolver._resolve_subject_token` activation, database commit, and fallback workspace resolution under RLS.
- `kanban/auth/oidc/flow.py`: Extended 2048-char query-safe `sanitize_return_to` path isolation.
- `deploy/standalone/entrypoint.py`: SHA-256 migration file and SQL content hashing for reliable Alembic execution on persistent volume warm boots.
- `database/migrations/sql/p4_18_oauth_mcp_scoping.up.sql`: Database migration adding `mcp_api_keys.label`, `resolve_workspace_slug`, `resolve_workspace_by_slug_or_id`, `get_default_workspace_id`, `resolve_project_key`, `resolve_project_keys`, `resolve_project_id_by_key_or_id`, and updating `introspect_mcp_api_key`.

---

## 2. Forensic Security & Technical Invariant Assessment

### 2.1 RFC 7591 Dynamic Client Registration Compliance & Schema Tolerances
- **Model Tolerances (`OAuthClientRegisterRequest`):** Configured with `model_config = ConfigDict(extra="ignore")`. Standard client metadata fields (`grant_types`, `response_types`, `token_endpoint_auth_method`, `scope`, `software_id`, `software_version`, `client_uri`, `contacts`) are accepted without `422 Unprocessable Entity`.
- **Default Client Naming:** When `client_name` is omitted or empty, it defaults safely to `"MCP Client"`.
- **Strict Anti-Spoofing & URI Checks:** In `validate_registration_redirect_uris`:
  - URIs with fragments (`#`) or userinfo (`user:pass@`) are strictly rejected (`invalid_redirect_uri`).
  - Plaintext `http` is restricted strictly to loopback interfaces (`127.0.0.1`, `localhost`, `::1`, `[::1]`); all other targets must utilize `https`.
- **Public Client Enforcement:** `token_endpoint_auth_method` enforces `"none"` for public clients; symmetric client secret mechanisms (`client_secret_basic`, `client_secret_post`) are forbidden.
- **RFC 7591 Response Parity:** `OAuthClientRegisterResponse` returns `client_id`, `client_name`, `client_type: "public"`, `redirect_uris`, `grant_types`, `response_types`, and `token_endpoint_auth_method: "none"`.

### 2.2 Hierarchical Scoped Resource Indicators & Bare `/mcp` Routing
- **Pattern Matching (`parse_resource_target`):** Replaced rigid `.endswith(f"/mcp/{surface}")` with robust segment parsing supporting:
  - Bare `/mcp` (defaults cleanly to `Surface.AGENT`)
  - Scoped `/mcp/w/{workspace_slug}`
  - Scoped `/mcp/w/{workspace_slug}/p/{project_key}`
  - Explicit `/mcp/{surface}`
  - Scoped `/mcp/{surface}/w/{workspace_slug}[/p/{project_key}]`
- **Audience Verification in Introspection:** In `introspect_subject_token` (`kanban/security/mcp_keys.py`), `token_aud` is parsed via `parse_surface_from_resource`, preventing false-positive `SURFACE_KEY_MISMATCH` rejections when tokens target hierarchical scoped URLs.

### 2.3 Row-Level Security (RLS) & Workspace Slug vs. UUID Resolution
- **Zero RLS Bypass Leakage:** All workspace/project resolution helpers (`resolve_workspace_slug`, `resolve_workspace_by_slug_or_id`, `get_default_workspace_id`, `resolve_project_key`, `resolve_project_keys`, `resolve_project_id_by_key_or_id`) execute as `SECURITY DEFINER` with fixed `SET search_path = pg_catalog, public`. They operate safely under the unprivileged `kanban_app` role (`NOBYPASSRLS`).
- **Slug vs. UUID Resolution in Scoping (`intersect_key_and_connection_scope`):**
  - Resolves `auth_ctx.workspace_slug` and checks against `scope.workspace_slug` OR matches against `auth_ctx.workspace_id`.
  - Maps `scope.project_key` against `allowed_projects` (UUIDs) and `allowed_project_keys` (slugs/identifiers), eliminating false-positive `403 KEY_SCOPE_VIOLATION`.
- **Subject Token Resolution & Commit:** `SessionCookieResolver._resolve_subject_token` is committed and active in `kanban/auth/sessions/resolver.py`. Session lookups and audit timestamps commit properly, and default workspace resolution uses `get_default_workspace_id()` under RLS.

### 2.4 Static SPA Routing Boundary Hardening
- **Boundary Protection in `PrecompressedSPAStaticApp._resolve_spa_fallback`:** Expanded `disallowed_prefixes` to:
  `("/api", "/ws", "/sse", "/mcp", "/.well-known", "/oauth", "/internal")`
  This guarantees unmapped API or metadata URLs return RFC 7807 problem JSON / 404 rather than serving `index.html` with a 200 OK.
- **Discovery Endpoints:** Mounted `@oauth_root_router.get("/.well-known/oauth-authorization-server/{subpath:path}")` and `@oauth_root_router.get("/.well-known/openid-configuration{subpath:path}")` alongside RFC 9728 protected resource endpoints in `mcp/app.py`.

---

## 3. Live-Deployment Hardening & Resilience Audit (5 Production Fixes)

### 3.1 Migration Digest Validation on Persistent Volumes (`deploy/standalone/entrypoint.py`)
- **Vulnerability / Operational Failure:** In standalone single-container deployments with persistent volumes mounted to `/var/lib/postgresql/data`, the entrypoint previously decided `is_warm` based only on file existence of `PG_VERSION`, `.alembic_head`, and `keyring.json`. Upgrading the container image with new migrations against an existing volume skipped Alembic upgrades because `.alembic_head` was present from earlier boots, leaving database schemas unmigrated (`p4_18_oauth_mcp_scoping`).
- **Implementation & Invariant:** `_compute_migrations_digest()` calculates a combined SHA-256 hash over both filenames and full file bytes for all files in `database/migrations/versions/*.py` and `database/migrations/sql/*.sql`. During boot, `migrations_current` is evaluated by comparing `stored_digest == current_digest`. If new migrations or schema updates exist, `is_warm` evaluates to `False`, triggering safe execution of `run_migrations()` and writing the new digest to `.alembic_head`.

### 3.2 Database Schema Migration Tolerance via Nested Savepoints (`kanban/security/mcp_keys.py`)
- **Vulnerability / Operational Failure:** During zero-downtime rolling upgrades or when connecting against read-only replicas where the `p4_18` migration has not completed, querying the 22-column signature of `introspect_mcp_api_key(:digest)` raised `UndefinedColumnError`, immediately poisoning the PostgreSQL session transaction and causing all authentication checks to fail.
- **Implementation & Invariant:** `introspect_subject_token` wraps the 22-column query inside an explicit nested savepoint block (`async with session.begin_nested():`). If the query fails due to an unmigrated database signature, the sub-transaction rolls back cleanly without poisoning the outer session, and execution falls back to the legacy 20-column query (`stmt_legacy`). A matching nested savepoint protects `resolve_project_keys(:p_ids)`, ensuring uninterrupted token authentication across migration phases.

### 3.3 Robust Reverse-Proxy Public Origin Resolution (`mcp/auth.py`)
- **Vulnerability / Operational Failure:** Production reverse proxies (such as OpenResty/Nginx terminating TLS on `k.hackedyour.info`) forward `Host: k.hackedyour.info` and `X-Forwarded-Proto: https` but often do not include `X-Forwarded-Host`. Previously, `McpAuthMiddleware._unauthorized_response` required both `x-forwarded-proto` and `x-forwarded-host` together, causing it to fall back to `self.settings.kanban_api_base_url` (`https://127.0.0.1:8443`), which advertised loopback metadata URLs to external MCP clients.
- **Implementation & Invariant:** In `McpAuthMiddleware._unauthorized_response`, host resolution checks `host = headers.get("x-forwarded-host") or headers.get("host")` and protocol resolution checks `proto = headers.get("x-forwarded-proto") or (str(scope.get("scheme", "https")) if scope else "https")`. If the host is not a loopback address or if `x-forwarded-proto` is present, it constructs `base_url = f"{proto}://{host}".rstrip("/")`. Remote clients connecting via OpenResty or Nginx receive exact public HTTPS URLs in `WWW-Authenticate` challenges (`resource_metadata="https://k.hackedyour.info/.well-known/oauth-protected-resource/mcp/..."`).

### 3.4 Interactive Authorization Ergonomics, RLS Session Binding, & Return-To Sanitization (`kanban/api/v1/oauth.py`, `kanban/auth/oidc/flow.py`)
- **Vulnerability / Operational Failure:**
  1. Standard OAuth 2.1 clients often omit RFC 8707 `resource` in `/oauth/authorize` calls; requiring it produced `422 Unprocessable Entity`.
  2. Unauthenticated calls to `/oauth/authorize` emitted an absolute redirect to `http://localhost:8000/login?next=...`, breaking reverse-proxied browser flows.
  3. Querying `Project` and `principals` for the consent screen within an unauthenticated database session failed to return tenant data under `FORCE ROW LEVEL SECURITY`.
  4. Encoded OAuth redirect URLs in the `next` parameter (e.g., `next=%2Foauth%2Fauthorize%3Fredirect_uri%3Dhttp%253A%252F%252F...`) exceeded the 512-character limit and were rejected by `sanitize_return_to` due to colon and slash characters in the query string.
- **Implementation & Invariant:**
  1. In `oauth_authorize`, `resource: Annotated[str | None, Query()] = None` defaults safely to `f"{base_url}/mcp/agent"`.
  2. The unauthenticated redirect uses a relative URL: `next_target = f"{request.url.path}?{request.url.query}"` and redirects to `/login?next={quote(next_target)}`.
  3. Session RLS context is explicitly bound before project/principal queries using `set_config('app.principal_id', ...), set_config('app.workspace_id', ...), set_config('app.aal_level', ...)`, ensuring clean data retrieval without RLS violations.
  4. In `kanban/auth/oidc/flow.py`, `RETURN_TO_REGEX` length is expanded to 2048 characters. `sanitize_return_to` partitions on `?` to isolate the path from query parameters, verifying that the unquoted path starts with `/`, does not start with `//` or `/\\`, and contains zero colons `:` or backslashes `\`. Query parameters may safely contain URL-encoded redirect URIs.

### 3.5 Consent Screen Route-Specific Content-Security-Policy (`kanban/oauth/server.py`)
- **Vulnerability / Operational Failure:** The global HTTP security policy enforces strict `default-src 'none'`, `style-src 'self'`, and `form-action 'self'`. This caused two browser failures on the server-rendered consent screen:
  1. Inline CSS styling was blocked, breaking typography and layout.
  2. Under CSP Level 3, submitting the consent form via POST to `/oauth/authorize/decision` resulted in a 302 redirect to the client's loopback callback (e.g., `http://127.0.0.1:45678/callback`). The browser blocked the form redirection because `form-action 'self'` forbids navigation to non-origin URLs.
- **Implementation & Invariant:** In `kanban/oauth/server.py`, `render_consent_screen` attaches an explicit route-specific `Content-Security-Policy` header:
  `default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self' http://127.0.0.1:* http://localhost:* http://[::1]:* https:; frame-ancestors 'none'; base-uri 'none';`
  Because `SecurityHeadersMiddleware` preserves existing `content-security-policy` response headers, this policy overrides the default for the consent screen. Inline styles render correctly, and form redirects to loopback or HTTPS MCP client callbacks proceed without browser security violations.

---

## 4. Test & Verification Evidence

All automated unit and integration tests executed cleanly:
- **Test Results:** 174 passed in 15.44s (`docs/qa/KANBA-184/unit-test-results.txt`).
- **Coverage Areas:**
  - `kanban/tests/oauth/test_oauth_flow.py`: Positive OAuth flow, PKCE S256, audience binding, RFC 7591 dynamic registration, unauthenticated 401/302 discipline, scoped resource indicators, and bare `/mcp`.
  - `kanban/tests/oauth/test_oauth_unit.py`: Redirect URI validation, IPv6 loopback, registration rate limiting, and resource parsing.
  - `kanban/tests/oauth/test_device_flow.py`: Headless RFC 8628 device authorization.
  - `mcp/tests/test_connection_scoping.py`: Global bot flows, monotonic narrowing, header conflicts, slug vs. UUID matching, bare `/mcp` routing, and metadata generation.
  - `kanban/tests/mcp/test_live_mcp_mount.py`: Live ASGI mounting, RFC 9728 metadata, authenticated sessions, and security headers.
  - `kanban/tests/api/test_workspaces_api.py`: RLS enforcement under `SET ROLE kanban_app`.
- **Static Analysis & Architecture Contracts:**
  - `uv run ruff check kanban/ mcp/ database/ deploy/`: All checks passed with 0 errors.
  - Clean unidirectional layer imports: `agent -> mcp -> kanban -> database`.

---

## 5. Final Verdict

The backend, MCP, and deployment fixes for **KANBA-184** solve all real-world deployment failure modes with defense-in-depth engineering.

**Certification: APPROVED (READY FOR PRODUCTION)**

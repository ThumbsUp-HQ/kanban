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
- `kanban/api/v1/oauth.py`: RFC 7591 Dynamic Client Registration, RFC 8414 / OIDC discovery routers, and public base URL derivation.
- `kanban/oauth/server.py`: PKCE S256 verification, strict URI validation, hierarchical resource target parsing, and accessible consent screen rendering.
- `kanban/security/mcp_keys.py`: MCP token introspection, audience/surface verification, `SECURITY DEFINER` workspace/project resolution, and key labeling.
- `mcp/scoping.py`: Monotonic connection narrowing, workspace slug vs. UUID matching, and project key array containment.
- `mcp/app.py`: Bare `/mcp` route resolution, scoped `/mcp/w/{workspace}[/p/{project}]` endpoints, and RFC 9728 protected-resource metadata routes.
- `mcp/auth.py`: Dynamic reverse-proxy public origin derivation (`X-Forwarded-Proto`, `X-Forwarded-Host`, `Host`), scoped `WWW-Authenticate` challenge preservation, and `McpAuthContext` propagation.
- `kanban/web_static.py`: Hardened SPA fallback routing boundary excluding `/.well-known`, `/oauth`, `/internal`, `/api`, `/ws`, `/sse`, and `/mcp`.
- `kanban/api/deps.py`: `get_rls_session` non-UUID `x-kb-scope-workspace` header slug-to-UUID resolution under RLS.
- `kanban/auth/sessions/resolver.py`: `SessionCookieResolver._resolve_subject_token` activation, database commit, and fallback workspace resolution under RLS.
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

### 2.5 Reverse-Proxy Public Origin Derivation
- **Dynamic Origin Resolution (`resolve_public_base_url`):** Inspects `KANBAN_PUBLIC_ORIGIN`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Host`, and request URL.
- **Scope-Preserving 401 Challenges:** `McpAuthMiddleware._unauthorized_response` constructs `WWW-Authenticate` challenges using the dynamic public origin and preserves the scoped `/w/{workspace_slug}[/p/{project_key}]` path in `resource_metadata`.

---

## 3. Test & Verification Evidence

All automated unit and integration tests executed cleanly:
- **Test Session:** 174 passed in 15.44s (`docs/qa/KANBA-184/unit-test-results.txt`).
- **Coverage Areas:**
  - `kanban/tests/oauth/test_oauth_flow.py`: Positive OAuth flow, PKCE S256, audience binding, RFC 7591 dynamic registration, unauthenticated 401/302 discipline, scoped resource indicators, and bare `/mcp`.
  - `kanban/tests/oauth/test_oauth_unit.py`: Redirect URI validation, IPv6 loopback, registration rate limiting, and resource parsing.
  - `kanban/tests/oauth/test_device_flow.py`: Headless RFC 8628 device authorization.
  - `mcp/tests/test_connection_scoping.py`: Global bot flows, monotonic narrowing, header conflicts, slug vs. UUID matching, bare `/mcp` routing, and metadata generation.
  - `kanban/tests/mcp/test_live_mcp_mount.py`: Live ASGI mounting, RFC 9728 metadata, authenticated sessions, and security headers.
  - `kanban/tests/api/test_workspaces_api.py`: RLS enforcement under `SET ROLE kanban_app`.
- **Static Analysis & Architecture Contracts:**
  - `uv run ruff check kanban/ mcp/ database/`: 0 errors.
  - Clean unidirectional layer imports: `agent -> mcp -> kanban -> database`.

---

## 4. Final Verdict

The API and backend implementation for **KANBA-184** meets all enterprise architectural, security, and protocol standards. 

**Certification: APPROVED (READY FOR PRODUCTION)**

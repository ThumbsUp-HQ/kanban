# Reality-Checker Verification Packet: KANBA-23

## Ticket Summary
- Ticket ID: KANBA-23 (KB-P0-10)
- Epic: KB-E0 (Phase 0 Bootstrap and Foundation)
- Title: [Phase 0 / Web Server] ASGI app factory, PrecompressedSPAStaticApp & security headers
- Author: builder-20
- Gates: reality-checker, api-specialist, ui-specialist
- Branch: feat/KANBA-23
- Base SHA: 75eb4e4ebbec9e0ba33f0cd11575728acc4c2253 (merged feat/KANBA-17 to build kanban/web/dist)

---

## 1. Specification Traceability Matrix
- **S2.3 (Single :8080 port runtime & pre-compressed assets):**
  - Implemented `kanban/app.py:create_app()` mounting `/api`, `/ws`, `/sse`, `/mcp/*` placeholders, and `PrecompressedSPAStaticApp` at `/`.
  - Implemented `kanban/web_static.py:PrecompressedSPAStaticApp` serving Brotli (`.br`) and Gzip (`.gz`) pre-compressed static assets with Accept-Encoding negotiation, strong ETags, and 304 Not Modified revalidation.
- **S5.4 (Production CSP & security headers):**
  - Implemented byte-identical `CSP_POLICY` in `kanban/security/headers.py`.
  - Stamped `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, and `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
  - Enforced `Strict-Transport-Security: max-age=63072000; includeSubDomains` in production mode, cleanly omitted in standalone mode.
  - Overwrites existing inner app headers to prevent duplication.
- **S3.5 (Standalone cleartext host gate):**
  - Implemented host inspection stripping port and retaining IPv6 brackets in `kanban/security/headers.py:_extract_host`.
  - When `deployment_mode == "standalone"` and request scheme is `http`, requests from non-loopback hosts return HTTP 403 Forbidden with RFC 9457 Problem Details `CLEARTEXT_HTTP_BLOCKED`.
  - Missing Host header returns HTTP 400 Bad Request.
  - Hosts listed in `KB_STANDALONE_CLEARTEXT_HOSTS` are permitted.
- **Layering Isolation & Non-Import of MCP:**
  - `kanban/app.py` implements `/mcp/{surface:path}` placeholders returning HTTP 501 without importing `mcp`.
  - Verified via `import-linter` (contract: agent -> mcp -> kanban -> database, 1 kept, 0 broken).

---

## 2. Deliverables Produced
1. `kanban/app.py`: `create_app(settings: Settings | None = None) -> FastAPI` ASGI factory.
2. `kanban/settings.py`: `Settings` model using Pydantic Settings with `KB_` prefix, `deployment_mode`, `web_dist`, `hsts_max_age`, and `standalone_cleartext_hosts`.
3. `kanban/web_static.py`: Pure ASGI `PrecompressedSPAStaticApp` with encoding negotiation, path traversal guards, 50 MiB size limit, 64 KiB chunk streaming, strong ETags, and SPA fallback.
4. `kanban/security/headers.py`: `CSP_POLICY` constant, `_extract_host`, and `SecurityHeadersMiddleware`.
5. `kanban/security/__init__.py`: Package exports for `CSP_POLICY` and `SecurityHeadersMiddleware`.
6. `kanban/__init__.py`: Package export for `create_app`.
7. `kanban/GEMINI.md`: Updated module manifest documenting contracts, budgets, and failure modes.
8. `kanban/pyproject.toml` & `pyproject.toml` & `uv.lock`: Pinned runtime dependencies (`fastapi==0.162.5`, `starlette==1.10.0`, `uvicorn[standard]==0.54.0`, `pydantic-settings==2.16.2`) and dev dependency (`httpx==0.28.1`).
9. `kanban/tests/test_app.py`: Tests for `/api/v1/health`, 404 problem JSON, `/ws` 1008 close, `/sse` 501, `/mcp/*` 501, OpenAPI schema access, and default settings parsing.
10. `kanban/tests/test_web_static.py`: Tests for Brotli/Gzip negotiation, wire payload verification, SPA fallback, path traversal/symlink guards, HEAD requests, and 50 MiB limit.
11. `kanban/tests/test_security_headers.py`: Tests for CSP presence on all endpoints (200, 404, 501), HSTS production vs standalone, header replacement, standalone cleartext blocking, missing Host, and non-http scope pass-through.

---

## 3. Forensic Proof Artifacts in docs/qa/KANBA-23/
- `docs/qa/KANBA-23/unit-test-results.txt`:
  - 27/27 unit tests passed in 0.67s.
  - Overall coverage across `kanban`: 96.39% statement and branch coverage (minimum threshold: >= 95%).
  - Exit code: 0.
- `docs/qa/KANBA-23/build-check.txt`:
  - `make check` passing cleanly (ruff check 0 errors, ruff format 235 files clean, mypy strict 48 source files clean, lint-imports 1 kept 0 broken, check_no_dashes 0 hits).
  - Exit code: 0.
- `docs/qa/KANBA-23/contract-sample.txt`:
  - Live uvicorn server captures on port 18000 against built `kanban/web/dist`:
    * Scenario 1: `GET /` with `Accept-Encoding: br` -> HTTP 200, `cache-control: no-cache`, `vary: Accept-Encoding`, canonical CSP, HSTS.
    * Scenario 2: `GET /assets/index-CJtVY9il.js` with `Accept-Encoding: gzip` -> HTTP 200, `content-encoding: gzip`, `cache-control: public, max-age=31536000, immutable`, canonical CSP.
    * Scenario 3: `GET /api/v1/health` -> HTTP 200, `{"status":"ok"}`.
    * Scenario 4: `GET /mcp/admin` -> HTTP 501 Not Implemented, problem JSON.
    * Scenario 5: Standalone `GET /` with `Host: 192.168.1.20:18000` -> HTTP 403 Forbidden, `CLEARTEXT_HTTP_BLOCKED`, no HSTS.
- `docs/qa/KANBA-23/api-specialist-review.md`:
  - Verbatim review from Systems/Backend Architect & API Specialist (`@arch-reviewer`, board post #73).
  - Verdict: `APPROVED`.
- `docs/qa/KANBA-23/ui-specialist-review.md`:
  - Verbatim review from UX Architect / UI Designer Specialist Gate (`@ui-specialist`, board post #71).
  - Verdict: `APPROVED`.
- `docs/qa/KANBA-23/dependency-evaluation.md`:
  - Supply-chain evaluation for `fastapi`, `starlette`, `uvicorn[standard]`, `pydantic-settings`, and `httpx`.
  - Pinned SHA-256 hashes from `uv.lock`.
  - Signed approvals from `qa-eng` (#28), `sec-eng` (#29), and `arch-reviewer` (#30).
- `docs/qa/KANBA-23/git-diff.patch`:
  - Unified diff covering all changes relative to the worktree merge commit.
- **Screenshots:**
  - N/A: Non-UI Ticket (no rendered UI changes; behavior validated via `contract-sample.txt`).
- **Typography & Dash Hygiene:**
  - Zero `U+2014` or `U+2013` unicode characters across all source files, tests, documentation, and QA artifacts.

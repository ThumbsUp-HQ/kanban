# API Specialist Gate Review: KANBA-23 (KB-P0-10)

- Ticket: KANBA-23 (KB-P0-10: ASGI app factory, PrecompressedSPAStaticApp & security headers)
- Auditor: Systems/Backend Architect & API Specialist (@arch-reviewer)
- Worktree Audited: /tmp/kb-wt-KANBA-23 on branch feat/KANBA-23
- Authoritative Specification: docs/tickets/KB-P0-10.md
- Verification Artifact: docs/qa/KANBA-23/contract-sample.txt

---

## 1. API Route Contracts and Problem Details (RFC 9457)
- GET /api/v1/health: Correctly mounts on APIRouter with prefix /api and returns HTTP 200 {"status": "ok"} with application/json.
- Unknown /api/* routes: Intercepted by wildcard fallback route returning HTTP 404 with application/problem+json and exact payload {"type": "about:blank", "title": "Not Found", "status": 404}.
- WebSocket /ws: Rejection gate correctly intercepts incoming WebSocket connections and closes with WebSocket status code 1008 prior to calling accept().
- GET /sse: Placeholder returns HTTP 501 application/problem+json with title "Not Implemented".
- MCP Placeholders (/mcp/agent, /mcp/docs, /mcp/admin and subpaths): Returns HTTP 501 application/problem+json across all HTTP methods.
- Layering Isolation: kanban/ does not import mcp/. Verified via import-linter contract (1 kept, 0 broken). Real MCP routes will be composed at root in later phases.

## 2. PrecompressedSPAStaticApp and Path Traversal Defense
- Safe Path Parsing: Rigorously verifies unquoted paths. Immediately rejects null bytes (\x00), backslashes (\\), and relative path segments (..) with HTTP 404.
- Symlink and Root Confinement: Resolves paths with Path.resolve(strict=True) and verifies is_relative_to(dist_dir.resolve()). Any symlink pointing outside dist/ safely fails with HTTP 404.
- Bounded Reads: Enforces 64 KiB chunked streaming and immediately aborts with HTTP 404 on files exceeding 50 MiB.
- HTTP Methods: Only GET and HEAD are permitted; other HTTP methods correctly return HTTP 405 Method Not Allowed with Allow: GET, HEAD header.
- Content Negotiation & Caching:
  * Efficient parsing of Accept-Encoding with q-values.
  * Correct variant selection: serves .br (Brotli) when accepted, falls back to .gz (Gzip), and defaults to identity.
  * Cache-Control headers: /assets/* correctly receives public, max-age=31536000, immutable. Root index.html and SPA fallback routes correctly receive no-cache.
  * Strong ETags and Revalidation: Deterministic ETag format "<sha256-hex-16>-<encoding>". If-None-Match headers accurately trigger HTTP 304 Not Modified with empty body.

## 3. Security Headers Middleware and Host Protection
- Content-Security-Policy: CSP_POLICY in kanban/security/headers.py is byte-identical to the canonical Section 5.4 policy string. Verified in live curl captures across all routes.
- Hardening Headers: Consistently stamps X-Content-Type-Options: nosniff, Referrer-Policy: no-referrer, X-Frame-Options: DENY, Cross-Origin-Opener-Policy: same-origin, Cross-Origin-Resource-Policy: same-origin, and Permissions-Policy: camera=(), microphone=(), geolocation=(). Overwrites existing headers to prevent header injection or duplication.
- Transport Security (HSTS): Strict-Transport-Security: max-age=63072000; includeSubDomains is stamped exclusively when deployment_mode == "production" and correctly omitted in standalone mode.
- Standalone Cleartext Host Gate: Correctly checks request Host header when scheme is HTTP in standalone mode. Allowed loopback hosts (localhost, 127.0.0.1, [::1]) pass; non-whitelisted remote IPs (e.g. 192.168.1.20:18000) are blocked with HTTP 403 Forbidden and RFC 9457 problem detail CLEARTEXT_HTTP_BLOCKED.

## 4. Live Verification Evidence Audit
- Audited contract-sample.txt: Live uvicorn captures against built kanban/web/dist confirm byte-for-byte fidelity with all 5 required contract scenarios.
- Unit Test Suite: 27 passed in 0.67s with 96.39% branch and line coverage (exceeding 95% threshold).
- Code Quality: make check clean (ruff, mypy strict in 48 source files, import-linter, check_no_dashes).

---

## Final Verdict
Verdict: APPROVED. The implementation of the ASGI factory, static file server, and security middleware satisfies all architectural and security invariants of KB-P0-10.

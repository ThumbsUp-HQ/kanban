# UI Specialist Gate Review: KANBA-23 (KB-P0-10)

## 1. Ticket and Review Scope
- Ticket: KANBA-23 (KB-P0-10)
- Epic: KB-E0 (Phase 0 Bootstrap and Foundation)
- Worktree: /tmp/kb-wt-KANBA-23
- Reviewer: ui-specialist (UX Architect / UI Designer Specialist Gate)
- Scope: Frontend-facing web server behavior, SPA fallback routing, client-side route handling, static asset caching vs index.html freshness, CSP compatibility with frontend bundle (KB-P0-03), and user-facing error ergonomics (CLEARTEXT_HTTP_BLOCKED).

## 2. SPA Fallback Routing and Client Navigation
- Client-Side Navigation: Requests to extensionless paths without dots (e.g. `/projects/KAN/board`, `/cycle/current`, `/settings`) correctly resolve to `index.html` with HTTP 200 and `Content-Type: text/html; charset=utf-8`. This guarantees that client-side routers (React Router) mount properly without 404 dead ends.
- Asset 404 Disambiguation: Requests for missing static files containing file extensions (e.g. `/assets/missing.js`, `/favicon.ico`) intentionally do NOT fall back to `index.html`. They return a clean 404 plain text `Not Found`. This prevents MIME-type mismatch parsing crashes when the browser attempts to execute HTML as JavaScript or CSS.
- Reserved Path Protection: Requests starting with reserved prefixes (`/api`, `/ws`, `/sse`, `/mcp`) never trigger SPA fallback. They return RFC 9457 `application/problem+json` error responses (404 or 501), ensuring unambiguous API failure signaling for frontend HTTP clients.

## 3. Asset Caching Strategy and Cache Invalidation
- Content-Hashed Assets: Files located under `/assets/` (e.g. `/assets/index-CJtVY9il.js`, `/assets/index-BAvQsaM-.css`) are stamped with `Cache-Control: public, max-age=31536000, immutable`. Because Vite emits unique content hashes in filenames, browsers and CDNs can cache assets indefinitely with zero stale asset bugs.
- SPA Entrypoint Freshness: `index.html` (served at `/` and via SPA fallback) is explicitly stamped with `Cache-Control: no-cache`. This ensures the browser revalidates before use, allowing instant rollout of new deployments as soon as `index.html` changes.
- Conditional Revalidation: Strong ETags (`"<sha256-hex-16>-<encoding>"`) and `Vary: Accept-Encoding` are attached to all static responses. `If-None-Match` requests return HTTP 304 Not Modified with zero body payload, saving mobile bandwidth.

## 4. Content Security Policy (CSP) Compatibility with Frontend Bundle
- S5.4 CSP Verification: Every static and dynamic HTTP response is stamped with the exact canonical CSP header:
  `default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self' blob: data:image/png data:image/webp; font-src 'self'; connect-src 'self' wss:; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify;`
- Bundle Compatibility:
  * Static stylesheets in `/assets/*.css` load without warnings under `style-src 'self'`.
  * ESM scripts in `/assets/*.js` execute cleanly under `script-src 'self'`.
  * Precompressed siblings (`.br`, `.gz`) are served with transparent `Content-Encoding` without modifying payload hashes or requiring separate CSP whitelisting.
- Anti-Framing and Hardening Headers:
  * `X-Frame-Options: DENY` and `frame-ancestors 'none'` prevent clickjacking.
  * `X-Content-Type-Options: nosniff` prevents MIME confusion attacks.
  * `Referrer-Policy: no-referrer` prevents credential leakage.
  * HSTS (`Strict-Transport-Security: max-age=63072000; includeSubDomains`) is cleanly enabled in production and suppressed in standalone mode to avoid development lockout.

## 5. User-Facing Error Ergonomics: CLEARTEXT_HTTP_BLOCKED
- Error Response Format: HTTP 403 Forbidden with `Content-Type: application/problem+json`.
- Title: `CLEARTEXT_HTTP_BLOCKED`.
- Detail: "Standalone mode serves cleartext HTTP only to localhost. Put a TLS reverse proxy in front or add the host to KB_STANDALONE_CLEARTEXT_HOSTS."
- UX Assessment: Clear, concise, and actionable. It explains why the connection was rejected (cleartext HTTP to a non-loopback host) and provides immediate, concrete remediation paths (TLS reverse proxy or configuration override) without cryptic codes or stack traces.

## 6. Gate Conclusion
The ASGI web server implementation, static file negotiation, SPA fallback routing, asset caching rules, and security headers meet all frontend architecture, UX ergonomics, and security requirements defined in KB-P0-10 and AGENTS.md.

Verdict: APPROVED

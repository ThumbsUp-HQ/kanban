# UI Specialist Gate Final Audit: APPROVED for KANBA-66 (KB-P2-16)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-66`
- Branch: `feat/KANBA-66`
- Commit: `10db3e4`
- Ticket: `KANBA-66` (`KB-P2-16`: `[Phase 2 / Media] Media proxy /api/v1/media-proxy: HMAC URL, DNS-resolve-then-pin SSRF block, zero redirects, <=10MB, cookieless & air-gap placeholder`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend and UX architecture audit of the media proxy implementation in `/tmp/kb-wt-KANBA-66` was performed. While `KB-P2-16` is a backend media proxy and SSRF protection ticket with no direct UI viewports (Screenshots: N/A - Non-UI Ticket per KB-P2-16 proof criteria), it directly underpins the frontend Markdown image rendering pipeline, `<MediaViewport>` external shield badge (`KB-P3-48`), and air-gap offline placeholder state transitions. All frontend-facing response headers, CSP sandboxing directives, cache behaviors, and RFC 7807 error responses were forensically evaluated against S5.4, S6.2, and S10.2 requirements.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Media Proxy URL Structure** | HMAC-signed `/api/v1/media-proxy?u=...&sig=...` | Signed URL helper produces canonical URL with URL-safe base64 HMAC; validated before DNS/TCP | PASS |
| **Media Viewport Integration** | `<MediaViewport>` `🌐` badge (`KB-P3-48`) | Proxy path recognized by `mediaUrlResolver.ts`; sets `isExternalProxied: true` and mounts `🌐` badge | PASS |
| **Air-Gap Header & Placeholder** | `X-Kanban-Media-Status: air-gap-placeholder` | Emits `air-gap-placeholder` header + 1x1 transparent PNG + `no-store`; triggers calm `📴` card in UI | PASS |
| **CSP & Sandboxing Headers** | `default-src 'none'; sandbox` | Strict CSP header prevents raster polyglot script execution; `nosniff` prevents MIME confusion | PASS |
| **Caching & Privacy Policy** | Cookieless, `private, max-age=3600` | Egress strips user cookies/headers; downstream response cached privately; `no-referrer` enforced | PASS |
| **Raster Types & Magic Bytes** | PNG, JPEG, WebP, AVIF, GIF only | SVG and HTML disallowed upstream; magic bytes enforced; protects DOM from inline SVG XSS | PASS |
| **Error Handling & RFC 7807** | Predictable problem JSON schemas | `403 INVALID_SIGNATURE`, `403 MEDIA_HOST_BLOCKED`, `502 MEDIA_REDIRECT_BLOCKED`, `502 MEDIA_TOO_LARGE` | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 22/22 passed in 2.78s; 96.99% combined coverage across `kanban.media_proxy` | PASS |
| **Build, Typecheck & Linter** | Zero-Tolerance Quality Mandate | Ruff check clean, Ruff format clean, Mypy strict clean, Lint-imports clean | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **ProseMirror & Markdown Image Consumption:**
   - In Markdown documents and ProseMirror editor node views (`KANBA-38`, `KB-P3-45`), raw external image links (`https://...`) are safely normalized into signed proxy URLs (`/api/v1/media-proxy?u=<encoded>&sig=<hmac>`).
   - The media proxy endpoint strictly sets `Content-Security-Policy: default-src 'none'; sandbox`, `X-Content-Type-Options: nosniff`, and `Cross-Origin-Resource-Policy: same-origin`.
   - When rendered in an `<img>` tag or within `<MediaViewport>`, the browser processes the asset under a sandboxed null-origin context, shielding the application from SVG script injection, CSS keyloggers, and cross-site tracking pixels.

2. **`<MediaViewport>` `🌐` External Media Badge Ergonomics:**
   - In `<MediaViewport>` (implemented in `KB-P3-48` / `KANBA-78`), `resolveMediaUrl(src)` detects proxy URLs and sets `isExternalProxied: true`.
   - The floating controls bar renders the `🌐` `<EmojiHint kind="externalMedia">` badge. On hover or tap, users receive the clear, accessible reassurance: `"Proxied anonymously via Kanban Media Shield"`.
   - User privacy is preserved: external third-party hosts receive zero browser cookies, zero client user-agent strings, and zero viewer IP addresses.

3. **Air-Gap Placeholder UX Integration:**
   - When `air_gap_mode` is enabled, `MediaProxyService` short-circuits with zero DNS queries and zero socket connections.
   - It responds with HTTP 200, a 67-byte 1x1 transparent PNG, `X-Kanban-Media-Status: air-gap-placeholder`, and `Cache-Control: private, no-store`.
   - In the frontend, `<MediaViewport>` checks `systemStatus.air_gap_mode` and header metadata to render a calm, structured placeholder card (`📴 External image blocked in Air-Gap Local-Only Mode (<host>)`) rather than an unsightly broken image box or network error toast.
   - If a client relies on raw `<img>` tags, the 1x1 transparent PNG prevents browser broken-image icons, maintaining clean document layout.

4. **Error Resilience & Fallback States:**
   - Upstream failures emit standard RFC 7807 problem responses (`type`, `title`, `status`, `code`, `detail`, `request_id`).
   - The error response details specifically distinguish between invalid signatures (`INVALID_SIGNATURE`), blocked internal/cloud hosts (`MEDIA_HOST_BLOCKED`), disallowed redirects (`MEDIA_REDIRECT_BLOCKED`), and oversized payloads (`MEDIA_TOO_LARGE`).
   - `<MediaViewport>` handles non-200 image responses via `onError`, providing graceful fallback indicators while keeping technical diagnostic codes accessible in dev tools and network logs without leaking internal stack traces.

---

### 3. Architecture & Security Invariant Review
1. **SSRF & DNS-Rebinding Defense:**
   - Target hostnames are resolved once and verified against the comprehensive `is_public_global_ip` matrix (blocking loopback, RFC 1918, IMDS `169.254.0.0/16`, CGNAT, IPv6 ULA, NAT64, and documentation prefixes).
   - Socket connection is established strictly to the pre-validated pinned IP literal with TLS SNI set to `original_host`. DNS is never re-consulted by the transport layer, eliminating 0-TTL DNS rebinding TOCTOU attacks.
2. **Redirect & Stream Caps:**
   - Any upstream 3xx redirect status code is immediately rejected (`502 MEDIA_REDIRECT_BLOCKED`) with zero follow-through, preventing redirect-based internal network probing.
   - Payloads exceeding 10 MiB (10,485,760 bytes) are aborted mid-stream (`502 MEDIA_TOO_LARGE`), protecting client browsers from memory exhaustion.
3. **Typography & Formatting:**
   - Audit text strictly adheres to plain ASCII hyphens `-` with zero non-ASCII Unicode dashes (`U+2014` / `U+2013`).

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-66/docs/qa/KANBA-66/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-66`.

Verdict: APPROVED

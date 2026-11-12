# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-66 (KB-P2-16)

- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-66` on branch `feat/KANBA-66`
- Ticket: `KANBA-66` (`KB-P2-16`: [Phase 2 / Media] Media proxy /api/v1/media-proxy: HMAC URL, DNS-resolve-then-pin SSRF block, zero redirects, <=10MB, cookieless & air-gap placeholder)
- Target File: `docs/qa/KANBA-66/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the external media proxy, cryptographic URL signing, DNS-resolve-then-pin SSRF defense, cookieless transport, raster magic byte verification, and air-gap short-circuit mechanisms was conducted in `/tmp/kb-wt-KANBA-66`:

1. **HMAC URL Signing & Short-Circuit Verification (`signing.py`):**
   - **Constant-Time Pre-Gate:** `verify_media_proxy_url` enforces `len(sig) <= 64` and verifies the HMAC-SHA256 signature using `hmac.compare_digest` BEFORE initiating URL parsing or DNS resolution. Unsigned, tampered, or cross-URL signatures are rejected immediately with 403 `INVALID_SIGNATURE`, eliminating unauthenticated CPU and network amplification.
   - **Strict URL Formatting Boundaries:** `validate_external_image_url` strictly enforces HTTPS (`scheme == "https"`), default HTTPS port (`port in (None, 443)`), maximum hostname length of 253 characters, maximum URL length of 2,048 characters, zero userinfo (`username`/`password`), and zero URL fragment identifiers.
   - **Port-Scanning Defense:** Rejecting non-standard ports (e.g. `:8080`, `:6379`, `:5432`) prevents attackers from utilizing the proxy for internal or external port probing. Literal IP hostnames in blocked or private ranges are rejected immediately at validation time.

2. **SSRF Guard & DNS-Resolve-Then-Pin Socket Architecture (`ssrf.py`, `client.py`):**
   - **Comprehensive Blocked IP Matrix:** `is_public_global_ip` validates that destination addresses are publicly routable global unicast IPs. It explicitly blocks:
     * IPv4 and IPv6 loopback (`127.0.0.0/8`, `::1`)
     * RFC 1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
     * Link-local and cloud metadata endpoints (`169.254.0.0/16` AWS/GCP IMDS, `fe80::/10`)
     * Carrier-Grade NAT (`100.64.0.0/10`)
     * IPv6 Unique Local (`fc00::/7`) and site-local (`fec0::/10`)
     * Multicast, broadcast, documentation, benchmarking, and unspecified addresses (`0.0.0.0/8`, `::`).
   - **IPv6 Tunnel & NAT Unwrapping:** Explicitly unwraps IPv4-mapped IPv6 (`::ffff:x.x.x.x`) and NAT64 (`64:ff9b::/96`) addresses, ensuring embedded private IPv4 addresses cannot bypass filtering via IPv6 encoding.
   - **Single DNS Resolution & Poisoning Rejection:** `resolve_and_select_pinned_ip` resolves the hostname once under a 2.0s timeout. If zero records are returned or if **ANY** returned `A` or `AAAA` record fails `is_public_global_ip`, the entire request is rejected with 403 `MEDIA_HOST_BLOCKED`.
   - **Zero-TTL DNS Rebinding Elimination:** `PinnedTlsMediaClient` establishes a direct TCP connection to the pinned IP literal (`host=str(pinned_ip)`, `port=443`) while supplying `server_hostname=original_host` to `ssl.create_default_context()` (`TLSv1_2` minimum, `CERT_REQUIRED`, `check_hostname=True`). Because the socket layer connects directly to the IP literal without performing a secondary lookup, DNS-rebinding TOCTOU attacks are architecturally impossible.

3. **Cookieless Outbound Protocol & Content Sanitization (`client.py`, `service.py`):**
   - **Total Header Cleansing:** Outbound HTTP/1.1 requests emit strictly:
     ```http
     GET {path} HTTP/1.1
     Host: {original_host}
     User-Agent: Kanban-Media-Proxy/1.0
     Accept: image/png, image/jpeg, image/webp, image/avif, image/gif
     Accept-Encoding: identity
     Connection: close
     ```
     No client `Cookie`, `Authorization`, `Referer`, `Origin`, or `X-Forwarded-For` headers are forwarded upstream.
   - **Zero Redirect Enforcement:** Any 3xx redirect response (`301`, `302`, `303`, `307`, `308`) immediately closes the socket and triggers 502 `MEDIA_REDIRECT_BLOCKED` without inspecting `Location`, preventing redirect-based SSRF into private networks.
   - **Raster-Only MIME & Magic Signature Verification:** Declared `Content-Type` must strictly reside in `{"image/png", "image/jpeg", "image/webp", "image/avif", "image/gif"}` (SVG and HTML rejected with 415 `MEDIA_TYPE_DISALLOWED`). The first 32 bytes are verified against raster magic byte headers (`\x89PNG`, `\xff\xd8\xff`, `GIF8`, `RIFF....WEBP`, `ftypavif`/`ftypavis`), returning 502 `MEDIA_SIGNATURE_MISMATCH` on polyglots or mismatched payloads.
   - **10 MiB Streaming Buffer Cap:** `MAX_PROXY_BYTES = 10_485_760`. Excess `Content-Length` is rejected upfront; streamed chunks are counted and aborted immediately upon exceeding 10 MiB with 502 `MEDIA_TOO_LARGE`.
   - **Downstream Header Hardening:** Response strips all upstream headers (`Set-Cookie`, `ETag`, `Server`, `Link`) and emits strictly:
     * `Content-Security-Policy: default-src 'none'; sandbox`
     * `X-Content-Type-Options: nosniff`
     * `Cross-Origin-Resource-Policy: same-origin`
     * `Referrer-Policy: no-referrer`
     * `Cache-Control: private, max-age=3600`

4. **Air-Gap Short-Circuit & Rate Limiting (`placeholder.py`, `media_proxy.py`):**
   - **Zero-Packet Air-Gap Isolation:** When `air_gap_mode` is enabled, `MediaProxyService` short-circuits with 0 DNS and 0 TCP calls, returning HTTP 200 with a 67-byte 1x1 transparent PNG, `X-Kanban-Media-Status: air-gap-placeholder`, and `Cache-Control: private, no-store`.
   - **Rate Limiting:** Enforces `MEDIA_PROXY_PRINCIPAL` sliding-window rate limit (120 req / 60s per authenticated principal) via `kanban.security.ratelimit`.

---

### 2. Independent Verification & Test Execution

- **Unit & Security Matrix Suite:** 22 / 22 tests passed cleanly in 2.68s across `test_ssrf_and_rebinding.py` and `test_media_proxy_api.py`.
  - Case 1: Positive cookieless proxy with header stripping and CSP sandboxing.
  - Case 2: HMAC gate verification, tamper rejection, and 0 DNS calls.
  - Case 3: Complete SSRF IP matrix (127.0.0.1, 10.0.0.1, 172.16.5.4, 192.168.1.1, 169.254.169.254, 100.64.0.1, 0.0.0.0, ::1, fe80::1, fc00::1, fd12:3456::1, mapped IPv4, NAT64, multi-record mixed responses) all rejected with 403 `MEDIA_HOST_BLOCKED` and 0 TCP connects.
  - Case 4: DNS rebinding TOCTOU assertion confirming exactly 1 DNS lookup and pinned IP literal connection.
  - Case 5: 3xx redirect rejection with 502 `MEDIA_REDIRECT_BLOCKED`.
  - Case 6: URL scheme, credential, and port scanning rejections with 400 `INVALID_MEDIA_URL`.
  - Case 7: Content-Type disallowance (SVG/HTML -> 415) and magic byte mismatch rejection (502).
  - Case 8: 10 MiB boundary cap enforcement.
  - Case 9: Air-gap mode placeholder with 0 DNS/TCP calls, 401 unauthenticated check, and 429 rate limit breach.
- **Coverage:** **96.76%** combined line and branch coverage across target modules (`kanban.media_proxy` and `kanban.api.v1.media_proxy`).
- **Static Quality & Build Gates:**
  - `ruff check .`: Clean (0 errors).
  - `ruff format --check .`: Clean.
  - `mypy --strict kanban database`: Clean (0 errors across 193 source files).
  - `lint-imports`: 2 kept, 0 broken.
  - `scripts/check_no_dashes.py --all`: Clean (0 non-ASCII dashes repo-wide).
  - `make license`: Clean (violations=0).

---

### 3. Verdict

The media proxy implementation in `/tmp/kb-wt-KANBA-66` establishes an uncompromising, attack-resistant boundary against SSRF, IP leakage, DNS rebinding, and untrusted media execution, fully satisfying `KB-P2-16`.

APPROVED

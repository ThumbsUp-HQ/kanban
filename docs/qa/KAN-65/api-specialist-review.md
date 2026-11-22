# API & Security Specialist Review: KAN-65 (`[KB-SEC-03]`)

- **Reviewer Persona:** `security-engineer` / `backend-architect` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-65` (`[KB-SEC-03] Strip Spoofed Headers & Block /internal/* in Caddyfile, Add Dedicated :8444 Runner mTLS Listener, & Configure KB_TRUSTED_PROXIES in Docker Compose`)
- **Audited Commit (`HEAD`):** `77ea4ae25bcefeff81ff2058af9c4d5aef1b28e3` (`77ea4ae2`)
- **Base Commit (`main`):** `4f836f69d99ce4837c4abb97a85a6892862fdade` (`4f836f69`)
- **Audited Branch:** `main` (merged from `feat/KAN-65-caddy-trusted-proxies`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-65/git-diff.patch`
  - `docs/qa/KAN-65/contract-sample.json`
  - `docs/qa/KAN-65/unit-test-results.txt`
  - `docs/qa/KAN-65/build-check.txt`
  - `docs/qa/KAN-65/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `deploy/caddy/Caddyfile`
  - `deploy/compose/docker-compose.yml`
  - `kanban/standalone/compose_export.py`
  - `kanban/security/headers.py`
  - `kanban/tests/security/test_caddy_and_trusted_proxies.py`
  - `kanban/tests/standalone/test_compose_export.py`
  - `kanban/tests/test_security_headers.py`
  - `tests/deploy/test_caddyfile.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-65` hardens the edge reverse-proxy topology and client IP resolution architecture, eliminating header-spoofing vectors and isolating runner mTLS traffic:
1. **Edge Route Blocking & Header Sanitization (Action 1):** In `deploy/caddy/Caddyfile`, requests targeting `/internal/*` and `/api/v1/internal/*` are intercepted directly at the edge with `respond @internal_routes 404`. All public reverse proxy directives strip client-supplied certificate and internal authentication headers (`header_up -X-Client-Cert-Pem`, `header_up -X-Client-Cert-Der-B64`, `header_up -X-Client-Cert-CN`, `header_up -X-SSL-Client-Cert`, `header_up -X-KB-Service-Principal`, `header_up -X-KB-Internal-Auth`, `header_up -X-KB-Internal-Timestamp`, `header_up -X-KB-Internal-Signature`).
2. **Dedicated Runner mTLS Listener (Action 2):** A dedicated `:8444` listener enforces TLS 1.3 with mandatory client authentication (`client_auth { mode require }`). It forwards strictly `/api/v1/runners/ws` (and its subpaths) to `kanban-api:8000` with `flush_interval -1` and securely injected client certificate headers, rejecting all other routes with HTTP 404.
3. **Spoof-Resistant Client IP Resolution (Action 3):** `resolve_client_ip` in `kanban/security/headers.py` verifies the direct peer IP from `scope['client']` against `trusted_proxies` (or `KB_TRUSTED_PROXIES` / `KANBAN_TRUSTED_PROXIES`). Untrusted peers have their direct peer IP returned immediately, ignoring all spoofed `X-Forwarded-For` and `X-Real-IP` headers. When trusted, `X-Forwarded-For` is traversed right-to-left to find the first untrusted upstream client.
4. **Docker Compose & Production Bundle Alignment:** `deploy/compose/docker-compose.yml` and `kanban/standalone/compose_export.py` expose port `8444:8444` on `reverse-proxy`, set `KB_TRUSTED_PROXIES: "172.28.0.0/16,127.0.0.1/32"`, and configure the internal `app_net` subnet `172.28.0.0/16`.
5. **Quality & Test Compliance:** 39 Pytest tests passed in 2.67s with 98% total coverage across touched Python modules (`compose_export.py` 100%, `headers.py` 97%). Static analysis (`make check`, `make compose-check`, Caddy validation) and repository-wide dash checks passed with 0 errors.

---

## 2. Architecture & Wire Contract Verification

### 2.1 Caddy Edge Reverse-Proxy Rules (`deploy/caddy/Caddyfile`)
- Route Blocking:
  `@internal_routes path /internal/* /api/v1/internal/*`
  `respond @internal_routes 404`
- Upstream Header Stripping:
  Applied across `/api/*`, `/ws`, `/sse*`, and `/mcp/*` proxy blocks. Prevents any external client from injecting spoofed internal service tokens or mTLS identity headers.
- Runner Listener (`:8444`):
  `protocols tls1.3`
  `client_auth { mode require }`
  `@runner_ws path /api/v1/runners/ws /api/v1/runners/ws/*`
  Proxies to `kanban-api:8000` with injected `X-Client-Cert-Pem` and `X-Client-Cert-Der-B64`.
  Default: `respond 404`.

### 2.2 Spoof-Resistant Client IP Resolution (`kanban/security/headers.py`)
- `_extract_direct_peer`: extracts IP from `scope['client'][0]`.
- `_is_trusted(peer, trusted_nets)`:
  - If direct peer is NOT trusted: returns `_format_ip(peer)` immediately.
  - If direct peer is trusted: traverses `X-Forwarded-For` right-to-left, returning the first untrusted client IP. If XFF is absent, falls back to `X-Real-IP`.
- IP normalization:
  - IPv4-mapped IPv6 addresses (`::ffff:192.0.2.1`) are normalized to standard IPv4.
  - Public IPv6 clients are bucketed by `/64` prefix to prevent rate limiter evasion.

### 2.3 Wire Frame Contracts (`docs/qa/KAN-65/contract-sample.json`)
The recorded exchanges verify:
- `1_public_listener_spoofed_headers_stripped`: Verified headers stripped before reaching upstream.
- `2_public_listener_internal_routes_blocked_404`: Edge returns 404 for `/api/v1/internal/*`.
- `3_runner_mtls_listener_8444_ws_forwarded`: Verified WebSocket forwarded with client cert headers.
- `4_runner_mtls_listener_8444_other_routes_blocked_404`: Non-runner routes on :8444 return 404.
- `5_resolve_client_ip_untrusted_peer_spoofing_rejected`: Spoofed XFF/X-Real-IP from untrusted direct peer ignored.
- `6_resolve_client_ip_trusted_peer_traversal_success`: Right-to-left XFF traversal from trusted Caddy proxy.
- `7_resolve_client_ip_trusted_peer_x_real_ip_success`: Trusted proxy X-Real-IP fallback.

---

## 3. Test Verification & Code Coverage

- **Pytest Suite Results (`39 passed in 2.67s`):**
  - `kanban/tests/security/test_caddy_and_trusted_proxies.py`: 18 passed
  - `kanban/tests/standalone/test_compose_export.py`: 3 passed
  - `kanban/tests/test_security_headers.py`: 11 passed
  - `tests/deploy/test_caddyfile.py`: 7 passed
- **Coverage Metrics:**
  - `kanban/security/headers.py`: **97%**
  - `kanban/standalone/compose_export.py`: **100%**
  - Combined total: **98%** (exceeds 95% project threshold)
- **Static Analysis & Edge Validation:**
  - `make check`: 0 errors
  - `make compose-check`: 0 errors
  - `docker run caddy:2.8-alpine caddy validate`: 0 errors
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (zero em/en-dashes)

---

## 4. Review Sign-Off

The Caddyfile edge hardening, runner mTLS listener, Docker Compose configuration, and spoof-resistant client IP resolution for `KAN-65` are approved.

**STATUS: APPROVED**

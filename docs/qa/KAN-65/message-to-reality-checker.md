# Forensic Verification Proof Packet: KAN-65

## Ticket Summary
`[KB-SEC-03] Strip Spoofed Headers & Block /internal/* in Caddyfile, Add Dedicated :8444 Runner mTLS Listener, & Configure KB_TRUSTED_PROXIES in Docker Compose`

- **Branch:** `main` (merged from `feat/KAN-65-caddy-trusted-proxies`)
- **Merged Commit (`HEAD`):** `77ea4ae25bcefeff81ff2058af9c4d5aef1b28e3` (`77ea4ae2`)
- **Pre-Ticket Base Commit (`main`):** `4f836f69d99ce4837c4abb97a85a6892862fdade` (`4f836f69`)
- **Visual Browser Screenshots:** `N/A - Non-UI Ticket` (Caddy reverse-proxy edge hardening, runner mTLS listener block, Docker Compose trusted proxy network configuration, and spoof-resistant resolve_client_ip; HTTP wire transcripts in `docs/qa/KAN-65/contract-sample.json` replace browser screenshots).

---

## Requirement-to-Proof Traceability Matrix

| Requirement | Implementation Location | Verification Proof Artifact |
| :--- | :--- | :--- |
| **Action 1: Strip Spoofed Client Headers & Block /internal/* in Caddyfile** | `deploy/caddy/Caddyfile` (added `@internal_routes path /internal/* /api/v1/internal/*` with `respond @internal_routes 404`; added `header_up -X-Client-Cert-Pem`, `header_up -X-Client-Cert-Der-B64`, `header_up -X-Client-Cert-CN`, `header_up -X-SSL-Client-Cert`, `header_up -X-KB-Service-Principal`, `header_up -X-KB-Internal-Auth`, `header_up -X-KB-Internal-Timestamp`, `header_up -X-KB-Internal-Signature` across all public reverse_proxy handlers). | `docs/qa/KAN-65/contract-sample.json` (`1_public_listener_spoofed_headers_stripped`, `2_public_listener_internal_routes_blocked_404`), `kanban/tests/security/test_caddy_and_trusted_proxies.py::test_caddyfile_blocks_internal_routes_with_404`, `kanban/tests/security/test_caddy_and_trusted_proxies.py::test_caddyfile_strips_spoofable_headers_on_public_listener` |
| **Action 2: Add Dedicated :8444 Runner mTLS Listener Block** | `deploy/caddy/Caddyfile` (added `:8444` block with `tls1.3`, `client_auth { mode require }`, `@runner_ws path /api/v1/runners/ws /api/v1/runners/ws/*` forwarding to `kanban-api:8000` with `flush_interval -1` and client cert headers `X-Client-Cert-Pem` and `X-Client-Cert-Der-B64`, stripped internal service headers, and default `respond 404`). | `docs/qa/KAN-65/contract-sample.json` (`3_runner_mtls_listener_8444_ws_forwarded`, `4_runner_mtls_listener_8444_other_routes_blocked_404`), `kanban/tests/security/test_caddy_and_trusted_proxies.py::test_caddyfile_dedicated_8444_runner_mtls_listener`, `docs/qa/KAN-65/build-check.txt` (Caddy validate exit 0) |
| **Action 3: Configure KB_TRUSTED_PROXIES in Compose & resolve_client_ip in headers.py** | `deploy/compose/docker-compose.yml` and `kanban/standalone/compose_export.py` (configured port `8444:8444` on `reverse-proxy`, `KB_TRUSTED_PROXIES: "172.28.0.0/16,127.0.0.1/32"` on `kanban-api`, and `app_net` internal subnet `172.28.0.0/16`); `kanban/security/headers.py` (`resolve_client_ip` only trusts `X-Forwarded-For` and `X-Real-IP` when immediate peer IP is within `trusted_proxies`, walking XFF right-to-left, falling back to X-Real-IP, normalizing IPv4-mapped IPv6, and bucketing IPv6 by /64). | `docs/qa/KAN-65/contract-sample.json` (`5_resolve_client_ip_untrusted_peer_spoofing_rejected`, `6_resolve_client_ip_trusted_peer_traversal_success`, `7_resolve_client_ip_trusted_peer_x_real_ip_success`), `kanban/tests/security/test_caddy_and_trusted_proxies.py`, `kanban/tests/standalone/test_compose_export.py` |
| **Unit Tests & >=95% Coverage Gate** | `kanban/tests/security/test_caddy_and_trusted_proxies.py`, `kanban/tests/standalone/test_compose_export.py`, `kanban/tests/test_security_headers.py`, `tests/deploy/test_caddyfile.py` | `docs/qa/KAN-65/unit-test-results.txt` (39 passed in 2.67s; 98% total coverage across touched modules: `kanban/standalone/compose_export.py` 100%, `kanban/security/headers.py` 97%) |
| **Build, Type, Lint & Compose Checks** | `make check`, `make compose-check`, `docker run caddy:2.8-alpine caddy validate`, `uv run python -m scripts.check_no_dashes --all` | `docs/qa/KAN-65/build-check.txt` (All checks passed, 0 errors, 65 migrations valid, 2 architecture contracts kept) |

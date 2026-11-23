# API Specialist Review: KAN-324

## Audit Metadata
- Ticket ID: KAN-324 ([KB-SEC-MODEL-01])
- Title: Fix Caddy Dedicated :8444 Runner mTLS Reverse-Proxy Route Mismatch for /api/v1/agent-runners/ws
- Reviewer: backend-architect (API Specialist)
- Date: 2026-11-23
- Status: APPROVED

---

## 1. Scope & Objective
Ticket KAN-324 resolves a route mismatch in the reverse-proxy configuration for remote agent runners connecting over mTLS on dedicated port `:8444`.
Previously, the Caddy matcher was defined as `@runner_ws path /api/v1/agent-runners/ws/*`, which failed to match the exact WebSocket handshake path `/api/v1/agent-runners/ws`.

---

## 2. API & Reverse-Proxy Route Verification
1. **Caddyfile Matcher Syntax:**
   - Updated `deploy/caddy/Caddyfile` line 104 to `@runner_ws path /api/v1/agent-runners/ws /api/v1/agent-runners/ws/*`.
   - Both exact handshake `/api/v1/agent-runners/ws` and parameterized child paths `/api/v1/agent-runners/ws/*` are matched.
2. **Standalone Compose Exporter Parity:**
   - Updated `kanban/standalone/compose_export.py` line 383 to maintain exact 1:1 parity in generated Caddy configs:
     `@runner_ws path /api/v1/agent-runners/ws /api/v1/agent-runners/ws/*`.
3. **mTLS & Trusted Header Security Invariants:**
   - Dedicated port `:8444` enforces client certificate verification with trusted CA bundle `{$RUNNER_MTLS_CLIENT_CA_FILE}`.
   - Clears untrusted client-supplied headers and injects verified cryptographic runner identity headers:
     `X-Kb-Runner-Cert-Sha256`, `X-Kb-Runner-Subject-Cn`, `X-Kb-Runner-Spiffe-Id`.
   - Upstream reverse-proxy destination points securely to `reverse_proxy localhost:8000`.

---

## 3. Test Coverage & Quality Gate
- `kanban/tests/security/test_caddy_and_trusted_proxies.py`: 18 tests passed, verifying exact path `/api/v1/agent-runners/ws` and wildcards across Caddy configurations.
- `kanban/tests/standalone/test_compose_export.py`: Verified generated Compose files reflect the corrected matcher.
- Coverage on `kanban.standalone.compose_export`: 100%.

---

## 4. Conclusion
The API and proxy contract is verified and hardened. Route mismatch is resolved with zero regressions. Approved for ticket closure.

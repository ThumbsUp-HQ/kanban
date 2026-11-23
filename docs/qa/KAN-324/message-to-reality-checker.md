# Forensic QA Handoff: KAN-324

## Overview & User Story
- Ticket ID: KAN-324 ([KB-SEC-MODEL-01] Fix Caddy Dedicated :8444 Runner mTLS Reverse-Proxy Route Mismatch for /api/v1/agent-runners/ws)
- Classification: N/A - Non-UI Security Ticket
- Branch: feat/KAN-324-328
- Touched Files:
  - `deploy/caddy/Caddyfile`
  - `kanban/standalone/compose_export.py`
  - `kanban/tests/security/test_caddy_and_trusted_proxies.py`
  - `kanban/tests/standalone/test_compose_export.py`

## User Story
As an infrastructure operator and remote execution agent runner, I need the dedicated :8444 mTLS reverse-proxy in Caddy to properly match the exact `/api/v1/agent-runners/ws` WebSocket endpoint so remote runners authenticate via client certificates and establish persistent control channels without route 404/rejection errors.

---

## Evidence Manifest
1. `git-diff.patch`: Unified diff showing exact route matchers `@runner_ws path /api/v1/agent-runners/ws /api/v1/agent-runners/ws/*` in `Caddyfile` and `compose_export.py`.
2. `unit-test-results.txt`: 21 passed tests (18 in `test_caddy_and_trusted_proxies.py`, 3 in `test_compose_export.py`).
3. `build-check.txt`: Clean static gate checks (`make check` exited 0).
4. `api-specialist-review.md`: Backend architect sign-off on mTLS proxy invariants.
5. `ui-specialist-review.md`: Confirmed N/A - Non-UI Ticket.
6. `changed-files-manifest.txt`: Cryptographic SHA-256 manifest verified with `sha256sum -c`.

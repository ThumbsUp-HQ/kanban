# Forensic QA Handoff: KAN-326

## Overview & User Story
- Ticket ID: KAN-326 ([KB-SEC-MODEL-03] Propagate MCP Read-Taint High-Water Mark to Realtime WebSocket Subscriptions)
- Classification: N/A - Non-UI Security Ticket
- Branch: feat/KAN-324-328
- Touched Files:
  - `kanban/security/read_taint.py`
  - `kanban/realtime/hub.py`
  - `kanban/api/ws.py`
  - `kanban/tests/realtime/test_ws_read_taint.py`

## User Story
As a security architect, I require all realtime WebSocket subscriptions to projects, issues, and docs to propagate their read-taint to the platform's MCP read-taint ledger so that AI agents connected via WebSockets cannot bypass data exfiltration controls when writing to wider scopes.

---

## Evidence Manifest
1. `git-diff.patch`: Unified diff showing `record_read_taint` extraction, WebSocket MCP session extraction, and `handle_subscribe` channel taint resolution.
2. `unit-test-results.txt`: 6 passed integration tests covering project/issue/doc channel taints, MCP session header propagation, unsubscribe monotonicity, and exfiltration blocking.
3. `build-check.txt`: Clean static gate checks (`make check` exited 0).
4. `api-specialist-review.md`: Backend architect sign-off on taint monotonicity and anti-exfiltration guards.
5. `ui-specialist-review.md`: Confirmed N/A - Non-UI Ticket.
6. `changed-files-manifest.txt`: Cryptographic SHA-256 manifest verified with `sha256sum -c`.

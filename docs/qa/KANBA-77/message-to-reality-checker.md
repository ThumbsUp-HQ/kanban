# Message to Reality-Checker: KANBA-77 (KB-P3-16)

## Overview
- **Ticket**: KANBA-77 (`KB-P3-16`: `[Phase 3 / API] Realtime WebSocket (/ws) & SSE (/sse Last-Event-ID) hub with per-event RLS filtering`)
- **Status**: Ready for Merge Queue and Reality-Checker QA Gate
- **Branch**: `feat/KANBA-77` in worktree `/tmp/kb-wt-KANBA-77`
- **Linear Lineage**: Cleanly merged with `main`, single linear head.

## Architecture and Product Spec Compliance (Sections 2.2, 2.3, 2.4, 3.3, 3.4)

### 1. Dual Transport Architecture (`kanban/api/ws.py`, `kanban/api/sse.py`)
- **WebSocket (`/ws`)**:
  * Origin validation: strict allowlist matching configured `settings.public_base_url` or loopback origins; mismatch rejected with WebSocket close code `4403 ORIGIN_MISMATCH` before `accept()`.
  * Authentication: reads session token from `__Host-` session cookie; missing or invalid session closes with `4401 UNAUTHENTICATED`.
  * Rate and resource limits: max 16 concurrent realtime connections per `(workspace_id, principal_id)` (`4429 CONCURRENT_LIMIT_EXCEEDED`); max 64 channels per connection (`CHANNEL_LIMIT_EXCEEDED`); max inbound frame size 4096 bytes (`4413 FRAME_TOO_LARGE`).
  * Protocol frames: strictly validated client frames (`op: subscribe`, `op: unsubscribe`, `op: pong`) with `extra="forbid"`.
- **Server-Sent Events (`/sse`)**:
  * Query parameters: `?channels=project:0193...,issue:0193...` parsed and validated.
  * Authentication: `__Host-` session cookie; unauthenticated returns HTTP 401.
  * Response headers: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-store`, `X-Accel-Buffering: no`.
  * Channel and connection limits: max 64 channels (`422`), max 16 concurrent connections (`429`).
  * Resumption: parses `Last-Event-ID` header for seamless reconnect.

### 2. Delivery-Time RLS Filtering and Anti-Harvesting (`kanban/realtime/rls_filter.py`, `kanban/realtime/replay.py`)
- **Batched Recipient Authorization**:
  * `authorize_event_recipients(session, event, candidate_principals)` executes batched evaluation against `effective_resource_access` for `(allow_mask & 1) == 1 and (deny_mask & 1) == 0`.
- **Mid-Session ACL Revocation Handling**:
  * If a recipient loses `VIEW` capability on an active subscription:
    - Direct object subscriptions (`issue:{id}` or `doc:{id}`) drop subscription and emit `{"type": "channel.revoked", "channel": "..."}` with strictly zero payload fields.
    - Container subscriptions (`project:{id}`) silently omit events targeting restricted child issues without revealing event presence.
- **Outbox Replay Safety**:
  * `OutboxReplayer.replay()` queries `outbox_events` within 15-minute / 500-event window.
  * Emits `resync_required` when client sequence is older than retained window or missing > 500 events.
  * Evaluates current `authorize_event_recipients` on every candidate replay event, preventing historical harvesting of revoked data.

### 3. Lifecycle, Session Termination, and Graceful Draining (`kanban/realtime/hub.py`, `kanban/app.py`)
- **Heartbeat & Keepalive**:
  * 25s ping frames on `/ws` and `: heartbeat\n\n` comments on `/sse`.
- **Session Expiry & Revocation**:
  * Background loop checks session expiration every 60s via `SessionService.resolve_session`.
  * Subscribes to `security.session_revoked` and `security.principal_deactivated` broker topics, closing matching sockets in <= 250ms with `4401`.
- **Lifespan Draining**:
  * FastAPI lifespan shutdown broadcasts `{"type": "server.draining", "retry_ms": 1000}` and closes active WebSocket connections with code `1001` within 3s.

## Quality & Forensic Proof Summary
- **Unit Tests**: 50/50 tests passing in 5.67s across `kanban/tests/realtime/` (`test_ws_hub.py`, `test_sse_resume.py`, `test_rls_event_filter.py`, `test_hub_unit.py`).
- **Coverage**: 96.28% total branch+line coverage across target modules (`kanban.realtime`, `kanban.api.ws`, `kanban.api.sse`), exceeding the >= 95% mandate.
- **Static Analysis**: All clean (Ruff check clean, Ruff format clean on 192 files, Mypy strict clean on 190 files, Lint-imports clean with 2 kept and 0 broken, License gate clean with violations=0, check_no_dashes clean).
- **Dual Specialist Gate**:
  * API Specialist Review: `docs/qa/KANBA-77/api-specialist-review.md` (APPROVED by `@arch-reviewer`, Board #471).
  * UI Specialist Review: `docs/qa/KANBA-77/ui-specialist-review.md` (APPROVED by `@ui-specialist`, Board #463).
- **Deterministic Packet Validator**: `uv run kanban-agent validate-qa-packet` reports Grade A, Readiness: READY (7/7 checks passed).

# API Specialist Gate Final Audit: APPROVED for KANBA-77 (KB-P3-16)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-77`
- Branch: `feat/KANBA-77`
- Ticket: `KANBA-77` (`KB-P3-16`: `[Phase 3 / API] Realtime WebSocket (/ws) & SSE (/sse Last-Event-ID) hub with per-event RLS filtering`)

---

### 1. Executive Summary & Verification Matrix
A forensic backend architecture and API Specialist Gate audit was conducted for `KANBA-77` in `/tmp/kb-wt-KANBA-77`. `KB-P3-16` delivers the authenticated realtime messaging hub powering live board movements, comment threads, and AI gate badges (`⏳🤖`/`✅🤖`/`🛑🤖`). The architecture provides dual-transport streaming (WebSocket `/ws` and Server-Sent Events `/sse` with `Last-Event-ID` resumption), per-event delivery-time Row-Level Security (RLS) enforcement, mid-session ACL revocation defenses with zero payload leakage, anti-harvesting replay filters, connection and channel caps, strict Origin checks, fast session revocation, and graceful server draining. All implementations were evaluated against Spec Sections 2.2, 2.3, 2.4, 3.3, and 3.4.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Dual Transport Architecture** | WebSocket `/ws` and SSE `/sse` endpoints | Both mounted on `create_app()` with unified session cookie auth | PASS |
| **Origin & Handshake Security** | Strict Origin allowlist matching base URL | Mismatched Origin closes with WebSocket code `4403` before `accept()` | PASS |
| **Session Authentication** | `__Host-` session cookie verification | Unauthenticated `/ws` closes `4401`; unauthenticated `/sse` returns `401` | PASS |
| **Connection & Channel Caps** | Max 16 conns/principal; max 64 channels/conn | Enforced (`4429`/`429` on conns; `4413`/`422`/`CHANNEL_LIMIT_EXCEEDED` on channels) | PASS |
| **Frame Size Safeguard** | Max 4096 bytes inbound frame limit | Exceeding 4096 bytes closes socket with `4413 FRAME_TOO_LARGE` | PASS |
| **Subscription Anti-Enumeration** | Identical `NOT_FOUND` on unreadable channels | Nonexistent and unreadable targets both return `subscribe_error` (`NOT_FOUND`) | PASS |
| **Delivery-Time RLS Filter** | Batched `effective_resource_access` query | Verifies `(allow_mask & 1) == 1 and (deny_mask & 1) == 0` at delivery time | PASS |
| **Mid-Stream ACL Revocation** | `channel.revoked` with zero payload leakage | Emits `{"type": "channel.revoked", "channel": "..."}` with zero payload data | PASS |
| **Silent Project Omission** | Restricted issues omitted from project stream | Project subscribers never receive events for restricted issues without access | PASS |
| **Anti-Harvesting Replay** | Replayed events pass current RLS check | Replays up to 500 events within 15m; checks current VIEW access per event | PASS |
| **Resync Fallback Protocol** | `resync_required` when outside replay window | Emits `resync_required` when `last_seq` predates retention or exceeds 500 missed | PASS |
| **Heartbeat & Fast Revocation** | 25s ping; <=250ms close on revocation | 25s keepalive; security events close sockets in <=250ms with `4401` | PASS |
| **Graceful Server Draining** | `server.draining` frame with close `1001` | Lifespan shutdown broadcasts `server.draining` and drains within 3s ceiling | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 50/50 passed in 5.45s; 96.28% branch+line coverage across target modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (192 files), Mypy strict clean (190 files) | PASS |

---

### 2. Forensic Architectural Analysis

1. **Handshake & Session Authentication Hardening (Spec S2.3, S3.4):**
   - In `kanban/api/ws.py`, `is_origin_allowed()` strictly inspects the `Origin` header against `settings.public_base_url` and standalone cleartext hosts (`localhost`, `127.0.0.1`, `testserver`). Any mismatched origin triggers `websocket.close(code=4403, reason="ORIGIN_MISMATCH")` prior to calling `websocket.accept()`.
   - Session authentication resolves the `__Host-` session cookie via `SessionService.resolve_session()` within an anonymous database session. Missing cookies, expired tokens, or unverified MFA sessions immediately close the socket with code `4401 UNAUTHENTICATED` or return HTTP `401 UNAUTHENTICATED` on `/sse`.
   - Inbound WebSocket frames are constrained to `MAX_INBOUND_FRAME_BYTES = 4096`. Oversized frames immediately terminate the connection with code `4413 FRAME_TOO_LARGE`.

2. **Connection Hub & Anti-Enumeration Channel Subscriptions (Spec S3.4):**
   - In `kanban/realtime/hub.py`, `RealtimeHub` manages concurrent connections with an atomic `asyncio.Lock()`.
   - Concurrency limits restrict each `(workspace_id, principal_id)` to at most 16 concurrent connections (`MAX_CONNECTIONS_PER_PRINCIPAL = 16`). Additional connection attempts fail with code `4429` on WebSocket or HTTP `429` on SSE.
   - Channel subscriptions are capped at 64 channels per connection (`MAX_CHANNELS_PER_CONNECTION = 64`). Exceeding this cap emits `CHANNEL_LIMIT_EXCEEDED`.
   - In `check_channel_viewable()`, channel subscriptions (`workspace:{uuid}`, `project:{uuid}`, `issue:{uuid}`, `doc:{uuid}`) evaluate `VIEW` capability in `effective_resource_access`. Nonexistent objects and unreadable objects both emit identical `{"type": "subscribe_error", "code": "NOT_FOUND"}`, preventing any cross-tenant existence enumeration.

3. **Per-Event Delivery-Time RLS Filtering (Spec S3.3, S3.4):**
   - Subscription state at connect time is never trusted alone. In `kanban/realtime/rls_filter.py`, before any outbox event is dispatched to candidate connections, `authorize_event_recipients()` executes a single batched query against `effective_resource_access` for all candidate principals:
     `SELECT principal_id, allow_mask, deny_mask FROM effective_resource_access WHERE object_id = :obj_id AND workspace_id = :ws_id AND principal_id = ANY(CAST(:candidate_ids AS uuid[]))`
   - Evaluates `(allow_mask & 1) == 1 and (deny_mask & 1) == 0`.
   - **Mid-Session ACL Revocation Defenses:**
     * If a principal subscribed directly to `issue:{id}` or `doc:{id}` has lost `VIEW` capability (e.g. an explicit `DENY VIEW` was inserted), the hub removes the channel from the connection's subscriptions and emits `{"type": "channel.revoked", "channel": "..."}` with strictly ZERO event payload fields.
     * If a principal is subscribed to `project:{id}` and an event targets a restricted issue inside that project, delivery to that connection is silently omitted without dropping the project subscription.
   - Out-of-boundary actor metadata is sanitized via `redact_event_payload()`, replacing actor objects with `{"redacted": true, "label": "1 External Collaborator"}` and stripping sensitive identifiers.

4. **Monotonic Replay & Anti-Harvesting Protocol (Spec S2.3):**
   - In `kanban/realtime/replay.py`, `OutboxReplayer` queries `outbox_events` for `seq > last_seq` within a 15-minute retention window (`created_at >= clock_timestamp() - interval '15 minutes'`) and a ceiling of 500 events (`DEFAULT_MAX_REPLAY_EVENTS = 500`).
   - If `last_seq` predates the earliest retained event or the missed count exceeds 500 events, the replayer returns `resync_required: true`, prompting the client to invalidate its cache.
   - **Anti-Harvesting Invariant:** Every historical candidate event retrieved during replay is evaluated through `authorize_event_recipients()` using the caller's *current* permissions. Events for objects where the user has since lost `VIEW` capability are omitted from the replay stream, preventing retrospective data harvesting.

5. **Fast Session Revocation & Lifespan Draining:**
   - Active connections are kept alive via 25-second server pings (`WebSocketConnection`) and `: heartbeat\n\n` comments (`SSEConnection`).
   - `_session_recheck_loop()` validates session tokens against `SessionService` every 60 seconds, closing revoked sessions with code `4401`.
   - Security broker events (`security.session_revoked`, `security.principal_deactivated`) immediately match active connections and disconnect them within `<= 250ms`.
   - In `kanban/app.py:lifespan`, server shutdown triggers `hub.drain(timeout_seconds=3.0)`, broadcasting `{"type": "server.draining", "retry_ms": 1000}` and closing sockets with code `1001` (`WS_CLOSE_DRAINING`).

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have completed the backend architecture and API Specialist Gate audit for `KANBA-77`. All streaming protocols, timing safeguards, delivery-time RLS evaluations, mid-session revocation cutoffs, anti-harvesting replays, and connection caps are satisfied.

Verdict: APPROVED

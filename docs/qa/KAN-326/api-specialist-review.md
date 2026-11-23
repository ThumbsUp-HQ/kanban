# API Specialist Review: KAN-326

## Audit Metadata
- Ticket ID: KAN-326 ([KB-SEC-MODEL-03])
- Title: Propagate MCP Read-Taint High-Water Mark to Realtime WebSocket Subscriptions
- Reviewer: backend-architect (API Specialist)
- Date: 2026-11-23
- Status: APPROVED

---

## 1. Scope & Objective
Ticket KAN-326 closes an exfiltration vector where an autonomous agent or MCP client could subscribe to confidential real-time channels (e.g., `project:<UUID>`, `issue:<UUID>`, `doc:<UUID>`) via WebSocket without having that read exposure recorded in `mcp_read_taint`. Subsequently, the agent could exfiltrate confidential content by writing to broader-scope projects without triggering `409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.

---

## 2. API & Architecture Verification
1. **Extracted `record_read_taint` Core Function:**
   - In `kanban/security/read_taint.py`: extracted reusable `record_read_taint` handling both session keys and credential token hashes.
   - Enforces monotonic TTLs: `SESSION_TAINT_TTL_SECONDS = 3600` and `CREDENTIAL_TAINT_TTL_HOURS = 8`.
   - Propagates `contains_untrusted_content` and `untrusted_source_object_id` when subscribing to flagged issues or docs.
2. **WebSocket Handshake Session Ingestion:**
   - In `kanban/api/ws.py`: extracted `x-kb-mcp-session` header or `mcp_session` query parameter into `conn.mcp_session_id`.
3. **Subscription Channel Taint Resolution:**
   - In `kanban/realtime/hub.py`: `handle_subscribe` delegates to `_propagate_subscription_read_taint`.
   - Subscribing to `project:<UUID>` records read-taint for that project ID.
   - Subscribing to `issue:<UUID>` resolves the parent `project_id` and records project read-taint.
   - Subscribing to `doc:<UUID>` resolves the parent `project_id` and records project read-taint.
   - When channel objects contain untrusted content (`is_untrusted_content = True`), read-taint marks `contains_untrusted_content = True`.
4. **Monotonicity & Exfiltration Canary:**
   - Monotonic high-water mark: unsubscribing from a channel does NOT clear recorded taints in `mcp_read_taint`.
   - Exfiltration canary: subscribing to a confidential project channel blocks subsequent MCP tool writes to broader projects with `409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.

---

## 3. Test Coverage & Quality Gate
- `kanban/tests/realtime/test_ws_read_taint.py`: 6 comprehensive integration tests validating project subscriptions, issue subscriptions, doc subscriptions, MCP session header propagation, unsubscribe monotonicity, and cross-scope write blocking.
- Clean RLS integration with zero race conditions.
- Strict McCabe complexity <= 10 and branches <= 12 across all touched methods.

---

## 4. Conclusion
The WebSocket subscription read-taint propagation architecture is sound, eliminates the exfiltration gap, and strictly aligns with platform security invariants. Approved for ticket closure.

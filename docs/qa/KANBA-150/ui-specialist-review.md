# UI & UX Specialist Review: KANBA-150

**Auditor:** UI Specialist (`ux-architect` / `ui-designer`)  
**Date:** 2026-11-15  
**STATUS: APPROVED**

---

## 1. Scope & UX Contract Review
The user interface ergonomics, realtime state contracts, and board transition lifecycle hooks for asynchronous agent transition gates have been reviewed against the requirements in `docs/tickets/KB-P5-18.md` and advisory guidance.

### A. HTTP 202 Accepted & Board Card Hold State
- On drag-and-drop or manual state transition encountering an async agent gate, the API responds with HTTP 202 Accepted:
  `{status: "pending_agent_gate", execution_id, active_agent, hook_name, harness_kind, state}`.
- **UX Impact:**
  - The card remains anchored in its current column (`from_state`), preventing premature or jarring column movement.
  - A pending hold overlay with a `⏳🤖` animated indicator and `active_agent` badge is displayed on the board card.
  - Conflicting user transitions on that card are disabled via `TRANSITION_PENDING` (409) guards.

### B. Countdown & Progress Bar Precision
- `pending_gate` serializer field:
  - Exposes `{execution_id, hook_name, agent_slug, harness_label, started_at, deadline_at}`.
  - Supplying both `started_at` and `deadline_at` ISO-8601 timestamps enables frontend components to render an accurate countdown progress bar without client-clock drift.

### C. Compact Header Badges & Verdict Chips
- `latest_gate_verdict` serializer field:
  - Exposes `{decision, hook_name, completed_at, latency_ms, verdict_sha256}`.
  - Enables compact header chips on the ticket detail screen (e.g., "✅ Approved in 1.4s" or "🛑 Vetoed by QA Gate").

### D. Realtime WebSocket Outbox Events (`workflow.gate.*`)
- The outbox event stream broadcasts five discrete event types:
  - `workflow.gate.pending`: Triggers the pending hold state on all connected client boards.
  - `workflow.gate.approved`: Animates the card smoothly into `to_state` column with a green approval flash.
  - `workflow.gate.rejected`: Snaps the card back to `from_state` with a subtle shake animation and displays the scrubbed `reason_preview` in a dismissible toast notification.
  - `workflow.gate.timed_out`: Snaps the card back to `from_state` with a timeout badge.
  - `workflow.gate.cancelled`: Clears the hold overlay immediately when an operator cancels the pending transition via `DELETE /api/v1/transitions/{execution_id}`.
- **Payload Safety:**
  - `reason_preview` is strictly bounded (first 2 lines, <= 280 characters, secret-scrubbed).
  - Raw `verdict_json` is completely excluded from WebSocket frames, preventing DOM bloating and client memory exhaustion.

---

## 2. Verification Summary
- **Contract Alignment**: Full alignment with board drag-and-drop hold requirements, countdown progress bar timing, and snap-back toast notifications.
- **Ergonomics**: Non-blocking asynchronous interaction pattern eliminates UI freezing during LLM or CLI gate evaluation.
- **Typography Standard**: Clean ASCII hyphens `-` only (0 non-ASCII dashes).

STATUS: APPROVED

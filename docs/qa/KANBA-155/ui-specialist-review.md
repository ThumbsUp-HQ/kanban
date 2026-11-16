# UI & UX Specialist Review: KANBA-155

**Auditor:** UI Specialist (`ux-architect` / `ui-designer`)  
**Date:** 2026-11-15  
**STATUS: APPROVED**

---

## 1. Executive Summary & Scope
Ticket `KANBA-155` (`KB-P5-22a`) establishes the backend infrastructure for the **Remote Runner Registry, mTLS Enrollment Tokens, WSS Control Hub, and `/mcp/admin` Tool 9 Runner Actions**.

While this ticket focuses on backend DDL, cryptographic PKI, WebSocket dispatch, and MCP administrative tooling without new client-side React UI components in this phase, it defines the REST endpoints, DTO contracts, status models, and error responses that will be rendered by the upcoming Remote Runner Management and Pool Monitoring settings interfaces.

---

## 2. DTO Ergonomics & Frontend Consumption Audit

### A. Enrollment Tokens & Safe Credential Handoff
- **Single-Use Plaintext Disclosure:**
  - `POST /api/v1/admin/agent-runners/enrollment-tokens` mints tokens (`kb_rnr_enroll_<token>`) and returns the plaintext token **once** in the creation response:
    `{ "id": "...", "enrollment_token": "kb_rnr_enroll_...", "pool_slug": "...", "expires_at": "...", "created_at": "..." }`.
  - The plaintext token is never persisted in storage (only its `SHA-256` hash is stored) and is never returned in subsequent GET or list endpoints. This allows UI modals to present a "Copy Token Now" one-time dialogue with an explicit ephemeral warning.
  - ISO-8601 timestamps (`expires_at`) allow UI timers to show remaining validity countdowns (default 300s TTL).

### B. Remote Runner Models & Table Presentation
- **Clean Field Normalization:**
  - `RemoteRunnerResponse` exposes normalized, presentation-ready fields: `id`, `pool_slug`, `hostname`, `status` (`online`, `offline`, `revoked`), `capabilities`, `cert_fingerprint_sha256`, `cert_expires_at`, `last_heartbeat_at`, `revoked_at`, and `created_at`.
  - Exposing the truncated `cert_fingerprint_sha256` (hex-encoded) enables clean table chips (e.g., `e3b0c442...`) and certificate inspector popovers without bloating list views with multiline PEM certificates.
  - The runner `status` enum (`online`, `offline`, `revoked`) maps directly to semantic status badges (green, grey, red) in UI design systems.

### C. Error Feedback & Operator Modal Guidance
- **Granular Error Codes:**
  - The API and hub emit distinct, machine-readable error codes:
    - `401 ENROLLMENT_TOKEN_INVALID`: informs operator that the token has already been consumed or expired.
    - `422 CSR_INVALID`: indicates malformed CSR or insecure key parameters.
    - `403 AAL2_REQUIRED`: enables the frontend to trigger AAL2 step-up authentication.
    - `REMOTE_RUNNER_POOL_OFFLINE`: provides actionable guidance when no active runners exist in the requested pool.
    - `REMOTE_RUNNER_DISCONNECTED`: reports connection drop cleanly.
    - `REMOTE_RUNNER_REVOKED`: reflects administrative termination.

---

## 3. Administrative MCP Tool 9 UX & Safety Friction
- **LOD (Level of Detail) Ergonomics:**
  - `list_remote_runners` supports `summary`, `standard`, and `full` tiers, keeping agent token consumption lean when querying pool status.
- **Two-Stage Destructive Confirmation:**
  - Invoking `revoke_remote_runner` without `confirm: true` returns a structured `confirmation_required` response with a detailed warning and an ephemeral `confirmation_token`, preventing accidental disconnection of production runners.

---

## 4. Final Verdict
The DTOs, security guarantees, error semantics, and MCP tool interactions are well-structured, secure, and provide an excellent foundation for frontend consumption.

STATUS: APPROVED

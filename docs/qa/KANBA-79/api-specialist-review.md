# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-79 (KB-P5-08)

- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist)
- Worktree: `/tmp/kb-wt-KANBA-79` on branch `feat/KANBA-79`
- Ticket: `KANBA-79` (`KB-P5-08`: SparkleCompletionPlugin: S9.1 state machine, caret portal, Decoration.widget ghost text, 320ms debounce, Tab/click accept)
- Target File: `docs/qa/KANBA-79/api-specialist-review.md`

---

### 1. Architectural Scope & API Contract Verification

This ticket implements the client-side ProseMirror inline completion engine (`src/editor/sparkle/*`) consuming the Sparkle FIM SSE backend (`KB-P5-07`, `S9.1`, `S9.3`, `S15.2`). The client interface has been forensically audited against the backend contract and security requirements:

1. **Endpoint & Wire Contract Compliance:**
   - **Method & Route:** `POST /api/v1/sparkle/complete`.
   - **Headers:** `Content-Type: application/json`, `Accept: text/event-stream`, and conditional `X-CSRF-Token`.
   - **Credentials:** Explicit `credentials: "same-origin"`, preventing credential leakage across origins while transmitting session cookies to the local API.
   - **Request Payload:** Strictly formatted JSON matching `SparkleRequest` (`project_id: string`, `object_id: string | null`, `surface: EditorSurfaceKind`, `prefix: string`, `suffix: string`, `client_request_id: string`).
   - **Client Request ID:** Standard UUIDv4 generated per request (`crypto.randomUUID()` with fallback), enabling end-to-end trace correlation in API server access logs without logging prompt prefixes or suffixes.

2. **Native SSE Streaming Parser & Framing:**
   - **Zero-Dependency Hand-Written Parser:** Implemented in `sparkleClient.ts` without introducing external SSE libraries. Normalizes `\r\n` and `\r` line breaks, slices on double newline `\n\n` boundaries, and ignores SSE comment lines (`:`).
   - **Strict Event Allowlist:** Explicitly permits only `event: completion` and `event: done`. Unknown event names trigger an immediate rejection (`throw new Error("Unknown SSE event received: ...")`), transitioning the state machine back to `IDLE`.
   - **Stream Cap & DoS Protection:** Strictly caps streaming response payload to 8 KiB (8,192 bytes) across `ReadableStream` chunks and non-stream `response.text()` fallback. When `totalBytes > maxBytes`, the reader is immediately canceled (`reader.cancel("Oversize stream")`) and rejected, preventing buffer exhaustion.
   - **Timeout & Cascading Cancellation:** Employs a 200ms client deadline (150ms budget + 50ms network grace) enforced via `AbortController`. In-flight network requests are cleanly aborted on user typing, selection expansion, cursor movement, or component unmount.

3. **Security Invariants & Untrusted Content Handling:**
   - **Zero DOM Injection:** Completion text from LLM providers is treated as untrusted text. In `createGhostDecoration`, text is rendered solely via `document.createElement('span')` with `span.textContent = suggestion` (zero `innerHTML` or `dangerouslySetInnerHTML`). Verified with test case `sparkle_stream_html_text.json` returning literal `<b>x</b>` with zero `<b>` DOM elements.
   - **CSRF Token Resolution:** Resolves CSRF token from either `__Host-kb_csrf` / `kb_csrf` cookie or `<meta name="csrf-token">` tag, preventing unauthorized cross-site request forgery attacks.
   - **History Closure:** Executes `closeHistory(tr)` immediately prior to inserting accepted completion text, guaranteeing that a single undo step (`Cmd/Ctrl+Z`) reverts exactly the completion without corrupting preceding user input.
   - **Fault States & Anti-Leakage:** Handles all backend status outcomes (`empty`, `timeout`, `secret_scrubbed`, `unavailable`, `budget`) and network failures (HTTP 500, fetch rejection) by silently resetting to `IDLE` with zero phantom ghost text or floating badges.

4. **S9.1 Pure State Machine Architecture:**
   - Reducer `sparkleReducer` in `sparkleMachine.ts` is completely decoupled from DOM and timers, operating across 6 formal states: `IDLE`, `TYPING`, `FETCHING`, `READY_BLINKING`, `ACCEPTED`, `DISMISSED`.
   - 25 table test cases verify every transition edge and invalid event non-edge.

---

### 2. Independent Verification & Test Execution

- **Vitest Unit Suite:** 280 / 280 tests passed cleanly in 5.68s.
  - `src/editor/sparkle/sparkleMachine.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines.
  - `src/editor/sparkle/sparkleClient.ts`: 100% Statements, 97.5% Branches, 100% Functions, 100% Lines.
  - `src/editor/sparkle/SparkleCompletionPlugin.ts`: 98.76% Statements, 94.07% Branches, 100% Functions, 100% Lines.
  - `src/editor/sparkle/SparkleOverlayPortal.tsx`: 97.67% Statements, 94.11% Branches, 100% Functions, 100% Lines.
  - Overall `src/editor/sparkle/**` combined coverage: **99.12% Statements, 96.28% Branches, 100% Functions, 100% Lines** (exceeds the 95% project threshold).
- **Playwright E2E Suite:** 6 / 6 tests passed across desktop, tablet, and mobile viewports with measured Cumulative Layout Shift (`CLS = 0`).
- **Static Quality & Build Gates:**
  - TypeScript `tsc -b --noEmit`: 0 errors.
  - ESLint `eslint . --max-warnings 0`: 0 warnings, 0 errors.
  - Production build `vite build`: Clean exit 0.
  - Supply Chain & License: `SUMMARY python=98 node=1 violations=0`, zero new dependencies in `package.json`.
  - Typography: 0 non-ASCII Unicode dashes (`scripts/check_no_dashes.py` passed).

---

### 3. Verdict

The implementation in `/tmp/kb-wt-KANBA-79` strictly satisfies all backend/API contract specifications, security invariants, streaming safety limits, and test coverage requirements for `KB-P5-08`.

APPROVED

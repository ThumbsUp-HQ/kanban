# API Specialist Forensic QA Review: KANBA-227

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-227 (Live Client WebSocket Subscriptions, Plain-HTTP/HTTPS Clipboard Utility, and Board Card Semantic Anchors)
Branch: feat/w3-rt (integrated into main at commit 980ef39 and e718b99)
Review Date: 2026-11-18

## 1. Architectural & Engineering Assessment

### 1.1 WebSocket Realtime Endpoint & Subscription Protocol (kanban/app.py, kanban/web/src/api/realtime.ts)
- Dual endpoint exposure: `@app.websocket("/api/v1/ws")` mounted alongside legacy `@app.websocket("/ws")` in `kanban/app.py`, ensuring backwards compatibility and canonical API path symmetry.
- Realtime Client Architecture:
  - `RealtimeClient` supports configurable WebSocket paths (`wsPath: '/api/v1/ws'`), transparent reconnection with jittered exponential backoff, and SSE fallback (`/api/v1/sse`).
  - Active event channels (`workspace:<id>`, `project:<id>`, `issue:<id>`) invalidate target TanStack Query keys in under 1 second without full page reloads (`F5`).
  - Structured event types mapped: `issue.created`, `issue.updated`, `issue.transitioned`, `comment.created`, `sticky.created`, `sticky.updated`, `sticky.promoted`, `resync_required`.
  - Added deterministic testability hooks (`simulateEvent`, `simulateFrame`, `resetForTesting`) for offline automated test suites without live network reliance.

### 1.2 Universal Clipboard Utility (kanban/web/src/utils/clipboard.ts)
- Dual-mode clipboard strategy:
  - Secure contexts (`isSecureContext` on HTTPS and localhost) utilize `navigator.clipboard.writeText`.
  - Insecure or restricted contexts (plain HTTP `http://<LAN-IP>:8921` deployments) gracefully fall back to hidden offscreen `<textarea>` and `document.execCommand('copy')`.
- Returns structured boolean status and never throws unhandled exceptions.
- React hook `useClipboard` provides automatic timeout cleanup (default 2000ms), preventing timer leaks.

### 1.3 Semantic Navigation & Route Integrity (kanban/web/src/features/board/BoardCard.tsx)
- Board cards render canonical `<a href="/w/:workspaceSlug/p/:projectKey/issues/:issueKey">` anchor elements.
- Interaction contract preserved:
  - Standard left-click opens the fast `?peek=KAN-N` Drawer.
  - Middle-click, `Ctrl+Click`, `Cmd+Click`, or right-click -> "Open link in new tab" opens the canonical issue route.
- Preserves keyboard accessibility (`Enter` and `Space`) and WAI-ARIA roles.

## 2. Test Verification & Code Quality

- Frontend Vitest Suites: 2189 unit tests pass across 183 suites with 95.02% branch coverage.
- Python Backend Tests: 2910 passed, 96.11% coverage.
- Architecture & Migration: Single-head migration chain verified; STRIDE security suite 65/65 tests passed.
- Static Analysis: `ruff check` (0 errors), `mypy` (0 errors), `pnpm typecheck` (0 errors), `pnpm lint` (0 errors).
- Plain ASCII Check: `scripts.check_no_dashes --all` passed (0 em/en-dashes).

## 3. Wave 3 API Drift Audit (KANBA-226 and KANBA-213)

- `KANBA-226` (A11y, ARIA landmarks, roving tabindex, contrast): Pure frontend change; 0 backend API endpoints modified, 0 schema changes, 0 API drift.
- `KANBA-213` (Theme tokens, contrast, mobile layout, CLS reservation, branded 404): Pure frontend change; 0 backend API endpoints modified, 0 schema changes, 0 API drift.

## 4. Specialist Verdict

The realtime client, dual WebSocket routing, universal clipboard helper, and board card semantic navigation satisfy all architectural, reliability, and security invariants.
`STATUS: APPROVED`

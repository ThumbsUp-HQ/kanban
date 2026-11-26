# API Specialist Review: KAN-432 (Fix HTTP 202 Pending Gate Indicator, Veto Snap-Back, Lane New-Item State Default, and /manifest.json CSP Error)

**Ticket:** KAN-432 (`[BUG][BOARD-UI]`)  
**Auditor:** `api-spec` (Backend Architect & API Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan432-ce28b9dd`  
**Target Branch:** `fix/KAN-432-board-gate-snapback-and-csp`  
**Target Commit:** `e4eecb2c` (base: `1bbc9981`)  

---

## 1. Executive Summary & Verdict

This API & Security Specialist Review evaluates the fixes implemented under **KAN-432** resolving four interrelated board lifecycle, workflow gate, and security header defects:
1. **HTTP 202 Pending Gate Indicator & Asynchronous Veto Snap-Back**:
   When an issue transition triggers an asynchronous workflow gate (e.g. `agent_interceptor`), `POST /api/v1/issues/{id}/move` returns HTTP 202 Accepted. Previously, the board lacked structured gate execution metadata in the response and on WebSocket events, resulting in silent card placement without gate progress indicators, and missing automated rollback (snap-back) when a gate rejected the transition.
2. **Lane New-Item State Default**:
   Clicking the `+` action button in a specific board column (e.g. "In Progress" or "In Review") previously lost or ignored `defaultStateId`, causing the issue creation modal to erroneously default to the first column (e.g. Backlog).
3. **CSP `/manifest.json` Directive Violation**:
   The `Content-Security-Policy` header in `kanban/security/headers.py` omitted `manifest-src`, resulting in browser console CSP violations when loading the PWA web application manifest (`/manifest.json`).

All defects have been remediated with strict protocol rigor, complete schema parity, robust websocket synchronization, and zero-mock automated tests.

**Verdict: APPROVED.** Security headers, API schemas, and board gate state synchronization are verified and fully compliant.

---

## 2. Technical & Protocol Architecture Audit

### 2.1 Async Gate Lifecycle & WebSocket Metadata Parity (`issue_move.py`, `async_gate.py`, `BoardView.tsx`)
- **Backend Schema & Service Enhancements (`kanban/api/v1/schemas/issue_move.py`, `kanban/services/issue_move.py`)**:
  - Extended `IssueMoveResponse` with explicit gate tracking fields:
    * `gate_status: str | None` ("pending" when an async gate evaluation is triggered)
    * `execution_id: uuid.UUID | None`
    * `hook_name: str | None`
    * `from_state_id: uuid.UUID | None`
    * `to_state_id: uuid.UUID | None`
  - When `outcome.gate_hold` is active, `move_issue` populates these fields directly in the HTTP 202 response.
- **WebSocket Event Traceability (`kanban/workflows/async_gate.py`)**:
  - `AgentGateDispatcher` and `GateCoordinator` now broadcast `from_state_id` and `to_state_id` alongside human-readable state names in `gate.started`, `gate.completed`, and `gate.failed` WebSocket payloads.
- **Client Real-Time Synchronization & Snap-Back (`useGateRealtimeSync.ts`, `BoardView.tsx`)**:
  - `BoardView` inspects HTTP 202 responses and attaches active gate indicators (`gate_status === 'pending'`) to the card.
  - When `useGateRealtimeSync` receives a terminal `gate.completed` event with `decision === 'reject'` (or `veto`), `BoardView` automatically triggers a smooth veto snap-back, returning the card to its original `from_state_id` column while rendering the rejection reason toast.

### 2.2 Lane New-Item State Default (`QuickCreateIssueModal.tsx`, `viewRegistry.tsx`)
- Corrected state resolution so the active column's `defaultStateId` is explicitly forwarded to `QuickCreateIssueModal`. Newly created issues immediately materialize in the clicked lane rather than defaulting to Backlog.

### 2.3 Security Headers & CSP Manifest Policy (`kanban/security/headers.py`)
- Added `manifest-src 'self';` to `CSP_POLICY`.
- Verified that modern browsers and PWAs fetch `/manifest.json` without CSP violations while maintaining strict `'none'` defaults on unlisted directives.

---

## 3. Quality Gates & Verification

### 3.1 Unit Testing & Coverage
- **Backend Pytest**:
  - 285 tests passed in 41.76s (0 failures, 0 warnings).
  - `kanban/security/headers.py`: **98%** coverage.
- **Frontend Vitest**:
  - 59 tests passed across 4 test suites in 2.78s (0 `act(...)` warnings).
  - Overall branch coverage: **95.85%**.
  - All touched files exceed 95% branch coverage:
    * `BoardColumn.tsx`: **100.00%**
    * `useGateRealtimeSync.ts`: **95.61%**
    * `BoardView.tsx`: **95.18%**

### 3.2 Static Linters, Build & Security
- **Ruff:** Clean (0 errors).
- **Mypy:** Clean across 4 source files (0 type errors).
- **TypeScript Typecheck:** Clean (0 errors).
- **ESLint:** Clean (0 warnings on touched files).
- **Vite Build:** Clean, completed in 1.25s.
- **Unicode Dash Audit:** 0 Unicode em/en-dashes (`python3 scripts/check_no_dashes.py`).
- **Browser CSP & Console Audit:** 0 CSP directive violations detected across all routes (`/setup`, `/login`, `/manifest.json`, `/projects/KAN/issues?layout=board`). Zero-mock evidence captured against live FastAPI + PostgreSQL 16 server on `127.0.0.1:18432`.

---

## 4. Final Verdict

- **API Protocol & Schema Design:** APPROVED
- **WebSocket State Synchronization:** APPROVED
- **Content Security Policy (CSP):** APPROVED
- **Test Coverage & Quality Standards:** APPROVED

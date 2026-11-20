# API Specialist Review: KAN-35 (KB-REALTIME-REFRESH)

- Ticket: KAN-35
- Title: [KB-REALTIME-REFRESH] Fix End-to-End Realtime Board & View Refresh for Agent/MCP & REST Ticket Mutations (5 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-35`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-35 on `main` (commit `23ae056d`), incorporating concrete evidence from zero-mock live full-stack verification (`docs/qa/KAN-35/live-fullstack-proof.txt`).

The ticket resolves five primary realtime and cache synchronization problems:
1. Transactional Outbox Event Capture: Capturing entity mutations (`issue.created`, `issue.updated`, `issue.transitioned`, `issue.moved`, `comment.created`) within the primary transaction via `outbox_events` table under PostgreSQL `FORCE ROW LEVEL SECURITY`.
2. Realtime Relay & Lifespan Management: Establishing `RealtimeBroker`, `RealtimeHub`, and `OutboxRelay` background workers inside FastAPI lifespan, streaming events over WebSocket (`/ws`) and Server-Sent Events (`/sse`).
3. Delivery-Time Row-Level Security: Enforcing GUC-isolated candidate delivery authorization (`kanban.actor_id`), anti-harvesting identity parity, and `SECURITY DEFINER` replay routines via migration `p4_22_outbox_replay_reader`.
4. Channel Normalization & Subscription Routing: Normalizing human-readable project keys (`project:KAN`) and UUIDs (`project:<uuid>`) across WebSocket and SSE listeners.
5. Reactive Frontend Query Invalidation & Optimistic Move Integrity: Upgrading TanStack Query cache management so remote mutations trigger surgical cache updates without full page reloads, while optimistic card moves preserve full `IssueSummary` properties without throwing `TypeError` exceptions.

During live-QA round 1 validation, rapid optimistic card movement stripped issue state sub-objects, causing subsequent accesses to `issue.state.name` or remote transitions to crash with `TypeError: Cannot read properties of undefined (reading 'name')`. The remediation in `fix/KAN-35-rc1` (now merged to `main` at `23ae056d`) resolved this by preserving the full issue reference in `applyOptimisticMove`, synchronously populating target state metadata (`id`, `name`, `group`, `color_hex`), and hardening `viewRegistry.tsx` state readers with `projectStates` fallbacks.

All API contracts, security invariants, transaction boundaries, frontend cache synchronization routines, and test coverage requirements are verified and approved:
- Root Cause Resolved: Full issue properties preserved during optimistic card moves; zero `TypeError` exceptions observed across rapid keyboard and drag-and-drop operations.
- Zero-Reload Realtime Sync: Verified live on container `kanban-liveqa-2` (`http://localhost:18952`) on `main` at commit `23ae056d`. Agent MCP mutations (`create_ticket`, `transition_ticket`, `add_comment`) rendered live across BoardView, ListView, and IssueSurface drawer with zero page reloads (`bootId` stable, `docLoads=2`).
- RLS Isolation & Replay Security: Non-admin `@member` denied subscription to `project:PRIV` with uniform `NOT_FOUND` error; zero private frames leaked over `/ws`; SSE `Last-Event-ID` replay via `p4_22_outbox_replay_reader` delivered authorized KAN events while completely withholding PRIV events.
- Zero External Dependencies: Zero new runtime packages added (`Apache-2.0` compliant).
- Unidirectional Layering: Architecture satisfies `import-linter` contracts (`agent -> mcp -> kanban -> database`).
- Style & Quality: Clean across static analyzers, zero console errors, zero CSP violations, and strict zero em-dashes and en-dashes.

---

## 2. Detailed Contract & Security Verification

### 2.1 Optimistic Cache Integrity & State Preservation (`boardApi.ts`)
- Client Source: `kanban/web/src/features/board/boardApi.ts` (`applyOptimisticMove`)
- Verification:
  - Signature: `applyOptimisticMove<T>(cache, params, availableStates)`
  - Preserves full item references (`...item`) and updates both `state_id` and the complete `state` sub-object (`id`, `name`, `group`, `color_hex`).
  - Supports both flat array caches (`T[]`) and envelope objects (`{ items: T[] }`).
  - Executes synchronously within the `< 12ms` UI responsiveness budget.

### 2.2 BoardView & View Registry Integration (`BoardView.tsx` & `viewRegistry.tsx`)
- Client Source: `kanban/web/src/features/board/BoardView.tsx` and `kanban/web/src/features/views/viewRegistry.tsx`
- Verification:
  - `BoardView.tsx` passes available workflow states into `applyOptimisticMove(..., states)`.
  - `viewRegistry.tsx` hardens `IssuesWorkspaceRoute` by resolving missing state metadata against `projectStates` whenever `state_id` is present, guaranteeing that accesses to `state.name` and `state.group` never crash even if raw cache entries contain partial state data.

### 2.3 Live Full-Stack Proof Audit (`live-fullstack-proof.txt` - R2)
- Environment: Container `kanban-liveqa-2` (`http://localhost:18952`), commit `23ae056d`.
- Audit Results:
  - Setup: Created non-admin `@member` (`WORKSPACE_MEMBER`) on project `KAN`. Created private project `PRIV` with explicit `DENY` (`effective_capabilities: []`). Minted scoped `/mcp/agent` key for `@member`.
  - Browser Realtime Baseline: Logged into board view at `/projects/KAN/issues?layout=board`. WebSocket connected to `/ws` and subscribed to `project:KAN`. Baseline document boot ID: `dvp2puu9vz6`, `docLoads=2`.
  - Realtime Ticket Creation: MCP call `create_ticket` KAN-8 in Backlog. Browser WS frame received on channel `project:KAN` (`topic: "issue.created"`). Rendered live on board with zero page reloads.
  - Critical Keyboard Alt+ArrowRight Optimistic Move: Focused KAN-8 card in Backlog and pressed `Alt+ArrowRight` to move to Todo. `applyOptimisticMove` updated shared cache synchronously. REST `POST /api/v1/issues/KAN-8/move` returned HTTP 200 OK. WS frames received for `issue.transitioned` and `issue.moved`. Visible in Todo column immediately. Console errors: 0, page errors: 0. Zero `TypeError: Cannot read properties of undefined (reading 'name')` crash!
  - Realtime MCP Transition: MCP call `transition_ticket` KAN-8 -> "In Progress". Browser WS frame received (`topic: "issue.transitioned"`). BoardView moved KAN-8 to In Progress column live with zero page reloads and zero UI freezes.
  - List View Realtime Sync: Switched to List View (`?layout=list`) via SPA routing. MCP call `create_ticket` KAN-9. Browser WS frame received (`topic: "issue.created"`). Rendered live in ListView row with zero page reloads.
  - Drawer Realtime Comment Sync: Opened IssueSurface drawer for KAN-8. MCP call `add_comment` on KAN-8. WS frame received on `issue:KAN-8` (`topic: "comment.created"`). Rendered live in drawer with zero page reloads.
  - Delivery-Time RLS Isolation: Subscribing to `project:PRIV` rejected with anti-harvesting `code: "NOT_FOUND"` (both for slug and UUID). While `@member` was connected, `@admin` created and transitioned `PRIV-1`; exactly 0 frames leaked to `@member`. When `@admin` created `KAN-10`, frame received by `@member`.
  - SSE Last-Event-ID Replay: `GET /sse` with `Last-Event-ID: 1` replayed authorized KAN events while completely withholding PRIV events (event IDs 17, 18, 26 withheld). Zero PRIV events leaked.

### 2.4 Test Suites and Coverage
- Backend Pytest Suite:
  - 67/67 tests passed in 34.70s across `kanban/tests/realtime/` with 97% statement coverage (hub 97%, broker 100%, sse 97%, replay 100%, rls_filter 95%, realtime_outbox 97%).
  - 1/1 migration test passed in `database/tests/migrations/test_p4_22_outbox_replay_reader_migration.py`.
- Frontend Vitest Suite:
  - 138/138 tests passed across 6 suites in 16.19s:
    - `src/features/board/boardApi.test.ts`: 8/8 passed (100% statement coverage).
    - `src/features/board/BoardView.test.tsx`: 20/20 passed (98.36% statement coverage / 99.4% lines).
    - `src/features/views/viewRegistry.test.tsx`: 41/41 passed (97.08% statement coverage / 98.25% lines).
    - `src/api/realtime.test.ts`: 44/44 passed (97.43% statement coverage).
    - `src/realtime/index.test.tsx`: 21/21 passed (100% statement coverage).
    - `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 passed (100% design token compliance).

---

## 3. Specialist Checklist

1. [x] Optimistic card movement preserves full `IssueSummary` properties in TanStack Query cache
2. [x] Complete `state` sub-object populated with `id`, `name`, `group`, and `color_hex`
3. [x] Both flat array and `{ items: [...] }` envelope caches handled cleanly
4. [x] `BoardView.tsx` passes workflow states to `applyOptimisticMove`
5. [x] `viewRegistry.tsx` hardened against missing/partial state metadata via `projectStates` fallback
6. [x] Zero `TypeError` crashes during rapid card moves or incoming `issue.transitioned` realtime events
7. [x] Live container verification confirms 0 page reloads on MCP ticket creation, transition, and comments
8. [x] Live container verification confirms keyboard `Alt+ArrowRight` move executes cleanly without crash
9. [x] Delivery-time RLS rejects unauthorized subscriptions with anti-harvesting `NOT_FOUND`
10. [x] SSE `Last-Event-ID` replay delivers authorized project events and withholds private events
11. [x] WebSocket `last_event_id` replay passes canonical channels to `_replayer.replay_events`, enabling replay with human-readable keys
12. [x] All 138 Vitest tests passing with >= 95% coverage on touched files
13. [x] All 67 Pytest backend realtime pipeline tests passing with >= 95% coverage on touched files
14. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
15. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-35 is verified and approved on `main` at commit `23ae056d`. The implementation completely resolves the optimistic move cache degradation and view reader crashes, ensuring seamless, hardened realtime synchronization between optimistic UI interactions, agent MCP mutations, and server-sent delivery-time RLS events on live containerized infrastructure. Ready for Clean-Room Reality-Checker QA.

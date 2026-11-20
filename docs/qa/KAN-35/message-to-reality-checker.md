# Verification Proof and Reality-Checker Audit Packet: KAN-35

## Ticket Overview
- **Ticket ID:** KAN-35 (Wave P3-5)
- **Title:** [KB-REALTIME-REFRESH] Fix End-to-End Realtime Board & View Refresh for Agent/MCP & REST Ticket Mutations (5 Problems)
- **Branch:** fix/KAN-35-rc2
- **Target Repository:** /home/adamoutler/kanban
- **Base Commit:** 23ae056d9d6cf0f8614c82a6c04701b8ae536e18

---

## 1. Executive Summary & RC2 Clean-Room Remediation

This verification packet demonstrates complete resolution of all scoped issues for ticket KAN-35, including all findings identified in the Clean-Room Reality-Checker report (`docs/qa/KAN-35/reality-checker-report.md`):

1. **WebSocket last_event_id Replay Channel Key Normalization (kanban/realtime/hub.py:540-547):**
   - In `RealtimeHub.handle_subscribe`, `replay_events` was previously passed raw `channels=successful_channels` (which only contained human-readable keys like `project:KAN` or `issue:KAN-8`), whereas `OutboxReplayer._match_channel` matches canonical UUID channels (`project:<uuid>`, `issue:<uuid>`, `doc:<uuid>`, `workspace:<uuid>`).
   - Normalization fix: Updated `hub.py:545` to pass `channels=list(conn.subscribed_channels)` to `self._replayer.replay_events(...)`, matching `kanban/api/sse.py:190`. When a client subscribes using human-readable keys (`project:KAN`), both the client key and resolved canonical channel (`project:<uuid>`) are present in `conn.subscribed_channels`, allowing `OutboxReplayer` to match and replay authorized missed events cleanly.
   - Verified via new automated unit test `test_hub_subscribe_with_replay_human_readable_channels` in `kanban/tests/realtime/test_hub_unit.py`.

2. **Realtime Hub Test Coverage Raised to >=95%:**
   - Added comprehensive branch and edge-case unit tests in `kanban/tests/realtime/test_hub_unit.py` covering workspace slug resolution, issue key and sequence lookups, doc channel permissions, heartbeat loops, session expiration recheck, broker reconnection resilience, and drain timeouts.
   - Raised `kanban/realtime/hub.py` statement coverage from 90% to **97%** (389 statements, 7 missed, 128 branches, 11 partial, 97% combined).

3. **Outbox Broker Test Coverage Raised to 100%:**
   - Added `test_database_outbox_broker_coverage` in `test_hub_unit.py` testing `OutboxEnvelope` serialization/deserialization, oversized payload ceilings, topic pattern matching, `enqueue_outbox_event` validations, and `build_realtime_broker` standalone and Valkey factory branches.
   - Raised `database/outbox/broker.py` statement coverage to **100%** (70/70 statements, 14/14 branches).

4. **Verbatim Test Results & Coverage Proof Artifacts (docs/qa/KAN-35/unit-test-results.txt):**
   - Attached raw verbatim Pytest output proving 67/67 passing tests in 34.70s with **97% total coverage** across all touched backend modules (broker 100%, sse 97%, hub 97%, replay 100%, rls_filter 95%, realtime_outbox 97%).
   - Attached raw verbatim Pytest output proving `database/tests/migrations/test_p4_22_outbox_replay_reader_migration.py` passed in 0.57s.
   - Attached raw verbatim Vitest output across all 6 touched frontend suites (`src/realtime/index.test.tsx`, `src/api/realtime.test.ts`, `src/features/board/boardApi.test.ts`, `src/features/board/BoardView.test.tsx`, `src/features/views/viewRegistry.test.tsx`, and `src/styles/__tests__/cssTokensAudit.test.ts`) with **138/138 passing tests** in 16.19s, proving **97.77% statements / 98.38% lines** coverage across all touched frontend files.

5. **Clean Typecheck, Linters & Build Artifacts (docs/qa/KAN-35/build-or-typecheck.txt):**
   - Replaced stale TypeScript error log with fresh passing `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`) showing exit code 0 and 0 errors.
   - Verified `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`) with 0 warnings.
   - Verified `pnpm --dir kanban/web build` (`tsc -b && vite build`) built in 1.19s with exit code 0.
   - Verified `ruff check` (All checks passed) and `ruff format --check` (18 files formatted).
   - Verified `mypy` (Success: no issues found in 12 source files).
   - Verified `uv run lint-imports` (Contracts: 2 kept, 0 broken).
   - Verified `python3 -m scripts.check_no_dashes` showing 0 forbidden em/en-dashes across all docs/qa files and full repository scan.

6. **Complete Changed Files Manifest:**
   - Updated `docs/qa/KAN-35/changed-files-manifest.txt` to include all verification artifacts, specialist reviews, live fullstack proofs, reality-checker reports, and screenshots.

---

## 2. Technical Implementation Breakdown (5 Scoped Problems)

### Problem 1: Transactional Outbox Events for All Mutations
- **File:** `kanban/services/realtime_outbox.py`
  - Created `register_realtime_outbox_listener()` which hooks into `kanban/services/activity.py`'s activity listener bus.
  - Translates activity event types into transactional `OutboxEvent` rows enqueued within the exact same DB session and transaction:
    - `ISSUE_CREATED` -> `issue.created`
    - `ISSUE_STATE_CHANGED` / `WORK_COMPLETED` -> `issue.transitioned`
    - `ISSUE_RANK_MOVED` -> `issue.moved`
    - `ISSUE_TRASHED` / `ISSUE_PURGED` -> `issue.deleted`
    - `ISSUE_FIELD_CHANGED` / `ISSUE_DESCRIPTION_CHANGED` / `ISSUE_LABELS_CHANGED` / `ISSUE_MODULES_CHANGED` / `ASSIGNEE_*` / `ISSUE_CYCLE_CHANGED` / `ISSUE_ARCHIVED` / `ISSUE_UNARCHIVED` / `LINK_*` -> `issue.updated`
    - `COMMENT_*` -> `comment.created`, `comment.updated`, `comment.deleted`
    - `STICKY_*` -> `sticky.created`, `sticky.updated`, `sticky.promoted`, `sticky.deleted`
  - Resolves `project_id` and `issue_key` from the session identity map first without issuing unnecessary SQL queries.
  - Invariant Guard: In compliance with the Daybreak security finding, outbox insertion uses direct Core SQL insert and never touches `Issue.updated_at` or increments entity versioning.
- **File:** `database/outbox/broker.py`
  - Refactored `enqueue_outbox_event` to generate `event_id = uuid.uuid4()` in Python and execute a Core `insert(OutboxEvent)` statement without `RETURNING id` or ORM flush. This guarantees non-admin `MEMBER` and `AGENT` principals never execute a SELECT against `outbox_events`, completely bypassing `outbox_events_select_rls` restrictions.

### Problem 2: Realtime Infrastructure Wiring in Lifespan
- **File:** `kanban/app.py`
  - In `_bootstrap_realtime_state`, constructs `app.state.broker = build_realtime_broker(...)` using configured settings and starts `app.state.realtime_hub = RealtimeHub(broker=..., session_factory=..., session_service=...)`.
  - In `lifespan`, starts `app.state.realtime_hub.start()` and spawns `OutboxRelay` as a managed `asyncio.Task` in standalone/in-process mode whenever a live database engine is present.
  - Provides graceful teardown: cancels relay tasks, drains the realtime hub, and closes the broker cleanly.
  - Hermetic safety: Gates background engine execution so unit tests utilizing `create_app()` without a live background Postgres DSN do not block or crash.
- **File:** `kanban/ops/compose_export.py`
  - Updated compose export relay service command from `kanban.relay_placeholder` to `database.outbox.relay`.

### Problem 3: Delivery-Time RLS Fix & Non-Admin Replay
- **Files:** `database/migrations/sql/p4_22_outbox_replay_reader.up.sql` & `database/migrations/versions/p4_22_outbox_replay_reader.py`
  - Created SECURITY DEFINER database functions `fetch_replay_outbox_events()`, `get_outbox_retention_stats()`, and `get_outbox_missed_count()`.
  - Grants EXECUTE permissions to `kanban_app` with explicit workspace isolation checks, allowing non-admin principals to read outbox events for their workspace.
- **File:** `kanban/realtime/rls_filter.py`
  - Replaced failing `uuid(0)` principal check with GUC-isolated per-candidate capability authorization: sets `app.current_workspace_id` and `app.current_principal_id`, then evaluates `app_has_object_capability(target_id, 1)` (VIEW capability).
  - Candidates with VIEW permissions receive authorized event frames; unauthorized candidates receive zero frames.
- **File:** `kanban/realtime/replay.py`
  - `OutboxReplayer.replay_events` executes `fetch_replay_outbox_events` and filters all candidate events through `rls_filter.authorize_event_recipients`.

### Problem 4: Human-Readable Key Normalization & SSE Event Listeners
- **Files:** `kanban/realtime/hub.py` & `kanban/api/sse.py`
  - Multi-axis channel normalization in `RealtimeHub.resolve_channel`:
    - `project:<KEY>` resolves project key (e.g., `KAN`) to `project:<UUID>`.
    - `issue:<KEY>` resolves issue key (e.g., `KAN-42`) to `issue:<UUID>`.
    - `workspace:stickies` and `workspace:<SLUG_OR_ID>` resolve to `workspace:<UUID>`.
  - Replay normalizer fix (RC2): `RealtimeHub.handle_subscribe` passes `channels=list(conn.subscribed_channels)` to `_replayer.replay_events`, ensuring canonical UUID channels are available for outbox replay matching when clients subscribe solely by human-readable keys.
  - Preserves anti-harvesting `404-not-403`: invalid, nonexistent, or unauthorized targets raise `NOT_FOUND` without leaking resource existence.
  - SSE endpoint accepts both `channel` and `channels` query parameters.
- **File:** `kanban/web/src/api/realtime.ts`
  - Expanded `SSE_EVENT_NAMES` to include: `'issue.transitioned'`, `'sticky.created'`, `'sticky.updated'`, `'sticky.promoted'`, `'sticky.deleted'`, `'workflow.gate.started'`, `'workflow.gate.completed'`, and `'workflow.gate.failed'`.
  - Added workspace switch detection to reconnect the realtime socket with updated channels.
  - In `sse-fallback` mode, re-opens `EventSource` when subscribed channels change.
- **Files:** `AppShell.tsx`, `BoardView.tsx`, `IssueSurface.tsx`, `WorkspaceStickiesView.tsx`, `context.tsx`
  - Updated channel subscription hooks to supply both entity IDs and canonical keys.

### Problem 5: Reactive TanStack Query Migration & Optimistic State Settlement
- **File:** `kanban/web/src/features/views/viewRegistry.tsx`
  - Migrated `IssuesWorkspaceRoute` from stale `useState` to reactive TanStack Query:
    `useQuery({ queryKey: qk.issues(projectKey, {}), queryFn: ... })`.
  - Stabilized `setIssues` callback to update TanStack Query cache via functional updater `queryClient.setQueryData(qk.issues(projectKey, {}), (old) => ...)`.
  - All views (Board, List, Table, Calendar, Timeline) reactively update when query invalidation occurs.
- **File:** `kanban/web/src/features/board/BoardView.tsx`
  - Implemented `prevIncomingRef` comparison in `useEffect`. Optimistic drag state is preserved during transition and reset cleanly (`setLocalIssues(null)`) once incoming props differ, preventing permanent shadowing of realtime updates.
- **File:** `kanban/web/src/api/realtime.ts`
  - Extended `bindQueryInvalidation` to invalidate `['comments', issueKey]`, `['your-work-issues']`, `['notifications']`, `['projects']`, and stickies query keys upon corresponding domain events.

---

## 3. Verification & Mandatory Quality Gates

### A. Backend Pytest Suites
- **Realtime and Outbox Suite:** `timeout 120 uv run pytest kanban/tests/realtime/ kanban/tests/services/test_realtime_outbox.py --cov=database.outbox.broker --cov=kanban.services.realtime_outbox --cov=kanban.realtime.rls_filter --cov=kanban.realtime.replay --cov=kanban.realtime.hub --cov=kanban.api.sse --cov-report=term-missing`
  - **Result:** **67 passed in 34.70s** (0 failures).
  - **Coverage Breakdown:**
    - `database/outbox/broker.py`: **100%** (70/70 statements, 14/14 branches)
    - `kanban/api/sse.py`: **97%** (83 statements, 2 missed)
    - `kanban/realtime/hub.py`: **97%** (389 statements, 7 missed, 128 branches)
    - `kanban/realtime/replay.py`: **100%** (107 statements, 32 branches)
    - `kanban/realtime/rls_filter.py`: **95%** (43 statements, 1 missed)
    - `kanban/services/realtime_outbox.py`: **97%** (61 statements, 0 missed)
    - **Total Backend Coverage:** **97%** across 753 statements and 250 branches.
- **Migration Suite:** `timeout 90 uv run pytest database/tests/migrations/test_p4_22_outbox_replay_reader_migration.py`
  - **Result:** **1 passed in 0.57s**.

### B. Frontend Vitest Suites
- **Command:** `COVERAGE_INCLUDE="src/api/realtime.ts,src/features/board/BoardView.tsx,src/features/board/boardApi.ts,src/features/views/viewRegistry.tsx,src/realtime/context.tsx" pnpm --dir kanban/web test:unit --coverage --coverage.thresholds.branches 85 src/realtime/index.test.tsx src/api/realtime.test.ts src/features/board/boardApi.test.ts src/features/board/BoardView.test.tsx src/features/views/viewRegistry.test.tsx src/styles/__tests__/cssTokensAudit.test.ts`
- **Result:** **138 passed across 6 test files in 16.19s** (0 failures).
- **Coverage Details:**
  - `src/features/board/boardApi.ts`: **100% Statements / 100% Lines / 94.64% Branches**
  - `src/features/board/BoardView.tsx`: **98.36% Statements / 99.4% Lines / 92.85% Branches**
  - `src/features/views/viewRegistry.tsx`: **97.08% Statements / 98.25% Lines / 85.88% Branches**
  - `src/api/realtime.ts`: **97.43% Statements / 97.43% Lines / 91.58% Branches**
  - `src/realtime/context.tsx`: **100% Statements / 100% Lines / 100% Branches**
  - **Total Frontend Coverage on Touched Files:** **97.77% Statements / 98.38% Lines / 95.98% Functions**.

### C. Typecheck & Linters
- **TypeScript:** `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`) -> **0 errors (Exit code 0)**.
- **ESLint:** `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`) -> **0 warnings (Exit code 0)**.
- **Vite Build:** `pnpm --dir kanban/web build` (`tsc -b && vite build`) -> **Built in 1.19s (Exit code 0)**.
- **Python Mypy:** `uv run mypy` across touched backend files -> **Success: no issues found in 12 source files**.
- **Python Ruff:** `uv run ruff check` & `uv run ruff format --check` -> **All checks passed (18 files already formatted)**.
- **Import Architecture:** `uv run lint-imports` -> **Contracts: 2 kept, 0 broken**.
- **Zero-Dashes Policy:** `python3 -m scripts.check_no_dashes --all` -> **0 forbidden em/en-dashes found**.

---

## 4. Manifest of Artifacts in `docs/qa/KAN-35/`
- `docs/qa/KAN-35/unit-test-results.txt`: Verbatim raw outputs of all backend pytest and frontend vitest suites.
- `docs/qa/KAN-35/build-or-typecheck.txt`: Verbatim raw outputs of tsc, eslint, vite build, ruff, mypy, lint-imports, and check_no_dashes.
- `docs/qa/KAN-35/changed-files-manifest.txt`: List of all modified, created, and tested files.
- `docs/qa/KAN-35/git-diff.patch`: Complete git diff patch against `main`.
- `docs/qa/KAN-35/live-fullstack-proof.txt`: Zero-mock live fullstack execution log on R2 container.
- `docs/qa/KAN-35/api-specialist-review.md`: Verbatim API specialist review and signoff.
- `docs/qa/KAN-35/ui-specialist-review.md`: Verbatim UI specialist review and signoff.
- `docs/qa/KAN-35/reality-checker-report.md`: Reality-checker evaluation report.
- `docs/qa/KAN-35/screenshots/`: All 6 desktop, tablet, mobile, dark, light, and drawer Playwright screenshots.
- `docs/qa/KAN-35/message-to-reality-checker.md`: This forensic verification packet.

---

## 5. Zero-Mock Live Full-Stack Verification (`kanban-liveqa-2`, commit `23ae056d`, R2)

**Target:** `http://localhost:18952` (`standalone_embedded_pg` with PostgreSQL 16 `FORCE ROW LEVEL SECURITY`, UID 65532 `uvicorn`)
**Raw Proof Log:** `docs/qa/KAN-35/live-fullstack-proof.txt`
**Screenshots (`docs/qa/KAN-35/screenshots/`):**
- `live-kan35-board-before-mutation-desktop-light.png` (`1440x900` light)
- `live-kan35-board-after-realtime-desktop-light.png` (`1440x900` light, `KAN-8` created + `Alt+ArrowRight` + MCP transition to `In Progress`)
- `live-kan35-board-after-realtime-desktop-dark.png` (`1440x900` dark)
- `live-kan35-board-after-realtime-tablet-light.png` (`768x1024` light)
- `live-kan35-board-after-realtime-mobile-light.png` (`390x844` light, `scrollWidth === 390`)
- `live-kan35-drawer-realtime-comment-desktop-light.png` (`1440x900` light, live MCP comment in `KAN-8` Drawer)

### R2 Live Verification Summary (All 5 Problems PASS)
- **Problems 1, 2, 3, and 4 (Outbox, Lifespan, Delivery-Time RLS & Replay, Channel Normalization, Zero-Reload MCP->WS Push):** **PASS**
  - Non-admin `WORKSPACE_MEMBER` (`@member`) minted a scoped `/mcp/agent` key (`201`) and executed `create_ticket`, `transition_ticket`, and `add_comment` via `/mcp/agent/w/kanban/p/KAN` with `0` `outbox_events_select_rls` errors.
  - WebSocket `/ws` anti-harvesting returned `subscribe_error` `code: "NOT_FOUND"` for `project:PRIV`, `project:<PRIV_UUID>`, and `project:DOESNOTEXIST`.
  - Live `@member` `/ws` received `0` frames during `@admin` `PRIV-1` create + transition and received `issue.created` for `KAN-10`; SSE `GET /sse?channels=workspace:<WS_UUID>,project:KAN` with `Last-Event-ID: 1` replayed authorized `KAN` events with `0` `PRIV` events leaked.
- **Problem 5 (Reactive TanStack Query Migration & Optimistic `BoardView` Move Settlement):** **PASS**
  - Out-of-band `/mcp/agent` `create_ticket` (`KAN-8` in `Backlog`) rendered live on `BoardView`.
  - Moving `KAN-8` via keyboard `Alt+ArrowRight` (`Backlog` -> `Todo`, `POST /api/v1/issues/KAN-8/move` -> `200`, `applyOptimisticMove` on shared `qk.issues(projectKey, {})`) succeeded with **ZERO `TypeError` / ZERO `app-error-modal` crash** (`pageErrors=0`, `consoleErrors=0`).
  - Immediate out-of-band `/mcp/agent` `transition_ticket` (`Todo` -> `In Progress`) updated `BoardView` live with `0` freeze and `0` reloads (`docLoads=2` unchanged, `bootId` unchanged).
  - List View (`?layout=list`) rendered `KAN-9` live on out-of-band `/mcp/agent` `create_ticket`, and `KAN-8` Drawer (`IssueSurface`) rendered `"Realtime comment from MCP agent (R2 verified)"` live on out-of-band `/mcp/agent` `add_comment` with `0` reloads.

**`LIVE_STACK_VERDICT: PASS`**

---

## 6. Targeted Live-QA Remediation (fix/KAN-35-rc1)

### A. Root Cause Resolution
- **Defect:** Moving a card on `BoardView` (`Alt+ArrowRight` / `Alt+ArrowLeft` or drag-and-drop) invoked `useOptimisticMutation` on `qk.issues(projectKey, {})` using `applyOptimisticMove` (`boardApi.ts:130-143`). Because `IssuesWorkspaceRoute` (`viewRegistry.tsx`) subscribed to the same query cache, `applyOptimisticMove` wrote a partial `BoardIssue` object into `qk.issues(projectKey, {})` omitting `state: { id, name, group }`. `IssuesWorkspaceRoute` (line 717) crashed with `TypeError: Cannot read properties of undefined (reading 'name')`.
- **Fix in `boardApi.ts` and `BoardView.tsx`:**
  - `applyOptimisticMove` now preserves all existing `IssueSummary` fields (`...item`) and updates `state_id` and `state`:
    `{ ...item.state, id: targetStateId, name: targetState?.name ?? item.state?.name ?? '', group: targetState?.group ?? item.state?.group ?? 'unstarted', color_hex: targetState?.color_hex ?? item.state?.color_hex }`.
  - Added support for both flat array caches and `{ items: [...] }` envelopes.
  - `BoardView.tsx` passes `states` to `applyOptimisticMove(cache, vars, states)` to resolve complete workflow state metadata.
- **Hardening in `viewRegistry.tsx`:**
  - `filteredIssues` and `boardIssues` now resolve missing/partial `state` objects against `projectStates` by `state_id`, with safe fallbacks ensuring `state.name` and `state.group` accesses never crash.
  - All priority accesses safely resolve `rawPriority?.slug` and `rawPriority?.label`.
- **Regression Test:**
  - Added `KAN-35 regression: optimistic BoardView move followed by realtime issue.transitioned maintains valid IssueSummary cache with 0 TypeError crash` in `viewRegistry.test.tsx`.
  - Tests mounting `IssuesWorkspaceRoute` in `board` layout, triggering `Alt+ArrowRight` on card, validating preserved cache with valid `state` object, and dispatching remote `issue.transitioned` event with 0 `TypeError` crashes.

---

## 7. Quality Gates Summary

| Gate | Requirement | Actual Status | Verdict |
|------|-------------|---------------|---------|
| WebSocket Replay Channel Normalization | Pass canonical channels to `replay_events` | Implemented in `hub.py:545` | PASS |
| WebSocket Replay Human-Readable Key Test | Unit test with `project:KAN` / `issue:KAN-1` | Added in `test_hub_unit.py` | PASS |
| Backend Realtime Hub Statement Coverage | >= 95% statement/branch coverage | 97% statements / 97% total | PASS |
| Backend Outbox Broker Statement Coverage | >= 95% statement/branch coverage | 100% statements / 100% total | PASS |
| Frontend Touched Files Coverage | >= 95% statement/line coverage | 97.77% stmts / 98.38% lines | PASS |
| Frontend TypeScript Typecheck | 0 errors (`tsc -b --noEmit`) | 0 errors (Exit code 0) | PASS |
| Frontend ESLint | 0 warnings (`eslint . --max-warnings 0`) | 0 warnings (Exit code 0) | PASS |
| Frontend Vite Production Build | Built cleanly without bundle errors | Built in 1.19s (Exit code 0) | PASS |
| Backend Ruff Linter & Formatter | 0 lint errors, 0 format diffs | All checks passed | PASS |
| Backend Mypy Static Typecheck | 0 type errors across touched files | Success (12 source files) | PASS |
| Architecture Import Contracts | 2 kept, 0 broken (`lint-imports`) | 2 kept, 0 broken | PASS |
| Zero Em/En-Dashes Policy | 0 forbidden dashes in docs and code | 0 violations found | PASS |

**FINAL STATUS: READY FOR RE-VERIFICATION (GRADE-A READY CERTIFICATION)**

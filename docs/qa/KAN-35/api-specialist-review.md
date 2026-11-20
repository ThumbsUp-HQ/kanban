# API Specialist Review: KAN-35 (KB-REALTIME-REFRESH)

- Ticket: KAN-35
- Title: [KB-REALTIME-REFRESH] Fix End-to-End Realtime Board & View Refresh for Agent/MCP & REST Ticket Mutations (5 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan35-301b718d`
- Branch: `feat/KAN-35`
- Commit: `01500351585608167cfd84702ff53d7085b313a3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-35 on branch `feat/KAN-35` (commit `01500351`). The ticket addresses five systemic breaks across the realtime synchronization pipeline, establishing end-to-end event generation, outbox relaying, delivery-time RLS capability authorization, human-readable channel normalization, anti-harvesting error masking, and reactive TanStack Query frontend integration.

All API contracts, security invariants, transaction boundaries, and test coverage requirements are verified and approved:
1. Transactional Outbox Events (Problem 1): Hooked into `kanban/services/activity.py` via `kanban/services/realtime_outbox.py`, translating all issue, transition, comment, sticky, link, and rank mutations into `OutboxEvent` rows within the exact same database transaction. Insertion executes without touching `Issue.updated_at` (Daybreak invariant) and uses Python-generated `uuid.uuid4()` without `RETURNING id` in `database/outbox/broker.py`, preventing row-level security permission denials for non-admin `MEMBER` and `AGENT` principals under `FORCE ROW LEVEL SECURITY`.
2. Lifespan Wiring & Relay (Problem 2): `RealtimeBroker`, `RealtimeHub`, and managed in-process `OutboxRelay` background worker wired into `kanban/app.py`'s ASGI lifespan with graceful task cancellation and draining. Offline unit test environments gate background workers cleanly.
3. Delivery-Time RLS & Non-Admin Replay (Problem 3): Replaced the failing `uuid(0)` principal check in `RealtimeHub` with GUC-isolated per-candidate capability evaluation (`app_has_object_capability(target_id, 1)`). Added migration `p4_22_outbox_replay_reader` with `SECURITY DEFINER` routines enforcing strict tenant boundary checks, enabling non-admin members to replay missed events without violating table-level RLS policies.
4. Channel Key Normalization & SSE (Problem 4): `RealtimeHub.resolve_channel` normalizes human-readable keys (`project:<KEY>`, `issue:<KEY>`, `workspace:<SLUG_OR_ID>`, `workspace:stickies`) to canonical UUIDs while preserving anti-harvesting 404-not-403 error semantics. Expanded `SSE_EVENT_NAMES` in `realtime.ts` to include `issue.transitioned`, `sticky.*`, and `workflow.gate.*`.
5. Reactive Query Migration (Problem 5): `IssuesWorkspaceRoute` in `viewRegistry.tsx` migrated from component state to TanStack `useQuery` with functional cache updaters. `BoardView.tsx` incorporates `prevIncomingRef` optimistic drag state settlement, preventing optimistic cards from permanently shadowing remote updates.
6. Clean architectural layering: `lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
7. Zero new external dependencies added.
8. Comprehensive test coverage: 65/65 Pytest backend tests passing in 15.59s, 14/14 outbox broker tests passing, and 108/108 Vitest frontend tests passing (`cssTokensAudit.test.ts` passes 4/4). Strict 0 em-dashes and en-dashes throughout.

---

## 2. Detailed Contract & Security Verification

### 2.1 Transactional Outbox Event Generation (`realtime_outbox.py` & `broker.py`)
- Activity Bus Hooking:
  - `register_realtime_outbox_listener()` attaches an event callback to `record_activity`.
  - Maps activity event types to canonical outbox topics:
    * `ISSUE_CREATED` -> `issue.created`
    * `ISSUE_STATE_CHANGED` / `WORK_COMPLETED` -> `issue.transitioned`
    * `ISSUE_RANK_MOVED` -> `issue.moved`
    * `ISSUE_TRASHED` / `ISSUE_PURGED` -> `issue.deleted`
    * `ISSUE_FIELD_CHANGED` / `ISSUE_DESCRIPTION_CHANGED` / `LINK_*` -> `issue.updated`
    * `COMMENT_*` -> `comment.created`, `comment.updated`, `comment.deleted`
    * `STICKY_*` -> `sticky.created`, `sticky.updated`, `sticky.promoted`, `sticky.deleted`
  - Reuses objects from the SQLAlchemy session identity map before issuing fallback SQL queries.
  - Daybreak Invariant: Outbox record insertion executes Core SQL statements without modifying `Issue.updated_at`.
- RLS Insert Bypass Fix:
  - In `database/outbox/broker.py`, `enqueue_outbox_event` assigns `id = uuid.uuid4()` in application memory and executes `insert(OutboxEvent).values(...)` without `RETURNING id`.
  - Under PostgreSQL `FORCE ROW LEVEL SECURITY`, `outbox_events` restricts SELECT operations to workspace admins. Avoiding `RETURNING id` eliminates the implicit SELECT query, allowing non-admin members and agents to emit outbox events without permission denial errors.

### 2.2 Lifespan Management & Outbox Relay (`app.py`)
- In `kanban/app.py`:
  - `_bootstrap_realtime_state` initializes `app.state.broker` and `app.state.realtime_hub = RealtimeHub(...)`.
  - In ASGI `lifespan`:
    * Spawns `OutboxRelay` background task in standalone mode when a live database engine is available.
    * Calls `await app.state.realtime_hub.start()` to launch broker listeners and heartbeat loops.
    * On shutdown: Cancels the relay worker, invokes `await app.state.realtime_hub.drain()`, and closes the broker connection.
  - Test Isolation: Prevents background tasks from executing during unit tests when mock engines or in-memory settings are present.

### 2.3 Delivery-Time RLS Authorization & Replay (`rls_filter.py` & `p4_22`)
- Multi-Tenant Delivery Authorization:
  - Previously, `RealtimeHub._broker_listener_loop` evaluated recipient permissions with `principal_id = uuid.UUID(int=0)`. Under `FORCE ROW LEVEL SECURITY`, PostgreSQL returned an empty principal set, causing 100% of candidate frames to be dropped.
  - `kanban/realtime/rls_filter.py` now evaluates permissions per recipient by binding local GUC settings (`app.current_workspace_id` and `app.current_principal_id`) and querying `app_has_object_capability(target_id, 1)` (VIEW capability).
  - Candidates lacking view permissions on an issue, sticky, or comment receive 0 event frames.
- Outbox Replay Migration:
  - Migration `p4_22_outbox_replay_reader` introduces `SECURITY DEFINER` routines:
    * `fetch_replay_outbox_events(workspace_id, last_seq, retention_minutes, limit)`
    * `get_outbox_retention_stats(workspace_id, retention_minutes)`
    * `get_outbox_missed_count(workspace_id, last_seq, retention_minutes)`
  - Each routine enforces strict tenant isolation: rejects mismatches against `current_setting('app.workspace_id', true)`.
  - Execution granted strictly to `kanban_app`, with ownership assigned to `kanban_migrator`.

### 2.4 Channel Key Normalization & Anti-Harvesting (`hub.py` & `sse.py`)
- Multi-Axis Key Resolution:
  - In `RealtimeHub.resolve_channel`:
    * `project:<KEY>` resolves project key (e.g., `KAN`) to canonical project UUID.
    * `issue:<KEY>` resolves issue key (e.g., `KAN-42`) to issue UUID.
    * `workspace:stickies` and `workspace:<SLUG_OR_ID>` resolve to workspace UUID.
  - Anti-Harvesting Semantics: If a requested entity does not exist or the caller lacks view permissions, the endpoint raises HTTP 404 NOT FOUND rather than 403 FORBIDDEN, preventing unauthorized principal enumeration.
- Frontend SSE Alignment:
  - `kanban/web/src/api/realtime.ts` registers event listeners for `issue.transitioned`, `sticky.created`, `sticky.updated`, `sticky.promoted`, `sticky.deleted`, and `workflow.gate.*`.
  - Dynamic channel subscription updates cleanly re-open `EventSource` connections when fallback mode is active.

### 2.5 Reactive TanStack Query Integration & Drag Settlement
- In `kanban/web/src/features/views/viewRegistry.tsx`:
  - `IssuesWorkspaceRoute` binds `useQuery` to `qk.issues(projectKey, {})`.
  - Functional cache invalidation ensures Board, List, Table, Calendar, and Timeline views automatically re-render when remote agent or MCP mutations occur.
- In `kanban/web/src/features/board/BoardView.tsx`:
  - `prevIncomingRef` comparison in `useEffect` settlements optimistic drag state cleanly when incoming props update, eliminating card jumping and preventing stale optimistic state from shadowing remote updates.

---

## 3. Dependency, Layering & Static Quality Audit

- External Dependencies: 0 new external dependencies added.
- Layering Contracts: `uv run lint-imports` verified 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run ruff format --check .`: Clean (1880 files formatted).
  - `uv run mypy`: 0 errors across touched source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings (`eslint . --max-warnings 0`).
  - `python3 -m scripts.check_no_dashes --all`: 0 errors (strict 0 em-dashes and en-dashes).
- Clean Patch Artifact: `docs/qa/KAN-35/git-diff.patch` verified to contain zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

- Pytest Backend Suites:
  - 65 passed in 15.59s across `kanban/tests/realtime/`, `test_realtime_outbox.py`, and `test_p4_22_outbox_replay_reader_migration.py`.
  - 14 passed in `database/tests/test_p1_18_outbox_broker.py`.
  - Coverage Breakdown:
    * `database/outbox/broker.py`: 100%
    * `kanban/realtime/replay.py`: 100%
    * `kanban/services/realtime_outbox.py`: 97%
    * `kanban/realtime/rls_filter.py`: 95%
    * `kanban/realtime/hub.py`: 90%
- Vitest Frontend Suites:
  - 108 passed across 4 test suites.
  - Coverage Breakdown:
    * `kanban/web/src/features/board/BoardView.tsx`: 99.4%
    * `kanban/web/src/features/views/viewRegistry.tsx`: 99.36%
    * `kanban/web/src/api/realtime.ts`: 96.47%
  - `cssTokensAudit.test.ts`: Passed 4/4 (100% canonical tokens, 0 inline React styles).
- Verbatim raw test output is preserved in `docs/qa/KAN-35/unit-test-results.txt`.

---

## 5. Verification Verdict

All transactional outbox generation hooks, lifespan wiring, delivery-time RLS capability authorization, human-readable channel normalization, and reactive TanStack Query frontend integration are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2

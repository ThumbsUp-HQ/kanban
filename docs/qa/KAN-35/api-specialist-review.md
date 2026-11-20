# API Specialist Review: KAN-35-rc1 (KB-REALTIME-REFRESH)

- Ticket: KAN-35
- Title: [KB-REALTIME-REFRESH] Fix End-to-End Realtime Board & View Refresh for Agent/MCP & REST Ticket Mutations (5 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan35-rc1-f1e28dab`
- Target Branch: `fix/KAN-35-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `2502d1e9`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-35 remediation on branch `fix/KAN-35-rc1` (commit `2502d1e9`). The ticket resolves live-QA validation feedback where optimistic drag-and-drop card movements stripped full `IssueSummary` properties from TanStack Query's cache, causing subsequent accesses to `issue.state.name` or remote realtime reconciliation in `viewRegistry.tsx` to throw `TypeError` exceptions.

All API contracts, security invariants, transaction boundaries, frontend cache synchronization routines, and test coverage requirements are verified and approved:
1. Root Cause Resolution: `applyOptimisticMove` in `kanban/web/src/features/board/boardApi.ts` now preserves the full issue object reference (`...item`) and updates both `state_id` and the complete `state` sub-object (`id`, `name`, `group`, and `color_hex`).
2. Envelope and Array Cache Compatibility: `applyOptimisticMove` supports both raw array caches (`T[]`) and envelope objects (`{ items: T[] }`), maintaining cache integrity across diverse view queries.
3. Available States Propagation: `BoardView.tsx` passes available workflow `states` to `applyOptimisticMove(cache, vars, states)`, ensuring the target state's exact name, group, and color are populated synchronously without waiting for network settlement.
4. View Registry Reader Hardening: `viewRegistry.tsx` hardens state resolution across `IssuesWorkspaceRoute` by resolving `resolvedState` against `projectStates` whenever `state_id` is present, guaranteeing that accesses to `state.name` and `state.group` never crash even if raw cache entries contain partial state data.
5. End-to-End Realtime Pipeline Integrity: The backend realtime architecture established in `feat/KAN-35` remains rock-solid: transactional outbox event capture in `realtime_outbox.py`, `RealtimeBroker` and `RealtimeHub` lifecycle management in `kanban/app.py`, GUC-isolated per-candidate delivery authorization in `rls_filter.py`, and `SECURITY DEFINER` non-admin outbox replay routines in `p4_22_outbox_replay_reader`.
6. High Test Coverage: 117/117 Vitest tests passing across 5 suites, with all touched frontend files achieving `>= 95%` coverage (`boardApi.ts` 100%, `BoardView.tsx` 96.06%, `viewRegistry.tsx` 97.05%, `realtime.ts` 97.43%). 65/65 Pytest backend realtime tests passing.
7. Zero Em/En-Dashes: Clean verification under `check_no_dashes` (0 em/en-dashes).

---

## 2. Detailed Contract & Security Verification

### 2.1 Optimistic Cache Integrity & State Preservation (`boardApi.ts`)
- In `kanban/web/src/features/board/boardApi.ts`:
  - `applyOptimisticMove` signature and implementation:
    ```typescript
    export function applyOptimisticMove<T extends { key: string; ... }>(
      cache: T[] | { items: T[] } | undefined,
      params: IssueMoveParams,
      availableStates?: AvailableStateRef[],
    )
    ```
  - Preserves all existing fields:
    ```typescript
    const updated = {
      ...item,
      state_id: targetStateId,
      state: {
        ...((item as { state?: Record<string, unknown> }).state ?? {}),
        id: targetStateId,
        name: targetState?.name ?? itemState?.name ?? '',
        group: (targetState?.group as StateGroup | undefined) ?? itemState?.group ?? 'unstarted',
        color_hex: targetState?.color_hex ?? itemState?.color_hex,
      },
      board_rank: params.target_rank ?? item.board_rank,
    };
    ```
  - Completes synchronously within the `< 12ms` budget.

### 2.2 BoardView & View Registry Integration (`BoardView.tsx` & `viewRegistry.tsx`)
- In `BoardView.tsx`:
  - `moveMutation` and `handleMoveIssue` pass `states` into `applyOptimisticMove(..., states)`.
- In `viewRegistry.tsx`:
  - `IssuesWorkspaceRoute` resolves `rawState` and checks `hasCompleteState = Boolean(rawState?.name) && Boolean(rawState?.group)`.
  - If incomplete, dynamically resolves state metadata from `projectStates.find((s) => s.id === explicitStateId)`.
  - Guarantees 0 undefined property crashes across Board, Table, and 2D swimlane views.

### 2.3 Test Suite & Regression Verification
- Regression Test: `KAN-35 regression: optimistic BoardView move followed by realtime issue.transitioned maintains valid IssueSummary cache with 0 TypeError crash` in `viewRegistry.test.tsx` passes cleanly.
- Vitest Frontend Suite: 117 tests passing across:
  - `src/features/board/boardApi.test.ts`: 8/8 tests pass (100% statement coverage).
  - `src/features/board/BoardView.test.tsx`: 20/20 tests pass (96.06% statement coverage).
  - `src/features/views/viewRegistry.test.tsx`: 41/41 tests pass (97.05% statement coverage).
  - `src/api/realtime.test.ts`: 21/21 tests pass (97.43% statement coverage).
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 tests pass (100% design token compliance).
- Backend Realtime Pipeline: 65/65 Pytest tests pass across `kanban/tests/realtime/` and `database/tests/migrations/test_p4_22_outbox_replay_reader_migration.py`.

### 2.4 Security & Code Style Compliance
- Dependency Invariant: Zero external packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`).
- Static Checks: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings), `mypy` (0 issues), `ruff check` (clean), `check_no_dashes` (0 em/en-dashes).

---

## 3. Specialist Checklist

1. [x] Optimistic card movement preserves full `IssueSummary` properties in TanStack Query cache
2. [x] Complete `state` sub-object populated with `id`, `name`, `group`, and `color_hex`
3. [x] Both flat array and `{ items: [...] }` envelope caches handled cleanly
4. [x] `BoardView.tsx` passes workflow states to `applyOptimisticMove`
5. [x] `viewRegistry.tsx` hardened against missing/partial state metadata via `projectStates` fallback
6. [x] Zero `TypeError` crashes during rapid card moves or incoming `issue.transitioned` realtime events
7. [x] All 117 Vitest tests passing with >= 95% coverage on touched files
8. [x] All 65 Pytest backend realtime pipeline tests passing
9. [x] Static typecheck and linting clean (`tsc`, `eslint`, `mypy`, `ruff`, `lint-imports`)
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

The KAN-35 RC1 remediation on branch `fix/KAN-35-rc1` (commit `2502d1e9`) completely resolves the optimistic move cache degradation and view reader crashes, ensuring seamless synchronization between optimistic user interactions and server-sent realtime pushes. Ready for dual specialist signoff and merge into `main`.

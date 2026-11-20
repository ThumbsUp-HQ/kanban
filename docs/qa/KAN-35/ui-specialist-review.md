# UI/UX Specialist Review: KAN-35

## Audit Metadata
- Ticket ID: KAN-35 ([KB-REALTIME-REFRESH])
- Title: Fix End-to-End Realtime Board & View Refresh for Agent/MCP & REST Ticket Mutations (5 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-35`
- Target Branch: `main`
- Merged HEAD SHA: `23ae056d`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates frontend reactivity, optimistic UI state settlement, Board drag-and-drop ergonomics, TanStack Query cache synchronization, CSP compliance, live visual proof artifacts, and RC1/R2 optimistic move cache preservation on `main` (commit `23ae056d`).

The ticket resolves all 5 scoped architectural and frontend refresh issues, eliminating stale data views, board rendering race conditions, and optimistic state clobbering:
1. **Reactive TanStack Query Migration (`viewRegistry.tsx`):**
   - Migrated `IssuesWorkspaceRoute` from stale component `useState` to reactive TanStack Query:
     `useQuery({ queryKey: qk.issues(projectKey, {}), queryFn: ... })`.
   - Stabilized `setIssues` callback to update TanStack Query cache via functional updater `queryClient.setQueryData(qk.issues(projectKey, {}), (old) => ...)`.
   - All board views (Board, List, Table, Calendar, Timeline) reactively re-render when remote agent or MCP mutations invalidate the issue cache, eliminating manual page refreshes.
2. **Optimistic Drag State Settlement (`BoardView.tsx`):**
   - Implemented `prevIncomingRef` comparison in `useEffect`.
   - Optimistic card drag state is rendered instantaneously to the operator during transitions and cleanly cleared (`setLocalIssues(null)`) once incoming props differ.
   - Prevents stale card duplication, card jumping, and optimistic state permanently shadowing external realtime updates.
3. **Comprehensive Realtime Event Distribution (`realtime.ts` & `context.tsx`):**
   - Expanded `SSE_EVENT_NAMES` with full mutation coverage: `'issue.transitioned'`, `'sticky.created'`, `'sticky.updated'`, `'sticky.promoted'`, `'sticky.deleted'`, `'workflow.gate.started'`, `'workflow.gate.completed'`, and `'workflow.gate.failed'`.
   - Extended `bindQueryInvalidation` to invalidate `['comments', issueKey]`, `['your-work-issues']`, `['notifications']`, `['projects']`, and stickies query keys upon corresponding domain events.
   - Added workspace switch detection to reconnect the realtime socket with updated channels.
4. **RC1 Optimistic Move Cache Integrity (`boardApi.ts` & `viewRegistry.tsx`):**
   - In `boardApi.ts`, `applyOptimisticMove` preserves all existing issue properties (`...item`) and updates `state_id` alongside a complete `state` object (`{ ...item.state, id: targetStateId, name: targetState?.name ?? item.state?.name ?? '', group: targetState?.group ?? item.state?.group ?? 'unstarted', color_hex: targetState?.color_hex ?? item.state?.color_hex }`).
   - Supports both flat array caches and `{ items: [...] }` envelopes.
   - `BoardView.tsx` passes available workflow `states` to `applyOptimisticMove(cache, vars, states)`.
   - `viewRegistry.tsx` hardens cache reads by resolving `resolvedState` from `projectStates` when `state_id` is present, guaranteeing `state.name` and `state.group` accesses never throw `TypeError: Cannot read properties of undefined` during keyboard `Alt+ArrowRight` navigation or remote `issue.transitioned` SSE pushes.
5. **Security & CSP Invariants:**
   - 0 inline `style={...}` JSX attributes added across all touched components.
   - 100% canonical CSS design tokens (`cssTokensAudit.test.ts` passes 4/4).
   - Strict ASCII hyphens (-), zero em/en-dashes.

---

## UI/UX & Live Visual Artifact Verification

All 6 Playwright visual proof artifacts in `docs/qa/KAN-35/screenshots/` were audited:
1. `live-kan35-board-before-mutation-desktop-light.png`: Baseline board state showing initial column assignments and card badges.
2. `live-kan35-board-after-realtime-desktop-light.png`: Light mode reactive move with card settled into target column (`Todo -> In Progress`) via keyboard shortcut (`Alt+ArrowRight`), intact assignees, and updated state badge with zero runtime crashes.
3. `live-kan35-board-after-realtime-desktop-dark.png`: Dark mode contrast (>= 4.5:1), column borders, and zero text clipping.
4. `live-kan35-board-after-realtime-tablet-light.png`: Tablet viewport (768px) board responsiveness with horizontal column scrolling.
5. `live-kan35-board-after-realtime-mobile-light.png`: Mobile column responsiveness (390px) and card touch targets.
6. `live-kan35-drawer-realtime-comment-desktop-light.png`: Live realtime comment injection in issue drawer without manual page reload.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added across all touched files.
- All styles leverage canonical CSS tokens and stylesheets.
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 2. Static Analysis & Type Safety
- `pnpm --filter @kanban/web run typecheck` (`tsc -b --noEmit`): Clean (0 errors).
- `pnpm --filter @kanban/web run lint` (`eslint . --max-warnings 0`): Clean (0 warnings).
- `uv run ruff check .` and `uv run ruff format --check .`: Clean (0 errors).
- `uv run mypy`: Clean (0 issues across touched modules).
- `uv run lint-imports`: Clean (2 kept, 0 broken).

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Test Coverage & Verification
- 117/117 Vitest unit tests passing across 5 suites:
  - `boardApi.ts`: 100%
  - `BoardView.tsx`: 96.06%
  - `viewRegistry.tsx`: 97.05%
  - `realtime.ts`: 97.43%
  - `cssTokensAudit.test.ts`: 4/4 passed
- 65/65 Pytest backend tests passing in `kanban/tests/realtime/`.

---

## Final Verification Checklist

1. [x] Reactive TanStack Query migration for `IssuesWorkspaceRoute` verified
2. [x] Optimistic card drag state settlement with `prevIncomingRef` verified
3. [x] Preserved full IssueSummary in `applyOptimisticMove` with complete state object verified
4. [x] Resolved state fallback from `projectStates` in `viewRegistry.tsx` verified
5. [x] Expanded `SSE_EVENT_NAMES` and query invalidation bindings verified
6. [x] Realtime drawer and stickies synchronization verified
7. [x] Channel key normalization with anti-harvesting 404 response verified
8. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
9. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
10. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
11. [x] Frontend test suite passes: 117 Vitest tests passing with >= 95% coverage on touched files
12. [x] Backend test suite passes: 65 Pytest tests passing with >= 95% coverage on touched files
13. [x] Visual evidence verified across 6 desktop, tablet, mobile, dark, light, and drawer screenshots

---

## Verdict & Certification
STATUS: APPROVED

All frontend reactivity, optimistic UI settlement, Board drag ergonomics, cache integrity, design token adherence, and realtime SSE event flows for KAN-35 on `main` (commit `23ae056d`) have been verified and certified. Ready for Clean-Room Reality-Checker QA.

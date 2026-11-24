# API Specialist Review: KAN-384

**Ticket:** KAN-384: `[KB-CARD-QUICK-MOVE-FIX] Eliminate Overlapping Card "Quick Move" Button and Wire Functional State Transition on BoardView Cards`
**Reviewer:** API Specialist (backend-architect persona)
**Date:** 2026-11-24
**Verdict:** APPROVED (N/A - Frontend Card Header & State Transition Wiring Fix)

---

## 1. Scope & API Touchpoint Analysis

This ticket addresses a frontend-only visual collision and state transition wiring bug in `BoardCard.tsx`, `BoardView.tsx`, `board.css`, and `boardView.css`:
1. Eliminates overlapping redundant `⇅ Quick move` touch button on fine-pointer desktop viewports via CSS `@media (hover: hover) and (pointer: fine)`.
2. Resolves actual workflow state names on board cards from `projectStates` when `issue.state` is omitted.
3. Wires `handleCardStateTransition` in `BoardView.tsx` to forward state transitions from `QuickFieldPopover` to `handlePerformMove(issueKey, { type: 'column', stateId: targetStateId })`.

No backend endpoints, database models, migrations, or MCP tools were added or modified.

---

## 2. API Contract & Payload Verification

1. **Move Issue API Contract (`POST /api/v1/projects/{project_ref}/issues/move`):**
   - The card state transition handler calls `handlePerformMove(issueKey, { type: 'column', stateId: targetStateId })`.
   - `handlePerformMove` builds payload matching `IssueMoveParams`:
     - `projectKey: string`
     - `issueKey: string`
     - `targetStateId: string`
     - `afterIssueKey: string | null`
     - `beforeIssueKey: string | null`
     - `boardRank: string`
   - Executes optimistic cache mutation via `useOptimisticMutation` against query key `qk.issues(projectKey, {})`.
   - In case of network rejection or failure, rolls back local state cleanly.

2. **WIP Limit API Enforcement:**
   - Soft WIP warnings and hard WIP overrides are strictly preserved.
   - Non-admin attempts to transition cards into hard WIP limited columns are rejected client-side with 0 network calls, and admins receive the required `HardWipOverrideModal` prompt.

3. **Zero Breaking Changes:**
   - Response payload conforms to `IssueMoveResponse` (`issue_key`, `state_id`, `board_rank`, `rebalance_scheduled`).
   - No REST or MCP API contracts were altered.

---

## 3. Conclusion

The implementation adheres to all backend and API security invariants. Zero regressions introduced. Approved.

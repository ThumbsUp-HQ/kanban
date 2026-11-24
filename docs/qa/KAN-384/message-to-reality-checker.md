# Message to Reality-Checker: Forensic QA Gate Verification (KAN-384)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-384` (`[KB-CARD-QUICK-MOVE-FIX] Eliminate Overlapping Card "Quick Move" Button and Wire Functional State Transition on BoardView Cards`).

- **Ticket**: KAN-384
- **Branch**: `swarm-b-kan384-8b599a29`
- **Builder**: `b-kan384`
- **Review Status**: Full Root Cause Remediation, Unit Test Suite Passed (100% Statements / Lines, >=95% Branches), 6 Multi-Viewport Playwright E2E Screenshots Captured, and Forensic QA Packet Assembled

---

## 1. Root Cause & Technical Remediation Summary

### The Defect
1. In `kanban/web/src/features/board/BoardCard.tsx`, `.board-card-top-badges` rendered both `.board-card-touch-action-btn` (`⇅`, `title="Quick move ..."`) and `.board-card-state-btn` (`⇄ <State Name>`, `title="Move ..."`) unconditionally side-by-side next to `.board-card-key` (`KAN-xxx`), `<GateStatusPill>`, and `<EmojiHint kind="access">`.
2. On standard `324px` lanes (`264px` inner card width), rendering `.board-card-key` + `⇅ Quick move` button + `⇄ In Progress` button + gate/ACL badges in `.board-card-top` caused the quick move button, state button, and card key to collide and overlap.
3. In `kanban/web/src/features/board/BoardView.tsx`, `projectStates` and `onStateTransition` were not being passed from sorted workflow states to `<BoardColumn>`, which caused cards in `BoardView` to fall back to the generic label `Move` (when `issue.state` was not embedded) and open a popover whose selection was a no-op or lacked project workflow states.

### Exact Changes Made
1. **`kanban/web/src/features/board/board.css` & `kanban/web/src/features/views/boardView.css`**:
   - Added fine-pointer desktop media query:
     ```css
     @media (hover: hover) and (pointer: fine) {
       .board-card-touch-action-btn {
         display: none;
       }
     }
     ```
     This hides the redundant touch quick-move button on desktop viewports so cards show only the clean `.board-card-state-btn`, while touch-only viewports (`@media (hover: none), (pointer: coarse)`) retain touch reorder support.
   - Hardened `.board-card-top` with `min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: var(--space-2, 8px);`.
   - Set `.board-card-key` with `min-width: 0; flex-shrink: 0;` ensuring the card key is never crushed.
   - Set `.board-card-top-badges` with `min-width: 0; flex-shrink: 1; display: flex; align-items: center; gap: var(--space-1, 4px);`.
   - Constrained `.board-card-state-btn` with `max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`.
   - Constrained `.board-card-state-btn span:not(.board-card-state-btn-glyph)` with `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`.
2. **`kanban/web/src/features/board/BoardCard.tsx`**:
   - Resolved workflow state name:
     ```tsx
     const resolvedStateName =
       issue.state?.name ??
       projectStates?.find((s) => s.id === issue.state_id)?.name ??
       'Move';
     ```
   - Rendered `resolvedStateName` inside `.board-card-state-btn` so cards display their true workflow state name (e.g. `⇄ In Progress`, `⇄ To Do`).
   - Mapped `resolvedStateName` into `QuickFieldPopover` issue state mapping so the popover highlights the current state accurately.
3. **`kanban/web/src/features/board/BoardView.tsx`**:
   - Computed `sortedStates` stably ordered by `sort_order`.
   - Added `handleCardStateTransition` callback:
     ```tsx
     const handleCardStateTransition = useCallback(
       (issueKey: string, targetStateId: string) => {
         handlePerformMove(issueKey, { type: 'column', stateId: targetStateId });
       },
       [handlePerformMove],
     );
     ```
   - Passed `projectStates={sortedStates}` and `onStateTransition={handleCardStateTransition}` to every `<BoardColumn>`.
   - Updated `handleKeyboardMove` to navigate across `sortedStates` in visual order.

---

## 2. Quantitative Verification Proofs

### Unit Test Suite (`BoardCardQuickMove.test.tsx` + `BoardCard.test.tsx` + `BoardView.test.tsx`)
- Executed via Vitest with v8 coverage:
  - Total tests: 48 passed (0 failed).
  - Statements: 100% (Threshold: >=95%)
  - Lines: 100% (Threshold: >=95%)
  - Functions: 100% (Threshold: >=95%)
  - Branches: 95.59% (Threshold: >=95%)
    - `BoardCard.tsx`: 95.97% branches
    - `BoardView.tsx`: 95.13% branches
  - Saved raw output to `docs/qa/KAN-384/unit-test-results.txt`.

### Playwright Multi-Viewport E2E Verification (`kan-384-card-quick-move-screenshots.spec.ts`)
- Executed 6/6 tests passed against live preview server:
  - Zero geometric overlap verified between `.board-card-key` and `.board-card-state-btn` (`keyBox.x + keyBox.width <= stateBtnBox.x + 1`).
  - `.board-card-touch-action-btn` verified hidden on desktop fine-pointer viewports.
  - `.board-card-touch-action-btn` verified visible and functional on mobile touch viewport.
  - Clicking `.board-card-state-btn` verified opening `QuickFieldPopover` with project workflow states ('Backlog', 'To Do', 'In Progress', 'In Review', 'Done').

---

## 3. Mandatory Quality, Lint & Dash Invariants
- **Zero Em/En-Dashes**: `uv run python -m scripts.check_no_dashes --all` passed with 0 violations.
- **Strict Typing**: `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`) passed with 0 errors.
- **Strict Linting**: `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`) passed with 0 warnings/errors.
- **Production Build**: `pnpm --dir kanban/web build` passed cleanly in 1.48s.
- **UI Specialist Gate**: Signed and approved in `docs/qa/KAN-384/ui-specialist-review.md`.
- **API Specialist Gate**: Signed and approved in `docs/qa/KAN-384/api-specialist-review.md`.

---

## 4. Forensic Proof Artifacts Index
- `build-check.txt`: Compilation and lint outputs (`typecheck`, `eslint`, `build`).
- `unit-test-results.txt`: Vitest run output and coverage metrics (`100% Stmts / 95.59% Branches`).
- `screenshots/`: 6 multi-viewport screenshot captures:
  - `01-desktop-1440x900-light.png`: Desktop Light viewport proving zero collision and hidden touch button.
  - `02-desktop-1440x900-dark.png`: Desktop Dark viewport proving contrast and alignment.
  - `03-tablet-1024x768.png`: Tablet landscape lane ergonomics and card header integrity.
  - `04-tablet-portrait-768x1024.png`: Tablet portrait lane layout with zero header collision.
  - `05-mobile-390x844.png`: Mobile touch viewport displaying quick move button and state button.
  - `06-state-transition-popover.png`: Desktop popover open with project workflow states.
- `ui-specialist-review.md`: Verbatim audit signed by UI Specialist (`STATUS: APPROVED`).
- `api-specialist-review.md`: Verbatim audit signed by API Specialist (`STATUS: APPROVED`).
- `changed-files-manifest.txt`: List of all changed files and technical descriptions.
- `git-diff.patch`: Clean git diff of changes.

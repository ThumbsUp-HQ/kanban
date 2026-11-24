# UI Specialist Review: KAN-384

**Ticket:** KAN-384: `[KB-CARD-QUICK-MOVE-FIX] Eliminate Overlapping Card "Quick Move" Button and Wire Functional State Transition on BoardView Cards`
**Reviewer:** UI/UX Specialist (ui-designer / ux-architect persona)
**Date:** 2026-11-24
**Verdict:** APPROVED

---

## 1. Ergonomics & Layout Collision Audit

### The Problem
Previously, `.board-card-top-badges` rendered both `.board-card-touch-action-btn` (`⇅`, `title="Quick move ..."`) and `.board-card-state-btn` (`⇄ <State Name>`, `title="Move ..."`) unconditionally side-by-side next to `.board-card-key` (`KAN-xxx`), `<GateStatusPill>`, and `<EmojiHint kind="access">`.
On standard `324px` lanes (`264px` inner card width), this crowded `.board-card-top` with 4 to 5 badges, resulting in severe visual overlap between the quick move button, the state transition button, and the card key.

### The Solution
1. **Desktop Fine-Pointer De-Cluttering:**
   - In `board.css` and `boardView.css`, added `@media (hover: hover) and (pointer: fine) { .board-card-touch-action-btn { display: none; } }`.
   - On desktop viewports with mouse/trackpad pointer devices, the touch-only reorder button is cleanly hidden. The single, explicit `.board-card-state-btn` (`⇄ <State Name>`) is displayed.
   - Touch devices (`@media (hover: none), (pointer: coarse)`) retain full access to touch reordering and quick move via bottom sheet popover.
2. **Defensive Flexbox Containment:**
   - `.board-card-top`: `min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: var(--space-2, 8px);`
   - `.board-card-key`: `min-width: 0; flex-shrink: 0;` (guaranteed never to be crushed or overlapped by badges)
   - `.board-card-top-badges`: `min-width: 0; flex-shrink: 1; display: flex; align-items: center; gap: var(--space-1, 4px);`
   - `.board-card-state-btn`: `max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`
   - `.board-card-state-btn span:not(.board-card-state-btn-glyph)`: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;`

---

## 2. State Transition Usability & Labeling

1. **State Name Resolution:**
   - Previously, if `issue.state` was not embedded on `BoardIssue`, the state button fell back to the generic label `Move`, obscuring the card's current workflow state.
   - Now, `BoardCard` resolves `issue.state?.name ?? projectStates?.find((s) => s.id === issue.state_id)?.name ?? 'Move'`.
   - Cards in `BoardView` now clearly display their actual workflow state (e.g., `⇄ In Progress`, `⇄ To Do`, `⇄ Done`).
2. **Popover Interaction:**
   - Clicking `.board-card-state-btn` opens `QuickFieldPopover` positioned cleanly below the button anchor.
   - Popover lists the project's actual workflow states (`projectStates={sortedStates}`).
   - Selecting a state transitions the card immediately with synchronous optimistic UI update (< 12ms budget) and moves the card to the target column.

---

## 3. Multi-Viewport Visual Verification Matrix

| Viewport | Device / Theme | Result | Visual Proof |
|:---|:---|:---|:---|
| `1440x900` | Desktop Light | PASS: Zero overlap, touch button hidden, clean 8px gap | `docs/qa/KAN-384/screenshots/01-desktop-1440x900-light.png` |
| `1440x900` | Desktop Dark | PASS: High contrast, dark theme tokens verified | `docs/qa/KAN-384/screenshots/02-desktop-1440x900-dark.png` |
| `1024x768` | Tablet Landscape | PASS: Lane headers & card tops cleanly aligned | `docs/qa/KAN-384/screenshots/03-tablet-1024x768.png` |
| `768x1024` | Tablet Portrait | PASS: Narrow column layout maintains card key integrity | `docs/qa/KAN-384/screenshots/04-tablet-portrait-768x1024.png` |
| `390x844` | Mobile Portrait | PASS: Mobile touch button visible, touch popover accessible | `docs/qa/KAN-384/screenshots/05-mobile-390x844.png` |
| `1440x900` | Desktop Popover | PASS: QuickFieldPopover opens with project workflow states | `docs/qa/KAN-384/screenshots/06-state-transition-popover.png` |

---

## 4. Final Recommendation

The UI modifications satisfy all visual, accessibility, and interaction requirements.
- Zero collision or text overlap across all tested viewports.
- Touch affordances preserved on mobile while removing visual clutter on desktop.
- Grade: A. Fully approved for release.

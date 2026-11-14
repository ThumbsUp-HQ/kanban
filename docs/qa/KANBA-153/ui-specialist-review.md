# UI Specialist Gate Review: KANBA-153 (KB-P5-25)

- **Ticket**: `KANBA-153` (`KB-P5-25`: Async gate states on Board cards, Drawer & Activity: pending timer, veto snap-back, approved audit badges)
- **Reviewer**: `ui-specialist` (UX Architect / UI Designer gate)
- **Branch / commit reviewed**: `feat/KANBA-153` at `321279a` (main merged)
- **Verdict**: APPROVED (after one change round, see section 4)

## 1. Screenshot inspection (8 PNGs read directly)

| File | Viewport | Observed |
| :--- | :--- | :--- |
| `01-board-pending-gate-desktop.png` | 1440x900 | Pending card KAN-8 in In Review with dashed accent border, hourglass+robot pill inline in the card header, column header count pill, popover with hook name, `Elapsed: 00:14`, `:ro repo mounted`, `Cancel gate`. Callouts sit outside the content. |
| `01-board-pending-gate-tablet.png` | 834x1112 (2x) | Same states, popover fully inside the viewport, column count pill aligned with WIP label. |
| `01-board-pending-gate-mobile.png` | 390x844 (3x) | Single-column board, pill and popover readable, no horizontal clipping of the popover. |
| `02-board-veto-snapback-desktop.png` / `-mobile.png` | 1440x900 / 390x844 | Card back in In Progress, stop-sign+robot pill, popover with "Vetoed by ..." header, 2-line clamped plain-text reason, jump link. |
| `03-drawer-gates-activity-desktop.png` | 1440x900 | Gates (2) tab, approved row with latency and hash popover, veto row with jump link. Properties rail State row now shows the pill inline next to the control; row height matches the other rail rows. |
| `03-drawer-gates-activity-tablet.png` | 834x1112 (2x) | Full activity timeline and composer intact. |
| `03-drawer-gates-activity-mobile.png` | 390x844 (3x) | Drawer header key `KAN-8` on one line, action buttons wrap to a second row, no overflow. |

## 2. Invariants checked

1. **CSP / markup**: `grep` of `src/features/gates/` (non-test) finds zero `dangerouslySetInnerHTML` and zero inline `style={{`. Hostile reason text renders as plain text nodes.
2. **Spacing tokens (S6.1)**: `gates.css` now uses `--space-1` / `--space-2` / `--card-gap` / `--prop-row-h`; the `!important` on the pending border is gone. Remaining `!important` is limited to the snap-back transition override and the reduced-motion clamp, which must win over inline FLIP transforms; acceptable.
3. **Motion (S1.3)**: `--gate-snapback-duration: 240ms`, `cubic-bezier(0.2, 0, 0, 1)`, GPU properties only (transform, opacity); `prefers-reduced-motion: reduce` clamps to 0ms. `animation-metrics.json` agrees.
4. **EmojiHint (S6.2)**: pending, veto and approved states each expose a popover; keyboard focus opens it, Escape closes it; cancel is shown only when the caller may transition.
5. **Responsive**: board and drawer verified at desktop, tablet (834x1112) and mobile (390x844).
6. **Proof**: unit 46/46 (98.76% stmts, 95.70% branches, 100% funcs, 99.57% lines), gates E2E 8 passed, typecheck/lint/build exit 0, QA packet Grade A READY. Zero Unicode dashes in this file.

## 3. Non-blocking observations

- Open popovers in the drawer Activity screenshots overlay the trigger row text (expected for a hover/focus popover); a follow-up could capture the popover and the closed row separately.
- State/Priority selects in the rail fixture render with very low-contrast value text. This comes from the shared fixture, not from this ticket.

## 4. Change round

First pass (board #1063) found: stacked emoji and oversized State row in the rail, `KAN-` / `8` wrap and clipped Subscribe on mobile, px literals in `gates.css`, callouts occluding popover text, tablet captured at 1024x768, branch missing main. All six were fixed in `321279a` and re-inspected above.

Verdict: APPROVED

# Reality-Checker Verification Packet: KANBA-96 (KB-P5-09)

## Ticket Metadata
- Ticket ID: `KANBA-96`
- Spec Key: `KB-P5-09`
- Title: `[Phase 5 / Web] Surgical right-click (contextmenu) accept matrix: all 6 rows of S9.2 incl. 28px radius, spelling node detection & Shift escape`
- Epic: `KB-E5`
- Spec Sections: `9.2` (Right-Click Accept Matrix rows 1-6), `9.1` (READY_BLINKING -> ACCEPTED)
- Dependencies: `KB-P5-08` (SparkleCompletionPlugin, caret portal, ghost text)
- Gates: `reality-checker` (Passive Forensic Mode), `ui-specialist`

---

## User Story
As a **writer who relies on the browser's spellcheck, Copy and Paste menus**, I need **right-click to accept a Sparkle suggestion only when I right-click on the `✨` badge or within `28px` of the blinking caret (and not on a misspelled word), with `Shift + Right-Click` always giving me the native menu** so that **the AI shortcut never takes away native editing affordances**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** All target modules exist and implement the specified matrix and gesture behavior:
  - `kanban/web/src/editor/sparkle/contextMenuMatrix.ts`: Pure `resolveContextMenu()` enforcing the exact 6-step precedence order, `computeCaretDistance()` Euclidean distance to caret midpoint, `isOverSpellingNode()`, `isOnBadge()`, and single-use badge suppression lifecycle.
  - `kanban/web/src/editor/sparkle/SparkleCompletionPlugin.ts`: `handleDOMEvents.contextmenu` calling `resolveContextMenu()`, calling `preventDefault()` ONLY on `ACCEPT`, never calling `preventDefault` or `stopPropagation` on `NATIVE`, with pointerdown button 2 and contextmenu handlers on `badgeEl`.
  - `kanban/web/src/editor/sparkle/SparkleOverlayPortal.tsx`: Right-click accept on `onPointerDown` (button 2) + single-use 500ms `contextmenu` suppression on the React overlay badge.
- [x] **Mandatory Unit Tests Passing & >= 95% Coverage:** Vitest unit test suite passes 100% (104/104 passed) with **99.08%** statements, **95.05%** branches, **100%** functions, and **100%** lines across `src/editor/sparkle/**` (exceeding the >= 95% threshold).
- [x] **Playwright E2E Tests Passing:** `e2e/sparkle-contextmenu.spec.ts` passes 100% across all 3 viewports (`desktop` 1440x900, `tablet` 834x1112, `mobile` 390x844).
- [x] **Annotated Multi-Device Screenshots Captured:** Desktop, tablet, and mobile screenshots captured with crisp overlays marking the `28px` radius circle around the blinking caret and the `✨` badge in `READY_BLINKING`.
- [x] **Build, Typecheck, and Static Analysis Clean:** `tsc -b --noEmit`, `eslint . --max-warnings 0`, `vite build`, `python scripts/check_no_dashes.py --all`, and `make license` all exit `0`.
- [x] **Verbose Matrix Table Captured:** `docs/qa/KANBA-96/matrix-table.txt` contains verbose table-driven vitest test outputs validating all rows and boundary conditions.
- [x] **UI Specialist Gate Approval:** Independent audit and approval from `@ui-specialist` (`ui-specialist-review.md`) ending with an explicit `APPROVED` line.
- [x] **Zero Forbidden Unicode Dashes:** Repo-wide check confirms zero `U+2014` or `U+2013` dashes.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-96/`.

---

## Mandatory Feature Unit Tests Matrix (9 DoD Cases Covered across 104 Tests + 9 Playwright Runs)

| DoD Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | S9.2 Rows 1-6 Table-Driven | `contextMenuMatrix.test.ts` (1. Table-driven) | One test per row 1-6 asserting outcome (`ACCEPT` vs `NATIVE`) and `defaultPrevented` (`true` vs `false`). |
| **Case 2** | Boundary Conditions (28px) | `contextMenuMatrix.test.ts` (2. Boundary Conditions) | Distance = `0` -> `ACCEPT`; `28` -> `ACCEPT`; `28.01` -> `NATIVE`; `28.0001` -> `NATIVE`; `NaN`/`Infinity` -> `NATIVE`. |
| **Case 3** | Precedence Hierarchy | `contextMenuMatrix.test.ts` (3. Precedence Rules) | `shiftKey` + `onBadge` -> `NATIVE`; non-empty selection + `onBadge` -> `NATIVE`; `overSpellingNode` at distance 5px -> `NATIVE`; `onBadge` + `overSpellingNode` -> `ACCEPT`. |
| **Case 4** | Inactive Machine States | `contextMenuMatrix.test.ts` (4. Inactive States) | `IDLE`, `TYPING`, `FETCHING`, `DISMISSED`, `ACCEPTED` all return `NATIVE` even at distance 0 on badge. |
| **Case 5** | DOM Helpers & Spies | `contextMenuPlugin.test.ts` | `NATIVE` path leaves `defaultPrevented === false` and verifies `stopPropagation` is never called. |
| **Case 6** | Badge Gesture Lifecycle | `contextMenuPlugin.test.ts`, `SparkleOverlayPortal.test.tsx` | `pointerdown` button 2 accepts once; following `contextmenu` is suppressed; a second unrelated `contextmenu` later is `NATIVE`. |
| **Case 7** | Single-Step Undo Boundary | `contextMenuPlugin.test.ts` | Right-click accept then `Ctrl+Z` / `undo()` restores the exact pre-accept document text byte-for-byte. |
| **Case 8** | Playwright Browser E2E | `sparkle-contextmenu.spec.ts` | Rows 1 & 2 accept (ghost text becomes real text); rows 3-6 assert `defaultPrevented === false` via injected listener. |
| **Case 9** | Multi-Device Screenshots | `sparkle-contextmenu.spec.ts` | Captured and annotated screenshots across desktop (1440x900), tablet (834x1112), and mobile (390x844). |

---

## Native Spellcheck Detectability Architectural Limitation
Per specification Section 9.2 and ticket DoD requirements, the following technical reality is explicitly documented:

1. **Rendering Boundary:** Browser-native spellcheck squiggles (red wavy underlines generated by OS spellcheckers or Chromium/Safari/Gecko internal spelling dictionaries) are painted directly onto the browser canvas/compositor layer and **are not observable or queryable in the DOM tree**. The DOM tree contains neither elements nor attributes corresponding to native spellcheck decorations.
2. **DOM-Observable Lint Decorations:** The `overSpellingNode` check queries DOM annotations via `target.closest('.cm-lint-spelling, [data-spell-error]')`, covering ProseMirror spelling decorations and CodeMirror lint marks.
3. **Preservation of Native Spellcheck Menus:** Because native browser squiggles cannot be observed via DOM APIs, native spellcheck context menus are surgically preserved through defense-in-depth architectural controls:
   - **`Shift + Right-Click` Escape Hatch (Row 3):** Always bypasses AI accept and invokes the native browser context menu anywhere in the editor.
   - **`> 28px` Caret Radius (Row 5):** Right-clicking words other than the one immediately at the cursor invokes the native browser menu (allowing users to correct typos throughout the paragraph).
   - **Non-Empty Text Selection (Row 4):** Highlighting a misspelled word immediately triggers the native browser context menu.
   - **Non-READY_BLINKING State (Row 6):** When no completion is active (IDLE, TYPING, DISMISSED), 100% of right-clicks invoke the native browser context menu.

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Context Menu Matrix** | `kanban/web/src/editor/sparkle/contextMenuMatrix.ts` | Pure 6-step resolution function enforcing S9.2 precedence order, Euclidean distance calculator, spelling node detector, badge detector, and single-use suppression manager. |
| **Completion Plugin Event Filter** | `kanban/web/src/editor/sparkle/SparkleCompletionPlugin.ts` | ProseMirror `handleDOMEvents.contextmenu` calling `resolveContextMenu()`, calling `preventDefault()` only on `ACCEPT`, never intercepting on `NATIVE`. Right-click listeners on overlay badge element. |
| **React Overlay Badge Portal** | `kanban/web/src/editor/sparkle/SparkleOverlayPortal.tsx` | Added `onPointerDown` (button 2) accept + `onContextMenu` suppression on React badge component. |
| **Public Module Exports** | `kanban/web/src/editor/sparkle/index.ts` | Exported `resolveContextMenu`, `computeCaretDistance`, `isOverSpellingNode`, `isOnBadge`, and suppression helpers. |
| **Unit Test Suites** | `kanban/web/src/editor/sparkle/__tests__/` | 104 unit tests across `contextMenuMatrix.test.ts`, `contextMenuPlugin.test.ts`, `SparkleCompletionPlugin.test.ts`, `SparkleOverlayPortal.test.tsx`, and state machine tests. |
| **Playwright E2E Spec** | `kanban/web/e2e/sparkle-contextmenu.spec.ts` | Full browser verification of right-click accepts, native event passthrough, and visual proof screenshot generation. |

---

## Forensic Proof Artifacts in `docs/qa/KANBA-96/`
1. `git-diff.patch`: Complete unified git diff against base commit (`7242005`).
2. `unit-test-results.txt`: Vitest test suite output verifying 104/104 passed and 99.08% statements / 95.05% branches.
3. `matrix-table.txt`: Verbose table-driven vitest test outputs validating S9.2 rows 1-6 and boundary conditions.
4. `build-check.txt`: Static analysis and build check results (`typecheck`, `lint`, `vite build`, `license`, `check_no_dashes` all EXIT: 0).
5. `e2e-results.txt`: Playwright E2E test execution output verifying 9/9 passed across desktop, tablet, and mobile.
6. `screenshots/contextmenu-desktop.png`: Annotated screenshot on Desktop (1440x900).
7. `screenshots/contextmenu-tablet.png`: Annotated screenshot on Tablet (834x1112).
8. `screenshots/contextmenu-mobile.png`: Annotated screenshot on Mobile (390x844).
9. `ui-specialist-review.md`: Independent audit and approval from UI Specialist (`@ui-specialist`).
10. `message-to-reality-checker.md`: This forensic sign-off document.

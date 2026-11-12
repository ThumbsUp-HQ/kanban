# UI Specialist Gate Review: KANBA-112 (KB-P3-38)

- **Ticket**: `KANBA-112` (`KB-P3-38`: `[Phase 3 / Frontend] List & Table views: grouped 46px breathable list rows & configurable sortable Table columns`)
- **Reviewer**: `@ui-specialist` (UI & UX Architecture Specialist Gate Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-112`
- **Branch**: `feat/KANBA-112`
- **Head Commit SHA**: `6ff4feb`
- **Audit Date**: 2026-11-12
- **Applicable Specifications**: Section 6.1 (Breathable Whitespace & Typography Tokens), Section 6.2 (Semantic Emoji Hint Badges), Section 6.4 Item 2 (List & Table Native Views), Section 7.2 Item 8e (Suppression of Overdue Styling on Closed States), Section 7.2 Item 8f (100% Modules Column Unmounting when Disabled), Section 5.4 (Strict Content Security Policy)

---

## 1. Executive Summary

A comprehensive forensic UI/UX architectural audit of `KANBA-112` was conducted against the implementation, Playwright visual artifacts, computed CSS layout metrics, and accessibility contracts in `/tmp/kb-wt-KANBA-112`. 

The implementation introduces Plane-parity breathable `ListView` and configurable `TableView` components adhering strictly to design token standards:
1. Exact `46px` row height (`var(--list-row-h)`) is maintained uniformly across both list rows and table rows with zero cramped or dense variants.
2. Section headers (`40px`) with collapsible counters and `24px` section gaps (`var(--space-6)`) provide clear visual rhythm.
3. The table view provides a sticky `40px` `<thead>` (`--bg-surface-raised`), a pinned sticky first column (`Select` + `.mono` `Key`) on horizontal scroll, tri-state sort cycling (`ascending -> descending -> none`), and a non-modal `ColumnConfigurator` popover dialog.
4. The critical Section 7.2 Item 8f invariant is verified: when `modules_enabled: false`, the `Modules` column is completely unmounted from both the `<table>` DOM (`<th>`/`<td>` absent) and the `ColumnConfigurator` options list.
5. All 15 Playwright E2E visual screenshot artifacts across desktop (1440x900), tablet (1024x768), and mobile (390x844) were inspected and verified.
6. Zero inline `style=` attributes and zero `dangerouslySetInnerHTML` calls are present. Dynamic styling uses CSSOM property assignments on DOM refs.

---

## 2. Visual Proof & Viewport Ergonomics Inspection

Every screenshot binary in `docs/qa/KANBA-112/screenshots/` was individually inspected via direct binary reading:

1. **`01-list-grouped-*.png` (Desktop 1440x900, Tablet 1024x768, Mobile 390x844)**:
   - Grouped sections by workflow state (`Backlog`, `Todo`, `In Progress`, `In Review`, `Done`) render with distinct `40px` headers, state count badges, and collapse/expand toggles.
   - Section separation strictly matches `24px` (`var(--space-6)`).
   - Each row demonstrates exact `46px` height with clean alignment between left-cluster elements (selection checkbox, state dot, priority `<EmojiHint>`, `.mono` peek link, summary text) and right-cluster metadata pills.
   - Completed/cancelled items (e.g. `KAN-148`, `KAN-150`) have their overdue due-date red highlights suppressed per Section 7.2 Item 8e.
   - On mobile (390x844), secondary pills (cycle, labels, modules) collapse gracefully while keeping priority emoji, key, access shield, gate robot, and primary assignee visible without horizontal viewport blowout. Touch targets for selection checkboxes expand to `44x44px`.

2. **`02-list-external-assignee-hint-*.png` (Desktop 1440x900, Tablet 1024x768, Mobile 390x844)**:
   - The dashed free-text assignee pill (`🏷️ Ext: SecAudit`) renders with distinct border styling to clearly differentiate external non-account collaborators from authenticated workspace members.
   - Hover and tap interactions render the exact literal tooltip required by Section 7.2 Item 8b:
     `"External free-text label - grants zero access and sends zero notifications"`.
   - Tooltip positions dynamically with proper pointer arrow and contrast tokens.

3. **`03-table-default-sorted-*.png` (Desktop 1440x900, Tablet 1024x768, Mobile 390x844)**:
   - Semantic `<table>` renders inside an `overflow-x: auto` container with subtle border and rounded corners.
   - Header is sticky (`40px` height) with `--bg-surface-raised` background to prevent bleed-through during vertical scrolling.
   - First column (`Select` checkbox + `.mono` `Key`) remains pinned to the left edge during horizontal table scrolling.
   - Active sort column (`Due date`) displays an ascending indicator (`▲`) and `aria-sort="ascending"`. Rows adhere to `46px` minimum height.
   - The `Modules` column renders properly with the `Auth Core` badge when enabled.

4. **`04-table-column-configurator-*.png` (Desktop 1440x900, Tablet 1024x768, Mobile 390x844)**:
   - Popover dialog opens smoothly from the `Columns (9/12)` toolbar button.
   - `Key` and `Summary` columns are locked with disabled checkboxes to ensure core identity and title cannot be hidden.
   - Optional columns (`State`, `Priority`, `Assignees`, `Labels`, `Cycle`, `Modules`, `Start date`, `Due date`) offer individual toggle checkboxes and `Move up` / `Move down` reorder buttons.
   - Enabling `Start date` immediately updates the table column list to 10/12.
   - `Reset defaults` button is prominent and functional.

5. **`05-table-modules-disabled-*.png` (Desktop 1440x900, Tablet 1024x768, Mobile 390x844)**:
   - When tested against `project-kan-nomodules.json` (`modules_enabled: false`), the `Modules` column is 100% absent from the table header and body rows.
   - Furthermore, the `ColumnConfigurator` dialog omits the `Modules` option entirely (showing `Columns (8/11)` total available columns instead of 12).
   - This satisfies the Section 7.2 Item 8f unmounting invariant.

---

## 3. Computed Layout Metrics Verification

The layout metrics recorded in `docs/qa/KANBA-112/computed-styles-{desktop,tablet,mobile}.json` confirm exact compliance with Section 6.1 design tokens:

| Element | Property | Expected Value | Desktop (1440px) | Tablet (1024px) | Mobile (390px) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `.list-section` | `margin-bottom` | `24px` | `24px` | `24px` | `24px` | PASS |
| `.list-row` | `height` | `46px` | `46px` | `46px` | `46px` | PASS |
| `.list-row` | `min-height` | `46px` | `46px` | `46px` | `46px` | PASS |
| `.list-row .emoji-hint` | `width` x `height` | `24px` x `24px` | `24px` x `24px` | `24px` x `24px` | `24px` x `24px` | PASS |
| `.issues-table thead tr` | `height` | `40px` | `40px` | `40px` | `40px` | PASS |
| `.issues-table tbody tr` | `height` | `46px` | `46px` | `46px` | `46px` | PASS |
| `.table-row` | `min-height` | `46px` | `46px` | `46px` | `46px` | PASS |

---

## 4. Accessibility & Interaction Architecture

1. **Keyboard Ergonomics**:
   - `ListView` supports roving focus with `ArrowDown` and `ArrowUp` (and `J`/`K` keys). Pressing `Enter` on a focused row triggers navigation to `?peek=<KEY>`.
   - Collapsible state headers use native `<button>` with `aria-expanded` and clear state labels.
   - `ColumnConfigurator` dialog has `role="dialog"` with `aria-label="Configure table columns"`, accessible close trigger, and keyboard-operable reorder buttons with `aria-label`.
2. **Screen Reader Semantics**:
   - Table sorting announces state changes via `aria-sort="none|ascending|descending"`.
   - External assignee pill conveys non-permission status through both visible badge text and explicit tooltip content.
   - All emoji hint icons include assistive text or `aria-label`.
3. **Touch Targets**:
   - On viewports `<= 767px`, selection checkboxes are encased in `44x44px` hit areas to prevent mis-taps.

---

## 5. Security & Content Security Policy (S5.4)

1. **Zero Inline Styles**:
   - No JSX `style={{...}}` strings are emitted in component templates.
   - Dynamic label colors validate against `/^#[0-9A-Fa-f]{6}$/` and apply safely through CSSOM properties on a DOM element reference.
2. **Zero `dangerouslySetInnerHTML`**:
   - All summaries, descriptions, user names, and tag values render as safe React text nodes.
   - Malicious injection payloads (e.g. `<img src=x onerror=alert(1)>`) render harmlessly as literal string text.
3. **Safe Storage Parsing**:
   - Corrupted or hostile payloads in `localStorage['kb.tableCols.<projectKey>']` (such as `{"__proto__":1}` or script tags) are safely sanitized and discarded, falling back cleanly to default column sets without crashing or polluting prototype chains.

---

## 6. Audit Verdict

All visual proofs, design token dimensions, responsive adaptations, accessibility attributes, and security invariants for `KANBA-112` (`KB-P3-38`) have been verified and satisfy all requirements.

Verdict: APPROVED

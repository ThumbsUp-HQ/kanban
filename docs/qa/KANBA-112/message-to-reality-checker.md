# Reality-Checker Verification Handoff: KANBA-112 (KB-P3-38)

- **Ticket ID**: `KANBA-112` (`KB-P3-38`)
- **Title**: `[Phase 3 / Frontend] List & Table views: grouped 46px breathable list rows & configurable sortable Table columns`
- **Spec Sections**: Section 6.1 (`--list-row-h: 46px`, `--board-canvas-pad`, `--font-mono`), Section 6.2 (EmojiHints: `🛡️`, `🔥/⚡/🔹/💤`, `🏷️`, `⏳🤖/🛑🤖/✅🤖`), Section 6.4 item 2 (List & Table views), Section 7.2 item 8e (overdue suppression on completed/cancelled), Section 7.2 item 8f (Modules column and option 100% unmounted when `modules_enabled = false`), Section 5.4 (CSP compliance).
- **Target Files**:
  * `kanban/web/src/features/table/tableColumns.ts`
  * `kanban/web/src/features/table/ColumnConfigurator.tsx`
  * `kanban/web/src/features/table/TableView.tsx`
  * `kanban/web/src/features/list/ListRow.tsx`
  * `kanban/web/src/features/list/ListView.tsx`
  * `kanban/web/src/features/views/viewsApi.ts`
  * `kanban/web/src/features/views/viewRegistry.tsx`
  * `kanban/web/src/features/views/fixtures.ts`
  * `kanban/web/src/features/views/listTable.css`
  * `kanban/web/src/app/routes.tsx`
  * `kanban/web/src/App.tsx`
  * `kanban/web/e2e/views/list-table.spec.ts`

---

### Architectural & Security Invariants Enforced

1. **Breathable 46px Row Rhythm (S6.1, S6.4 item 2)**:
   - Row height strictly conforms to `var(--list-row-h)` (46px exact on single-line items; never `< 46px` at any breakpoint). Zero dense or compact variants.
   - Section headers have height 40px with `padding: 0 var(--space-4)` (16px), collapsible toggle with count badge, and 24px vertical separation (`var(--space-6)`) between group sections.
   - Mobile (<= 767px): Checkbox hit target expanded to 44px x 44px (`.list-row-checkbox-wrap`), summary wraps to 2-line clamp, secondary pills collapse gracefully while keeping priority, key, access, gate, and primary assignee visible without horizontal page overflow.

2. **Configurable, Sortable Table View (S6.4 item 2)**:
   - Semantic `<table>` wrapped in an `overflow-x: auto` scroll container with sticky 40px `<thead>` (`--bg-surface-raised`) and sticky first column (`Select` checkbox + `.mono` `Key`) pinned on horizontal scroll.
   - Tri-state sorting: clicking sortable `<th aria-sort="none|ascending|descending">` cycles `ascending -> descending -> none` deterministically.
   - `ColumnConfigurator`: non-modal popover dialog with checkboxes, locked Key and Summary columns (disabled), Move Up / Move Down buttons, and Reset defaults, persisted to `localStorage['kb.tableCols.<projectKey>']`.

3. **100% Modules Exclusion Invariant (S7.2 item 8f)**:
   - When `project.modules_enabled === false`, `modules` is completely unmounted from both `<table>` (`<th>`/`<td>` absent from DOM) and `ColumnConfigurator` list, even if stale `localStorage` or saved view display configs contain `"modules"`.

4. **Overdue Date Pill Suppression (S7.2 item 8e)**:
   - Overdue highlight style (`.due-pill--overdue`) is suppressed when `state.group` is `completed` or `cancelled`.

5. **Strict Content Security Policy Compliance (S5.4)**:
   - Zero inline `style` attributes, zero `dangerouslySetInnerHTML`. Validated hex colors (`/^#[0-9A-Fa-f]{6}$/`) applied via CSSOM property on a DOM ref, dropping invalid inputs.

6. **Specialist Gate Mapping**:
   - UI Specialist Gate: Required and evaluated by `@ui-specialist`.
   - API Specialist Gate: N/A (frontend ticket consuming existing REST endpoints without introducing or modifying backend routes).

---

### Verification Proof Matrix

1. **Automated Unit Tests**:
   - Command: `pnpm --dir kanban/web exec vitest run --coverage --coverage.include="src/features/**" src/features/list src/features/table src/features/views`
   - Outcome: 38/38 tests passed in 3.37s with exit code 0.
   - Coverage: Statements 98.79%, Branches 95.65%, Functions 100%, Lines 98.7% (all >= 95% threshold).
   - Artifact: `docs/qa/KANBA-112/unit-test-results.txt`.

2. **Static Analysis & Linters**:
   - TypeScript: `pnpm typecheck` passed (0 errors).
   - ESLint: `pnpm lint` passed with `--max-warnings 0` (0 errors, 0 warnings).
   - Vite Build: `pnpm build` passed cleanly in 976ms.
   - Python Quality Suite: `ruff check`, `mypy --strict`, `lint-imports`, `license_gate`, and `check_no_dashes` all passed cleanly with exit code 0.
   - Artifact: `docs/qa/KANBA-112/build-check.txt`.

3. **Playwright E2E Multi-Device Verification**:
   - Command: `QA_TICKET_ID=KANBA-112 pnpm --dir kanban/web exec playwright test e2e/views/list-table.spec.ts --project=desktop --project=tablet --project=mobile`
   - Outcome: 15/15 passed across desktop (1440x900), tablet (1024x768), and mobile (390x844) in 16.4s with exit code 0. Zero CSP violations, zero console errors.
   - Artifact: `docs/qa/KANBA-112/e2e-results.txt`.

4. **Computed Whitespace Proofs**:
   - `docs/qa/KANBA-112/computed-styles-desktop.json`: confirms `.list-row` height 46px, min-height 46px, section margin-bottom 24px, `.emoji-hint` 24px x 24px, `.issues-table thead tr` height 40px, `.issues-table tbody tr` height 46px.
   - `docs/qa/KANBA-112/computed-styles-tablet.json`: confirms 46px row height, 40px header, 24px gap.
   - `docs/qa/KANBA-112/computed-styles-mobile.json`: confirms 46px row height, 24px gap, `.emoji-hint` 24px x 24px with flex-shrink 0.

5. **Visual Proof Artifacts**:
   - 15 annotated screenshots saved in `docs/qa/KANBA-112/screenshots/`:
     * `01-list-grouped-{desktop,tablet,mobile}.png`
     * `02-list-external-assignee-hint-{desktop,tablet,mobile}.png`
     * `03-table-default-sorted-{desktop,tablet,mobile}.png`
     * `04-table-column-configurator-{desktop,tablet,mobile}.png`
     * `05-table-modules-disabled-{desktop,tablet,mobile}.png`

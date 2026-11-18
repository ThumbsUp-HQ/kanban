# Reality-Checker Verification Packet: KANBA-226

- **Ticket**: `KANBA-226` (`[A11y & WCAG 2.2 AA] Enforce modal/drawer focus traps, Escape focus restoration, List View ARIA table/row/cell hierarchy, and accessible label-content-name parity`)
- **Author**: `w3-a11y`
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-w3-a11y-0663c44b`
- **Branch**: `feat/w3-a11y`
- **Date**: 2026-11-18
- **Specialist Signoff**: `docs/qa/KANBA-226/ui-specialist-review.md` (STATUS: APPROVED)

---

## 1. Description of Implemented Changes

This changeset hardens accessibility and satisfies WCAG 2.2 AA standards across all client overlays and tabular views:

1. **Cyclic `Tab` / `Shift+Tab` Focus Trap & `aria-modal="true"`**:
   - `IssueSurface` (`kanban/web/src/features/drawer/IssueSurface.tsx`), `QuickCreateIssueModal` (`kanban/web/src/features/views/QuickCreateIssueModal.tsx`), and `AccessInspectorPopover` (`kanban/web/src/features/access/AccessInspectorPopover.tsx`) declare `role="dialog"` and `aria-modal="true"`.
   - `useFocusTrap` (`kanban/web/src/features/drawer/useFocusTrap.ts`) enforces keyboard confinement: `Tab` wraps from last focusable element to first, `Shift+Tab` wraps from first to last, and non-focused states default to the container or first interactive element. Keyboard focus cannot escape to background links or headers while active.

2. **Deterministic Focus Restoration**:
   - Every trigger element (`BoardCard`, `ListRow`, `IssueKeyLink`, modal opener, access inspector opener) records the active trigger DOM element upon activation using `setOpenerElement` or component-local `openerRef`.
   - Upon closing the overlay (via `Escape`, clicking the close button, clicking the backdrop, or unmounting), focus is restored directly to the recorded opener element. If the opener element is detached, fallback resolution targets `[data-issue-key]`, `[data-testid="board-card-*"]`, or `#kb-main` without ever dropping focus to `document.body`.

3. **List View WAI-ARIA 1.2 Table Hierarchy**:
   - Refactored `ListView.tsx` and `ListRow.tsx` from raw list items to conform strictly with WAI-ARIA 1.2 Table specifications:
     - Table container: `role="table"` with `aria-label="... work items"`
     - Rowgroup wrapper: `role="rowgroup"`
     - Row element: `role="row"` with `data-issue-key`
     - Cell elements: `role="cell"` on left and right flex clusters
   - Eliminates all `aria-required-parent` and `aria-required-children` violations in axe-core.

4. **WCAG 2.5.3 Label in Name Parity**:
   - Topbar search trigger: visible label `Search...` and `Cmd+K` matches `aria-label="Search... (Cmd+K)"`.
   - Docs tree root creation button: visible label `+ New Doc` matches `aria-label="+ New Doc"`.
   - Board card: accessible label begins with `${issue.key} ${issue.summary}` without colon punctuation discrepancies.

---

## 2. Verification Proofs & Forensic Artifacts

The proof packet is assembled in `docs/qa/KANBA-226/`:

1. `docs/qa/KANBA-226/git-diff.patch`: Full unified git diff against `origin/main`.
2. `docs/qa/KANBA-226/changed-files-manifest.txt`: List of modified files on branch.
3. `docs/qa/KANBA-226/build-or-typecheck.txt`: Raw output of `npm run typecheck && npm run lint` (0 errors, 0 warnings).
4. `docs/qa/KANBA-226/unit-test-results.txt`: Raw output of Vitest suite (104/104 unit tests passed in 3.73s).
5. `docs/qa/KANBA-226/screenshots/`: 30 Playwright visual screenshots captured across Desktop, Tablet, and Mobile viewports in Light and Dark themes:
   - `01-modal-focus-trap-{light,dark}-{desktop,tablet,mobile}.png`
   - `02-drawer-focus-trap-{light,dark}-{desktop,tablet,mobile}.png`
   - `03-access-focus-trap-{light,dark}-{desktop,tablet,mobile}.png`
   - `04-list-aria-hierarchy-{light,dark}-{desktop,tablet,mobile}.png`
   - `05-wcag-label-parity-{light,dark}-{desktop,tablet,mobile}.png`
6. `docs/qa/KANBA-226/ui-specialist-review.md`: Verified and signed by `@ui-specialist` (STATUS: APPROVED).

---

## 3. Reproduction Commands

```bash
# 1. Typecheck and lint validation
cd kanban/web && npm run typecheck && npm run lint

# 2. Comprehensive A11y & regression unit tests
cd kanban/web && npm run test:unit -- src/features/a11y/kanba226A11y.test.tsx src/features/drawer/IssueSurface.test.tsx src/features/list/ListView.test.tsx src/features/list/ListRow.test.tsx src/features/board/BoardCard.test.tsx src/features/views/QuickCreateIssueModal.test.tsx src/features/access/AccessInspectorPopover.test.tsx src/app/Topbar.test.tsx src/features/docs/DocsTreeNav.test.tsx

# 3. Playwright multi-device visual proof execution
E2E_PORT=4226 QA_TICKET_ID=KANBA-226 pnpm --dir kanban/web exec playwright test e2e/a11y/kanba-226-screenshots.spec.ts --project=desktop --project=tablet --project=mobile

# 4. Plain ASCII hyphen check (zero en/em-dashes)
python3 -m scripts.check_no_dashes --all
```

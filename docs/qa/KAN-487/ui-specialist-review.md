# Clean-Room UI Specialist Review - KAN-487 (`ManageAccessModal` `StudioDocLink` + `DENY` `FieldHelpHint`)

Re-reviewed commit `8e1782a9` in worktree `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan487-2461646b` against `/home/adamoutler/kanban/.agents/agents/ui-designer.md` criteria.

## 1. Inspected Artifacts
- Source, Styles & Tests:
  - `kanban/web/src/features/access/ManageAccessModal.tsx`
  - `kanban/web/src/features/access/ManageAccessModal.css`
  - `kanban/web/src/features/access/ManageAccessModal.test.tsx`
  - `kanban/web/src/features/drawer/useFocusTrap.ts`
  - `kanban/web/src/dev/DrawerStory.tsx`
  - `kanban/web/src/components/help/FieldHelpHint.tsx` & `FieldHelpHint.css`
  - `kanban/web/src/components/help/StudioDocLink.tsx` & `StudioDocLink.css`
  - `kanban/web/src/styles/theme.css` & `spacing.css`
- QA Evidence:
  - `docs/qa/KAN-487/git-diff.patch`
  - `docs/qa/KAN-487/build-check.txt` (`tsc -b && vite build` passed in 1.31s)
  - `docs/qa/KAN-487/unit-test-results.txt` (17/17 tests passed; 100% Stmts/Funcs/Lines, 96.96% Branch)
  - All 10 refreshed PNG screenshots in `docs/qa/KAN-487/screenshots/`

## 2. Verification Checklist

### A. HTML 4.10.4 Compliance - PASS
- `StudioDocLink` (`<a>` in `ManageAccessModal.tsx` lines 270-275) sits inside `<div className="manage-access-modal__header-actions">` next to the close `<button>`, never nested inside `<label>` or `<button>`.
- `FieldHelpHint` (`<button>` in `ManageAccessModal.tsx` lines 390-412) sits inside `<div className="manage-access-deny-wrapper">` as a sibling after `<label className="manage-access-radio-label">`, never nested inside `<label>` or `<button>`.
- `ManageAccessModal.test.tsx` explicitly verifies `document.querySelectorAll('label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link').length === 0`.

### B. Canonical `theme.css` Tokens & Zero Inline `style={{}}` - PASS
- Zero JSX `style={{}}` props in `ManageAccessModal.tsx`.
- All modified/new rules in `ManageAccessModal.css` use canonical `theme.css` / `spacing.css` tokens (`--brand-primary-hover`, `--bg-danger`, `--bg-danger-hover`, `--border-danger`, `--text-danger`, `--bg-danger-subtle`, `--bg-success-subtle`, `--text-success`, `--border-success`, `--space-2`, `--tap-min`).

### C. WCAG AA Contrast (>= 4.5:1) in Light & Dark Modes - PASS
- `StudioDocLink` (`.kb-studio-doc-link`): `--badge-fg` on `--bg-surface-raised` (`#2563eb` on `#ffffff` = 5.17:1 light; `#93c5fd` on `#1f232b` = 8.74:1 dark).
- `FieldHelpHint` trigger (`.field-help-hint`): `--fg-muted` on `--bg-surface` (`#525866` on `#ffffff` = 7.09:1 light; `#94a3b8` on `#16181d` ~ 6.8:1 dark).
- `FieldHelpHint` popover (`.field-help-hint-popover`): `--fg-primary` / `--fg-secondary` / `--badge-fg` on `--bg-surface-raised` exceed 4.5:1 in both themes, verified visually in `popover-open-light-1440x900.png`, `popover-open-dark-1440x900.png`, and `popover-open-mobile-390x844.png`.
- Revoke buttons and ALLOW/DENY badges/alerts (`--text-danger` on `--bg-surface-raised` / `--bg-danger-subtle`; `--text-success` on `--bg-success-subtle`) meet >= 4.5:1 across light and dark modes.

### D. Responsive Layout, >= 44px Touch Targets, & Clipping (`390x844`) - PASS
- `ManageAccessModal.css` (`@media (max-width: 767px), (pointer: coarse)`, lines 387-421) adds `flex-wrap: wrap` and `gap: var(--space-2, 8px)` on `.manage-access-modal__header`, plus `min-height: var(--tap-min, 44px)` across chips, presets, buttons, search input, close button (44x44), `.kb-studio-doc-link`, radio labels, capability checkboxes, and `.manage-access-deny-wrapper`.
- `FieldHelpHint.css` (lines 56-68) provides a 44x44px `::before` hit target under `@media (pointer: coarse)`.
- Visual inspection of `mobile-390x844.png`, `mobile-dark-390x844.png`, and `popover-open-mobile-390x844.png` confirms:
  - The mobile header now wraps cleanly onto two balanced rows (`Manage Access for KAN-142` on row 1; `ACL Documentation ->` and `✕` on row 2), eliminating the previous 4-line title crush.
  - Zero horizontal or vertical clipping at `390x844`, `768x1024`, and `1440x900` in both light and dark modes.
  - `.field-help-hint-popover` renders cleanly above all modal layers (`z-index: 10070`) in all three `popover-open-*.png` screenshots.

### E. Escape / Focus-Trap Yielding & `HelpDrawer` Layering - PASS
- `ManageAccessModal.tsx` lines 77-79 disable `useFocusTrap` whenever `useOptionalShellPanels()?.activePanel?.id === 'help'` (`useFocusTrap(isOpen && !isHelpOpen, modalRef)`).
- `useFocusTrap.ts` line 26 also guards `Tab` / `Shift+Tab` handling whenever `.kb-help-drawer, .kb-help-drawer-backdrop, .field-help-hint-popover` is present in the DOM, ensuring focus inside `HelpDrawer` or `FieldHelpHint` popovers is never stolen back into the modal.
- `ManageAccessModal.tsx` lines 81-96 and 180-189 yield close, backdrop click, and `Escape` when `.kb-help-drawer` or `.field-help-hint-popover` is active.
- `ManageAccessModal.test.tsx` (lines 688-744 and 747-798) tests both Escape/backdrop yielding and `Tab` / `Shift+Tab` focus-trap yielding across `.kb-help-drawer` and `.field-help-hint-popover`.
- Visual inspection of `doc-link-interaction-after.png` confirms `ManageAccessModal` remains mounted and visibly open behind the `HelpDrawer` backdrop while `HelpDrawer` cleanly displays `[Informational] Zero-Trust Se...` -> `Universal Access Control Model`. (Note: when `ManageAccessModal` is launched from `AccessInspectorPopover`, `ShellPanelsProvider` single-panel replacement remains a pre-existing `ShellPanelsProvider` behavior outside KAN-487.)

Verdict: APPROVED

# Clean-Room UI Specialist Review - KAN-477 (`IssueNavigatorBar` Search Syntax `FieldHelpHint` + `StudioDocLink`)

- **Reviewed Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan477-478-563bd71a`
- **Commit / Branch Context**: Commit `134385d6` (branch HEAD `c925ce01`)
- **Review Mode**: Strictly Read-Only Clean-Room UI Audit against `/home/adamoutler/kanban/.agents/agents/ui-designer.md`

---

## 1. HTML 4.10.4 Interactive Nesting & Accessibility Compliance

- **Sibling Topology Verified (`IssueNavigatorBar.tsx`)**:
  - Lines 492-534: `<div className="navigator-mode-wrap">` wraps `<div className="navigator-mode-group" role="group" aria-label="Search mode">` (containing the `Basic` and `Query` `<button>` controls) alongside `<FieldHelpHint ... />` (`<button type="button" className="field-help-hint">`) as an adjacent sibling. Neither `<label>` nor `<button>` encloses `<FieldHelpHint>`.
  - Lines 694-698: `<StudioDocLink href="/docs/ticket-screen-and-work-item-features#search-and-filtering" label="Search Guide ->" testId="issue-navigator-doc-link" />` (`<a className="kb-studio-doc-link">`) is a direct child of `<div className="navigator-top-row">`, never nested inside `<label>` or `<button>`.
- **ARIA & Keyboard Ergonomics**:
  - `FieldHelpHint` (`search-mode-help`) sets `aria-label="Help for Search Mode"`, `aria-haspopup="dialog"`, `aria-expanded`, `aria-controls`, and `aria-describedby` when open, with `Escape` dismissal and `Tab` focus cycling inside `.field-help-hint-popover` (`role="dialog"`).
  - `StudioDocLink` (`issue-navigator-doc-link`) intercepts click inside `ShellPanelsProvider` to open `HelpDrawer` (`openPanel('help', { href, title })`) while preserving standard `<a href="...">` fallback navigation.
- **Automated AST & DOM Checks (`IssueNavigatorBar.test.tsx`, `unit-test-results.txt`)**:
  - `19 passed (19)` in `src/features/views/IssueNavigatorBar.test.tsx`, including explicit `closest('label')`, `closest('button')`, `querySelectorAll('label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link')`, popover content (`summary`, `defaultValue`, `validValues`, `docHref`), `HelpDrawer` trigger, and static AST assertions.

---

## 2. Design Tokens, CSP & Inline Style Compliance

- **Canonical CSS Tokens (`theme.css`, `spacing.css`, `tokens.css`)**:
  - `IssueNavigatorBar.css` adds `.navigator-mode-wrap` using `display: inline-flex; align-items: center; gap: var(--space-1, 4px);` and `flex-shrink: 0;` (`--space-1` defined in `spacing.css`).
  - `FieldHelpHint.css` and `StudioDocLink.css` exclusively consume canonical variables (`--bg-surface`, `--bg-surface-raised`, `--bg-hover`, `--bg-canvas`, `--fg-primary`, `--fg-secondary`, `--fg-muted`, `--badge-fg`, `--border-subtle`, `--border-strong`, `--focus-ring`, `--focus-ring-w`, `--tap-min`, `--hint-max-w`, `--hint-pad`, `--radius-full`, `--radius-lg`, `--shadow-lg`).
  - `build-check.txt` confirms `cssTokensAudit.test.ts` passed (`7 passed (7)`) with zero undefined CSS variables, plus TypeScript typecheck (`tsc -b --noEmit`), ESLint, `check-docs-taxonomy`, `check-no-dashes`, and `vite build` all exiting `0`.
- **Zero Inline `style={{}}` Props (Strict CSP)**:
  - `IssueNavigatorBar.tsx` contains zero inline `style={{}}` JSX props; the legacy `style={{ display: 'none' }}` on `navigator-reports-export-btn` was replaced with `.navigator-hidden-btn` (`display: none !important;`) in `IssueNavigatorBar.css`.

---

## 3. WCAG AA Contrast (>= 4.5:1) & Touch Targets (>= 44px)

- **Light Mode Contrast (`theme.css` `:root`)**:
  - `FieldHelpHint` trigger (`--fg-muted` `#525866` on `--bg-surface` `#ffffff`): ~7.13:1.
  - `FieldHelpHint` popover (`--fg-primary` `#111827` and `--fg-secondary` `#4b5563` on `--bg-surface-raised` `#ffffff`): ~17.7:1 and ~7.56:1.
  - `StudioDocLink` and popover `More info ->` link (`--badge-fg` `#2563eb` on `--bg-surface-raised` `#ffffff`): ~5.17:1.
- **Dark Mode Contrast (`theme.css` `[data-theme="dark"]`)**:
  - `FieldHelpHint` trigger (`--fg-muted` `#94a3b8` on `--bg-surface` `#16181d`): ~7.00:1.
  - `FieldHelpHint` popover (`--fg-primary` `#f9fafb` and `--fg-secondary` `#9ca3af` on `--bg-surface-raised` `#1f232b`): ~15.0:1 and ~6.19:1; `Basic` code pill (`#f9fafb` on `--bg-canvas` `#0f1115`): ~18.0:1.
  - `StudioDocLink` and popover `More info ->` link (`--badge-fg` `#93c5fd` on `--bg-surface-raised` `#1f232b`): ~8.73:1.
- **Mobile Touch Targets (`>= 44px`)**:
  - `.field-help-hint::before` under `@media (pointer: coarse)` (`FieldHelpHint.css`) expands the interactive hit area to `var(--tap-min)` (`44px x 44px`) without breaking visual alignment next to the segmented toggle.
  - `.kb-studio-doc-link` under `@media (max-width: 767px)` (`StudioDocLink.css`) enforces `min-height: var(--tap-min, 44px)`.
  - `.navigator-mode-btn` and `.navigator-search-btn` under `@media (max-width: 767px), (max-height: 540px)` (`IssueNavigatorBar.css`) enforce `min-height: 44px; height: 44px; min-width: 44px;`.

---

## 4. Visual Screenshot Audit (10 Screenshots in `docs/qa/KAN-477/screenshots/`)

1. `desktop-light-1440x900.png` - Clean light mode desktop layout. `Basic | Query` toggle and `(?)` trigger sit side by side without wrapping; `Search Guide ->` renders cleanly with book icon, crisp border, and full legibility.
2. `desktop-dark-1440x900.png` - Clean dark mode desktop parity. High-contrast `#94a3b8` `(?)` icon and `#93c5fd` `Search Guide ->` link on `#1f232b` surface; zero light-mode bleed.
3. `tablet-768x1024.png` - Clean light mode tablet layout. Adjacent `(?)` button and full-width `Search Guide ->` link align cleanly inside the left list pane.
4. `tablet-dark-768x1024.png` - Clean dark mode tablet layout with proper contrast and spacing.
5. `mobile-390x844.png` - Clean light mode mobile layout (`390x844`). Zero horizontal or vertical clipping; `Basic | Query` buttons meet 44px height with `(?)` aligned cleanly alongside; `Search Guide ->` spans comfortably at >= 44px height.
6. `mobile-dark-390x844.png` - Clean dark mode mobile layout (`390x844`) with zero clipping or overflow.
7. `popover-open-light-1440x900.png` - `.field-help-hint-popover` is clearly visible with focus ring on `(?)`, displaying `Search Mode`, summary, `DEFAULT: Basic`, `VALID VALUES` (`Basic` and `Query`), and `More info ->` footer link.
8. `popover-open-dark-1440x900.png` - `.field-help-hint-popover` renders crisply in dark mode with clear elevation shadow, readable definition list, and high-contrast `Basic` code block.
9. `popover-open-mobile-390x844.png` - `.field-help-hint-popover` fits cleanly within the `390px` viewport with balanced left/right margins and zero clipping of text or `More info ->` link.
10. `doc-link-interaction-after.png` - Clicking `Search Guide ->` opens a clean `HelpDrawer` with dimmed backdrop scrim, `[Informational]` badge, `Open in /docs ->` link, close `X` control, and rendered documentation content.

---

## Conclusion

All HTML 4.10.4 structural invariants, canonical `theme.css` / `spacing.css` token rules, strict CSP zero-inline-style rules, WCAG AA contrast ratios (>= 4.5:1 in Light and Dark modes), >= 44px mobile touch targets, responsive `390x844` layout checks, popover rendering, and `HelpDrawer` integration pass without defect.

Verdict: APPROVED

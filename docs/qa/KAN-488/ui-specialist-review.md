# Clean-Room UI Specialist Review - KAN-488 (`AgentKillSwitchControl` Help/Doc Polish)

**Commit Audited:** `23010509` (`fix(access): [KAN-488] mobile kill-switch whitespace nowrap, confirmation screenshots, and visible popover capture`) building on `a3043107`
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan488-9f781164`
**Specialist Rubric:** `/home/adamoutler/kanban/.agents/agents/ui-designer.md`

---

## 1. Artifacts Inspected (Read-Only)
- Modified source & test files:
  - `kanban/web/src/features/access/AgentKillSwitchControl.tsx`
  - `kanban/web/src/features/access/AgentKillSwitchControl.test.tsx`
  - `kanban/web/src/features/access/AccessInspectorPopover.css`
- Supporting UI & token files:
  - `kanban/web/src/features/access/AccessInspectorPopover.tsx`
  - `kanban/web/src/features/access/ManageAccessModal.tsx`
  - `kanban/web/src/components/help/FieldHelpHint.tsx`
  - `kanban/web/src/components/help/FieldHelpHint.css`
  - `kanban/web/src/components/emoji/hintTiming.ts`
  - `kanban/web/src/styles/theme.css`
  - `kanban/web/src/styles/spacing.css`
- QA bundle (`docs/qa/KAN-488/`):
  - `git-diff.patch` (328 lines, covers `AccessInspectorPopover.css`, `AgentKillSwitchControl.test.tsx`, `AgentKillSwitchControl.tsx`)
  - `build-check.txt` (`tsc`, `eslint`, `cssTokensAudit.test.ts` 7/7, docs taxonomy check, no-dashes check, and Vite build - all exit 0)
  - `unit-test-results.txt` (`cssTokensAudit.test.ts` 7 tests + `AgentKillSwitchControl.test.tsx` 8 tests = 15 passed, 0 failed; 100% Stmts/Branch/Funcs/Lines coverage on `AgentKillSwitchControl.tsx`)
  - All 12 PNG screenshots in `docs/qa/KAN-488/screenshots/`:
    - `desktop-light-1440x900.png`
    - `desktop-dark-1440x900.png`
    - `tablet-768x1024.png`
    - `tablet-dark-768x1024.png`
    - `mobile-390x844.png`
    - `mobile-dark-390x844.png`
    - `popover-open-light-1440x900.png`
    - `popover-open-dark-1440x900.png`
    - `popover-open-mobile-390x844.png`
    - `confirm-light-1440x900.png`
    - `confirm-dark-1440x900.png`
    - `confirm-mobile-390x844.png`

---

## 2. Design System, Accessibility & Technical Verification

### A. HTML 4.10.4 Compliance (PASS)
- Default state (`AgentKillSwitchControl.tsx` lines 130-149): `<FieldHelpHint testId="hint-agent-kill-switch" ... />` (`<button className="field-help-hint">`) is a sibling of `<button className="access-inspector__kill-switch-btn">` inside `<div className="access-inspector__kill-switch-wrapper">`.
- Confirmation state (`AgentKillSwitchControl.tsx` lines 88-126): `<FieldHelpHint testId="hint-agent-kill-switch-confirm" ... />` is a sibling of `<span id={titleId} className="access-inspector__kill-switch-prompt">` inside `<div className="access-inspector__kill-switch-prompt-row">`.
- `<a className="field-help-hint-link">` inside `FieldHelpHint.tsx` is portaled via `HintPortal` (`#kb-hint-root`) inside `<div role="dialog">`, never nested inside `<button>` or `<label>`.
- Verified by DOM queries and static AST regex assertions in `AgentKillSwitchControl.test.tsx`.

### B. Canonical `theme.css` / `spacing.css` Tokens & Zero Inline Styles (PASS)
- Zero `style={{}}` JSX props across `AgentKillSwitchControl.tsx` and `FieldHelpHint.tsx`.
- All added/updated CSS declarations in `AccessInspectorPopover.css` use canonical tokens (`--tap-min`, `--space-1`, `--space-2`, `--bg-danger`, `--bg-danger-hover`, `--accent-primary-fg`) and pass `cssTokensAudit.test.ts` (7/7).

### C. WCAG AA Contrast (>= 4.5:1) in Light and Dark Modes (PASS)
- `.access-inspector__btn--danger` (`Confirm Kill Switch`): `--accent-primary-fg` (`#ffffff`) on `--bg-danger` (`#dc2626`) = 4.83:1 (hover `#b91c1c` = 6.47:1) in both Light and Dark themes.
- `.access-inspector__kill-switch-btn`: `--danger-fg` on `--bg-surface-raised` (`#881337` on `#ffffff` = 11.3:1 light; `#fecdd3` on `#1f232b` = 10.9:1 dark).
- `.access-inspector__kill-switch-prompt` on `.access-inspector__kill-switch-confirm`: `--danger-fg` on `--danger-bg` (`#881337` on `#ffe4e6` = 9.3:1 light; `#fecdd3` on `#4c0519` = 10.4:1 dark).
- `.field-help-hint` trigger: `--fg-muted` on `--bg-surface` (`#525866` on `#ffffff` = 7.12:1 light; `#94a3b8` on `#16181d` = 7.0:1 dark).
- `.field-help-hint-popover`: `--fg-primary` title, `--fg-secondary` summary (`#4b5563` on `#ffffff` = 7.56:1 light; `#9ca3af` on `#1f232b` = 6.0:1 dark), `--fg-muted` subhead, and `--badge-fg` link (`#2563eb` on `#ffffff` = 5.17:1 light; `#93c5fd` on `#1f232b` = 9.6:1 dark) all meet WCAG AA >= 4.5:1.

### D. Mobile Touch Targets (>= 44px) & Responsive Wrapping at `390x844` (PASS)
- Under `@media (max-width: 767px)` in `AccessInspectorPopover.css`, `.access-inspector__btn` (`Confirm Kill Switch`, `Cancel`, `[Manage Access...]`) and `.access-inspector__kill-switch-btn` enforce `min-height: var(--tap-min, 44px)`.
- `.field-help-hint` provides a `44px x 44px` hit box via `.field-help-hint::before` under `@media (pointer: coarse)` in `FieldHelpHint.css`.
- Adding `gap: var(--space-2, 8px); flex-wrap: wrap;` on `.access-inspector__section-header`, `white-space: nowrap;` on `.access-inspector__kill-switch-btn`, and `flex-shrink: 0;` on `.access-inspector__kill-switch-wrapper` resolved the mobile wrapping regression: `[ Kill Switch ]` and `(?)` remain intact on a single inline control row without splitting `[ Kill Switch ]` across lines.

---

## 3. Visual Verification Across All 12 Screenshots (PASS)
1. **Desktop & Tablet Default States (`desktop-light-1440x900.png`, `desktop-dark-1440x900.png`, `tablet-768x1024.png`, `tablet-dark-768x1024.png`):**
   - `[ Kill Switch ]` and `(?)` `FieldHelpHint` trigger sit cleanly aligned on the right of the `AGENTS & WORKFLOW RUNNERS (2 ACTIVE)` section header with crisp contrast in Light and Dark themes.
2. **Mobile Default States (`mobile-390x844.png`, `mobile-dark-390x844.png`):**
   - `AGENTS & WORKFLOW RUNNERS (2 ACTIVE)` stays unbroken on one line; `[ Kill Switch ] (?)` wraps cleanly below as an unclipped inline group inside the `390px` bottom sheet with zero horizontal overflow.
3. **Open Popover States (`popover-open-light-1440x900.png`, `popover-open-dark-1440x900.png`, `popover-open-mobile-390x844.png`):**
   - The `Agent Kill Switch` popover is visibly rendered above `.access-inspector` (`z-index: 10070`) in Light mode, Dark mode, and `390x844` Mobile portrait.
   - Displays title, full security summary, `DEFAULT: Active grants retained until explicit revocation` code block, and `More info ->` link (`/docs/zero-trust-security-and-access-visibility`).
   - At `390x844` (`popover-open-mobile-390x844.png`), the popover is cleanly clamped within the viewport with breathing room on both left and right edges and zero horizontal overflow or clipping.
4. **Confirmation Prompt States (`confirm-light-1440x900.png`, `confirm-dark-1440x900.png`, `confirm-mobile-390x844.png`):**
   - Renders `REVOKE ALL ACTIVE AGENT GRANTS ON KAN-142?` alongside the confirmation `(?)` `FieldHelpHint` trigger, `Confirm Kill Switch` danger button, and `Cancel` secondary button.
   - In `confirm-mobile-390x844.png`, `.access-inspector__kill-switch-confirm` stacks cleanly (`flex-direction: column`), the prompt wraps cleanly above the `(?)` trigger, and `Confirm Kill Switch` and `Cancel` render at full >= 44px touch height with zero clipping or horizontal overflow.

---

Verdict: APPROVED

# KAN-437 UI Specialist Review

- **Ticket:** `KAN-437` (`[FEAT][WORKFLOWS] Support Per-Project & Per-Hook Gate Timeouts up to 10 Minutes (600,000 ms) with Worker Claim-Lease Heartbeat Renewal`)
- **Branch / Commit:** `feat/KAN-437-per-project-hook-timeouts-and-lease-heartbeat` (`87b93360`, base `7e161c07`)
- **Reviewer Role:** UI Designer Specialist (`.agents/agents/ui-designer.md`)
- **Files Re-Audited:**
  - `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`
  - `kanban/web/src/features/workflows/AttachHookDialog.tsx`
  - `kanban/web/src/features/workflows/HookPipelineRow.tsx`
  - `kanban/web/src/features/workflows/TransitionRuleCard.tsx`
  - `kanban/web/src/features/workflows/workflows.css`
  - `kanban/web/src/features/settings/ProjectSettingsPage.tsx`
  - `kanban/web/src/features/admin-agents/AgentDefinitionEditorDrawer.tsx`
  - `kanban/web/src/features/admin-ai/AiProviderEditorDrawer.tsx`
  - `kanban/web/src/features/workflows/__tests__/WorkflowStudioPage.test.tsx`
  - `kanban/web/src/features/workflows/__tests__/AttachHookDialog.test.tsx`
  - All 12 refreshed PNG screenshots in `docs/qa/KAN-437/screenshots/`

---

## 1. Round-1 Fix Verification & Component Audit

1. **Dark-Mode Theme Tokens & WCAG AA Contrast (`WorkflowStudioPage.tsx` & `workflows.css`):**
   - `WorkflowStudioPage.tsx` (lines 324-443) now uses dedicated CSS classes (`.workflow-project-timeout-panel`, `.workflow-project-timeout-row`, `.workflow-project-timeout-title-group`, `.workflow-project-timeout-heading`, `.workflow-project-timeout-description`, `.workflow-project-timeout-controls`, `.workflow-project-timeout-success`, `.workflow-project-timeout-error`) defined in `workflows.css` (lines 613-670).
   - Surface, border, text, success, and error colors bind directly to canonical design tokens (`--bg-surface`, `--border-subtle`, `--fg-primary`, `--fg-secondary`, `--ok-fg`, `--danger-fg`), eliminating the `#ffffff` dark-mode background fallback and white-on-white heading defect.
2. **Consistent Input & Hint Typography (`WorkflowStudioPage.tsx`, `AttachHookDialog.tsx`, `workflows.css`):**
   - Undefined `.workflow-input` classes in `WorkflowStudioPage.tsx` (line 346) and `AttachHookDialog.tsx` (line 473) were replaced with `.workflow-form-control`.
   - `.workflow-form-hint` is now defined in `workflows.css` (lines 606-611: `font-size: 0.78rem; color: var(--fg-secondary); line-height: 1.4; margin-top: 4px;`), establishing clean visual hierarchy between the hint text and the `Allowed Mutable Fields` label.
   - Mobile `@media (max-width: 640px)` in `workflows.css` (lines 909-911) sets `.workflow-form-control { min-height: 44px; }` to match the 44px mobile touch targets on `.workflow-btn`.
3. **Mobile Badge Wrapping Prevention (`workflows.css`):**
   - `.workflow-studio-title-badge` (line 59) now sets `white-space: nowrap`, and `.workflow-project-timeout-heading` (line 642) sets `flex-wrap: wrap`, so `600000 ms` wraps cleanly as a single intact pill on 390px viewports.
4. **Client-Side Range Validation (`1000..600000` ms) & `NaN` Guards:**
   - `WorkflowStudioPage.tsx` (lines 129-132, 350-364) validates `Number.isNaN(val) || val < 1000 || val > 600000` and surfaces `role="alert"` (`data-testid="project-timeout-error"`) without dispatching invalid `PATCH` calls.
   - `AttachHookDialog.tsx` (lines 135-138, 476-490) validates `Number.isNaN(timeoutMs) || timeoutMs < 1000 || timeoutMs > 600000` and surfaces `role="alert"`, preventing silent native-validation blocks when `AdvancedSection` is collapsed.
   - `ProjectSettingsPage.tsx` (lines 542-551, 1706-1719) enforces the same `1000..600000` ms bounds and `Number.isNaN` checks on save and change.
   - `WorkflowStudioPage.test.tsx` (lines 590-615) and `AttachHookDialog.test.tsx` (lines 645-681) verify client-side rejection of `<1000` and `>600000` inputs and `activeOverridesCount` updates.
5. **`activeOverridesCount` Accuracy (`AttachHookDialog.tsx`):**
   - `AttachHookDialog.tsx` (line 401) now includes `(hookKind === 'agent_interceptor' && timeoutMs !== null ? 1 : 0)`, accurately incrementing the `Advanced Hook Settings` override badge when a per-hook timeout is set.
6. **Precedence Display & Neighboring Drawers (`HookPipelineRow.tsx`, `TransitionRuleCard.tsx`, `AgentDefinitionEditorDrawer.tsx`, `AiProviderEditorDrawer.tsx`):**
   - `HookPipelineRow.tsx` accurately renders `10m` (`600000` ms), `5m` (`300000` ms), `3m` (`180000` ms), and `60s` (`60000` ms) with precedence resolution (`hook override` > `project default` > `agent default`).
   - `AgentDefinitionEditorDrawer.tsx` and `AiProviderEditorDrawer.tsx` cleanly expose `1000..600000` ms bounds and `FieldHelpHint` metadata.

---

## 2. Refreshed Screenshot Inspection (`docs/qa/KAN-437/screenshots/`)

All 12 refreshed PNG screenshots from commit `87b93360` were opened and visually inspected:

1. `01-workflow-studio-default-timeout-desktop-light-1440x900.png`
   - Clean 1440x900 desktop light layout with generous whitespace and zero error banners. The `Project Default Gate Timeout` card, `600000 ms` badge, `workflow-form-control` input (`600000`), preset pills (`60s`, `3m`, `5m`, `10m`, `Inherit`), `Save` button, `Transition: In QA ========( 1 Active Hook )========> Done` rule card, `10m` pill on `QA Gatekeeper Helper`, and `Git Repository Bindings` section all align cleanly with zero clipping or overlap.

2. `01-workflow-studio-default-timeout-desktop-dark-1440x900.png`
   - Round-1 dark-mode defect is completely resolved. The `Project Default Gate Timeout` panel now renders on the dark `--bg-surface` (`#16181d`) card with crisp `--fg-primary` (`#f9fafb`) heading text `"Project Default Gate Timeout"`, legible `600000 ms` badge, high-contrast `--fg-secondary` description, and properly styled dark `--bg-surface-raised` (`#1f232b`) input (`600000`) and preset buttons. Zero clipping, overlap, or error banners.

3. `01-workflow-studio-default-timeout-tablet-768x1024.png`
   - Clean 768x1024 tablet light layout. Header actions wrap gracefully beneath the title; the `Project Default Gate Timeout` controls (`600000` input, `60s`, `3m`, `5m`, `10m`, `Inherit`, `Save`) fit on a single balanced row; `TransitionRuleCard` and `HookPipelineRow` (`10m` pill, `Fail-Closed`, `Edit`, `Detach`) render with zero overflow or clipping.

4. `01-workflow-studio-default-timeout-mobile-390x844.png`
   - Round-1 mobile defects are resolved. The `600000 ms` badge wraps cleanly onto the second line as a single unbroken pill (`600000 ms`). The `600000` `.workflow-form-control` input matches the 44px touch-target height and rounded border radius of the adjacent `60s`, `3m`, `5m`, `10m`, `Inherit`, and `Save` buttons. `TransitionRuleCard` stacks cleanly below with zero horizontal clipping or error banners.

5. `02-attach-hook-timeout-override-desktop-light-1440x900.png`
   - Clean centered modal in 1440x900 light mode. `Advanced Hook Settings` accurately displays `2 custom settings active`. The `600000` `.workflow-form-control` input matches the `Failure Policy` select styling and aligns cleanly beside `Inherit`. Below the presets (`60s`, `3m`, `5m`, `10m`), `.workflow-form-hint` (`"Override transition gate execution deadline up to 10 minutes (600,000 ms)."`) renders in crisp muted secondary typography clearly separated from `Allowed Mutable Fields`. Sticky footer (`Cancel`, `Attach Hook`) is unobstructed.

6. `02-attach-hook-timeout-override-desktop-dark-1440x900.png`
   - Clean 1440x900 dark-mode modal. `2 custom settings active` badge, `Failure Policy` select, `600000` `.workflow-form-control` input, `Inherit` and preset buttons, muted `.workflow-form-hint` caption, `Allowed Mutable Fields` checkboxes, and `Raw Execution Logs & Diagnostics` all exhibit strong WCAG AA contrast on `--bg-surface` with zero clipping or visual defects.

7. `02-attach-hook-timeout-override-tablet-768x1024.png`
   - Clean 768x1024 tablet modal layout. `2 custom settings active`, `Per-Hook Timeout Override (ms)` input (`600000`), `Inherit`, presets, muted `.workflow-form-hint`, mutable field checkboxes, and sticky footer fit comfortably with balanced margins and zero overlap.

8. `02-attach-hook-timeout-override-mobile-390x844.png`
   - Clean 390x844 mobile modal layout. The `600000` `.workflow-form-control` input and `Inherit` / `60s` / `3m` / `5m` / `10m` buttons all share consistent 44px touch-friendly heights. The muted `.workflow-form-hint` caption cleanly separates the timeout group from `Allowed Mutable Fields`, and the sticky `Cancel` / `Attach Hook` footer remains anchored without occluding controls.

9. `desktop-light-1440x900.png`
   - Clean 1440x900 desktop light workflow studio view. All cards, inputs, presets, and `10m` pill are crisp and legible with zero clipping or error banners.

10. `desktop-dark-1440x900.png`
    - Clean 1440x900 desktop dark workflow studio view. Dark-mode card surface, heading contrast, input styling, and `10m` pill are all properly themed and legible.

11. `tablet-768x1024.png`
    - Clean 768x1024 tablet light workflow studio view. Responsive spacing and card alignment are clean with zero overlap.

12. `mobile-390x844.png`
    - Clean 390x844 mobile light workflow studio view. Intact `600000 ms` pill and 44px-aligned input and buttons render cleanly with zero horizontal overflow.

---

Verdict: APPROVED

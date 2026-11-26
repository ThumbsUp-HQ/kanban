# UI Specialist Review (Round 3): KAN-529 (`[UX-SIMPLIFY][ADMIN-OPS-MCP] Low Contrast on Import Source Selection Tabs (Light Mode)`)

**Scope Reviewed:** Branch `fix/KAN-529-import-tabs-contrast` at commit `2498f570`, auditing `docs/qa/KAN-529/git-diff.patch`, `kanban/web/src/features/admin-imports/PlaneImportStudio.css`, `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`, `kanban/web/src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx`, `kanban/web/src/styles/theme.css`, `docs/qa/KAN-529/unit-test-results.txt`, and `docs/qa/KAN-529/build-check.txt`.

---

## 1. Diff Cleanliness (`docs/qa/KAN-529/git-diff.patch`)

- `docs/qa/KAN-529/git-diff.patch` is strictly scoped to the 3 expected files:
  1. `kanban/web/src/features/admin-imports/PlaneImportStudio.css`
  2. `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`
  3. `kanban/web/src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx`
- All hardcoded low-contrast hex and rgba values have been replaced with semantic theme tokens across tabs, dropzone, textarea, stat cards, diff cards, alerts, warnings, buttons, and progress bar.
- Mobile responsiveness remains intact (`flex-wrap: wrap;` on `.kb-plane-mode-row` and `padding: 16px;` on `.kb-plane-import-container` under `@media (max-width: 768px)`).

---

## 2. WCAG 2.1 AA Contrast Across All Three Theme Scopes

Contrast verified against `kanban/web/src/styles/theme.css` in `:root` (Light), `[data-theme="dark"]`, and `@media (prefers-color-scheme: dark)` (`:root:not([data-theme="light"])`):

- **Active Import Source & Mode Tabs (`.kb-plane-mode-active`, `.kb-plane-mode-active:hover`):**
  - Uses `background-color: var(--bg-accent-subtle)`, `border-color: var(--badge-fg)`, `color: var(--badge-fg)`, `font-weight: 600`.
  - **Light (`:root`):** `#2563eb` on `#eff6ff` = **4.75:1** (>= 4.5:1 normal text); border `#2563eb` on `#ffffff` = **5.17:1** (>= 3:1 UI component).
  - **Dark (`[data-theme="dark"]` & `prefers-color-scheme: dark`):** `#93c5fd` on `rgba(37, 99, 235, 0.2)` over `#16181d` (`#192746`) = **8.20:1** and over `#0f1115` (`#142140`) = **~8.77:1**.
- **Inactive Tabs (`.kb-plane-mode-btn` & `:hover`):**
  - **Light:** `--fg-secondary` (`#4b5563`) on `--bg-surface-raised` (`#ffffff`) = **7.24:1**; hover `--fg-primary` (`#111827`) on `--bg-hover` (`#f1f3f5`) = **~15.8:1**.
  - **Dark (`[data-theme="dark"]` & `prefers-color-scheme: dark`):** `--fg-secondary` (`#9ca3af`) on `--bg-surface-raised` (`#1f232b`) = **5.45:1**; hover `--fg-primary` (`#f9fafb`) on `--bg-hover` (`#262b35`) = **~13.5:1**.
  - **Touch Targets:** `min-height: 44px` on `.kb-plane-mode-btn` and `.kb-plane-btn`.
- **Alerts, Warnings & Action Buttons:**
  - `.kb-plane-warnings-box` / `.kb-plane-warnings-title` / `.kb-plane-warnings-list`: `--warn-fg` on `--warn-bg` = **8.21:1** (Light) and **~12.5:1** (Dark and `prefers-color-scheme: dark`).
  - `.kb-plane-alert-error`: `--danger-fg` on `--danger-bg` = **~8.35:1** (Light) and **~11.4:1** (Dark and `prefers-color-scheme: dark`).
  - `.kb-plane-alert-success`: `--text-success` on `--bg-success-subtle` = **5.24:1** (Light) and **5.13:1** (Dark and `prefers-color-scheme: dark`).
  - `.kb-plane-btn-primary` & `.kb-plane-btn-execute`: `--accent-primary-fg` (`#ffffff`) on `--accent-primary` = **6.70:1** (Light and `prefers-color-scheme: dark`) and **5.17:1** (`[data-theme="dark"]`).

---

## 3. ARIA Semantics, Keyboard Focus & Activation

- **Import Source Selector (`kanban/web/src/features/admin-imports/PlaneImportStudio.tsx` lines 400-459):**
  - Container `[data-testid="source-selector-bar"]` declares `role="group"` and `aria-label="Import source"`.
  - All 4 source buttons (`Plane`, `Jira`, `GitHub Issues`, `Linear`) are native `<button type="button">` elements with `aria-pressed={source === '...'}`.
- **Step 1 Input Mode Selector (`kanban/web/src/features/admin-imports/PlaneImportStudio.tsx` lines 478-501):**
  - Container declares `role="group"` and `aria-label="Input mode"`.
  - Both mode buttons (`mode-upload-btn`, `mode-paste-btn`) are native `<button type="button">` elements with `aria-pressed={inputMode === '...'}`.
- **Test Verification (`kanban/web/src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx`):**
  - Verifies CSS semantic token bindings and responsive rules, Light/Dark tab switching, `role="group"`, `aria-label`, `aria-pressed` toggles, `focus()`, `document.activeElement`, and click/keyboard button activation across both tab groups.

---

## 4. Unit Tests, Coverage & Build Checks

- `docs/qa/KAN-529/unit-test-results.txt`: **17/17** tests passed in `kanban/web/src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx` (`Exit code: 0`), with v8 coverage on `PlaneImportStudio.tsx` at **100% Stmts / 95.36% Branch / 100% Funcs / 100% Lines**.
- `docs/qa/KAN-529/build-check.txt`: `pnpm tsc --noEmit`, `eslint . --max-warnings 0`, `vite build`, and `uv run python -m scripts.check_no_dashes --all` all passed (`Exit code: 0`).

Verdict: APPROVED

# Message to Reality-Checker for KANBA-190

## Overview & Scope Summary
Ticket: `KANBA-190` ([KB-UX-CSS])
Focus: Fix Dark/Light Theme Contrast on Admin Auth Drawer, Define Missing CSS Classes, and Audit All Undefined CSS Variables Across Web UI.

## Scoped Requirements Matrix & Forensic Proofs
1. **WCAG AA / AAA Contrast on Admin Auth Drawer (`/admin/auth`):**
   - Remediation:
     - `.auth-presets-bar` and `.auth-advanced-accordion` set to recessed dark tray `background: var(--bg-canvas); border: 1px solid var(--border-subtle);` (`#0f1115` on `#16181d` drawer in Dark Mode; `#f7f8fa` on `#ffffff` in Light Mode).
     - `.auth-preset-btn` set to `background: var(--bg-surface-raised); color: var(--fg-primary); border: 1px solid var(--border-strong);` providing `15.0:1` WCAG AAA contrast ratio in Dark Mode (`#f9fafb` on `#1f232b`) and `17.7:1` in Light Mode (`#111827` on `#ffffff`).
     - Active preset `.auth-preset-btn--active` set to `background: var(--accent-primary); color: var(--accent-primary-fg); border-color: var(--accent-primary);`.
     - Active tab `.auth-tab-btn--active` and primary badge `.auth-badge-primary` set to `color: var(--focus-ring);` (`#3b82f6` in Dark Mode, `#2563eb` in Light Mode), achieving `>= 4.8:1` WCAG AA contrast against dark backgrounds.
   - Proof: `docs/qa/KANBA-190/computed-styles-dark-mobile.json` and annotated Playwright screenshots in `docs/qa/KANBA-190/screenshots/`.

2. **Mobile (390x844) Viewport Horizontal Responsiveness:**
   - Remediation: In `adminAuth.css` under `@media (max-width: 767px)`:
     - `.auth-editor-prop-row { flex-direction: column; align-items: stretch; gap: var(--space-2, 8px); min-height: var(--prop-row-h, 38px); }`
     - `.auth-editor-label { width: 100%; min-width: 0; }`
     - `.auth-editor-input-group { width: 100%; min-width: 0; }`
     - `.auth-editor-input-group .auth-editor-input { flex: 1 1 0; min-width: 0; }`
     - `.auth-editor-input-group .auth-btn-secondary { flex-shrink: 0; }`
   - Proof: `admin-auth-drawer-mobile-dark.png` and `admin-auth-drawer-mobile-light.png` in `docs/qa/KANBA-190/screenshots/`.

3. **Complete CSS Class Definitions in `adminAuth.css`:**
   - Defined all missing classes referenced in `AuthStudioPage.tsx` and `AuthCardEditorDrawer.tsx`:
     - `.auth-success-banner`
     - `.auth-users-container`
     - `.auth-user-name-cell`
     - `.auth-user-display-name`
     - `.auth-user-handle`
     - `.auth-user-email`
     - `.auth-editor-field`
     - `.auth-editor-required`
     - `.auth-empty-state`
     - `.auth-panel`
     - `.auth-title`
     - `.auth-badge-provider--ad`, `.auth-badge-provider--active-directory`, `.auth-badge-provider--local`, `.auth-badge-provider--google`, `.auth-badge-provider--github`, `.auth-badge-provider--ldap`, `.auth-badge-provider--oauth` with theme-aware tokens.
   - Proof: Verified by `src/styles/__tests__/cssTokensAudit.test.ts` (test case 2).

4. **100% Canonical CSS Tokens Audit Gate Across All 55 Web UI Stylesheets:**
   - `base.css` configured with `color-scheme: light` and `color-scheme: dark` + `button, input, select, textarea { color: inherit; font-family: inherit; }`.
   - `spacing.css` expanded with non-color design tokens (`--radius-full`, `--text-xs` through `--text-2xl`, `--font-medium`, `--font-semibold`, `--scrim-bg`, `--shadow-sm` through `--shadow-xl`, `--gate-snapback-*`).
   - Replaced all undefined variables across 28 stylesheets with canonical `theme.css` / `tokens.css` / `spacing.css` tokens.
   - Preserved `StandaloneStatusPanel.css` per swarm contract.
   - Proof: `cssTokensAudit.test.ts` scans all `.css` files under `kanban/web/src/` and verifies 0 undefined `var(--*)` references.

5. **Automated Validation Results:**
   - Unit tests: `vitest run` on `cssTokensAudit.test.ts`, `theme.test.ts`, `tokens.test.ts`, and `AuthCardEditorDrawer.test.tsx` passed (42 of 42 tests passing). Raw log in `docs/qa/KANBA-190/unit-test-results.txt`.
   - Build checks: `typecheck`, `lint` (0 warnings), and `build` clean exit code 0. Raw log in `docs/qa/KANBA-190/build-check.txt`.
   - Dash compliance: `scripts.check_no_dashes --all` passed with exit code 0.

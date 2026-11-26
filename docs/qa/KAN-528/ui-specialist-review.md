# UI Specialist Review: KAN-528

**Scope Reviewed (Commit `d33dcadd`):**
- `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`
- `kanban/web/src/features/admin-imports/PlaneImportStudio.css`
- `kanban/web/src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx`
- `docs/qa/KAN-528/git-diff.patch`
- `docs/qa/KAN-528/unit-test-results.txt`
- `docs/qa/KAN-528/build-check.txt`
- `docs/qa/KAN-528/screenshots/*.png` (all 8 Light and Dark screenshots across 1440x900, 768x1024, and 390x844)

## 1. Round-1 Remediation Verification
1. **Field Proximity & `(?)` Trigger Alignment (`PlaneImportStudio.css`):**
   - `.kb-plane-field` and `.kb-plane-input-control` now share `max-width: 450px; width: 100%;` (matching `.kb-plane-export-form`).
   - Visual verification in `docs/qa/KAN-528/screenshots/desktop-light-1440x900.png`, `desktop-dark-1440x900.png`, `tablet-768x1024.png`, and `tablet-dark-768x1024.png` confirms the `(?)` triggers for `Target Workspace Slug`, `Target Project Key`, and `Custom User Mapping JSON` sit directly aligned with the right edge of their 450px inputs/textarea rather than drifting to the far right edge of `.kb-plane-section`.
   - Visual verification in `docs/qa/KAN-528/screenshots/popover-open-light-1440x900.png` and `popover-open-dark-1440x900.png` confirms the `Target Workspace Slug` `FieldHelpHint` dialog opens directly above its field trigger in both Light and Dark themes.
2. **Label Wrapping & 390px Mobile Layout (`PlaneImportStudio.css`):**
   - `.kb-plane-field-label` enforces `flex-wrap: nowrap; justify-content: space-between; gap: 8px;`, `.kb-plane-field-label > span` sets `flex: 1 1 auto; min-width: 0;`, and `.kb-plane-field-label .field-help-hint` sets `flex-shrink: 0;`.
   - `@media (max-width: 480px)` enforces `max-width: 100%; width: 100%;`, `min-height: 44px; height: 44px;`, and `font-size: 16px;` on `.kb-plane-input-control` and `.kb-plane-export-input`.
   - Visual verification in `docs/qa/KAN-528/screenshots/mobile-390x844.png` and `mobile-dark-390x844.png` confirms `Target Workspace Slug`, `Target Project Key`, and expanded `Advanced Import Options` are scrolled into view: long label text wraps cleanly inside its `<span>` while the `(?)` trigger remains aligned beside it with zero orphan-line wrapping and zero horizontal overflow.

## 2. WCAG 2.1 AA Contrast & Theme Parity
- `.kb-plane-field-label` and `.kb-plane-field-helper` use `var(--kb-color-text-secondary, var(--fg-secondary))` against `var(--kb-color-bg-surface, var(--bg-surface))` (and `AdvancedSection` open `var(--bg-surface)`):
  - Light (`#4b5563` on `#ffffff`): `7.56:1` (passes >= 4.5:1).
  - `[data-theme='dark']` (`#9ca3af` on `#16181d`): `6.99:1` (passes >= 4.5:1).
  - `prefers-color-scheme: dark` (`#9ca3af` on `#16181d`): `6.99:1` (passes >= 4.5:1).
- `.kb-plane-field-error` uses `var(--danger-fg, var(--kb-color-danger, #ef4444))`: `9.56:1` in Light (`#881337` on `#ffffff`) and `12.58:1` in Dark / System-Dark (`#fecdd3` on `#16181d`).
- `.kb-plane-checkbox-label` uses `var(--fg-primary)` (`> 17:1` across all three theme modes).

## 3. CSP, ARIA/Keyboard Accessibility & Non-Behavioral Safety
- **Zero inline `style={{}}` props:** All 16 inline style props in `PlaneImportStudio.tsx` were replaced with semantic CSS classes in `PlaneImportStudio.css`.
- **ARIA & Keyboard:** `aria-describedby` links `#target-ws-slug`, `#target-proj-key`, `#import-user-mapping`, and `#export-workspace-slug` to their `*-helper` spans; `FieldHelpHint` provides `type="button"`, `aria-label`, `aria-haspopup="dialog"`, `aria-expanded`, `aria-controls`, `role="dialog"`, focus-open, Escape-dismiss with focus restoration, and Tab navigation.
- **Non-Behavioral Safety & Gates:** Zero backend/API/schema/logic changes in `docs/qa/KAN-528/git-diff.patch`. `docs/qa/KAN-528/unit-test-results.txt` reports 22/22 tests passing (`100%` statements, `95.7%` branches, `100%` functions, `100%` lines, exit code `0`). `docs/qa/KAN-528/build-check.txt` reports `pnpm tsc --noEmit`, `pnpm run lint` (`--max-warnings 0`), `pnpm run build`, and `uv run python -m scripts.check_no_dashes --all` all passing with exit code `0`.

Verdict: APPROVED

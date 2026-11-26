# UI Specialist Review: KAN-444 (`[UX-SIMPLIFY][THEME-CADENCE] Hardcoded White Background and Dark Text in Media Viewport`)

- **Commit:** `368e31a6`
- **Reviewer Role:** Clean-Room UI Specialist (`.agents/agents/ui-designer.md`)
- **Files Audited:**
  - `kanban/web/src/editor/media/MediaViewport.css`
  - `kanban/web/src/editor/__tests__/MarkdownEditor.test.tsx`
  - `kanban/web/src/styles/theme.css`
  - `docs/qa/KAN-444/git-diff.patch`
  - `docs/qa/KAN-444/unit-test-results.txt`
  - `docs/qa/KAN-444/build-check.txt`
  - `docs/qa/KAN-444/screenshots/{desktop-light-1440x900.png, desktop-dark-1440x900.png, tablet-768x1024.png, mobile-390x844.png}`

---

## 1. Semantic Token & Theme Cadence Verification

Audited `kanban/web/src/editor/media/MediaViewport.css` against `kanban/web/src/styles/theme.css` across `:root` (Light), `[data-theme="dark"]`, and `@media (prefers-color-scheme: dark)`:

1. **Container & Surface Hierarchy:**
   - `.media-viewport` consumes `border: 1px solid var(--border-subtle)`, `background-color: var(--bg-surface)`, and `color: var(--fg-primary)` with no hardcoded white `#ffffff` or slate fallback overrides.
   - `.media-viewport__skeleton` uses `background: var(--bg-surface-raised)` and `color: var(--fg-muted)`.
2. **Backdrop Canvas Presets:**
   - `.media-bg--theme` pairs `background-color: var(--bg-surface)` with `color: var(--fg-primary)`.
   - Explicit contrast overrides `.media-bg--light` (`#ffffff` / `#111827`) and `.media-bg--dark` (`#0f172a` / `#f8fafc`) explicitly pair background and foreground values so inherited text or `currentColor` SVG strokes remain legible regardless of active app theme.
   - `.media-bg--checkerboard` replaces hardcoded `#f1f5f9` / `#cbd5e1` with `background-color: var(--bg-hover)`, `color: var(--fg-primary)`, and `repeating-conic-gradient(var(--border-subtle) 0% 25%, var(--bg-hover) 0% 50%)`.
3. **Controls Bar, Interactive Hover & Alt Badge:**
   - `.media-viewport__controls` removes hardcoded `rgba(15, 23, 42, 0.85)` / `rgba(255, 255, 255, 0.15)` / `#ffffff` and binds directly to `var(--bg-surface-raised)`, `var(--border-subtle)`, and `var(--fg-primary)`.
   - `.media-btn:hover` replaces hardcoded `rgba(255, 255, 255, 0.12)` with `background-color: var(--bg-hover)` and `color: var(--fg-primary)`.
   - `.media-alt-badge` eliminates hardcoded `rgba(15, 23, 42, 0.75)` and `#f8fafc` in favor of `background-color: var(--bg-surface-raised)`, `border: 1px solid var(--border-subtle)`, and `color: var(--fg-primary)`.
4. **Air-Gap Card & Lightbox Scrim:**
   - `.media-airgap-placeholder`, `__badge`, and `__host` cleanly reference `var(--bg-surface-raised)`, `var(--bg-surface)`, `var(--border-subtle)`, `var(--fg-muted)`, `var(--fg-primary)`, and `var(--fg-secondary)`.

---

## 2. WCAG AA Contrast Audit (>= 4.5:1)

All semantic pairings defined in `theme.css` and applied in `MediaViewport.css` exceed WCAG AA (4.5:1 for normal text):

| Surface / Element | Light Mode Pairing & Contrast | Dark Mode Pairing & Contrast | Result |
| :--- | :--- | :--- | :--- |
| `.media-viewport` / `.media-bg--theme` | `#111827` on `#ffffff` (~17.7:1) | `#f9fafb` on `#16181d` (~17.0:1) | PASS |
| `.media-viewport__controls` / `.media-alt-badge` | `#111827` on `#ffffff` (~17.7:1) | `#f9fafb` on `#1f232b` (~15.1:1) | PASS |
| `.media-btn:hover` | `#111827` on `#f1f3f5` (~15.9:1) | `#f9fafb` on `#262b35` (~13.6:1) | PASS |
| `.media-bg--checkerboard` | `#111827` on `#f1f3f5` / `#e5e7eb` (>= 14.3:1) | `#f9fafb` on `#262b35` / `#2d333f` (>= 12.1:1) | PASS |
| `.media-bg--light` (explicit preset) | `#111827` on `#ffffff` (~17.7:1) | `#111827` on `#ffffff` (~17.7:1) | PASS |
| `.media-bg--dark` (explicit preset) | `#f8fafc` on `#0f172a` (~17.1:1) | `#f8fafc` on `#0f172a` (~17.1:1) | PASS |
| `.media-viewport__skeleton` / `.media-airgap-placeholder` | `#525866` on `#ffffff` (~7.1:1) | `#94a3b8` on `#1f232b` (~6.1:1) | PASS |
| `.media-airgap-placeholder__host` | `#4b5563` on `#ffffff` (~7.5:1) | `#9ca3af` on `#1f232b` (~6.2:1) | PASS |

---

## 3. Visual & Responsive Screenshot Audit

Inspected all four rendered Playwright screenshots in `docs/qa/KAN-444/screenshots/`:

1. **`desktop-light-1440x900.png`**: Real Mermaid diagram renders crisply inside `MediaViewport` on light `#ffffff` surface. `Alt: Mermaid diagram` badge and floating `.media-viewport__controls` use light raised surface styling with high-contrast dark typography (`#111827`) and subtle border (`#e5e7eb`). Zero error banners or toasts.
2. **`desktop-dark-1440x900.png`**: Dark theme (`#16181d` surface, `#1f232b` raised controls and alt badge, `#f9fafb` foreground text, `#2d333f` subtle borders) applies uniformly across the viewport, alt badge, floating control bar, and Mermaid diagram nodes. Zero error banners or toasts.
3. **`tablet-768x1024.png`**: Responsive header and single-column issue layout adapt cleanly. Floating controls and `Tap to pan & zoom` pill sit side-by-side cleanly without overlapping. Zero error banners or toasts.
4. **`mobile-390x844.png`**: Mobile navigation header, issue metadata, and `MERMAID` card scale within the 390px viewport with zero horizontal overflow and zero error banners or toasts.

---

## 4. Test & Build Verification

- **`docs/qa/KAN-444/unit-test-results.txt`**: `src/editor/__tests__/MarkdownEditor.test.tsx` passed 4/4 tests.
- **`docs/qa/KAN-444/build-check.txt`**: `eslint . --max-warnings 0` passed with zero warnings, and `tsc -b && vite build` succeeded cleanly (765 modules transformed).
- **`docs/qa/KAN-444/git-diff.patch`**: Confirmed changes outside `docs/qa/` are strictly scoped to `MediaViewport.css` and `MarkdownEditor.test.tsx`.

Verdict: APPROVED

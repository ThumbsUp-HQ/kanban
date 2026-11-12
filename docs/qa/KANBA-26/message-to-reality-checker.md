# Reality-Checker QA Dossier: KANBA-26 (KB-P3-30)

## Ticket Overview
- Ticket ID: KANBA-26 (Authoritative spec: `docs/tickets/KB-P3-30.md`)
- Title: [Phase 3 / Frontend] Breathable design tokens, light/dark theming & self-hosted fonts
- Worktree: `/tmp/kb-wt-KANBA-26`
- Branch: `feat/KANBA-26`
- Implementing Author: `builder-17`

---

## 1. Traceability & Definition of Done Verification

All 9 scoped technical actions in `docs/tickets/KB-P3-30.md` have been implemented:

1. **S6.1 Design Tokens (`kanban/web/src/styles/tokens.css`):**
   - Implements verbatim all 16 variables from Section 6.1 of the Product Spec.
   - Includes typography, shell/board dimensions, card padding/gaps, drawer sizing, and editorial spacing.
   - Banned compact/dense variants verified by AST inspection and Vitest test suites.

2. **Supplemental Spacing Scale (`kanban/web/src/styles/spacing.css`):**
   - Implements semantic scale `--space-0` through `--space-16`, radius tokens, elevation tokens, tap targets (`--tap-min: 44px`), and focus ring (`--focus-ring-w: 2px`).
   - Strictly enforces zero dense/compact scale variants.

3. **Semantic Theme Hex Colors (`kanban/web/src/styles/theme.css`):**
   - Declares light theme on `:root`, dark theme on `:root[data-theme="dark"]`, and system preference defaults.
   - Contrast verified via Vitest: `--fg-primary` exceeds 7:1 (AAA), secondary/accent/warning/danger exceed 4.5:1 (AA) in both light and dark themes.
   - Includes all 6 S8.1 sticky palette tones (`amber`, `mint`, `sky`, `lavender`, `coral`, `slate`).

4. **Self-Hosted Variable Fonts (`kanban/web/src/styles/fonts.css`):**
   - Vendored `InterVariable.woff2` and `JetBrainsMonoVariable.woff2` under `kanban/web/public/fonts/`.
   - Vendored upstream `OFL-Inter.txt` and `OFL-JetBrainsMono.txt` licenses.
   - Configured `license-allowlist.toml` for vendored fonts (`make license` exits 0 with 0 violations).
   - Local `@font-face` definitions with zero external network queries (`font-src 'self'`).

5. **Typography & Base Reset (`kanban/web/src/styles/base.css`):**
   - Configured `html { font-size: 100%; }`, body reset, line-height 1.73, tabular-nums for monospace, and reduced-motion guard.

6. **Unified CSS Entrypoint (`kanban/web/src/styles/index.css`):**
   - Imports stylesheets in strict order: fonts, tokens, spacing, theme, base.

7. **Breakpoints Module (`kanban/web/src/styles/breakpoints.ts`):**
   - Defines canonical breakpoints `mobileMax: 767`, `tabletMax: 1279`.
   - Exports typed `useBreakpoint()` hook with dynamic `matchMedia` event listeners and proper unmount cleanup.

8. **Theme Provider (`kanban/web/src/theme/ThemeProvider.tsx`):**
   - Manages `'light' | 'dark' | 'system'` state, synchronized to `document.documentElement.dataset.theme`.
   - Hostile input defense in `sanitizeTheme()` catches corrupted storage values without throwing exceptions.

9. **Token Story Component (`kanban/web/src/dev/TokenStory.tsx` + `TokenStory.css`):**
   - Mounted at `/__dev/tokens` when `VITE_ENABLE_STORY=1` or dev mode.
   - Displays S6.1 token table, spacing ruler with visual cards/lanes/rows, semantic & sticky swatches, prose and mono key KAN-142, and accessible theme switcher radiogroup.

---

## 2. Verification Artifacts & Test Results

The following raw proof artifacts are populated in `docs/qa/KANBA-26/`:

1. `unit-test-results.txt`:
   - 109/109 Vitest unit tests passed (100% statement, branch, function, and line coverage across all files in `src/`).
2. `build-check.txt`:
   - `typecheck` (`tsc -b --noEmit`): Clean (0 errors).
   - `lint` (`eslint . --max-warnings 0`): Clean (0 warnings).
   - `build` (`vite build`): Clean production bundle with SRI hashes and precompressed `.br` and `.gz` assets.
3. `e2e-results.txt`:
   - 12/12 Playwright tests passed across `desktop` (1440x900), `tablet` (1024x768), and `mobile` (390x844).
4. `computed-styles-{desktop,tablet,mobile}.json`:
   - Validates live browser computed styles for card padding (`16px 18px`), card gap (`12px`), lane width (`324px`), lane gutter (`20px`), list row (`46px`), and property row (`38px`).
5. `screenshots/`:
   - 12 annotated PNG screenshots covering all 4 test scenarios across desktop, tablet, and mobile.
   - Inspected via `read_file` to confirm all red boxes and numbered badges tightly frame their targets with zero scroll clipping.
6. `dependency-evaluation.md`:
   - Complete OFL-1.1 license assessment, exact SHA-256 hashes for font binaries, and signed-off evaluations from `arch-reviewer` (#30), `sec-eng` (#29), and `qa-eng` (#28).
7. `ui-specialist-review.md`:
   - Verbatim audit and `APPROVED` verdict from `@ui-specialist` (message #172).
8. `git-diff.patch`:
   - Full unified patch against `origin/main` (excluding `dist/`, including font binaries and allowlist).

---

## 3. Dash & Invariant Compliance

- Unicode Dashes: Zero `U+2014` or `U+2013` dashes exist across all source files, documentation, and commit messages (validated via `check_no_dashes.py`).
- License Gate: `make license` exits 0 with 0 violations.
- Security Invariants: CSP `font-src 'self'`, no style injection, hostile storage sanitization, safe keyboard accessibility.

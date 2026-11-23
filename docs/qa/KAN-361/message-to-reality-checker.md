# Evidence Packet & Verification Hand-off: KAN-361

- **Ticket ID:** KAN-361
- **Title:** [KB-A11Y-CONTRAST-TOKENS] Audit and Eliminate Hardcoded Non-Token Hex Values in Flow Analytics, Burndown SVG Charts, and Status Badges
- **Author / Implementer:** `b-kan361`
- **Branch:** `feat/KAN-361`
- **Audit Target:** `reality-checker` (Forensic QA Gate)
- **Target Verification Level:** Grade-A READY Certification

---

## 1. Executive Summary

Ticket KAN-361 eliminates hardcoded non-token hex colors and introduces non-color series differentiation across Flow Analytics, Burndown SVG charts, and status badges:
1. **Canonical Palette & High-Contrast Tokens (`theme.css`):**
   - Added canonical tokens `--chart-line-1` (#2563eb light / #60a5fa dark) and `--chart-line-2` (#94a3b8 light / #cbd5e1 dark) to `:root`, `[data-theme="dark"]`, and `@media (prefers-color-scheme: dark)`.
   - Added dark mode high-contrast border overrides (`--state-*-border: rgba(..., 0.45)`) to guarantee >= 3:1 graphical object boundary contrast against dark canvas/surface backgrounds.
2. **Hardcoded Hex Color Elimination (`FlowAnalyticsPage.css` & Charts):**
   - Refactored `.kb-badge-p50`, `.kb-badge-p85`, and `.kb-badge-p95` to utilize semantic CSS variables (`var(--chart-line-1)`, `var(--warn-fg)`, `var(--ok-fg)`).
   - Replaced all raw SVG strokes and fills across `CycleBurndownChart.tsx`, `AgingWipChart.tsx`, `CycleTimeScatterChart.tsx`, and `CfdAreaChart.tsx` with semantic CSS variables (`var(--chart-line-1)`, `var(--chart-line-2)`, `var(--danger-fg)`, `var(--warn-fg)`, `var(--ok-fg)`, `var(--state-*-fg)`). Zero raw hex values remain in chart presentation.
3. **Non-Color Series Differentiation (WCAG 1.4.1):**
   - Sprint Cycle Burndown chart contrasts the ideal target trajectory (dashed stroke `6 4`, stroke width 2) against the actual remaining scope (solid stroke width 2.5) with anchored circular markers on each data point.
   - Cycle time scatterplot percentile threshold lines use distinct stroke dash arrays (`4 4` for P50, `6 4` for P85, `2 2` for P95). Exceeded items feature enlarged radii, thicker strokes, and dashed perimeter styling.
   - Aging WIP active items exceeding P85 threshold feature scaled marker radius, dashed styling, bold typography, and explicit `(EXCEEDS p85)` text cues.
   - Status badges combine Unicode emoji icons, SVG progress rings, and text labels for complete non-color status identification.
4. **Comprehensive Automated Test Gate (`analyticsContrastAudit.test.tsx`):**
   - Created `kanban/web/src/features/a11y/analyticsContrastAudit.test.tsx` with 9 automated tests implementing all 3 required test cases with 100% statement/line/function coverage on modified components.
   - All 28 tests across `analyticsContrastAudit.test.tsx`, `cssTokensAudit.test.ts`, and `FlowAnalyticsPage.test.tsx` pass.

---

## 2. Deliverables & Artifact Index

1. **Source Code Modifications:**
   - `kanban/web/src/styles/theme.css`
   - `kanban/web/src/features/analytics/FlowAnalyticsPage.css`
   - `kanban/web/src/features/analytics/charts/CycleBurndownChart.tsx`
   - `kanban/web/src/features/analytics/charts/AgingWipChart.tsx`
   - `kanban/web/src/features/analytics/charts/CycleTimeScatterChart.tsx`
   - `kanban/web/src/features/analytics/charts/CfdAreaChart.tsx`

2. **Feature Unit Tests:**
   - `kanban/web/src/features/a11y/analyticsContrastAudit.test.tsx` (9 tests covering SVG tokens, non-color differentiation, and badge contrast)
   - `kanban/web/src/styles/__tests__/cssTokensAudit.test.ts` (6 tests validating 100% canonical CSS variable resolution)
   - `kanban/web/src/features/analytics/__tests__/FlowAnalyticsPage.test.tsx` (13 regression tests)

3. **QA & Specialist Review Documentation:**
   - `docs/qa/KAN-361/api-specialist-review.md` (APPROVED by `@backend-architect`)
   - `docs/qa/KAN-361/ui-specialist-review.md` (APPROVED by `@ui-designer`)
   - `docs/qa/KAN-361/build-check.txt` (Typecheck, lint, and build verification log)
   - `docs/qa/KAN-361/unit-test-results.txt` (Vitest run log with 28 passing tests)
   - `docs/qa/KAN-361/git-diff.patch` (Verbatim git diff patch)
   - `docs/qa/KAN-361/changed-files-manifest.txt` (SHA-256 checksum manifest)
   - `docs/qa/KAN-361/screenshots/` (5 responsive screenshots covering desktop light/dark, tablet, and mobile portrait/landscape)

---

## 3. Verification Commands for Reality Checker

```bash
# 1. Verify changed files integrity
sha256sum -c docs/qa/KAN-361/changed-files-manifest.txt

# 2. Verify zero em-dashes / en-dashes
uv run python -m scripts.check_no_dashes --all

# 3. Execute unit tests
pnpm --dir kanban/web exec vitest run src/features/a11y/analyticsContrastAudit.test.tsx src/styles/__tests__/cssTokensAudit.test.ts src/features/analytics/__tests__/FlowAnalyticsPage.test.tsx

# 4. Typecheck, lint, and build
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build
```

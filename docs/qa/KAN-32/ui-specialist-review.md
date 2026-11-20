# UI Specialist Review: KAN-32

**Ticket ID:** KAN-32  
**Title:** [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, and Publish Step-by-Step [Guide] How to Use Custom Fields (3 Problems)  
**Branch:** `feat/KAN-32`  
**Commit:** `77044d53`  
**Reviewer:** ui-spec-2 (Clean-Room UI Specialist)  
**Date:** 2026-11-20  
**Status:** `STATUS: APPROVED`  

---

## 1. Executive Summary

A clean-room UI and UX audit was performed on ticket KAN-32 (`feat/KAN-32` commit `77044d53`). The implementation introduces fail-closed user experience gating for isolated `nsjail` execution when running in Standalone mode (`tier_b_sandbox_available == False`), preventing confusing runtime 422 execution failures by proactively badging, disabling, and guiding users directly in the Web UI.

The UI changes are thoroughly tested, WCAG AA accessible, strictly compliant with design tokens, free of inline styles, and contain zero em-dashes or en-dashes.

---

## 2. Detailed UI/UX Audit Findings

### 2.1 Standalone Guidance Callout (`CustomFieldDefinitionEditor.tsx`)
- **Visual Presentation & Ergonomics:** When `isTierBAvailable` evaluates to `false` (Standalone mode), an informative guidance callout (`.custom-field-standalone-callout`, `data-testid="standalone-guidance-callout"`) renders at the top of the editor.
- **Content & Microcopy:** Plain ASCII copy communicates capability tier boundaries without tech jargon:
  `Standalone Mode Active: Scalar (<1ms), Formula (<5ms), and WebAssembly (<25ms) work out of the box in Standalone mode.`
- **Actionable Links:** Provides clear hyperlinks to documentation (`[Guide] How to Use Custom Fields ->` linking to `/docs/Guide-Custom-Fields`) and infrastructure promotion (`Promote to Multi-Container ->` linking to `/admin/standalone`), preventing dead-ends.
- **Accessibility:** Uses semantic `role="status"` and accessible aria markings (`aria-hidden="true"` on the emoji icon `💡`).

### 2.2 Disabled and Badged `nsjail` Selection Controls
- **Form Select Elements:**
  - In `field-flavor-select`, the `nsjail` option is disabled with clear text: `Isolated Sandbox (nsjail) [Multi-Container Compose Required]`.
  - In `field-tier-select`, the `nsjail` option is disabled with clear text: `nsjail (Isolated Container Sandbox) [Multi-Container Compose Required]`.
  - Prevents form submission in an invalid state, eliminating 422 API errors before they can occur.
- **Flavor Decision Matrix (`FlavorDecisionMatrix.tsx`):**
  - The `nsjail` card is badged with `.flavor-matrix-unavailable-badge` displaying `Multi-Container Compose Required`.
  - The select button is disabled with an explanatory tooltip, guiding the administrator to choose `scalar`, `formula`, or `wasm`.
- **Preset Gallery (`PresetGallery.tsx`):**
  - Presets requiring nsjail execution (`total-project-issues` and `git-pr-link`) render with `.preset-badge--unavailable` displaying `Multi-Container Compose Required`.
  - The "Use Preset" button is disabled (`use-preset-btn-total-project-issues`, `use-preset-btn-git-pr-link`).
  - Presets running on scalar, formula, or wasm remain fully enabled and functional.

### 2.3 Pre-Existing `nsjail` Field Inspection
- **Warning Banner (`.custom-field-warning-banner`):** When an administrator inspects an imported or pre-existing custom field configured with `tier === 'nsjail'` in Standalone mode, an alert banner (`data-testid="preexisting-nsjail-warning-banner"`, `role="alert"`) displays:
  `Execution Unavailable in Standalone: This pre-existing custom field uses an isolated nsjail sandbox, which cannot execute in standalone mode. To run or test this field, promote this instance to a multi-container compose deployment or reassign it to WebAssembly or Formula.`
- **Metadata Editing Preservation:** The UI permits updating metadata (name, description, enabled) without blocking saves on pre-existing fields, matching backend service behavior.

### 2.4 Design System, CSS Tokens & CSP Compliance
- **Design Tokens:** All styles in `custom-fields.css` exclusively utilize canonical tokens from `theme.css`:
  - Backgrounds: `var(--bg-surface-raised)`, `var(--warn-bg)`
  - Borders: `var(--border-subtle)`, `var(--border-warning)`
  - Accents: `var(--accent-primary)`
  - Typography: `var(--text-xs)`, `var(--text-sm)`, `var(--leading-prose)`, `var(--font-semibold)`
  - Spacing: `var(--space-1)`, `var(--space-2)`, `var(--space-3)`
- **CSP Compliance:** Zero inline `style={...}` JSX attributes (`style-src 'self'` compliant). Verified by `src/styles/__tests__/cssTokensAudit.test.ts` (4/4 passed).
- **Contrast & Hierarchy:** Warning badges and callouts provide strong, legible contrast exceeding WCAG AA minimums (>= 4.5:1).

---

## 3. Automated Test Verification

All unit test suites executed cleanly in clean-room verification:
1. `src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx`: 40/40 tests passed.
2. `src/features/custom-fields/__tests__/PresetGallery.test.tsx`: 8/8 tests passed.
3. Total TypeScript test suite: 165/165 tests passed across 10 test files (100% stmts, 95.69% branch).
4. `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 tests passed (0 inline styles).

---

## 4. Certification

The UI/UX changes in ticket KAN-32 provide clean, defensive, and user-friendly gating for standalone instances. All design system rules, accessibility standards, and test thresholds are satisfied.

**STATUS: APPROVED**

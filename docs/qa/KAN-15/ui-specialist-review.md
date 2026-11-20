# UI/UX Specialist Review: KAN-15

## Audit Metadata
- Ticket ID: KAN-15 ([KB-P3-AUDIT-09])
- Title: Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan15-rc1-825368b6`
- Target Branch: `fix/KAN-15-rc1`
- Base Commit: `5998e9ab`
- Head Commit: `82f8683d`
- STATUS: APPROVED

---

## Executive Summary
This clean-room review evaluates UI components, user assistance ergonomics, responsive behavior, accessibility (WCAG AA), interaction timing, CSP compliance, live visual proof artifacts, and RC1 formula preset AST alignment for ticket KAN-15 ([KB-P3-AUDIT-09]) on branch `fix/KAN-15-rc1` (commit `82f8683d`).

The ticket resolves all 3 scoped problems with outstanding frontend craftsmanship and solid formula execution reliability:
1. **Accessible `<FieldHelpHint />` Component (`FieldHelpHint.tsx` + `FieldHelpHint.css`):**
   - High-performance, accessible contextual popover utilizing existing `HintPortal`, `positionHint`, and `hintTiming.ts` primitives.
   - Strict CSP compliance (`style-src 'self'`): 0 inline `style={...}` JSX attributes; positioning coordinates and arrow offsets are driven purely by DOM CSS variables (`style.setProperty`).
   - Accessible interaction model: 180ms hover open delay, instantaneous 0ms keyboard `Tab` focus open, 120ms hover-bridge grace period allowing mouse traversal into the popover body without accidental dismissal, and `Escape` key dismissal with immediate focus restoration to the trigger button.
   - Comprehensive content slots: Header with Title and close button (`aria-label="Close help popover"`), plain English summary, optional definition list (`<dl>`) for valid configuration keys, formatted example snippets, warning callout blocks, and configurable `More info ->` footer documentation link (`docHref`).
   - Coarse pointer hit area: Expands to >= 44x44px under `@media (pointer: coarse)` while preserving compact desktop label alignment.
2. **Contextual Studio & Issue Rail Help Integration:**
   - 10 contextual help popovers wired across `CustomFieldDefinitionEditor.tsx` (Display Name, Identifier Slug, Field Flavor, Output Format, Format Metadata JSON, Sandbox Execution Tier, Target Scope, Credential Mode, Egress Allowlist, and Script / Formula Source).
   - 4 contextual help popovers wired across `EscalationApprovalPanel.tsx` (Target Scope, Credential Mode, Business Justification, and AAL2 Step-Up Verification).
   - Custom field row hints wired into `CustomFieldsRailSection.tsx`.
3. **4-Flavor Decision Matrix & 6-Preset Starter Gallery (`FlavorDecisionMatrix.tsx`, `PresetGallery.tsx`, `presets.ts`):**
   - Interactive 4-flavor comparison matrix evaluating latency budgets, execution tiers, and security boundaries: Scalar (<1ms), Formula (<5ms), WebAssembly (<25ms), and Project Rollup / nsjail (<=3,000ms).
   - 6 production-grade, 1-click starter presets: CVSS 3.1/4.0 Score, Total Issues in Project, Days Until Due / SLA Breach, Blocker Count, Sub-Issue Completion %, and Git PR Link Badge.
   - Non-destructive dirty-form guard: Detects unsaved editor changes before applying a preset, rendering a clear confirmation prompt and an instant undo toast strip.
4. **RC1 Formula Preset & Runtime Schema Alignment:**
   - Replaced naive regex in `kanban/custom_fields/executor.py` with bracket-, brace-, parenthesis-, and quote-aware recursive parser `_convert_js_ternary`, preventing colons inside dict literals (`{"level": ...}`) from breaking AST conversion.
   - Updated formula presets in `presets.ts` (`days-until-due-sla`, `blocker-count`, `sub-issue-completion`) to clean Python expressions referencing real runtime issue context keys (`days_until_due`, `blocker_count`, `completed_sub_issue_count`, `sub_issue_count`).
   - Verified live PostgreSQL E2E execution via `test_preset_formulas_e2e.py` reading `presets.ts` directly from disk and confirming 200 OK computed outputs with 0 NoneType or 422 errors.

---

## UI/UX & Ergonomics Audit

### 1. Contextual Assistance Ergonomics (`FieldHelpHint.tsx`)
- Trigger button uses standard accessible emoji glyph `(?)` styled with `--text-muted` transitioning smoothly to `--text-primary` on hover/focus.
- Popover container uses canonical card surface tokens (`--bg-surface`, `--border-default`, `--radius-md`, `--shadow-lg`) with high-contrast borders ensuring WCAG AA contrast (>= 4.5:1) in both Light and Dark themes.
- The 120ms bridge timer provides comfortable mouse transit from the trigger icon across the margin gap to clickable documentation links inside the popover.

### 2. Decision Matrix Usability (`FlavorDecisionMatrix.tsx`)
- Distinct cards for each flavor feature clear visual hierarchy: Flavor Name, Latency Pill Badge, Security Tier, and Recommended Use Case bullet points.
- Enables operators and developers to select the lowest privilege and lowest latency tier required for their use case without guessing.

### 3. Preset Gallery Experience (`PresetGallery.tsx`)
- 6 starter presets populate complete, valid configuration JSON and code templates matching backend validation schemas.
- Applying a preset on a clean form applies configuration instantly; on a dirty form, an accessible confirmation dialog ensures work is never unintentionally overwritten, supplemented by an instant undo strip.

### 4. Live Visual & Screenshot Artifact Verification
All 9 Playwright visual proof artifacts in `docs/qa/KAN-15/screenshots/` were audited:
- `live-kan15-field-help-popover-desktop-light.png`: Light mode popover showing readable title, definition list, and clean border contrast.
- `live-kan15-field-help-popover-desktop-dark.png`: Dark mode popover showing high-contrast text and dark surface tokens.
- `live-kan15-rail-hint-desktop-light.png`: Custom field row hint rendering in issue drawer rail section.
- `live-kan15-presets-gallery-desktop-light.png`: 6 starter preset cards showing descriptions, output formats, and 1-click apply buttons.
- `live-kan15-presets-matrix-desktop-light.png`: Light mode 4-flavor comparison matrix with latency pills.
- `live-kan15-presets-matrix-desktop-dark.png`: Dark mode 4-flavor comparison matrix with WCAG AA compliant text contrast.
- `live-kan15-presets-matrix-mobile-light.png`: Responsive mobile layout with wrapped flavor cards.
- `live-kan15-dirty-confirm-modal-desktop-light.png`: Accessible dirty-form overwrite confirmation dialog.
- `live-kan15-dirty-confirm-undo-desktop-light.png`: Instant undo toast strip with action button.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- 0 inline `style={...}` JSX attributes across all newly created and modified components.
- Verified by automated static inspection (`grep -rn "style="` yields 0 matches).

### 2. CSS Design Tokens Audit
- 100% of CSS rules reference canonical variables from `theme.css` and `tokens.css`.
- `cssTokensAudit.test.ts` passes 4/4 tests cleanly.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, CSS, tests, or documentation. All punctuation uses standard ASCII hyphens (-).
- Verified clean via `python3 -m scripts.check_no_dashes --all`.

### 4. Unit Test Coverage & Verification
- Frontend Vitest: 157/157 passed across 9 test files with 100% lines coverage on all custom fields components.
- Backend Pytest: 61/61 passed with 96% coverage on `kanban/custom_fields/executor.py`.
- Real PostgreSQL E2E test `test_preset_formulas_e2e.py` passed across all preset scenarios.
- Static checks: `tsc -b --noEmit` clean (0 errors), `eslint` clean (0 warnings), `ruff check` and `mypy` clean.

---

## Final Verification Checklist

1. [x] `<FieldHelpHint />` accessible popover component verified
2. [x] 180ms hover / 0ms focus / 120ms bridge grace / Escape dismiss interaction timing verified
3. [x] Coarse pointer >= 44x44px touch target verified
4. [x] Zero inline `style={...}` JSX attributes (100% CSP compliant)
5. [x] 10 Studio field hints + 4 Escalation hints + Issue rail row hints verified
6. [x] 4-flavor decision matrix with latency badges verified
7. [x] 6 one-click starter presets with dirty-form confirmation and undo verified
8. [x] 100% canonical design tokens verified (`cssTokensAudit.test.ts` passes 4/4)
9. [x] Strict ASCII hyphenation verified (0 em/en-dashes across codebase and docs)
10. [x] Formula presets AST parsing and runtime schema alignment verified
11. [x] Real PostgreSQL E2E test passes on all formula presets without error
12. [x] Visual evidence verified across 9 desktop, mobile, dark, light, and modal screenshots

---

## Verdict & Certification
STATUS: APPROVED

All UI layout, component accessibility, interaction ergonomics, formula preset alignment, design tokens, and unit test suites for KAN-15 RC1 have been verified and certified. Ready for dual specialist signoff and coordinator merge into `main`.

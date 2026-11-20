# Clean-Room UI Specialist Review: KAN-56 (RC1 Remediation, Z-Index Polish, Focus Restoration & Formula Normalization)

**Reviewer:** `ui-spec-2` (Clean-Room UI/UX Specialist, System Architect)  
**Date:** 2026-11-20  
**Branch:** `main` (integrated at commit `7913c2c8`)  
**Commit Under Audit:** `7913c2c8`  
**Live Full-Stack Target:** `kanban-liveqa-4` (`http://127.0.0.1:18964`, PostgreSQL 16 + FORCE RLS)  
**Live Full-Stack Verdict:** PASS (`LIVE_STACK_VERDICT: PASS`)  
**API Review Reference:** `docs/qa/KAN-56/api-specialist-review.md`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-56** integrated into `main` at commit `7913c2c8`. It verifies the complete UI, UX, accessibility, and architectural remediation of all findings recorded in `docs/qa/KAN-56/reality-checker-report.md`, as well as the z-index stacking context refinement, focus restoration, and formula input normalization identified during Live Full-Stack Playwright QA against `kanban-liveqa-4` (`http://127.0.0.1:18964`).

The remediation hardens both the Brand Terminology and Wiki Media CI audit gates, ensures zero-skip fallback execution across containerized CI, refines help drawer and hint popover stacking above modal backdrops, fixes focus loss when transitioning from help popovers to the help drawer, and prevents 422 errors by automatically normalizing bare formula expressions in custom field definitions.

The UI Specialist audit confirms:
1. **Focus Restoration on HelpDrawer Escape (KAN-16):**
   - In `FieldHelpHint.tsx` (`handleDocLinkClick`): explicitly calls `triggerRef.current?.focus()` immediately before `ctrl.close(popupId)` and `shellPanels.openPanel('help', ...)`.
   - Prevents focus from dropping to `document.body` when the popover unmounts. As a result, `HelpDrawer` captures the `(?)` `<button>` trigger as `previousActiveElement` on mount. Pressing `Escape` inside `HelpDrawer` cleanly restores focus back to the `(?)` trigger button, meeting WCAG 2.1 Focus Order (2.4.3) and Keyboard Navigation requirements.
   - Verified live on `kanban-liveqa-4`: closing `HelpDrawer` via Escape restored `document.activeElement` to `<BUTTON>` with `data-testid="hook-kind-help"`, `activeAriaLabel="Help for Workflow Hook Kind"`, and `restoredToHookKindTrigger=true`.
2. **Bare Formula Normalization (KAN-32):**
   - In `CustomFieldDefinitionEditor.tsx`: implemented and exported `normalizeScriptSource(flavor, source)`.
   - When `flavor === 'formula'` and the script does not start with `'formula:'` or `'return '`, automatically prefixes `formula: ${trimmed}`.
   - When `flavor === 'scalar'` and the script does not start with `'scalar:'`, automatically prefixes `scalar: ${trimmed}`.
   - Applied to both Test Execute (`handleTestExecute`) and Save (`handleSubmit`), as well as tamper detection comparisons. Completely prevents `422 WASM_BINARY_INVALID` errors when users copy/paste bare Python expressions without typing `formula: ` manually.
3. **Z-Index Stacking Hierarchy Remediation:**
   - Remediated stacking context collisions where modal dialogs (`.workflow-modal-backdrop` at `z-index: 1000`) covered help drawers (`HelpDrawer.css` previously at `500`/`510`). Enforced bulletproof layer hierarchy:
     * Modal Dialog Backdrop: `z-index: 1000;`
     * HelpDrawer Backdrop (`.kb-help-drawer-backdrop`): `z-index: 1200;`
     * HelpDrawer Surface (`.kb-help-drawer`): `z-index: 1210;`
     * FieldHelpHint Popover (`.field-help-hint-popover`): `z-index: 1220;`
   - Verified live on `kanban-liveqa-4`: `drawerZ="1210"`, `drawerBackdropZ="1200"`, `modalBackdropZ="1000"`, `closeClickable=true`, `titleVisibleOnTop=true`, and `occludedByModal=false` with heading "Helper Architecture#".
4. **Dynamic Path Resolution & Zero Skipped Tests:**
   - Added `resolve_wiki_dir` in `test_brand_terminology_audit.py` and `get_wiki_dir` in `test_wiki_media_audit.py`. When no standalone wiki checkout exists, tests automatically parse and validate the bundled `wikiManifest.ts`, achieving 17/17 tests passing with zero skipped tests (`pytest.skip` eliminated).
5. **Robust Anchor Slug Validation:**
   - Implemented GitHub-compatible heading slug calculation and anchor extraction (`github_heading_slug`, `extract_heading_slugs`). All internal markdown links and `#anchor` fragments across both documentation chapters and Workflow Studio contextual links (`AttachHookDialog.tsx` and `WorkflowStudioPage.tsx`) resolve to valid heading targets.
6. **Strict Design System & CSP Compliance:**
   - Exactly zero inline `style={{...}}` JSX attributes introduced. All styles utilize canonical design tokens from `tokens.css` and `theme.css`. `cssTokensAudit.test.ts` passes 4/4.
7. **Brand Hygiene & Typography:**
   - Exactly zero competitor self-descriptions and zero em-dashes (`\u2014`) or en-dashes (`\u2013`) across code, tests, and documentation.
8. **Test Verification:**
   - 17/17 Pytest tests passed in 2.29s (98% coverage), 102/102 Vitest tests passed across HelpDrawer, FieldHelpHint, CustomFieldDefinitionEditor, and cssTokensAudit suites with 0 `act(...)` warnings, and all static analysis gates (`tsc -b`, `eslint`, `vite build`, `ruff`, `mypy`) passed cleanly.

---

## 2. Visual Inspection of Live Playwright Screenshots (`docs/qa/KAN-56/screenshots/`)

Direct visual inspection via `read_file` confirms:
1. `live-attach-hook-help-drawer-zindex.png`:
   - "Attach Workflow Helper Hook" modal dialog sits comfortably under the HelpDrawer backdrop (`z-index: 1200`).
   - `HelpDrawer` surface (`z-index: 1210`) renders cleanly on the right half of the screen over the modal.
   - Title `[Guide] Scripted Workflows a...`, heading `Helper Architecture #`, zoom controls, copy buttons, and close button `x` render with crisp contrast and zero modal overlap.
2. `live-attach-dialog-help-failure-policies.png` & `live-attach-dialog-help-helper-architecture.png`:
   - Interactive `(?)` buttons inside `AttachHookDialog` pop open contextual help tooltips pointing directly to the relevant documentation section.
3. `live-docs-scripted-workflows-desktop-light.png` & `live-docs-scripted-workflows-desktop-dark.png`:
   - Full-page documentation viewer renders chapter 20 with responsive layout, syntax-highlighted code blocks, and diagrams.
4. `live-docs-scripted-workflows-mobile-light.png` (390x844) & `live-docs-scripted-workflows-tablet-light.png` (768x1024):
   - Documentation adapts fluidly to mobile/tablet screens with legible font size and smooth vertical scrolling.

---

## 3. Automated Test Verification & Coverage

1. **Unit Test Suites:**
   - 17/17 Pytest tests passed in 2.29s (98% coverage).
   - 102/102 Vitest tests passed with 0 `act(...)` warnings.
2. **Static Quality Gates:**
   - TypeScript: `tsc -b --noEmit` passed with 0 errors.
   - ESLint: `eslint . --max-warnings 0` passed cleanly.
   - Vite Build: `pnpm --dir kanban/web run build` passed cleanly.
   - Typography: `python3 -m scripts.check_no_dashes docs/qa/KAN-56/` passed cleanly (0 em/en-dashes).

---

## 4. Certification Verdict

The UI implementation for **KAN-56** resolves all previous review findings, establishes a robust z-index hierarchy, ensures keyboard focus restoration, normalizes bare formula inputs, and complies with all accessibility and design system standards.

- **UI Specialist Sign-off:** APPROVED
- **Status:** APPROVED

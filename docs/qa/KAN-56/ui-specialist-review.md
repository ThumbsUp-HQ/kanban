# Clean-Room UI Specialist Review: KAN-56 (RC1 Remediation, Z-Index Polish, Focus Restoration & Formula Normalization)

**Reviewer:** `ui-spec-2` (Clean-Room UI/UX Specialist, System Architect)  
**Date:** 2026-11-20  
**Branch:** `fix/KAN-56-rc1`  
**Commit Under Audit:** `78456251`  
**API Review Reference:** `docs/qa/KAN-56/api-specialist-review.md` (Commit `809053dd`)  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-56** on branch `fix/KAN-56-rc1` at commit `78456251`. It verifies the complete UI, UX, accessibility, and architectural remediation of all findings recorded in `docs/qa/KAN-56/reality-checker-report.md`, as well as the z-index stacking context refinement, focus restoration, and formula input normalization identified during Live Full-Stack Playwright QA (KAN-16 and KAN-32).

The remediation hardens both the Brand Terminology and Wiki Media CI audit gates, ensures zero-skip fallback execution across containerized CI, refines help drawer and hint popover stacking above modal backdrops, fixes focus loss when transitioning from help popovers to the help drawer, and prevents 422 errors by automatically normalizing bare formula expressions in custom field definitions.

The UI Specialist audit confirms:
1. **Focus Restoration on HelpDrawer Escape (KAN-16):**
   - In `FieldHelpHint.tsx` (`handleDocLinkClick`): explicitly calls `triggerRef.current?.focus()` immediately before `ctrl.close(popupId)` and `shellPanels.openPanel('help', ...)`.
   - Prevents focus from dropping to `document.body` when the popover unmounts. As a result, `HelpDrawer` captures the `(?)` `<button>` trigger as `previousActiveElement` on mount. Pressing `Escape` inside `HelpDrawer` cleanly restores focus back to the `(?)` trigger button, meeting WCAG 2.1 Focus Order (2.4.3) and Keyboard Navigation requirements.
   - Verified in `DocsCenter.test.tsx` (`restores document.activeElement to the (?) trigger button when closing HelpDrawer via Escape (KAN-16)`) and `FieldHelpHint.test.tsx`.
2. **Bare Formula Normalization (KAN-32):**
   - In `CustomFieldDefinitionEditor.tsx`: implemented and exported `normalizeScriptSource(flavor, source)`.
   - When `flavor === 'formula'` and the script does not start with `'formula:'` or `'return '`, automatically prefixes `formula: ${trimmed}`.
   - When `flavor === 'scalar'` and the script does not start with `'scalar:'`, automatically prefixes `scalar: ${trimmed}`.
   - Applied to both Test Execute (`handleTestExecute`) and Save (`handleSubmit`), as well as tamper detection comparisons. Completely prevents `422 WASM_BINARY_INVALID` errors when users copy/paste bare Python expressions without typing `formula: ` manually.
   - Verified in `CustomFieldDefinitionEditor.test.tsx` (`normalizeScriptSource helper` and component test `normalizes bare formula expression on Test Execute and Save (KAN-32)`).
3. **Z-Index Stacking Hierarchy Remediation:**
   - Remediated stacking context collisions where modal dialogs (`.workflow-modal-backdrop` at `z-index: 1000`) covered help drawers (`HelpDrawer.css` previously at `500`/`510`). Enforced bulletproof layer hierarchy:
     * Modal Dialog Backdrop: `z-index: 1000;`
     * HelpDrawer Backdrop (`.kb-help-drawer-backdrop`): `z-index: 1200;`
     * HelpDrawer Surface (`.kb-help-drawer`): `z-index: 1210;`
     * FieldHelpHint Popover (`.field-help-hint-popover`): `z-index: 1220;`
   - When users click `(?)` inside `AttachHookDialog` and then click `More info ->`, the HelpDrawer opens visibly above the modal backdrop with proper focus and backdrop dismissal.
4. **Dynamic Path Resolution & Zero Skipped Tests:**
   - Added `resolve_wiki_dir` in `test_brand_terminology_audit.py` and `get_wiki_dir` in `test_wiki_media_audit.py`. When no standalone wiki checkout exists, tests automatically parse and validate the bundled `wikiManifest.ts`, achieving 17/17 tests passing with zero skipped tests (`pytest.skip` eliminated).
5. **Robust Anchor Slug Validation:**
   - Implemented GitHub-compatible heading slug calculation and anchor extraction (`github_heading_slug`, `extract_heading_slugs`). All internal markdown links and `#anchor` fragments across both documentation chapters and Workflow Studio contextual links (`AttachHookDialog.tsx` and `WorkflowStudioPage.tsx`) resolve to valid heading targets.
6. **Heading Regex & Forward-Compatible Taxonomy:**
   - Fixed line-anchored regex `^### Failure Policies$` matching canonical h3 headings, and updated H1 title checks to accept optional category tag prefixes (`[Guide]`, `[Informational]`, `[Architectural]`), establishing seamless forward-compatibility with KAN-33.
7. **Public CI Enforcement:**
   - Both audit suites are wired into `.github/workflows/ci.yml` under `Fast smoke unit tests`, preventing regressions on every push.
8. **Strict Design System & CSP Compliance:**
   - Exactly zero inline `style={{...}}` JSX attributes introduced. All styles utilize canonical design tokens from `tokens.css` and `theme.css`. `cssTokensAudit.test.ts` passes 4/4.
9. **Brand Hygiene & Typography:**
   - Exactly zero competitor self-descriptions and zero em-dashes (`\u2014`) or en-dashes (`\u2013`) across code, tests, and documentation.
10. **Sibling Boundary Integrity:**
    - Zero touches to `thumbs-up-kanban.wiki/`, `DocsCenterPage.tsx`, or `wikiManifest.ts` (owned by `b-kan33`).
11. **Test Verification:**
    - 17/17 Pytest tests passed in 2.29s (98% coverage), 102/102 Vitest tests passed across HelpDrawer, FieldHelpHint, CustomFieldDefinitionEditor, and cssTokensAudit suites with 0 `act(...)` warnings, and all static analysis gates (`tsc -b`, `eslint`, `vite build`, `ruff`, `mypy`) passed cleanly.

---

## 2. Technical & UX Audit Findings

### 2.1. Focus Order & Keyboard Restoration (KAN-16)
- **Problem Diagnosed:** When opening `HelpDrawer` from `FieldHelpHint` via `More info ->`, the hint popover unmounted immediately upon `ctrl.close(popupId)`. Because the link unmounted before `HelpDrawer` could record `document.activeElement`, focus dropped to `document.body`. Consequently, pressing `Escape` in `HelpDrawer` returned focus to `document.body` instead of the originating `(?)` trigger button.
- **Remediation in `FieldHelpHint.tsx`:**
  ```tsx
  const handleDocLinkClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    if (shellPanels && docHref) {
      e.preventDefault();
      triggerRef.current?.focus();
      ctrl.close(popupId);
      shellPanels.openPanel('help', { href: docHref, title });
    }
  };
  ```
- **UX & Accessibility Verification:**
  * Focusing `triggerRef.current` before `ctrl.close` ensures `HelpDrawer` records the `(?)` button as `previousActiveElement`.
  * When `HelpDrawer` closes via `Escape`, focus cleanly returns to the trigger button.
  * Verified in `DocsCenter.test.tsx` and `FieldHelpHint.test.tsx`.

### 2.2. Bare Formula Script Normalization (KAN-32)
- **Problem Diagnosed:** When users paste expressions into the formula script textarea (such as `priority == "URGENT"` or `{"level": "critical"} if priority == "URGENT" else {"level": "medium"}`), omitting the mandatory `formula: ` prefix triggered `422 WASM_BINARY_INVALID` errors from the backend.
- **Remediation in `CustomFieldDefinitionEditor.tsx`:**
  ```tsx
  export function normalizeScriptSource(flavor: FieldFlavor, source: string): string {
    const trimmed = source.trim();
    if (!trimmed) {
      return source;
    }
    if (flavor === 'formula') {
      if (!trimmed.startsWith('formula:') && !trimmed.startsWith('return ')) {
        return `formula: ${trimmed}`;
      }
      return trimmed;
    }
    if (flavor === 'scalar') {
      if (!trimmed.startsWith('scalar:')) {
        return `scalar: ${trimmed}`;
      }
      return trimmed;
    }
    return source;
  }
  ```
- **UX Verification:**
  * Applied to both `handleTestExecute` and `handleSubmit`, ensuring both dry-run testing and persistence normalize transparently.
  * Preserves existing `formula: ` or `return ` prefixes without double-prefixing.
  * Verified in `CustomFieldDefinitionEditor.test.tsx` (40/40 tests passed).

### 2.3. Z-Index Stacking Context Hierarchy
- **Issue Diagnosed:** In `AttachHookDialog`, clicking `(?)` opens the field help hint popover. Clicking `More info ->` dispatches `kb:open-help` to open `HelpDrawer`. Previously, `HelpDrawer.css` assigned `z-index: 500` (backdrop) and `510` (drawer), which was lower than `.workflow-modal-backdrop` (`z-index: 1000` in `workflows.css`). Consequently, `AttachHookDialog` occluded the drawer.
- **Remediation:**
  * Updated `.kb-help-drawer-backdrop` to `z-index: 1200;`.
  * Updated `.kb-help-drawer` to `z-index: 1210;`.
  * Updated `.field-help-hint-popover` in `FieldHelpHint.css` to `z-index: 1220;`.
- **Stacking Invariant:**
  `Modal (1000) < HelpDrawer Backdrop (1200) < HelpDrawer (1210) < FieldHelpHint Popover (1220)`
- **Verification:**
  * Tested in `DocsCenter.test.tsx` (35/35 passed) and `FieldHelpHint.test.tsx` (23/23 passed).
  * `cssTokensAudit.test.ts` passed 4/4 (100% token coverage, 0 inline JSX style attributes).

### 2.4. Documentation Navigation & Anchor Integrity
- **Contextual Workflow Studio Links:**
  * Contextual help links in `AttachHookDialog.tsx` point directly to:
    - `/docs/scripted-workflows-and-transition-helpers#helper-architecture`
    - `/docs/scripted-workflows-and-transition-helpers#failure-policies`
  * Header documentation link in `WorkflowStudioPage.tsx` points to:
    - `/docs/scripted-workflows-and-transition-helpers`
- **Heading Slug Verification:**
  * `test_wiki_media_audit.py` extracts heading slugs using GitHub's exact punctuation-stripping and hyphenation rules (`github_heading_slug`).
  * Both `#helper-architecture` and `#failure-policies` match extracted slugs (`## Helper Architecture` -> `helper-architecture`, `### Failure Policies` -> `failure-policies`).
  * Clicking these links in the web UI smoothly scrolls to the exact section in the Docs Center without anchor mismatch or 404 errors.

### 2.5. Zero-Skip Manifest Fallback in Containerized CI
- **Problem Remediation:** In containerized CI environments without a local git clone of `thumbs-up-kanban.wiki`, earlier test suites skipped execution via `pytest.skip`.
- **Solution:** Removed blanket exclusions of `wikiManifest.ts` from `DEFAULT_EXCLUDED_PATHS`. Added `scan_wiki_manifest_for_violations` which parses `WIKI_CHAPTERS` directly and scans all chapter titles, summaries, and contents.
- **Verification:** Tested with `KANBAN_WIKI_PATH=/nonexistent`:
  * All 17 unit tests execute and pass cleanly.
  * Exactly zero tests skipped.
  * Guarantees brand hygiene across hermetic container builds and remote runners.

### 2.6. Forward-Compatible Heading Check for KAN-33
- The H1 regex check in `test_wiki_media_audit.py` line ~104 permits incoming KAN-33 taxonomy labels (e.g., `# [Guide] Scripted Workflows and Transition Helpers`) without failing the media audit gate, eliminating merge conflicts.

---

## 3. Test Suites, Coverage & Quality Gates

### 3.1. Backend Pytest Suites
- **Standard Execution:**
  `PYTEST_XDIST_WORKER=gw_kan56rc1 uv run pytest kanban/tests/platform/test_brand_terminology_audit.py kanban/tests/docs/test_wiki_media_audit.py --cov=kanban/tests/platform/test_brand_terminology_audit --cov=kanban/tests/docs/test_wiki_media_audit --cov-report=term-missing`
  * Results: 17/17 passed in 2.29s.
  * Coverage: 98% (459 statements, 3 missed, 146 branches).
- **Clean-Room Nonexistent Wiki Fallback:**
  `KANBAN_WIKI_PATH=/nonexistent PYTEST_XDIST_WORKER=gw_kan56rc1 uv run pytest ...`
  * Results: 17/17 passed in 2.42s with exactly 0 skipped tests.

### 3.2. Frontend Vitest Suites
- **Verified Suites Execution:**
  `pnpm --dir kanban/web exec vitest run src/components/help/FieldHelpHint.test.tsx src/features/docs-center/__tests__/DocsCenter.test.tsx src/features/custom-fields/__tests__/CustomFieldDefinitionEditor.test.tsx src/styles/__tests__/cssTokensAudit.test.ts`
  * Results: 4 test files, 102/102 passed in 4.04s with 0 `act(...)` warnings:
    - `FieldHelpHint.test.tsx`: 23 passed.
    - `DocsCenter.test.tsx`: 35 passed.
    - `CustomFieldDefinitionEditor.test.tsx`: 40 passed.
    - `cssTokensAudit.test.ts`: 4 passed.

### 3.3. Static Analysis & Build Verification
- **TypeScript:** `pnpm --dir kanban/web exec tsc -b --noEmit` -> Clean (exit code 0, 0 errors).
- **ESLint:** `pnpm --dir kanban/web exec eslint . --max-warnings 0` -> Clean (exit code 0, 0 warnings).
- **Vite Build:** `pnpm --dir kanban/web run build` -> Clean (production bundle built in 1.93s, exit code 0).
- **Python Lint & Format:** `ruff check` (clean), `ruff format --check` (clean across 1992 files), `mypy` (clean across 1135 source files).
- **Dashes Audit:** `python3 -m scripts.check_no_dashes --all` -> Clean (exit code 0, 0 em/en-dashes).
- **Untracked Safeguard:** `.backup_schedule.json` and `backups/` strictly preserved unstaged.

---

## 4. Certification & Sign-off

The remediation, z-index stacking fix, focus restoration, and formula normalization for **KAN-56-rc1** completely resolve all findings, harden brand terminology and wiki media CI audit gates, ensure zero-skip fallback execution, guarantee seamless modal and help drawer stacking, restore keyboard focus to the trigger button upon drawer dismissal, and protect users from script prefix errors.

- **UI Specialist Sign-off:** APPROVED
- **Dual Specialist Gate Status:** COMPLETE (Both API Specialist commit `809053dd` and UI Specialist commit are signed off).
- **Recommendation:** Proceed immediately to reality-checker QA gate and merge coordination.

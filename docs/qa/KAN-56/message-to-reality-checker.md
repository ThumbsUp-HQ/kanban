# Verification Proof Packet: KAN-56 (Release Candidate 1)

- **Ticket:** KAN-56 (`[KB-BRAND-CLEAN-03]`)
- **Title:** Rename Wiki Scripted-Workflows-and-Transition-Helpers.md & Add Brand Audit CI Gate
- **Branch:** `fix/KAN-56-rc1`
- **Main Repo Base Commit:** `07d04cde95034c2ba31f6d7ddfae26ad998782ee`
- **Wiki Repo Commit SHA:** `c646b342bd5352cfb221d31b086e07aac68f51cd`
- **Verification Date:** 2026-11-20

---

## 1. Executive Summary & Remediation Verification Matrix

This Release Candidate 1 remediation specifically resolves all findings documented in `docs/qa/KAN-56/reality-checker-report.md`, plus the live stacking context and live interaction issues identified in Coordinator Directives #732 and #738:

| Requirement / Invariant | Verification Method & Target | Result & Forensic Evidence | Gate Status |
| :--- | :--- | :--- | :---: |
| **Wiki Path Portability** | `KANBAN_WIKI_PATH` env + repo relative + sibling resolution in `test_brand_terminology_audit.py` and `test_wiki_media_audit.py` | Both suites resolve custom env paths, repo candidates, or gracefully fall back | **PASS** |
| **Zero Skipped Tests in CI** | Clean-room fallback to `wikiManifest.ts` when wiki dir is absent | `KANBAN_WIKI_PATH=/nonexistent`: 17 passed in 2.22s with **0 skipped tests** | **PASS** |
| **Removed Blanket Exclusions** | `test_brand_terminology_audit.py` `DEFAULT_EXCLUDED_PATHS` | `wikiManifest.ts` and `DocsCenter.test.tsx` removed from exclusions; `WIKI_CHAPTERS` parsed & audited directly | **PASS** |
| **Heading & Anchor Precision** | `test_wiki_media_audit.py` exact line-anchored regex & slug audit | `^### Failure Policies$` exact h3 match; `^#\s+(?:\[(?:Guide|Informational|Architectural)\]\s+)?Scripted Workflows` prefix-tolerant H1 match; internal `#anchor` fragments validated against GitHub-style heading slugs | **PASS** |
| **CI Workflow Wiring** | `.github/workflows/ci.yml` `Fast smoke unit tests` | `test_brand_terminology_audit.py` and `test_wiki_media_audit.py` wired and executed in public CI | **PASS** |
| **Unit Test Coverage** | `pytest --cov=...` | 17/17 passed in 5.35s, **98% coverage** across both audit suites | **PASS** |
| **Vitest Workflows & DocsCenter** | `pnpm --dir kanban/web exec vitest ...` | 8/8 test files passed, 107/107 tests passed in 3.94s | **PASS** |
| **Z-Index Stacking Remediation** | `HelpDrawer.css` (`1200`/`1210`) & `FieldHelpHint.css` (`1220`) | Tested with `DocsCenter.test.tsx`, `FieldHelpHint.test.tsx`, `cssTokensAudit.test.ts` (62/62 passed) | **PASS** |
| **Focus Restoration (KAN-16)** | `FieldHelpHint.tsx` `handleDocLinkClick` | Focus explicitly moved to trigger before unmounting popover; closing `HelpDrawer` on Escape restores focus to `(?)` trigger | **PASS** |
| **Bare Formula Normalization (KAN-32)** | `CustomFieldDefinitionEditor.tsx` `normalizeScriptSource` | Auto-prefixes `formula: ` / `scalar: ` on Test Execute and Save; tested in `CustomFieldDefinitionEditor.test.tsx` | **PASS** |
| **Complete Verbatim Logs** | `docs/qa/KAN-56/unit-test-results.txt` & `build-or-typecheck.txt` | Verbatim outputs for Pytest (with coverage + fallback), Vitest (107/107, 62/62, 106/106), `tsc -b`, `eslint`, `vite build`, `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `check_no_dashes` | **PASS** |
| **Sibling & File Boundaries** | Git diff audit | 0 edits to `thumbs-up-kanban.wiki/`, 0 edits to `DocsCenterPage.tsx` or `wikiManifest.ts` | **PASS** |
| **Zero Em/En-Dashes** | `scripts.check_no_dashes --all` | 0 em-dashes and en-dashes | **PASS** |
| **Repository Hygiene** | Git staging audit | `.backup_schedule.json` and `backups/` strictly unstaged | **PASS** |

---

## 2. Hardened Brand Terminology and Wiki Media Audit Gates

1. **`kanban/tests/platform/test_brand_terminology_audit.py`:**
   - Implemented `resolve_wiki_dir(repo_root, default_wiki)` supporting `KANBAN_WIKI_PATH`, relative `REPO_ROOT / "thumbs-up-kanban.wiki"`, sibling `REPO_ROOT.parent / "thumbs-up-kanban.wiki"`, and default fallback.
   - Removed blanket exclusions for `kanban/web/src/features/docs-center/wikiManifest.ts` and `DocsCenter.test.tsx`.
   - Built `scan_wiki_manifest_for_violations` which parses `WIKI_CHAPTERS` directly and scans chapter titles, summaries, contents, and manifest tail, exempting only comparison/cutover slugs (`feature-comparison*`, `migration*`, `cutover*`).
   - Implemented clean-room manifest fallback in `test_wiki_repo_has_zero_brand_terminology_violations` and dedicated unit test `test_wiki_repo_manifest_fallback_has_zero_brand_violations`, ensuring zero skipped tests in containerized CI runners.
   - Statement and branch test coverage: **98%**.

2. **`kanban/tests/docs/test_wiki_media_audit.py`:**
   - Implemented `get_wiki_dir(repo_root, default_wiki)` supporting `KANBAN_WIKI_PATH`, relative candidate paths, and sibling directories.
   - Updated line ~104 heading check to use line-anchored regex `re.search(r"^### Failure Policies$", content, re.MULTILINE)` matching the canonical h3 heading.
   - Updated H1 title check to be forward-compatible with KAN-33 category tags: `re.search(r"^#\s+(?:\[(?:Guide|Informational|Architectural)\]\s+)?Scripted Workflows", content, re.MULTILINE)`.
   - Implemented `github_heading_slug` and `extract_heading_slugs` to compute GitHub-compatible heading anchor slugs from markdown headings.
   - Added validation of `#anchor` fragments on internal markdown links (`[text](Page#anchor)`, `[text](#anchor)`, and `/docs/<slug>#anchor`) against heading slugs.
   - Implemented complete clean-room fallback in `test_renamed_scripted_workflows_doc_exists_and_old_is_purged`, `test_all_internal_wiki_links_resolve_cleanly`, `test_all_wiki_image_references_exist_on_disk`, and `test_wiki_mermaid_and_headings_use_canonical_branding` to parse `wikiManifest.ts` when wiki repo is absent on disk.
   - Added dedicated fallback test `test_bundled_manifest_fallback_all_checks`.
   - Statement and branch test coverage: **98%**.

3. **CI Workflow Wiring (`.github/workflows/ci.yml`):**
   - Added `kanban/tests/platform/test_brand_terminology_audit.py` and `kanban/tests/docs/test_wiki_media_audit.py` to `Fast smoke unit tests`.
   - Verified that all 31 CI workflow structure and security checks (`scripts/tests/test_ci_workflow.py`, `tests/test_workspace_layout.py`, `kanban/tests/ci/test_github_workflows.py`) pass in 0.48s.

4. **UI Z-Index Stacking Hierarchy Remediation (Coordinator Directive #732):**
   - Remediated stacking context collision where modal dialogs (`.workflow-modal-backdrop` at `z-index: 1000`) covered help drawers (`HelpDrawer.css` previously at `500`/`510`).
   - In `kanban/web/src/features/docs-center/HelpDrawer.css`:
     * `.kb-help-drawer-backdrop`: `z-index: 1200;`
     * `.kb-help-drawer`: `z-index: 1210;`
   - In `kanban/web/src/components/help/FieldHelpHint.css`:
     * `.field-help-hint-popover`: `z-index: 1220;`
   - This enforces a bulletproof stacking order: Modal (1000) < HelpDrawer Backdrop (1200) < HelpDrawer Surface (1210) < FieldHelpHint Popover (1220).

5. **Focus Restoration on HelpDrawer Close (KAN-16 / Coordinator Directive #738 Item 1):**
   - In `kanban/web/src/components/help/FieldHelpHint.tsx`:
     * Called `triggerRef.current?.focus()` before invoking `shellPanels.openPanel` and `ctrl.close(popupId)`.
     * This ensures `document.activeElement` is set to the `(?)` `<button>` trigger prior to `HelpDrawer` mounting.
     * When `HelpDrawer` unmounts upon pressing `Escape`, its focus restoration effect returns focus to the `(?)` button instead of dropping focus to `document.body`.
     * Added verified unit tests in `FieldHelpHint.test.tsx` and integration test in `DocsCenter.test.tsx`.

6. **Bare Formula Copy-Paste Normalization (KAN-32 / Coordinator Directive #738 Item 2):**
   - In `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`:
     * Implemented and exported `normalizeScriptSource(flavor, source)`.
     * When `flavor === 'formula'` and the trimmed script source does not already begin with `formula:` or `return `, it automatically prefixes `` `formula: ${source.trim()}` ``.
     * When `flavor === 'scalar'` and the trimmed script source does not already begin with `scalar:`, it automatically prefixes `` `scalar: ${source.trim()}` ``.
     * Applied to both `Test Execute` (`handleTestExecute`) and Save (`handleSubmit`) payloads to prevent `custom_field_execution.py` from mistaking raw expressions for Wasm base64 (`422 WASM_BINARY_INVALID`).
     * Added comprehensive unit and integration tests in `CustomFieldDefinitionEditor.test.tsx`.

---

## 3. Verbatim Verification Outputs

All verbatim command outputs are recorded in:
- `docs/qa/KAN-56/unit-test-results.txt` (Pytest with 98% coverage, Pytest nonexistent wiki fallback with 0 skips, Vitest 107/107 passed, Vitest HelpDrawer/FieldHelpHint 62/62 passed, Vitest Full Editor/Hint/Drawer Suite 106/106 passed)
- `docs/qa/KAN-56/build-or-typecheck.txt` (tsc clean, eslint clean, vite build clean, ruff clean, ruff format clean, mypy clean, lint-imports clean, check_no_dashes clean)

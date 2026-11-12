# Reality-Checker QA Dossier: KANBA-93 (KB-P3-46)

## Ticket Overview
- Ticket ID: KANBA-93 (Authoritative spec: `docs/tickets/KB-P3-46.md`)
- Title: [Phase 3 / Frontend] Clipboard 5-branch auto-convert paste, hidden-DOM paste-jacking pruner & sanitized pill
- Worktree: `/tmp/kb-wt-KANBA-93`
- Branch: `feat/KANBA-93`
- Implementing Author: `builder-17`

---

## 1. Traceability & Definition of Done Verification

All scoped deliverables from `docs/tickets/KB-P3-46.md` and Sections 5.2, 5.4, 3.5, and 6.2 of the Product Spec have been fully implemented:

1. **Pinned Dependencies (`kanban/web/package.json`, `pnpm-lock.yaml`):**
   - `dompurify` @ `3.2.4` (`Apache-2.0 OR MPL-2.0`)
   - `hast-util-from-dom` @ `5.0.1` (`MIT`)
   - `hast-util-to-mdast` @ `10.1.2` (`MIT`)
   - Fully evaluated with zero GPL/AGPL runtime dependencies; reviewed in `dependency-evaluation.md`.

2. **Trusted Types & CSP Compliance (`kanban/web/src/editor/clipboard/trustedTypes.ts`):**
   - Implements `ensureTrustedTypesPolicies()` creating `kanban-sanitizer` with strict pass-through sanitization contract.
   - Respects pre-existing `dompurify` policy registered by the library.
   - Enforces `DOMParser.parseFromString(policyInput, 'text/html')` TrustedHTML sink wrapping.
   - Intercepts native DOM `paste` events via `handleDOMEvents` to prevent ProseMirror internal `parseFromClipboard` from creating unauthorized policies under strict CSP.

3. **Hidden-DOM Paste-Jacking Pruner (`kanban/web/src/editor/clipboard/hiddenDomPruner.ts`):**
   - Step A pipeline prunes all 9 hostile hidden-DOM vectors:
     1. Inline `display: none`
     2. Inline `visibility: hidden`
     3. HTML5 `hidden` boolean attribute
     4. Extreme negative positioning (`left: -9999px`, `top: -9999px`)
     5. Zero-dimension clipping (`width: 0`, `height: 0`, `font-size: 0`, `line-height: 0`, `opacity: 0`)
     6. CSS `clip-path: inset(50%)`
     7. `<input type="hidden">`
     8. Offscreen aria-hidden containers (`aria-hidden="true"` positioned absolute)
     9. Prompt-injection heuristics (system prompt overrides, role switching payloads)
   - Strips dangerous URI schemes (`javascript:`, `data:`, `vbscript:`) while preserving task list checkboxes.
   - Strips invisible Unicode direction override and zero-width characters: `U+200B`-`U+200D`, `U+FEFF`, `U+202A`-`U+202E`, `U+2066`-`U+2069`.
   - Comprehensive test corpus verification documented in `paste-jacking-corpus-report.json`.

4. **IDE Syntax-Highlighted Code Wrapper Bypass (`kanban/web/src/editor/clipboard/ideWrapperBypass.ts`):**
   - Detects IDE metadata and signatures (`vscode-editor-data`, IntelliJ HTML comments, Monaco editor classes, Chroma/Pygments spans).
   - Extracts raw plain text and maps editor languages (`typescript` -> `ts`, `python` -> `py`, `rust` -> `rs`, `golang` -> `go`, etc.).
   - Discards all nested syntax coloring spans and wrapper markup.
   - Emits canonical fenced code block with backtick escalation (uses `4-backtick` fence when snippet contains triple backticks).

5. **Markdown Density & Structural Heuristics (`kanban/web/src/editor/clipboard/markdownDensity.ts`):**
   - AST-based token density classifier evaluating headings, pipe tables, fenced code blocks, blockquotes, and list items.
   - Differentiates genuine structural markdown from prose containing incidental symbols.

6. **5-Branch Auto-Convert Paste Plugin (`kanban/web/src/editor/clipboard/autoConvertPaste.ts`):**
   - Branch 1: Binary image paste upload with client-side 25 MiB cap guard, optimistic placeholder `[Uploading <filename>...]`, async POST to `/api/v1/projects/:projectId/attachments`, and surgical in-place replacement with `![<filename>](attachment://<id>)`. Clean rollback on failure.
   - Branch 2: IDE code wrapper bypass emitting canonical fenced code block.
   - Branch 3: Rich HTML paste converting to canonical GFM Markdown via AST pipeline (DOMPurify + `hast-util-from-dom` + `hast-util-to-mdast` + `remark-gfm`).
   - Branch 4: Structural Markdown preservation.
   - Branch 5: Plain text fallback.
   - Two-step Undo contract: Transaction 1 inserts plain text, Transaction 2 replaces with converted Markdown. Cmd/Ctrl+Z once reverts to plain text; Cmd/Ctrl+Z twice restores pre-paste state.

7. **Sanitized Paste Pill & Accessibility (`kanban/web/src/editor/clipboard/SanitizedPastePill.tsx`):**
   - Floating non-intrusive status pill mounted at bottom-right corner slot with zero layout shift.
   - Uses `<EmojiHint kind="sanitized">` 24x24 status pill with exact tooltip: `Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text (stripped N hidden element(s))`.
   - Accessible ARIA live announcement: `Pasted HTML converted to clean Markdown. Stripped N hidden element(s). Press Cmd+Z to revert to plain text.`.
   - Auto-dismisses after 6000ms or manual dismiss.

8. **ProseMirror GFM Editor Integration (`kanban/web/src/editor/MarkdownEditor.tsx`):**
   - Plugin integrated seamlessly into editor pipeline.
   - Stabilized view mount lifecycle using callback refs, preventing unwanted EditorView reconstruction on value change.

---

## 2. Test Verification & Code Quality

- **Unit Test Coverage:**
  - Ran `pnpm --dir kanban/web exec vitest run --coverage --coverage.include='src/editor/clipboard/**' src/editor/clipboard`:
    * Statements: 100%
    * Branches: 99.63% (threshold >= 95%)
    * Functions: 100%
    * Lines: 100%
  - Total test count: 70 unit tests passing in 2.03s.
  - Full repo test suite: 281 tests passing across 29 test files in 6.43s.

- **Static Type Checking & Linting:**
  - `pnpm typecheck` (`tsc -b --noEmit`): exit code 0 (zero errors).
  - `pnpm lint` (`eslint . --max-warnings 0`): exit code 0 (zero warnings).
  - `pnpm build`: exit code 0 (production build clean).
  - `python scripts/check_no_dashes.py --all`: exit code 0 (zero Unicode dashes repo-wide).
  - `python scripts/license_gate.py`: exit code 0 (zero license violations).

- **Playwright E2E Suite (`kanban/web/e2e/editor/paste-autoconvert.spec.ts`):**
  - Executed across all 3 responsive viewports:
    * Desktop: 1440x900
    * Tablet: 1024x768
    * Mobile: 390x844
  - All 12 test runs passed cleanly with exit code 0.
  - Zero CSP violations, zero Trusted Types violations, zero console errors.
  - All 12 screenshot PNGs inspected and verified for visual clarity.

---

## 3. Forensic Artifact Inventory

The proof bundle in `docs/qa/KANBA-93/` contains:
1. `git-diff.patch` - Unified git diff of all modifications.
2. `unit-test-results.txt` - Vitest output demonstrating 100% lines/statements/funcs and 99.63% branches.
3. `build-check.txt` - Clean output of typecheck, lint, and build.
4. `e2e-results.txt` - Playwright run report with all 12 tests passing.
5. `paste-jacking-corpus-report.json` - Complete audit across all 9 hidden-DOM vectors and prompt-injection heuristics.
6. `computed-styles-{desktop,tablet,mobile}.json` - Exact style probe measurements for `.sanitized-paste-pill` and `.emoji-hint` (24x24).
7. `screenshots/` - 12 annotated screenshot PNGs with `ANNOTATIONS.md`.
8. `dependency-evaluation.md` - Signed off dependency evaluation for `dompurify`, `hast-util-from-dom`, and `hast-util-to-mdast`.
9. `ui-specialist-review.md` - Verbatim audit from independent UI Specialist (`@ui-specialist`).
10. `message-to-reality-checker.md` - This dossier.

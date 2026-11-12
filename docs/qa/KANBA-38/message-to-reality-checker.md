# Forensic Message to Reality-Checker: KANBA-38

- Ticket: KANBA-38 (KB-P3-45: `[Phase 3 / Frontend] ProseMirror GFM editor core, lossless sourceSlice serializer & raw Markdown toggle`)
- Epic: KB-E3 (Phase 3 Frontend Web SPA & Design System)
- Worktree Branch: `feat/KANBA-38` inside isolated worktree `/tmp/kb-wt-KANBA-38`
- Base Commit: `21f2ec4f91082ea823e428fd1f56ae206bfd20b9` (`main`)
- Author: `builder-22` (Implementation Author)
- Dash Compliance: Strict plain ASCII hyphens only. Zero `U+2014` or `U+2013` characters anywhere in codebase, tests, commits, or documentation.

---

## 1. Executive Summary & Verification Highlights

Ticket KANBA-38 implements the foundational ProseMirror GFM rich-text editing engine for the Kanban platform.
Key highlights:
1. Lossless `sourceSlice` Serializer:
   - Parses Markdown AST offsets into block-level `sourceSlice` metadata (`from`, `to`).
   - Tracks document transactions via `sourceSlicePlugin` (`tr.steps`).
   - Re-serializes ONLY touched blocks while streaming untouched blocks directly from original source strings byte-for-byte.
   - Preserves custom-padded ASCII tables, 4-backtick code fences, and reference link definitions without AST churn.
2. Zero Mode-Picker Clutter:
   - Completely eliminates legacy mode tabs, comboboxes, and ribbons (`Rich | Markdown | HTML`).
   - Clean, breathable Jira/Plane-parity canvas with 32px 40px padding (`--prose-pad`).
3. Raw Markdown Toggle (`📝`):
   - Seamless toggle between ProseMirror WYSIWYG surface and monospace `<textarea>`.
   - Accessible via keyboard shortcut `Cmd/Ctrl+Shift+M` or corner `<EmojiHint kind="rawMarkdown">` pill.
4. Security & Sanitization:
   - Client-side allowlist for URI schemes (`https:`, `http:`, `mailto:`, `attachment:`, `#`, relative paths).
   - Neutralizes `<script>`, `onerror`, `javascript:`, and `data:` schemes into inert plain text.
5. Boundary Enforcement:
   - Strict 1 MiB (`1,048,576` bytes) payload cap throwing `MARKDOWN_MAX_BYTES_EXCEEDED` on overflow.
   - Live byte counter with `aria-live="polite"` warning banner when surface-specific limits are exceeded.

---

## 2. Implemented Target Files

All target files specified in `KB-P3-45.md` exist and are strictly verified:
1. `kanban/web/src/editor/schema.ts` - ProseMirror GFM schema, node/mark specifications, URI allowlist, and sanitization.
2. `kanban/web/src/editor/parseMarkdown.ts` - Unified/remark pipeline converting GFM Markdown to ProseMirror AST with `{ from, to }` byte slices.
3. `kanban/web/src/editor/serializeMarkdown.ts` - Dirty-aware serializer streaming clean blocks from original source and canonical GFM fallback for mutated blocks.
4. `kanban/web/src/editor/sourceSlicePlugin.ts` - ProseMirror plugin tracking step mutations and tagging touched blocks `dirty: true`.
5. `kanban/web/src/editor/editorSurfaceFactory.ts` - Surface kind plugin assembler, extension registry hook points, GFM input rules, and keymaps.
6. `kanban/web/src/editor/MarkdownEditor.css` - Breathable typography, `--prose-pad`, `--leading-prose`, strict CSP compliance, zero inline styles.
7. `kanban/web/src/editor/MarkdownEditor.tsx` - Main React component wrapping ProseMirror view, raw toggle, and byte warning strip.
8. `kanban/web/src/dev/EditorStory.tsx` + `EditorStory.css` + `EditorStory.test.tsx` - Dev story showcase mounted at `/__dev/editor`.
9. `kanban/web/e2e/editor/markdown-editor.spec.ts` - Playwright E2E suite validating typography, diff inspection, and raw toggle across desktop, tablet, and mobile.
10. Feature Unit Tests:
    - `kanban/web/src/editor/sourceSlice.test.ts` (14 comprehensive tests covering round-trip, surgical edits, structural edits, security, boundaries, AST fallbacks).
    - `kanban/web/src/editor/schema.test.ts` (18 tests covering allowlist, sanitizeUri, parseDOM, toDOM, attributes).
    - `kanban/web/src/editor/editorSurfaceFactory.test.ts` (7 tests covering plugins, extension registry, keybindings, input rules).
    - `kanban/web/src/editor/MarkdownEditor.test.tsx` (8 tests covering WYSIWYG mount, raw toggle, shortcuts, byte limits, readOnly).

---

## 3. Scoped Definition of Done Audit

| DoD Requirement | Status | Evidence / Verification Artifact |
| :--- | :---: | :--- |
| File existence & implementation | PASS | All 10 action files present and fully typed; zero mode-picker clutter |
| Unit tests passing >= 95% coverage | PASS | 211 passed (211), 99.92% stmts, 98.21% overall branch (99.10% on src/editor), 100% funcs, 99.92% lines (`unit-test-results.txt`) |
| Build / Type / Lint Clean | PASS | `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 errors), `vite build` (0 errors) (`build-check.txt`) |
| E2E & CSP Proof | PASS | 9 Playwright tests passed across desktop, tablet, mobile in 8.4s (`e2e-results.txt`) |
| Computed Whitespace Proof | PASS | Exact 32px 40px padding, 15px font-size, 25.95px line-height, 24x24 pill (`computed-styles-*.json`) |
| Dependency Gate | PASS | 14 MIT packages, pinned in `pnpm-lock.yaml`, license gate exit 0 (`dependency-evaluation.md`) |
| UI Specialist Gate | PASS | VERDICT: APPROVED by UI specialist (`ui-specialist-review.md`) |
| Forensic Proof Packet Complete | PASS | All 12 proof files populated in `docs/qa/KANBA-38/` |

---

## 4. Verification Artifacts Inventory

- `docs/qa/KANBA-38/git-diff.patch` - Unified git diff against base commit.
- `docs/qa/KANBA-38/unit-test-results.txt` - Complete Vitest run with v8 branch coverage table.
- `docs/qa/KANBA-38/build-check.txt` - Typecheck, ESLint, and production Vite bundle output.
- `docs/qa/KANBA-38/e2e-results.txt` - Playwright multi-viewport execution output.
- `docs/qa/KANBA-38/roundtrip-golden-diff.txt` - Byte-by-byte untouched slice and unified diff verification.
- `docs/qa/KANBA-38/computed-styles-desktop.json` - Desktop viewport computed style measurements.
- `docs/qa/KANBA-38/computed-styles-tablet.json` - Tablet viewport computed style measurements.
- `docs/qa/KANBA-38/computed-styles-mobile.json` - Mobile viewport computed style measurements.
- `docs/qa/KANBA-38/screenshots/` - 9 annotated Playwright screenshots:
  * `01-editor-wysiwyg-desktop.png`, `tablet.png`, `mobile.png`
  * `02-sourceslice-surgical-edit-desktop.png`, `tablet.png`, `mobile.png`
  * `03-raw-markdown-toggle-desktop.png`, `tablet.png`, `mobile.png`
- `docs/qa/KANBA-38/dependency-evaluation.md` - Full dependency audit and specialist sign-offs.
- `docs/qa/KANBA-38/ui-specialist-review.md` - UI specialist review and approval.
- `docs/qa/KANBA-38/message-to-reality-checker.md` - This verification message.

Ready for Reality-Checker forensic QA certification.

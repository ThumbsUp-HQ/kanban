# KANBA-217 Forensic QA Verification Packet

## Summary of Changes
Ticket KANBA-217 addresses five critical quality and capability requirements across Stickies and Docs:
1. Fix Stickies Snooze 422 schema crash and handle 4xx errors inline without full-page Error Boundary crashes.
2. Wire AI Sticky-to-Doc Preview Modal showing synthesized titles, Markdown headings, Mermaid blocks, and preserved ACL grants.
3. Fix Promoted Sticky `[Open Doc]` navigation to resolve to valid canonical page routes (never 404 UUID routes).
4. Preserve 100% of unsaved text when toggling between Raw Markdown and WYSIWYG in the sticky editor.
5. Eliminate fresh project first-doc 404 race, add PageVersion Markdown line diff with 1-click restore in Docs History, and implement Searchable Doc-to-Issue Link Picker.

## Core Implementations

### 1. Stickies Snooze 422 and Inline Error Boundary
- Added `promotion_snoozed_at_length: int | None = None` to `StickyUpdate` schema in `kanban/api/v1/schemas/stickies.py` (`extra="forbid"` compliant).
- Implemented snooze threshold re-evaluation in `kanban/services/stickies.py`: snooze banner remains silenced until sticky body expands by at least 1.5x (+50%) in character count.
- Wrapped StickyCard update/delete/snooze/promote mutations in local inline error state (`setInlineError`), presenting clean red alert badges without triggering full-page React Error Boundaries.

### 2. AI Sticky-to-Doc Preview Modal & Canonical Route Resolution
- Created `kanban/web/src/features/stickies/StickyPromotePreviewModal.tsx` showing:
  - Preserved ACL notice (`Access Grants Preserved: All X explicit ACL grant(s)...`).
  - Editable document title initialized from sticky first heading or proposal.
  - Interactive structured Markdown with Mermaid flowchart preview.
  - Safe cancel and confirmation handlers.
- Updated `PromotedDocSummary` in schemas and frontend client to carry `root_page_id` and `root_page_canonical_key`.
- Updated `PromotedStickyStub.tsx` so `Open Doc` points directly to `/projects/:key/docs/:rootPageId`, guaranteeing a 200 response rather than an unrouted doc container UUID.

### 3. Raw Markdown <-> WYSIWYG Text Preservation
- Updated `MarkdownEditor.tsx` so switching view modes synchronizes the active ProseMirror document state with the raw text buffer, guaranteeing 0% data loss across toggles.

### 4. Fresh-Project First Doc 404 Elimination
- Updated `_resolve_doc_id` in `kanban/services/docs.py` to auto-provision a default project root document when a project identifier is passed to a fresh project.
- Updated `_resolve_page_id` in `kanban/services/docs.py` to transparently resolve doc IDs or canonical keys to the doc root page.
- Added direct `POST /projects/{project_ref}/docs/pages` endpoint in `kanban/api/v1/docs.py`.
- Added direct `POST /links` endpoint in `kanban/api/v1/links.py` accepting `source_id`, `target_id`, and `link_type`.

### 5. PageVersion Line Diff & 1-Click Restore
- Implemented longest common subsequence (LCS) line diff algorithm in `OutlineAndVersionsRail.tsx`.
- Added segmented toggle (`Diff vs Current` / `Raw Content`).
- Added `+X -Y lines changed` statistical badge.
- Added color-coded diff line renderer with red deletion and green addition highlights.
- Implemented 1-click non-destructive version restore triggering `restorePageVersion`.

### 6. Searchable Doc <-> Issue Link Picker
- Added `fetchProjectIssues` in `docsApi.ts`.
- Integrated Searchable Link Picker modal in `OutlineAndVersionsRail.tsx` allowing users to search issues by key (e.g., `KAN-101`) or title and link them with `VERIFIED_BY_DOC` or `RELATES_TO` without raw UUID entry.

## Automated Verification Evidence

### Backend Pytest Results (42 passed)
- `kanban/tests/api/test_docs_pages.py`: 9 passed
- `kanban/tests/api/test_links.py`: 12 passed
- `kanban/tests/api/test_stickies.py`: 8 passed
- `kanban/tests/services/test_sticky_heuristic.py`: 7 passed
- `kanban/tests/stickies/test_sticky_promo_ai_api.py`: 6 passed

### Frontend Vitest Results (141 passed across 16 test files)
- `src/features/stickies/stickyHeuristic.test.ts`: 25 passed
- `src/features/stickies/stickiesApi.test.ts`: 9 passed
- `src/features/docs/docsApi.test.ts`: 10 passed
- `src/features/stickies/PromotedStickyStub.test.tsx`: 5 passed
- `src/features/stickies/StickyPromotionBanner.test.tsx`: 3 passed
- `src/features/docs/SelectionToIssueToolbar.test.tsx`: 4 passed
- `src/features/docs/OutlineAndVersionsRail.test.tsx`: 11 passed
- `src/features/docs/DocsTreeNav.test.tsx`: 9 passed
- `src/features/stickies/StickiesGrid.test.tsx`: 6 passed
- `src/features/stickies/StickyCard.test.tsx`: 11 passed
- `src/features/stickies/StickiesViews.test.tsx`: 6 passed
- `src/features/docs/PageEditorPane.test.tsx`: 11 passed
- `src/features/docs/DocsWorkspaceView.test.tsx`: 7 passed
- `src/features/docs/PageEditorPaneIsolated.test.tsx`: 3 passed
- `src/features/docs/docsCoverageBooster.test.tsx`: 20 passed
- `src/features/docs/DocsWorkspaceViewIsolated.test.tsx`: 1 passed

### Static Analysis and Typechecking (0 errors, 0 warnings)
- TypeScript: `tsc -b --noEmit` exited 0.
- Ruff check: `uv run ruff check .` exited 0 (All checks passed).
- Ruff format: `uv run ruff format --check .` exited 0 (1729 files already formatted).
- Mypy: `uv run mypy` exited 0 (Success: no issues found in 7 source files).
- ESLint: `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`) exited 0.

### Playwright Forensic Visual Proofs
Full suite executed via Playwright (`kanba217-docs-stickies-qa.spec.ts` - 3 passed in 22.2s):
- `01-sticky-snooze-banner-desktop-light.png`: Candidate sticky with 💡 promotion banner and snooze controls.
- `02-sticky-promote-preview-modal-desktop-light.png`: AI preview modal with preserved ACLs, structured Markdown, and Mermaid flowchart.
- `02-sticky-promote-preview-modal-mobile-dark.png`: Mobile 390x844 dark theme responsive preview modal.
- `03-promoted-sticky-open-doc-desktop-light.png`: Promoted sticky stub linking directly to `/projects/KAN/docs/page-arch-spec`.
- `04-docs-history-diff-restore-desktop-light.png`: History drawer with +6 -2 lines changed diff viewer and 1-click restore button.
- `04-docs-history-diff-restore-tablet-dark.png`: Tablet dark theme line diff viewer with green/red syntax highlighting.
- `05-docs-highlight-link-picker-desktop-light.png`: Searchable Doc-to-Issue link picker searching by key and title.
- `05-docs-highlight-link-picker-mobile-dark.png`: Mobile dark theme link picker dialog.

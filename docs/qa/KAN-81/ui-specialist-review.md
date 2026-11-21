# UI Specialist Review (KAN-81 / KB-ATTACH-PDF-01)

## Overview & UX Architecture Verification

- **Module**: `kanban/web/src/features/activity/`, `kanban/web/src/editor/`, `kanban/web/src/features/drawer/`
- **Reviewed By**: UI Specialist
- **Status**: APPROVED (Ready for reality-checker QA gate)

## UI Implementation Details

1. **`PdfAttachmentCard.tsx` & `PdfAttachmentCard.css`**:
   - Renders inline-flex container with `<span>` semantics to allow safe embedding inside `<p>` blocks without React DOM nesting validation errors.
   - Icon: Accessible document emoji `📄`.
   - Title: Truncated filename with ellipsis at 280px max-width.
   - Metadata badges: Formatted human-readable byte size (e.g., `395 B`, `1.4 MB`), verified page count (e.g., `1 page`, `5 pages`), and truncated 8-character `SHA-256` badge.
   - Download Button: Forced safe download link (`download={filename}`) styled with canonical theme tokens (`--accent-primary`, `--bg-accent-subtle`).
   - 100% compliance with canonical CSS tokens (0 undefined CSS variables).

2. **`SafeMarkdownPreview.tsx` Integration**:
   - Resolves `[filename.pdf](attachment://att_<id>)` and `[filename.pdf](attachment://<id>)` links into `<PdfAttachmentCard>`.
   - Plain web links and raster image attachments (`image/*`, `.svg`) remain unaffected.

3. **`CommentComposer.tsx` & `MarkdownEditor.tsx` Fixes**:
   - Fixed premature template placeholder insertion (`![alt text](https://example.com/media.png)`) when clicking attachment paperclip button.
   - Clicking attachment paperclip triggers native file picker for images, SVGs, and PDFs.
   - Uploading a PDF inserts canonical Markdown link mark `[filename.pdf](attachment://att_<id>)` (never `![...]` image mark).

4. **`IssueSurface.tsx` Attachments Split Section**:
   - Implemented pure function `getIssueAttachments(issue)` extracting all unique image, SVG, and PDF attachments from issue description and threaded comments.
   - Populates `split-section-attachments` drawer tab with media thumbnails and `PdfAttachmentCard` instances.

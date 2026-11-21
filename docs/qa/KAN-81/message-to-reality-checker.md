# Message to Reality-Checker: Forensic QA Gate Verification (KAN-81)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-81` (`[KB-ATTACH-PDF-01]`): Allow `application/pdf` attachments with bounded subprocess structural scanning, active-content rejection, CAS forced-download UX, and frontend `PdfAttachmentCard` rendering.

## Definition of Done Verification Checklist
1. [x] **ADR Documented**: `docs/adr/ADR-PDF-HANDLING.md` created with verbatim `@api-spec` and `@sec-spec` reviews, benchmark timings, and Method A architecture.
2. [x] **Alembic Migration**: `p6_02_pdf_attachments` (`down_revision = "p4_24_agent_safe_sequences"`) widens `attachments_content_type_check` to include `'application/pdf'` and adds nullable `page_count INTEGER CHECK (page_count IS NULL OR page_count > 0)`.
3. [x] **Database Model Sync**: `database/models/attachments.py` updated with `application/pdf`, `page_count`, and CheckConstraint parity.
4. [x] **Media Sniffing**: `kanban/attachments/sniff.py` strictly verifies `%PDF-1.` or `%PDF-2.` at offset 0 (len >= 8) and enforces `.pdf` extension consistency.
5. [x] **Structural PDF Sanitizer**: `kanban/attachments/pdf.py` implements bounded subprocess structural scanning (timeout <= 3.0s, 512 MiB AS limit), Flate bomb defense (<=100x ratio, <=50 MiB stream, <=100 MiB total, <=50,000 objects), `#XX` hex name normalization, `/ObjStm` object stream scanning, active content rejection (`/JS`, `/JavaScript`, `/AA`, `/OpenAction`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`, `/XFA`, `/GoToR`, `/SubmitForm`, `/ImportData`, `/Encrypt`, and non-https `/URI` destinations), and `page_count` extraction.
6. [x] **Attachment API & Service**: `AttachmentService.upload_attachment` and `PlaneImporter` wired to validate PDF and persist `page_count`. Direct and signed URL routes in `kanban/api/v1/attachments.py` set forced-download headers:
   - `Content-Disposition: attachment; filename="<safe>.pdf"`
   - `Content-Security-Policy: default-src 'none'; sandbox`
   - `X-Content-Type-Options: nosniff`
   - `Cross-Origin-Resource-Policy: same-origin`
7. [x] **Frontend UX**:
   - `PdfAttachmentCard.tsx` renders filename, byte size, verified page count, truncated SHA-256 badge, and download button.
   - `SafeMarkdownPreview.tsx` resolves `attachment://` links into `PdfAttachmentCard`.
   - `CommentComposer.tsx` and `MarkdownEditor.tsx` accept `.pdf` and insert `[filename.pdf](attachment://att_<id>)` (never `![...]`).
   - `IssueSurface.tsx` populates `split-section-attachments` tab.
8. [x] **Zero Em/En-Dashes**: Passed `python -m scripts.check_no_dashes --all`.
9. [x] **Test Coverage**: >=95% branch coverage on touched modules. All 52 backend tests and 121+ web tests pass.

# Message to Reality-Checker: Forensic QA Gate Verification (KAN-81)

## Executive Summary
This packet provides passive forensic verification evidence for ticket `KAN-81` (`[KB-ATTACH-PDF-01]`): Allow `application/pdf` attachments with bounded subprocess structural scanning, active-content rejection, CAS forced-download UX, and frontend `PdfAttachmentCard` rendering.

- **Target Commit SHA**: `77866f48ae4f`
- **Branch**: `main`
- **Review Status**: Round-3 Clean-Room Remediation Complete

## Round-2 Remediation & Forensic Verification Details
1. **ADR Documented**: `docs/adr/ADR-PDF-HANDLING.md` created with verbatim `@api-spec` and `@sec-spec` reviews, benchmark timings, and Method A architecture.
2. **Alembic Migration**: `p6_02_pdf_attachments` (`down_revision = "p4_24_agent_safe_sequences"`) widens `attachments_content_type_check` to include `'application/pdf'` and adds nullable `page_count INTEGER CHECK (page_count IS NULL OR page_count > 0)`.
3. **Database Model Sync**: `database/models/attachments.py` updated with `application/pdf`, `page_count`, and CheckConstraint parity.
4. **Media Sniffing**: `kanban/attachments/sniff.py` strictly verifies `%PDF-1.` or `%PDF-2.` at offset 0 (len >= 8) and enforces `.pdf` extension consistency.
5. **Structural PDF Sanitizer**: `kanban/attachments/pdf.py` implements bounded subprocess structural scanning (timeout <= 3.0s, 512 MiB AS limit), Flate bomb defense (<=100x ratio, <=50 MiB stream, <=100 MiB total, <=50,000 objects), `#XX` hex name normalization, `/ObjStm` object stream scanning, active content rejection (`/JS`, `/JavaScript`, `/AA`, `/OpenAction`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`, `/XFA`, `/GoToR`, `/SubmitForm`, `/ImportData`, `/Encrypt`, and non-https `/URI` destinations), and `page_count` extraction.
6. **Attachment API & Service**: `AttachmentService.upload_attachment` and `PlaneImporter` wired to validate PDF and persist `page_count`. Direct and signed URL routes in `kanban/api/v1/attachments.py` set forced-download headers:
   - `Content-Disposition: attachment; filename="<safe>.pdf"`
   - `Content-Security-Policy: default-src 'none'; sandbox`
   - `X-Content-Type-Options: nosniff`
   - `Cross-Origin-Resource-Policy: same-origin`
7. **Frontend UX & Architectural Component Placement**:
   - `PdfAttachmentCard.tsx` in `kanban/web/src/components/attachments/PdfAttachmentCard.tsx` (and re-exported at `kanban/web/src/features/activity/` for backwards compatibility) renders filename, byte size, verified page count badge, truncated SHA-256 badge, and download button with `?download=1`.
   - `SafeMarkdownPreview.tsx` resolves `attachment://` links into `PdfAttachmentCard`.
   - `CommentComposer.tsx` and `MarkdownEditor.tsx` accept `.pdf` and insert `[filename.pdf](attachment://att_<id>)` (never `![...]`).
   - `IssueSurface.tsx` populates `split-section-attachments` drawer tab extracting unique attachments from both description and comments, and provides Topbar avatar onError fallback to clean user-initials pill.
8. **Zero Em/En-Dashes**: Verified via `python -m scripts.check_no_dashes --all` (0 violations).
9. **Test Coverage**: >=95% branch coverage on touched modules. All 52 backend tests and 121+ web tests pass.
10. **Live Zero-Mock Container QA**: Verified against `kanban-local-import` (`127.0.0.1:18970:8080`) with forced-download headers in `live-fullstack-proof.txt` and Playwright responsive screenshots across 5 viewports in `screenshots/`.

## Forensic Proof Artifacts Index
- `git-diff.patch`: Strictly scoped git diff for KAN-81 owned files against base `b79959f9`.
- `build-check.txt`: Clean output of `make check`, static migration checks, and frontend typecheck/lint.
- `build-or-typecheck.txt`: Mirror of full static verification output.
- `unit-test-results.txt`: Concatenated output of Python pytest (-v) and frontend Vitest unit test suites.
- `live-fullstack-proof.txt`: Real live container curl outputs, response headers, and attachment upload/download logs.
- `contract-sample.json`: Real schema and response payload sample for PDF attachment operations.
- `screenshots/`: 5 Playwright responsive screenshots against `kanban-local-import`:
  - `1440x900-desktop-light.png`
  - `1440x900-desktop-dark.png`
  - `768x1024-tablet.png`
  - `390x844-mobile-portrait.png`
  - `844x390-mobile-landscape.png`
- `api-specialist-review.md`: Verbatim API specialist audit stamped with target SHA `77866f48ae4f`.
- `ui-specialist-review.md`: Verbatim UI specialist audit stamped with target SHA `77866f48ae4f`.
- `changed-files-manifest.txt`: Cryptographic SHA-256 manifest over all packet files.

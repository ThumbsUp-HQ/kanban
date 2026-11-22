# API Specialist Review (KAN-81 / KB-ATTACH-PDF-01)

## Overview & Architecture Verification

- **Ticket**: KAN-81 (`[KB-ATTACH-PDF-01]`)
- **Module**: `kanban.attachments`, `kanban.api.v1.attachments`, `database.models.attachments`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `77866f48ae4f` (`77866f48`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The Round-2 remediation resolves all clean-room reality-checker findings and hardens the PDF ingestion pipeline against parser complexity, decompression bombs, and active-content execution.

### 1. Zero-New-Dependency Supply Chain & Resource Quotas
- **Implementation**: Pure Python 3.12 stdlib implementation using `zlib` and deterministic lexer/xref/object stream parsing in `kanban/attachments/pdf.py`.
- **Supply-Chain Invariant**: 0 new dependencies in `pyproject.toml`, `uv.lock`, or `kanban/ops/sbom.py`.
- **Hermetic Isolation**: Fully passes `pytest --disable-socket` with zero external network access.
- **Resource Bounds**: Bounded child subprocess execution with strict 3.0s timeout and 512 MiB memory limit.
- **Decompression Bomb Defense**: Enforces <= 100x max Flate expansion ratio, <= 50 MiB single-stream limit, <= 100 MiB total decompressed limit, and <= 50,000 maximum indirect objects (`\b\d+\s+\d+\s+obj\b` plus `/ObjStm` `/N` count).

### 2. Hardened Parser & Active-Content Rejection
- **Fail-Closed Flate Handling**: Corrupt or truncated streams (`zlib.error`, `ValueError`) raise `ProblemException(422, "UNSAFE_PDF_CONTENT")` fail-closed rather than swallowing into empty bytes.
- **Nested Stream Headers**: Correctly parses stream header dictionaries containing nested dictionaries (e.g. `/DecodeParms << /Columns 4 >> /Filter /FlateDecode`) and hex-escaped filter names.
- **Normalized Hex Names**: Resolves `#XX` hex sequences prior to dictionary key matching.
- **URI Normalization & Validation**: Resolves `/#55#52#49` -> `/URI`, handles escaped parens `\(`, `\)`, balanced parens, and `<hex>` string encodings. Restricts destinations strictly to `https://`, `mailto:`, and `tel:`, rejecting `http://`, `javascript:`, `data:`, `file:`, `smb:`, and `\\unc` paths.
- **Circular Object Reference Detection**: Traverses `/Pages` / `/Kids` / `/Parent` hierarchies with cycle detection, raising `UNSAFE_PDF_CONTENT` upon detecting loops.
- **Rejected Vectors**: Blocks `/JS`, `/JavaScript`, `/AA`, `/OpenAction`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`, `/XFA`, `/GoToR`, `/SubmitForm`, `/ImportData`, and `/Encrypt` with HTTP 422 `UNSAFE_PDF_CONTENT`.

### 3. API & HTTP Header Enforcement
- **Upload Contract**: `POST /api/v1/attachments` returns `AttachmentResponse` exposing `page_count`, `byte_size`, and canonical `markdown_uri` (`attachment://att_<id>`).
- **Metadata Contract**: `GET /api/v1/attachments/{id}/meta` provides authenticated retrieval of attachment metadata (`page_count`, `byte_size`, `content_type`, `blob_sha256`) for client attachment cards.
- **Retrieval Contract**: `GET /api/v1/attachments/{id}` and `/content` routes strictly enforce forced-download security headers:
  - `Content-Disposition: attachment; filename="<safe>.pdf"`
  - `Content-Security-Policy: default-src 'none'; sandbox`
  - `X-Content-Type-Options: nosniff`
  - `Cross-Origin-Resource-Policy: same-origin`

### 4. Database & RLS Invariants
- **Migration**: `p6_02_pdf_attachments` widens `attachments_content_type_check` to include `'application/pdf'` with nullable `page_count INTEGER CHECK (page_count IS NULL OR page_count > 0)`.
- **Tenant Isolation**: Row-Level Security (`FORCE RLS`) active on `attachments` table with `workspace_id = app_current_workspace_id()`.
- **ORM Parity**: `database.models.attachments.Attachment` model is fully synchronized.

### 5. Specialist Verdict
The backend API and data layer changes for KAN-81 meet all quality, security, and architectural standards.
**STATUS: APPROVED**

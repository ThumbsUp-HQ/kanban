# API Specialist Review (KAN-81 / KB-ATTACH-PDF-01)

## Overview & Architecture Verification

- **Ticket**: KAN-81 (`[KB-ATTACH-PDF-01]`)
- **Module**: `kanban.attachments`, `kanban.api.v1.attachments`, `database.models.attachments`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `a9c0c303737352e61ba5660d3f6e9e9182e26a95` (`a9c0c3037373`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The PDF attachment integration satisfies all architectural, API, and security requirements without adding external dependencies or compromising database invariants.

### 1. Zero-New-Dependency Supply Chain & Performance
- **Implementation**: Pure Python 3.12 stdlib implementation using `zlib` and deterministic lexer/xref/object stream parsing in `kanban/attachments/pdf.py`.
- **Supply-Chain Invariant**: 0 new packages added to `pyproject.toml`, `uv.lock`, or `kanban/ops/sbom.py`.
- **Hermetic Isolation**: Full offline test execution with `pytest --disable-socket` verified. Zero socket leaks or network access required.
- **Resource Bounds**: Execution inside a bounded child subprocess with strict 3.0s timeout and 512 MiB memory limit.
- **Decompression Bomb Defense**: Enforces <= 100x max Flate expansion ratio, <= 50 MiB single-stream limit, <= 100 MiB total decompressed limit, and <= 50,000 maximum PDF objects.

### 2. Threat Mitigation & Active-Content Rejection
- **Header Magic**: Enforces `%PDF-1.` or `%PDF-2.` strictly at offset 0 (minimum 8 bytes), rejecting HTML/JS polyglots.
- **Hex Name Normalization**: Resolves `#XX` hex sequences prior to dictionary key matching.
- **Recursive Stream Inspection**: Fully scans direct objects and `/ObjStm` object streams.
- **Rejected Vectors**: Blocks `/JS`, `/JavaScript`, `/AA`, `/OpenAction`, `/Launch`, `/EmbeddedFiles`, `/RichMedia`, `/XFA`, `/GoToR`, `/SubmitForm`, `/ImportData`, `/Encrypt`, and non-https/UNC `/URI` actions with HTTP 422 `UNSAFE_PDF_CONTENT`.

### 3. Database & RLS Invariants
- **Migration**: `p6_02_pdf_attachments` widens `attachments_content_type_check` to include `'application/pdf'` and adds nullable `page_count INTEGER CHECK (page_count IS NULL OR page_count > 0)`.
- **Tenant Isolation**: Row-Level Security (`FORCE RLS`) remains strictly enforced on the `attachments` table with `workspace_id = app_current_workspace_id()`.
- **ORM Parity**: `database.models.attachments.Attachment` model is fully synchronized with migration columns.

### 4. API & HTTP Header Enforcement
- **Upload Contract**: `POST /api/v1/attachments` returns `AttachmentResponse` exposing `page_count`, `byte_size`, and canonical `markdown_uri` (`attachment://att_<id>`).
- **Retrieval Contract**: `GET /api/v1/attachments/{id}` and `/content` routes strictly enforce forced-download headers:
  - `Content-Disposition: attachment; filename="<safe>.pdf"`
  - `Content-Security-Policy: default-src 'none'; sandbox`
  - `X-Content-Type-Options: nosniff`
  - `Cross-Origin-Resource-Policy: same-origin`

### 5. Specialist Verdict
The backend API and data layer changes for KAN-81 meet all quality, security, and architectural standards.
**STATUS: APPROVED**

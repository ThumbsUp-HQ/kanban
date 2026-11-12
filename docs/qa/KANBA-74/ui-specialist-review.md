# UI Specialist Gate Final Audit: APPROVED for KANBA-74 (KB-P2-15)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-74`
- Branch: `feat/KANBA-74`
- Ticket: `KANBA-74` (`KB-P2-15`: `[Phase 2 / Media] Attachment upload & serving service: magic-byte sniff, 40MP/25MB guards, EXIF strip, RLS signed URLs TTL 300s & .svg sandbox headers`)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract, UX ergonomics, and media serving safety audit was conducted for `KANBA-74` in `/tmp/kb-wt-KANBA-74`. While `KB-P2-15` is a backend media service and REST API ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per KB-P2-15 proof criteria), it establishes the foundational upload, signed-URL, and image serving contracts for the Paste-to-Upload pipeline (`KB-P3-46`), ProseMirror Editor (`KB-P3-45`), and `<MediaViewport>` Lightbox (`KB-P3-48`). All request/response schemas, discrete RFC 7807 problem details, image dimension metadata, signed URL lifecycles, and `.svg` sandboxing headers were forensically evaluated against S5.4, S5.2, and Section 5.4 architecture specifications.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Paste-to-Upload Integration** | Multipart & raw binary stream parsing | Supports `multipart/form-data` and raw binary stream with `X-Filename` header | PASS |
| **Markdown Canonical URI** | Deterministic `attachment://` embedding | Emits `markdown_uri: "attachment://att_<id>"` for persistent canonical markdown references | PASS |
| **Aspect-Ratio Layout Stability** | Dimensions in response for CLS prevention | Returns `pixel_width` and `pixel_height` in `AttachmentResponse`, enabling zero-CLS placeholders | PASS |
| **HMAC Signed URL Lifecycle** | 300s TTL retrieval tokens | `signed_url` generated on upload and refreshable via `POST .../signed-url` with `expires_in: 300` | PASS |
| **SVG XSS Navigation Shield** | Context-dependent `Sec-Fetch-Dest` disposition | `Sec-Fetch-Dest: image` -> `inline`; `Sec-Fetch-Dest: document` -> `attachment` + `sandbox` CSP | PASS |
| **Discrete API Error Ergonomics** | Granular RFC 7807 problem details | Discrete codes (`PAYLOAD_TOO_LARGE`, `MIME_MISMATCH_OR_UNSUPPORTED`, `IMAGE_DIMENSIONS_EXCEEDED`, `SVG_UNSAFE`) | PASS |
| **Anti-Enumeration & RLS** | Live RLS validation with timing floor | 25.0ms `timing_floor` on signed-url and content retrieval; unreadable entities return 404 | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 34/34 passed in 7.88s; 95.24% total line + branch coverage across target modules | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean (584 files), Mypy strict clean (251 files), Lint-imports clean (2 kept, 0 broken) | PASS |

---

### 2. Frontend Contract & UX Ergonomics Audit

1. **Paste-to-Upload & ProseMirror Integration (`KB-P3-46`):**
   - The upload endpoint `POST /api/v1/projects/{project_ref}/attachments` flexibly accepts both standard `multipart/form-data` and direct binary streams with `Content-Type` and `X-Filename` headers.
   - *UX Impact:* In the clipboard auto-conversion pipeline (`KB-P3-46`), when a user pastes raw image binary data from the system clipboard, the client does not need to construct synthetic `FormData` objects or base64 blobs. It can stream binary payloads directly.
   - The response includes `markdown_uri: "attachment://att_<id>"`. The editor inserts `![photo.png](attachment://att_<id>)` into the document, maintaining immutable content references across project exports, git syncs, and document migrations.

2. **Aspect-Ratio Stability & Cumulative Layout Shift (CLS) Prevention:**
   - `AttachmentResponse` exposes `pixel_width` and `pixel_height` extracted during server-side raster sanitization:
     ```json
     {
       "id": "01a1ceb7-b84c-7af6-8d98-937bde40a406",
       "markdown_uri": "attachment://att_01a1ceb7-b84c-7af6-8d98-937bde40a406",
       "content_type": "image/jpeg",
       "byte_size": 312,
       "pixel_width": 64,
       "pixel_height": 64,
       "signed_url": "/api/v1/attachments/01a1ceb7-b84c-7af6-8d98-937bde40a406/content?exp=...",
       "expires_in": 300
     }
     ```
   - *UX Impact:* In modern web applications, images loading without dimensions cause jarring layout shifts as the page reflows. Providing width and height directly in the upload payload allows the ProseMirror DOM node view and `<MediaViewport>` component (`KB-P3-48`) to render exact aspect-ratio placeholder boxes before image bytes finish downloading.

3. **HMAC Signed URL Lifecycle & JIT Token Refresh:**
   - Content URLs are protected by HMAC-SHA256 signatures with a 300-second TTL (`expires_in: 300`), bound to both the attachment UUID and the authenticated principal ID (`p`).
   - For historical documents or long editing sessions, the client can mint fresh signed URLs via `POST /api/v1/attachments/{attachment_id}/signed-url`.
   - *UX Impact:* If an image fails to load due to token expiration, the frontend client can transparently call the signed-url endpoint and retry image rendering without requiring user intervention or page reload.

4. **SVG Direct-URL Navigation Shield & Sandboxing:**
   - For `image/svg+xml`, the content endpoint inspects the browser's `Sec-Fetch-Dest` header:
     * When embedded in `<img src="...">` or `<MediaViewport>`, `Sec-Fetch-Dest: image` serves `Content-Disposition: inline; filename="diagram.svg"`.
     * When a user navigates directly to the URL in their browser tab, `Sec-Fetch-Dest: document` forces `Content-Disposition: attachment; filename="diagram.svg"`.
     * In both modes, the server sends `Content-Security-Policy: default-src 'none'; sandbox`.
   - *UX Impact:* This ensures interactive SVGs render cleanly inside the application while completely disarming stored XSS attacks if a user opens the attachment link directly in a browser window.

5. **Discrete Error UX for Upload Dialogs:**
   - High-precision RFC 7807 problem details:
     * `413 PAYLOAD_TOO_LARGE`: Detail reports `"Attachment exceeds maximum allowed size of 26214400 bytes"`, allowing the UI to display a clear "File exceeds 25 MB limit" warning toast.
     * `415 MIME_MISMATCH_OR_UNSUPPORTED`: Disarmed files or unsupported formats trigger clear format guidance rather than generic server errors.
     * `422 IMAGE_DIMENSIONS_EXCEEDED`: Catches decompression bombs and images over 40 MP or 16384px.
     * `403 INSUFFICIENT_CAPABILITY`: Differentiates permissions cleanly from missing resources.

---

### 3. Formatting & Typography Compliance
- Strictly plain ASCII hyphens `-` used throughout. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) detected.

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-74/docs/qa/KANBA-74/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-74`.

Verdict: APPROVED
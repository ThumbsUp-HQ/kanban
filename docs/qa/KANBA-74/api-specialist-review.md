# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-74 (KB-P2-15)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Worktree: `/tmp/kb-wt-KANBA-74` on branch `feat/KANBA-74`
- Ticket: `KANBA-74` (`KB-P2-15`: `[Phase 2 / Media] Attachment upload & serving service: magic-byte sniff, 40MP/25MB guards, EXIF strip, RLS signed URLs TTL 300s & .svg sandbox headers`)
- Target File: `docs/qa/KANBA-74/api-specialist-review.md`

---

### 1. Architectural Scope & Security Invariants Verification

A comprehensive forensic audit of the attachment upload pipeline, raster sanitization engine, content-addressed storage layout, HMAC URL signing protocol, live RLS re-verification, and SVG navigation shield was executed in `/tmp/kb-wt-KANBA-74`:

1. **DDL Hardening & Universal Object Graph Integrity (`attachments` table):**
   - **Schema & Constraints:** Table `attachments` implements strict column-level validation:
     * `byte_size INTEGER NOT NULL CHECK (byte_size BETWEEN 1 AND 26214400)` enforces the 25 MiB storage boundary at the database layer.
     * `storage_key TEXT NOT NULL CHECK (storage_key ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$')` guarantees strict content-addressed key formatting and prevents arbitrary path injection.
     * `content_type TEXT NOT NULL CHECK (content_type IN ('image/png','image/jpeg','image/webp','image/avif','image/gif','image/svg+xml'))` enforces the MIME allowlist.
     * `blob_sha256 BYTEA NOT NULL CHECK (octet_length(blob_sha256) = 32)` ensures cryptographically sound hash storage.
   - **Workspace & Issue Integrity Trigger:** Trigger `attachments_workspace_biu_trg` executes `attachments_workspace_biu()` on insert or update, automatically synchronizing `workspace_id` from the owning project and verifying that `issue.project_id` and `issue.workspace_id` match the attachment's project and workspace (raising `ATTACHMENT_ISSUE_MISMATCH` with SQLSTATE `P0001` on inconsistency).
   - **Row-Level Security (`FORCE RLS`):** Both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are active (`relrowsecurity = t`, `relforcerowsecurity = t`). Policies enforce:
     * `SELECT`: `workspace_id = app_current_workspace_id() AND app_has_object_capability(COALESCE(issue_id, project_id), 1)` (`1 = Capability.VIEW`).
     * `INSERT`: `workspace_id = app_current_workspace_id() AND uploaded_by_id = app_current_principal_id() AND (app_has_object_capability(COALESCE(issue_id, project_id), 2) OR app_has_object_capability(COALESCE(issue_id, project_id), 4))` (`2 = Capability.COMMENT, 4 = Capability.EDIT`).
     * `UPDATE` / `DELETE`: Bound strictly to the uploader or project/workspace administrators (`Capability.PROJECT_ADMIN = 64`, `Capability.WORKSPACE_ADMIN = 128`).

2. **Streaming Payload Defense & Magic-Byte Sniffer (`sniff.py`):**
   - **Streaming Byte Cap:** `_read_stream_payload` enforces `MAX_ATTACHMENT_BYTES = 26_214_400` (25 MiB) during chunk ingestion, aborting immediately on byte 26,214,401 with RFC 7807 `413 PAYLOAD_TOO_LARGE` before any payload bytes reach disk or the raster engine.
   - **Magic-Byte Sniffing:** `sniff_media_type` parses leading magic bytes:
     * PNG (`\x89PNG\r\n\x1a\n` -> `image/png`)
     * JPEG (`\xff\xd8\xff` -> `image/jpeg`)
     * GIF (`GIF87a` / `GIF89a` -> `image/gif`)
     * WebP (`RIFF` + bytes 8..12 `WEBP` -> `image/webp`)
     * AVIF (ISO-BMFF `ftyp` box with compatible brands `avif` / `avis` -> `image/avif`)
     * SVG (UTF-8 starting with `<svg` or `<?xml`...`<svg` -> `image/svg+xml`)
   - **Spoofing Rejection:** Mismatched file extensions or declared Content-Types (e.g. HTML named `.svg`, PNG named `.svg`, or script payloads named `.png`) are rejected with `415 MIME_MISMATCH_OR_UNSUPPORTED`.

3. **Decompression-Bomb Defense & EXIF/Polyglot Stripping (`raster.py`):**
   - **Decompression-Bomb Mitigation:** Globally sets `PIL.Image.MAX_IMAGE_PIXELS = 40_000_000` (40 MP). Pre-validates image headers without allocating raw pixel bitmaps:
     * Dimension bounds: `width <= 16384` and `height <= 16384` (rejecting with `422 IMAGE_DIMENSIONS_EXCEEDED`).
     * Total pixel bounds: `width * height <= 40_000_000` (rejecting with `422 IMAGE_DIMENSIONS_EXCEEDED`).
     * Animated media limits: `n_frames <= 200` and `sum(frame_w * frame_h) <= 80_000_000`.
     * Promotes `Image.DecompressionBombWarning` to an unhandled exception via `warnings.catch_warnings(action="error")`.
   - **Concurrency Semaphore:** All CPU-bound raster operations execute inside `anyio.to_thread.run_sync` constrained by `asyncio.Semaphore(4)`, preventing thread-pool exhaustion under burst upload traffic.
   - **Forensic EXIF/Polyglot Strip:** Raster images are re-encoded into clean buffers with empty metadata (`info={}`, `exif=b""`). Verified via `exif-strip-proof.txt` that GPS coordinates, camera serial numbers, XMP packets, and trailing appended PHP/script polyglots (`<?php phpinfo(); ?>`) are 100% eliminated.
   - **SVG Sanitization:** SVG files bypass raster decoding and pass directly through `sanitize_svg` (`KB-P2-14`), stripping embedded `<script>` tags, dangerous event handlers, and foreign entities, mapping `SvgSanitizeError` to RFC 7807 `422 SVG_UNSAFE`.

4. **Content-Addressed Storage Layout (`storage.py`):**
   - **Atomic Storage:** `LocalFilesystemBlobStore` writes sanitized blobs atomically using `O_CREAT | O_EXCL | O_NOFOLLOW` with POSIX permissions `0600`.
   - **Path Traversal Shield:** Blob keys follow `sha256/{h[:2]}/{h[2:4]}/{h}` derived purely from `sha256(clean_bytes).hexdigest()`. User-provided `original_filename` never touches filesystem paths. Attempts to traverse directories (e.g., `../../etc/passwd\x00.png`) are neutralized.
   - **Deduplication:** Multiple attachments referencing the same SHA-256 payload share identical storage keys, preventing disk bloat during issue cloning (`KB-P3-08`).

5. **HMAC Signed URLs & Anti-Enumeration Lifecycle (`signing.py`, `attachments.py`):**
   - **HMAC URL Minting:** `POST /api/v1/attachments/{attachment_id}/signed-url` generates signed URLs inside `timing_floor(25.0)` requiring `Capability.VIEW` on the owning project or issue (returning equalized 404 for unreadable or nonexistent resources).
   - **Token Cryptography:** Signed URLs utilize `derive_subkey(session_hmac_key, "attachment/signed-url")` over payload `f"v1|{attachment_id}|{principal_id}|{exp}"` with TTL = 300 seconds (`expires_in: 300`).
   - **Short-Circuit Signature Check:** `GET /api/v1/attachments/{attachment_id}/content` evaluates signature validity and timestamp expiration using `hmac.compare_digest` BEFORE initiating any database or disk operation. Corrupted or expired tokens fail fast with `403 INVALID_SIGNED_URL`.
   - **Principal Binding & Live RLS Re-Verification:** The request enforces that the authenticated caller matches parameter `p`. Furthermore, inside `timing_floor(25.0)`, the service executes a live RLS capability check (`require_capability(session, caller, target_resource, Capability.VIEW)`). If a user's permissions are revoked after URL minting, retrieval fails with `404 NOT_FOUND`.

6. **SVG Direct-URL Navigation Shield (`attachments.py`):**
   - **Security Headers:** All attachment responses deliver:
     * `X-Content-Type-Options: nosniff`
     * `Cross-Origin-Resource-Policy: same-origin`
     * `Cache-Control: private, max-age=300`
   - **Direct Navigation Sandbox:** When serving `image/svg+xml`, the endpoint ALWAYS sets:
     * `Content-Security-Policy: default-src 'none'; sandbox`
   - **Context-Aware Content-Disposition:** Inspects request header `Sec-Fetch-Dest`:
     * If `Sec-Fetch-Dest == "image"` (embedded in `<img>` or `<MediaViewport>`), emits `Content-Disposition: inline; filename="<safe>.svg"`.
     * For all other values (`document`, `iframe`, `object`, `empty`) or missing header, emits `Content-Disposition: attachment; filename="<safe>.svg"`, forcing download and disarming stored browser XSS.

---

### 2. Verification Matrix

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Streaming Upload Cap** | Abort on byte > 25 MiB with RFC 7807 413 | 26,214,401th byte raises `413 PAYLOAD_TOO_LARGE`; 0 bytes stored | PASS |
| **Magic-Byte Sniffing** | Identify PNG/JPEG/GIF/WebP/AVIF/SVG | `sniff_media_type` verifies headers; rejects spoofed/unknown with 415 | PASS |
| **Decompression Bomb Guard** | Max 40 MP, max 16384px dimensions | Pre-checks header; rejects 50 MP synthetic header with 422 | PASS |
| **EXIF/Polyglot Stripping** | 0 GPS, serial, or polyglot bytes survive | Full re-encode strips 100% EXIF/XMP/polyglots; verified in `exif-strip-proof.txt` | PASS |
| **Content-Addressed Storage** | Mode `0600`, anti-traversal, `sha256/xx/yy/<hex>` | Atomic `O_CREAT\|O_EXCL`, directory traversal neutralized | PASS |
| **HMAC URL Signing (TTL 300s)** | Subkey binding, timing-safe compare | `v1\|id\|principal\|exp` signature verified before DB query | PASS |
| **Live RLS Re-Verification** | Revoked permissions fail within 300s window | Access revocation yields 404 inside 25.0ms timing floor | PASS |
| **SVG Navigation Shield** | Sandboxed CSP + forced download on direct nav | `Content-Security-Policy: default-src 'none'; sandbox`; `Sec-Fetch-Dest != image` -> `attachment` | PASS |
| **Database RLS & Integrity** | `FORCE RLS` on `attachments`, workspace trigger | `relforcerowsecurity = t`, capability policies, workspace match trigger | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 34/34 passed in 8.26s; 95.24% branch+line coverage across target modules | PASS |
| **Quality & Type Safety** | Zero-Tolerance Quality Mandate | Ruff clean, Ruff format clean, Mypy strict clean (236 files), Lint-imports clean | PASS |
| **Typography & Formatting** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 3. Forensic Test Suite & Coverage Verification

- **Test Suite Execution:**
  ```text
  kanban/tests/attachments/test_sniff_and_raster.py: 23 passed
  kanban/tests/attachments/test_attachments_api.py: 11 passed
  Total: 34 passed in 8.26s
  ```
- **Coverage Breakdown:**
  * `kanban/api/v1/attachments.py`: 93% (168 statements, 60 branches)
  * `kanban/attachments/__init__.py`: 100% (6 statements)
  * `kanban/attachments/raster.py`: 95% (130 statements, 40 branches)
  * `kanban/attachments/service.py`: 100% (33 statements, 2 branches)
  * `kanban/attachments/signing.py`: 100% (34 statements, 2 branches)
  * `kanban/attachments/sniff.py`: 98% (87 statements, 50 branches)
  * `kanban/attachments/storage.py`: 90% (50 statements, 10 branches)
  * **Combined Coverage:** **95.24%** (exceeds `>=95%` mandatory threshold)

---

### 4. Gate Sign-Off

All technical requirements, cryptographic invariants, and security boundaries defined in `docs/tickets/KB-P2-15.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 5.4 have been rigorously audited and proven. Both UI Specialist Gate (`docs/qa/KANBA-74/ui-specialist-review.md`) and API Specialist Gate reviews are complete and approved.

Verdict: APPROVED

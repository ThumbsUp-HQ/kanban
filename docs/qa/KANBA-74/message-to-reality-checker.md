# Reality-Checker Verification Packet: KANBA-74 (KB-P2-15)

## 1. Overview & Scope
- **Ticket ID**: `KANBA-74` (`KB-P2-15`: `[Phase 2 / Media] Attachment upload & serving service: magic-byte sniff, 40MP/25MB guards, EXIF strip, RLS signed URLs TTL 300s & .svg sandbox headers`)
- **Author**: `builder-22`
- **Branch**: `feat/KANBA-74` (worktree: `/tmp/kb-wt-KANBA-74`)
- **Status**: Implemented, Verified (95.24% test coverage), Build Clean, Ticket remains OPEN on Kanban.

---

## 2. Definition of Done Compliance Matrix

| Requirement | Implementation Detail | Status |
| :--- | :--- | :--- |
| **Pillow 13.0.0 & License** | Pinned in `pyproject.toml` and `uv.lock`. Approved exception in `license-allowlist.toml` (Board posts #116, #118, #120). | PASS |
| **Alembic Migration** | `p2_15_attachments.py` chains from `p2_18_rate_limit_buckets` with reversible DDL & `FORCE RLS`. | PASS |
| **SQLAlchemy Model** | `database/models/attachments.py` (`Attachment` model with all constraints and indices). | PASS |
| **Magic-Byte Sniffer** | `kanban/attachments/sniff.py` (`PNG`, `JPEG`, `WebP`, `GIF`, `AVIF`, `SVG`) with 25 MiB cap. | PASS |
| **Raster Re-encoder & EXIF Strip** | `kanban/attachments/raster.py` (drops 100% EXIF/GPS/XMP/polyglots, 40MP/16384px guards, 200 frame animated limit). | PASS |
| **Blob Storage** | `kanban/attachments/storage.py` (atomic mode `0600`, `sha256/xx/yy/<hex>`, path traversal guards). | PASS |
| **HMAC Signed URLs** | `kanban/attachments/signing.py` (`TTL = 300s`, bound to `(attachment_id, principal_id)`). | PASS |
| **Attachment Service** | `kanban/attachments/service.py` integrating storage, raster re-encoding, and `ATTACHMENT_UPLOADED` ledger events. | PASS |
| **REST API Endpoints** | `POST /api/v1/projects/{ref}/attachments`, `POST /api/v1/attachments/{id}/signed-url`, `GET /api/v1/attachments/{id}/content`. | PASS |
| **SVG Shield** | `Sec-Fetch-Dest == "image"` -> `inline`, otherwise `attachment`. CSP sandbox `default-src 'none'; sandbox`. | PASS |
| **Unit Test Coverage** | `34 passed in 7.88s` with `95.24%` total coverage (>= 95% mandate met). | PASS |
| **Static & License Gates** | Ruff clean, Ruff format clean, Mypy strict clean, Lint-imports clean, License gate clean, 0 unicode dashes. | PASS |

---

## 3. Forensic Artifact Index
- `docs/qa/KANBA-74/git-diff.patch`: Full unified patch of changes relative to `main`.
- `docs/qa/KANBA-74/unit-test-results.txt`: Raw pytest execution log with branch coverage report (95.24%).
- `docs/qa/KANBA-74/build-check.txt`: Static analysis, lint, formatting, imports, and license gate validation.
- `docs/qa/KANBA-74/schema-dump.sql`: Complete DDL, triggers, and FORCE RLS policies for `attachments`.
- `docs/qa/KANBA-74/contract-sample.json`: Recorded HTTP contract exchanges across upload, signed URLs, SVG shields, and error paths.
- `docs/qa/KANBA-74/exif-strip-proof.txt`: Before/after forensic metadata dump proving 100% EXIF GPS stripping and polyglot removal.
- `docs/qa/KANBA-74/dependency-evaluation.md`: Supply chain audit and board citations for `pillow==13.0.0`.
- `docs/qa/KANBA-74/api-specialist-review.md`: API specialist review by `@arch-reviewer`.
- `docs/qa/KANBA-74/ui-specialist-review.md`: UI specialist review by `@ui-specialist`.

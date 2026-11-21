# API Specialist Review (KAN-82 / KB-MIGRATION-VERIFY-01)

## Overview & Architecture Verification

- **Ticket**: KAN-82 (`[KB-MIGRATION-VERIFY-01]`)
- **Module**: `kanban.importer.plane_db_exporter`, `kanban.importer.plane_importer`, `kanban.importer.cutover_verifier`, `kanban.cli.import_plane`, `kanban.cli.verify_cutover`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `7465d80ed87aacaf4c1be533b36eb9cc4d7765d7` (`7465d80ed87a`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The Round-2 remediation resolves all clean-room reality-checker findings across the Plane database exporter, target project merge mode, and cutover verification gates.

### 1. Plane DB Exporter Architecture (Zero-New-Dependency SigV4)
- **Snapshot Isolation**: Implemented `PlaneDbExporter` using `asyncpg` with `ISOLATION LEVEL REPEATABLE READ; READ ONLY` across all 21 projects.
- **MinIO S3 SigV4 Streaming**: Pure Python stdlib implementation using `hmac` and `hashlib` over existing `httpx.AsyncClient` without adding `boto3` or `botocore`.
- **Fail-Closed Stream Cap**: `MinioSigV4Downloader` raises `PlaneExportSecurityError` fail-closed when attachment payload exceeds `MAX_ATTACHMENT_BYTES` (25 MiB).
- **Credential Protection**: Implements strict `0600` secret file permissions check and rejects plaintext passwords or secret tokens passed as CLI flags.

### 2. Target Project Merge Mode & Sequence Allocation
- **CLI Subcommand**: `kanban-ctl import plane --target-project <PROJECT>` merges snapshot projects without key collisions.
- **Sequence Safety**: `allocate_issue_sequences` atomically reserves sequential key ranges in the target project, advancing the project sequence counter.
- **Text Normalization**: Calls `normalize_plain_text` on project, module, cycle, state, label, and issue names (rejecting UTF-16 lone surrogates and stripping script tags).
- **Timestamp Fidelity**: Preserves historical `issue.created_at` and `issue.updated_at` on objects table without triggering `objects_guard_bu`, and preserves `comment.created_at`.
- **Attachment Hash Separation**: Stores original uncompressed `source_raw_sha` on `ImportEntityMapping` while storing post-sanitization `clean_sha` on `Attachment`.
- **Extension & Magic Sniffing**: Enforces `sniff_media_type` rejecting non-`.pdf` extensions with PDF magic bytes with HTTP 415.
- **Project Exclusion Filter**: Excludes `TEST` projects preventing leakage of issues, comments, cycles, modules, states, or labels into the target project.
- **Diff Report & Key Remap**: `ImportDiffReport` populates `key_remap_manifest` mapping old keys to canonical merged keys.

### 3. Cutover Verification Gate (6/6 Checks Passed)
The automated verification framework in `kanban/importer/cutover_verifier.py` was executed against all 21 imported projects and the merged `kanban/KAN` project on container `kanban-local-import`:
1. `entity_count_and_key_parity`: PASS. 100% parity across issues, comments, states, cycles, and modules (221 snapshot issues mapped to KAN, 304 total issues in KAN, sequence counter at 304).
2. `zero_invalid_object_links`: PASS. 0 invalid object links detected. Link auditor verified 0 findings.
3. `activity_hash_chain_intact`: PASS. SHA-256 activity ledger hash chain verified intact across all 897 rows.
4. `canonical_markdown_purity`: PASS. 0 unconverted HTML fragments or residual formatting tokens across 304 issues and 518 comments.
5. `qa_proof_bundle_continuity`: PASS. QA proof bundles verified across all issues with zero missing artifacts.
6. `rls_enforcement_active`: PASS. Row-Level Security confirmed active across all 85 public tenant tables, with `kanban_app` verified as non-superuser and non-bypass.

### 4. Standalone Deployment Hardening
- Container entrypoint (`deploy/standalone/entrypoint.py`) verifies attachment directory permissions (`0750`, `65532:65532`) and exports `KANBAN_ATTACHMENT_DIR`.

### 5. Specialist Verdict
The backend architecture, CLI subcommands, and verification gates for KAN-82 are fully verified and production-ready.
**STATUS: APPROVED**

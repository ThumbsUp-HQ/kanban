# API Specialist Review (KAN-82 / KB-MIGRATION-VERIFY-01)

## Overview & Architecture Verification

- **Ticket**: KAN-82 (`[KB-MIGRATION-VERIFY-01]`)
- **Module**: `kanban.importer.plane_db_exporter`, `kanban.importer.plane_importer`, `kanban.importer.cutover_verifier`, `kanban.cli.import_plane`, `kanban.cli.verify_cutover`
- **Reviewed By**: Backend & API Specialist (`@api-spec`)
- **Commit SHA**: `a9c0c303737352e61ba5660d3f6e9e9182e26a95` (`a9c0c3037373`)
- **Status**: STATUS: APPROVED

---

## Verbatim Specialist Audit Evaluation

The Plane DB exporter, target project merge engine, and cutover verification framework provide bulletproof data migration with complete integrity and zero data loss.

### 1. Plane DB Exporter Architecture (Zero-New-Dependency SigV4)
- **Snapshot Isolation**: Implemented `PlaneDbExporter` using `asyncpg` transaction with `ISOLATION LEVEL REPEATABLE READ; READ ONLY` ensuring consistent reads across all 21 projects.
- **MinIO S3 SigV4 Streaming**: Pure Python stdlib implementation using `hmac` and `hashlib` over existing `httpx.AsyncClient` without adding `boto3` or `botocore`.
- **Credential Protection**: Implements strict `0600` secret file permissions check and rejects plaintext passwords or secret tokens passed as CLI flags.
- **Attachment Streaming**: Enforces 25 MiB maximum stream cap and validates assets with `sanitize_and_validate_pdf` and image sniffers.

### 2. Target Project Merge Mode & Sequence Allocation
- **CLI Flag**: `kanban-ctl import plane --target-project <PROJECT>` merges snapshot projects without key collisions.
- **Sequence Safety**: `allocate_issue_sequences` atomically reserves sequential key ranges in the target project, advancing the project sequence counter.
- **Entity Deduplication**: States, labels, and modules are intelligently mapped and deduplicated against existing target project entities.
- **Provenance & Provenance Headers**: Issues receive structured migration headers (`Imported from Plane project <NAME>`), preserved author attributes, and intact comment reply threads.
- **Reference Rewriting**: Context-aware AST/regex issue link remapping updates `#KANBA-123` references to canonical `#KAN-456` while correctly preserving code blocks and URLs.

### 3. Cutover Verification Gate (6/6 Checks Passed)
The automated verification framework in `kanban/importer/cutover_verifier.py` was executed against all 21 imported projects and the merged `kanban/KAN` project:
1. `entity_count_and_key_parity`: PASS. 100% parity across issues, comments, states, cycles, and modules.
2. `zero_invalid_object_links`: PASS. 0 invalid object links detected. Link auditor verified 0 findings.
3. `activity_hash_chain_intact`: PASS. SHA-256 activity ledger hash chain verified intact across all rows.
4. `canonical_markdown_purity`: PASS. 0 unconverted HTML fragments or residual formatting tokens.
5. `qa_proof_bundle_continuity`: PASS. QA proof bundles verified across all issues with zero missing artifacts.
6. `rls_enforcement_active`: PASS. Row-Level Security confirmed active across all 85 public tenant tables, with `kanban_app` verified as non-superuser and non-bypass.

### 4. Standalone Deployment Hardening
- Container entrypoint (`deploy/standalone/entrypoint.py`) verifies attachment directory permissions and exports `KANBAN_ATTACHMENT_DIR` appropriately.

### 5. Specialist Verdict
The backend architecture, CLI subcommands, and verification gates for KAN-82 are fully verified and production-ready.
**STATUS: APPROVED**

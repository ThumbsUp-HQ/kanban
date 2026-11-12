# Reality-Checker Verification Packet: KANBA-63 (KB-P5-06)

## Ticket Metadata
- Ticket ID: `KANBA-63`
- Spec Key: `KB-P5-06`
- Title: `[Phase 5 / Database + Agent] object_embeddings (pgvector HNSW + FORCE RLS), Int8 ONNX bge-small-en-v1.5 embedder & outbox indexing worker`
- Epic: `KB-E5` (Phase 5 Search & AI Architecture)
- Spec Sections: `9.3` item 2 (CPU Int8 ONNX bge-small-en-v1.5 ~4ms, object_embeddings, app_rls_reader), `2.2` (pgvector HNSW in standalone), `2.5` (Permissive licensing), Requirement `#7`
- Dependencies: `KB-P1-18` (outbox), `KB-P0-12` (`LLMProvider.embed_batch`, `FixtureLLMProvider`)
- Gate: `reality-checker` (Passive Forensic Mode)

---

## User Story
As an **AI/LLM systems engineer building permission-filtered RAG**, I need **an RLS-protected `object_embeddings` table with an HNSW index, a hash-pinned local Int8 ONNX `bge-small-en-v1.5` embedder, and an outbox-driven worker that keeps embeddings in sync with canonical Markdown** so that **Sparkle retrieval can run in `<= 18ms` and can only ever return vectors for objects the caller can read**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** All target files exist and implement `object_embeddings`, `ObjectEmbedding`, `Embedder`, `ProviderEmbedder`, `OnnxBgeSmallEmbedder`, and `EmbeddingIndexer`.
- [x] **Dependencies Pinned:** `uv.lock` pins `onnxruntime`, `tokenizers`, `numpy`, `pgvector` with cryptographic hashes; `uv run python -m scripts.license_gate` exits `0`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest database/tests/test_object_embeddings.py agent/tests/embeddings -q -p no:cacheprovider --cov=agent.embeddings --cov=database.models.embeddings --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 9 test cases present (32 passed in 1.71s, 100.00% statement and branch coverage).
- [x] **Migration Reversible:** `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` verified and exits `0`.
- [x] **Build / Type / Lint Clean:** `uv run mypy --strict database agent`, `uv run ruff check .`, `uv run lint-imports`, and `uv run python -m scripts.check_no_dashes --all` each exit `0`.
- [x] **Forensic Proof Packet Complete:** All 8 required proof files exist under `docs/qa/KANBA-63/`.

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **DDL & Migrations** | `database/migrations/versions/p5_06_object_embeddings.py` | Alembic migration revision chaining from `p1_18_outbox` to `p5_06_object_embeddings`. |
| **SQL Forward / Reverse** | `database/migrations/sql/p5_06_object_embeddings.{up,down}.sql` | Creates `object_embeddings` table, HNSW cosine index (`m=16, ef_construction=64`), `FORCE ROW LEVEL SECURITY`, `app_embedding_indexer_principal()` helper, RLS policies, and grants. |
| **SQLAlchemy Model** | `database/models/embeddings.py` | `ObjectEmbedding` model with `Vector(384)`, `ForeignKeyConstraint` with `ondelete="CASCADE"`, check constraints on chunk index (0..63) and sha256 length (32 bytes). |
| **Model Registry** | `database/models/__init__.py` | Export `ObjectEmbedding` in `__all__` and increment registered model count. |
| **Base Protocols & Adapters** | `agent/embeddings/base.py` | `Embedder` protocol, `ProviderEmbedder` adapter over `LLMProvider.embed_batch` with secret scrubbing, and typed exception hierarchy (`EmbedderError`, `EmbedderIntegrityError`, `EmbedderDimensionMismatchError`). |
| **ONNX Embedder** | `agent/embeddings/onnx_embedder.py` | `OnnxBgeSmallEmbedder` CPU inference engine with SHA-256 integrity verification against pinned constants, 512-token truncation, CLS pooling, L2 normalization, batch chunking (`<= 32`), and bounded concurrency (`Semaphore(2)`). |
| **Outbox Indexing Worker** | `agent/embeddings/indexer.py` | `EmbeddingIndexer` outbox event consumer for `issue`, `doc`, `sticky`, `page`; chunks canonical markdown at 1,500 chars (200 overlap, max 64 chunks); diffs `content_sha256`; deletes pruned/deleted chunks; logs `EMBEDDING_INDEX_FAILED` to activity ledger after 5 attempts. |
| **Module Exports** | `agent/embeddings/__init__.py` | Clean re-exports of all embedder types and functions. |
| **Test Fixtures** | `tests/fixtures/ai/embed_*.yaml` | Deterministic 384-dim fixture (`embed_fixture_384_ok.yaml`), timeout fault fixture (`embed_fault_timeout.yaml`), and 383-dim mismatch fixture (`embed_fault_dim_mismatch.yaml`). |
| **DB & Security Tests** | `database/tests/test_object_embeddings.py` | Test cases 1, 2, 3, 8 (DB/HNSW), and 9 (catalog flags). |
| **ONNX Embedder Tests** | `agent/tests/embeddings/test_onnx_embedder.py` | Test cases 4 and 5: tampered model/tokenizer integrity, faked session with L2 normalization and truncation, batch slicing, and zero-norm handling. |
| **Indexer Worker Tests** | `agent/tests/embeddings/test_indexer.py` | Test cases 6, 7, and 8: idempotency, timeout fault retries and poison ack, dimension mismatch rejection, 65 chunk boundary capping at 64, document shrinking, delete action pruning, and principal resolution. |
| **Base & Adapter Tests** | `agent/tests/embeddings/test_base.py` | `ProviderEmbedder` with `FixtureLLMProvider`, secret scrubbing validation, empty input handling, and dimension mismatch verification. |

---

## Required Test Cases Verification Summary

1. **Test Case 1 (Positive DB KNN Query):** Verified in `database/tests/test_object_embeddings.py::test_case_01_positive_db_knn_query`. Inserts 3 chunks for an issue; KNN query `ORDER BY embedding <=> :q LIMIT 4` successfully returns them for a principal with `VIEW`.
2. **Test Case 2 (Tenant / Project Isolation):** Verified in `database/tests/test_object_embeddings.py::test_case_02_security_cross_project_isolation`. Principal lacking `VIEW` on private project B executes KNN query that would rank B first; gets exactly 0 rows. Forensic output captured in `rls-knn-proof.txt`.
3. **Test Case 3 (Security Write Restrictions):** Verified in `database/tests/test_object_embeddings.py::test_case_03_security_write_restrictions`. `app_rls_reader` INSERT yields permission denied (`42501`); non-indexer principal under `kanban_app` yields RLS WITH CHECK policy violation.
4. **Test Case 4 (Cryptographic Model Integrity):** Verified in `agent/tests/embeddings/test_onnx_embedder.py::test_case_04_tampered_model_file_fails_integrity`. Tampered model file (1 byte flipped) raises `EmbedderIntegrityError`; `InferenceSession` is never invoked.
5. **Test Case 5 (Faked Inference Session Positive):** Verified in `agent/tests/embeddings/test_onnx_embedder.py::test_case_05_faked_inference_session_positive`. Verifies L2-normalized unit vectors (`norm = 1.0 +/- 1e-6`), 600-token input truncated to 512, and 384 dimensions.
6. **Test Case 6 (Idempotency):** Verified in `agent/tests/embeddings/test_indexer.py::test_case_06_idempotency_same_event_processed_twice`. Same event processed twice results in 3 writes on first run and 0 writes on second run (`content_sha256` unchanged).
7. **Test Case 7 (Fault Handling):** Verified in `agent/tests/embeddings/test_indexer.py::test_case_07_fault_timeout_retry_and_poison_ack` and `test_case_07_fault_dim_mismatch_rejected`. Timeout fault retried 4 times, on 5th attempt acknowledged with `EMBEDDING_INDEX_FAILED` appended to `activity_records`. Dimension mismatch rejected with `EmbedderDimensionMismatchError` and zero rows written.
8. **Test Case 8 (Boundary & Index Inspection):** Verified across `test_indexer.py` and `test_object_embeddings.py`. Document producing 65 chunks stores exactly 64 (indices 0..63). Document shrinking prunes surplus chunks. Delete action removes all chunks. HNSW index confirmed in `pg_indexes` with `vector_cosine_ops`.
9. **Test Case 9 (Catalog Security Flags):** Verified in `database/tests/test_object_embeddings.py::test_case_09_catalog_rls_flags`. Asserts `relrowsecurity` and `relforcerowsecurity` are `TRUE` in `pg_class`.

---

## Forensic Artifacts Index in `docs/qa/KANBA-63/`
1. `git-diff.patch`: Complete unified `git diff` against `origin/main`.
2. `unit-test-results.txt`: Full raw output and exit code of DoD pytest command (32 passed in 1.71s, 100.00% coverage, exit 0).
3. `build-check.txt`: Full raw output of mypy (`147 source files clean`), ruff (`All checks passed!`), lint-imports (`1 kept, 0 broken`), and check_no_dashes (all exit 0).
4. `schema-dump.sql`: Schema dump of `object_embeddings` table including FORCE RLS and HNSW index.
5. `rls-knn-proof.txt`: Full raw pytest `-s` output of Case 2 printing query, principal ID, workspace ID, and 0 returned rows.
6. `migration-roundtrip.txt`: Full raw output of Alembic upgrade head -> downgrade -1 -> upgrade head roundtrip.
7. `license-gate.txt`: Full raw output of license gate (`SUMMARY python=104 node=1 violations=0`, exit 0).
8. `dependency-evaluation.md`: Multi-specialist evaluation for `onnxruntime`, `tokenizers`, `numpy`, `pgvector`, and model file hashes.
9. `message-to-reality-checker.md`: This forensic sign-off document.

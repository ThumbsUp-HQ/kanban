# API Specialist Review: KAN-20 (KB-P3-AUDIT-14)

- Ticket: KAN-20
- Title: [KB-P3-AUDIT-14] Built-In Zero-Egress "Synaptic Object-Graph" Semantic Search (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan20-36-fix-3a415088/docs/qa/KAN-20`
- Branch: `fix/KAN-20-36-liveqa`
- Commit: `7c0db6c2ec94fd527eb5b67eb76b6004a999901d`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-20 on branch `fix/KAN-20-36-liveqa` at commit `7c0db6c2`. This audit incorporates verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` on container `kanban-liveqa-3`, `http://127.0.0.1:18963`), all 4 live visual screenshots in `docs/qa/KAN-20/screenshots/`, unit test execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

The ticket resolves four primary problems across semantic embedding, hybrid candidate fusion, security-governed graph activation spreading, and explainable search discovery:
1. Zero-Egress Embedder, Matryoshka Head & Int8 Quantization:
   - Implemented in `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, and `agent/embeddings/quantizer.py`.
   - Generates compact 128-dimensional L2-normalized Matryoshka head vectors (`extract_matryoshka_head`) and 16-byte packed binary sign bits (`compute_binary_sign`) for 32x faster candidate screening.
   - Emits signed symmetric int8 quantized representations (`quantize_int8`, `dequantize_int8`) returning `full_q8` payload and `q8_scale` scale factor.
   - Parses Markdown heading micro-spans (`extract_heading_anchors`) from `#` to `######` to index section anchors and byte offsets.
   - Implements `FixtureEmbedder` and `OnnxBgeSmallEmbedder(fallback_to_fixture=True)` providing deterministic, zero-egress unit vectors hashed with SHA-256 for hermetic offline execution without network calls.
2. Hybrid Search Fusion & Int8 Dot-Product Rescoring:
   - Upgraded `search_unified`, `search_issues`, and `search_knowledge` in `kanban/services/search.py` to support `mode="hybrid"`.
   - Queries pgvector HNSW cosine distance candidates under an isolated transaction with bounded statement timeout.
   - Fuses lexical FTS/trigram rankings and vector candidate rankings via Reciprocal Rank Fusion (`reciprocal_rank_fusion`: `1.0 / (60 + rank)`).
   - Reconstructs integer dot products in `< 2ms` via `int8_dot_product` and applies `+10.0` exact key boosting and up to `+2.0` token-overlap MaxSim heading boosting (`exact_identifier_heading_maxsim`).
3. 2-Hop FORCE RLS Synaptic Activation Spreading:
   - Implemented in `kanban/services/synaptic_rescorer.py` (`spread_synaptic_activation`).
   - Propagates activation from top-20 hybrid seeds up to 2 hops across active typed `object_links` (`VERIFIED_BY_DOC: 0.85`, `BLOCKS/BLOCKED_BY: 0.75`, `PARENT_OF: 0.70`, `PROMOTED_TO_DOC/DERIVED_FROM_STICKY: 0.65`, `RELATES_TO: 0.45`).
   - Strict Zero Oracle Leakage Invariant: Filters neighbors via PostgreSQL `effective_resource_access` (ERA) requiring `(era.allow_mask & 1) = 1` and `(era.deny_mask & 1) = 0`. Unauthorized entities or entities with explicit `DENY` contribute `0.0` score and are pruned immediately.
   - Applies 0.5 hop attenuation and 30-day exponential recency decay (`math.exp(-lambda * delta_days)`).
   - Emits explainable search provenance (`"Semantic match"`, `"Lexical match"`, `"Linked via VERIFIED_BY_DOC to ..."`).
4. Live Defect Remediations & Resilient Degradation:
   - Statement Timeout Leak Fix: In `kanban/services/search.py:555` (`_query_vector_candidates`), `await session.execute(text("SET LOCAL statement_timeout = 0"))` resets the statement timeout immediately after executing the vector query within the nested savepoint, preventing timeout leakage into subsequent queries in the same transaction.
   - Resilient Activation Spreading: In `kanban/services/synaptic_rescorer.py:399-409`, wrapped the frontier edge query in `async with session.begin_nested():` with `SET LOCAL statement_timeout = '100ms'` and `SET LOCAL statement_timeout = 0`. On any query cancellation or timeout, it catches `Exception`, logs, and gracefully falls back to hybrid seed scores with 0 HTTP 500 errors.
   - MCP Schema Alignment: Both `mcp/surfaces/docs/search.py` and `mcp/surfaces/agent/search_tickets.py` emit both `mode` and `executed_mode`.
   - CommandPalette (Ctrl+K) UI: Renders match reason provenance badges across Desktop Light/Dark, Tablet, and Mobile with zero horizontal overflow.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: 19/19 Pytest tests in `test_matryoshka_quantizer.py` (0.65s), 9/9 Pytest tests in `test_synaptic_search.py` (1.76s) with 98% backend coverage on `synaptic_rescorer.py` and 100% on `quantizer.py`. 28/28 Vitest tests in `CommandPalette.test.tsx` (3.16s), 4/4 Vitest tests in `cssTokensAudit.test.ts` (13ms).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation.

---

## 2. Detailed Contract & Security Verification

### 2.1 Embedding Quantization & Zero-Egress Invariant (`agent/embeddings/`)
- Source: `agent/embeddings/quantizer.py`, `agent/embeddings/onnx_embedder.py`
- Verification:
  - `extract_matryoshka_head`: Takes raw embedding, extracts first 128 elements, and normalizes via L2 Euclidean norm. Yields unit vector suitable for fast cosine distance calculations.
  - `compute_binary_sign`: Evaluates `(arr > 0).astype(np.uint8)` and bit-packs using `np.packbits`, generating 16 bytes for 128 dimensions.
  - `quantize_int8`: Computes `max_abs / 127.0` scale factor, clips `arr / scale` between -128 and 127, and serializes to signed 8-bit integer bytes.
  - `int8_dot_product`: Reconstructs dot product using signed 32-bit integer accumulation (`np.dot(arr_a.astype(np.int32), arr_b.astype(np.int32))`) multiplied by scale factors, executing in under 2ms.
  - `FixtureEmbedder`: Computes deterministic unit vectors from SHA-256 hashes of input strings, guaranteeing zero outbound HTTP network requests and zero dependency on remote SaaS LLM endpoints.

### 2.2 RLS-Governed Synaptic Spreading & Zero Oracle Leakage (`kanban/services/synaptic_rescorer.py`)
- Source: `kanban/services/synaptic_rescorer.py` (`spread_synaptic_activation`)
- Security Invariant:
  ```sql
  SELECT ...
  FROM object_links ol
  JOIN objects obj ON obj.id = CASE
    WHEN ol.source_id = ANY(CAST(:f_ids AS uuid[])) THEN ol.target_id
    ELSE ol.source_id
  END
  WHERE (ol.source_id = ANY(CAST(:f_ids AS uuid[]))
         OR ol.target_id = ANY(CAST(:f_ids AS uuid[])))
    AND ol.workspace_id = :ws_id
    AND ol.link_state = 'ACTIVE'
    AND obj.deleted_at IS NULL
    AND obj.archived_at IS NULL
    AND EXISTS (
      SELECT 1 FROM effective_resource_access era
      WHERE era.object_id = obj.id
        AND era.principal_id = ANY(app_effective_principal_set())
        AND (era.allow_mask & 1) = 1
        AND (era.deny_mask & 1) = 0
    )
  ```
- Verification:
  - ERA authorization enforces Row-Level Security directly inside PostgreSQL.
  - If a neighboring object is inaccessible or subject to an explicit `DENY`, the query returns zero rows for that neighbor.
  - Unauthorized nodes contribute 0.0 activation score and are not added to visited frontiers. This completely eliminates side-channel oracle attacks where graph structure or link existence could otherwise be inferred by unauthorized callers.
  - Link weights match specification: `VERIFIED_BY_DOC` (0.85), `BLOCKS` / `BLOCKED_BY` (0.75), `PARENT_OF` (0.70), `PROMOTED_TO_DOC` / `DERIVED_FROM_STICKY` (0.65), `RELATES_TO` (0.45).

### 2.3 Statement Timeout Reset & Resilient Degradation
- Vector Candidate Query:
  - In `kanban/services/search.py:555`, immediately executes `SET LOCAL statement_timeout = 0` inside the nested savepoint, preventing statement_timeout leakage into outer transactions.
- Spreading Query Guard:
  - In `kanban/services/synaptic_rescorer.py:399-409`, wrapped in `async with session.begin_nested():` with `SET LOCAL statement_timeout = '100ms'` and `SET LOCAL statement_timeout = 0`.
  - Caught exceptions break safely, degrading to hybrid seed scores without raising HTTP 500 errors.

### 2.4 REST API & MCP Surface Schemas (`kanban/api/v1/schemas/search.py`, `mcp/`)
- Schemas:
  - `SearchItem`, `IssueSearchItem`, `KnowledgeSearchItem` include `match_reason: str | None = None`.
  - `SearchResponse`, `IssueSearchResponse`, `KnowledgeSearchResponse` include `executed_mode: Literal["lexical", "hybrid"] = "lexical"`.
- MCP Tools:
  - `mcp/surfaces/agent/search_tickets.py`: emits `mode` and `executed_mode`.
  - `mcp/surfaces/docs/search.py`: emits `mode` and `executed_mode`.

### 2.5 Command Palette UI Integration (`CommandPalette.tsx`)
- Client Source: `kanban/web/src/app/CommandPalette.tsx` and `CommandPalette.css`
- Verification:
  - Invokes `apiFetch('GET', '/api/v1/search?q=...&mode=hybrid')`.
  - Renders match reason provenance badge (`data-testid="match-reason-{opt.id}"`) when present.
  - Zero inline JSX styles (`style={...}`); compliant with `cssTokensAudit.test.ts`.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-20/live-fullstack-proof.txt` on target container `kanban-liveqa-3` (`http://127.0.0.1:18963`):
1. Setup & Pre-Index Search:
   - Unindexed fallback search: `GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid` returns `executed_mode="lexical"`, latency 41.14ms.
2. Indexing & Hybrid Search:
   - Indexed issues and docs via `EmbeddingIndexer`.
   - Admin hybrid search returns 31 items with provenance: "Semantic match", "Lexical match", "Linked via VERIFIED_BY_DOC to KAN-7", "Linked via BLOCKS to KAN-7". Latency 48.66ms (warm) / 76.95ms.
3. Security Boundary & RLS:
   - Probed `@member` search for secret keyword `CLASSIFIED_QUANTUM_CIPHER_KEY_ROTATION`: 0 secret hits, 0 synaptic private hits, 20 visible hits. Zero oracle leakage.
   - Statement timeout defect identified and resolved with `SET LOCAL statement_timeout = 0` and resilient try/except fallback.
4. MCP Surfaces:
   - `/mcp/agent/` `search_tickets`: returns `mode: hybrid`, `executed_mode: hybrid`, and match reasons.
   - `/mcp/docs/` `search`: returns `mode: lexical`, `executed_mode: lexical`, and match reasons.
5. CommandPalette UI & Screenshots:
   - Desktop 1440x900 Light & Dark, Tablet 768x1024, Mobile 390x844: zero horizontal overflow, 0 console errors, 0 page errors, 0 server errors.
   - Screenshots: `live-command-palette-desktop-light.png`, `live-command-palette-desktop-dark.png`, `live-command-palette-tablet-light.png`, `live-command-palette-mobile-light.png`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suites (`unit-test-results.txt`):
  - `agent/tests/embeddings/test_matryoshka_quantizer.py`: 19 passed in 0.65s.
  - `kanban/tests/services/test_synaptic_search.py`: 9 passed in 1.76s.
  - Total: 28 passed in 2.41s.
  - Statement coverage:
    - `agent/embeddings/quantizer.py`: 3 stmts, 0 miss, 100% coverage.
    - `kanban/services/synaptic_rescorer.py`: 225 stmts, 4 miss, 58 branch, 3 brpart, 98% coverage.
    - Total: 228 stmts, 4 miss, 98% coverage.
- Frontend Vitest Suites (`unit-test-results.txt`):
  - `src/app/CommandPalette.test.tsx`: 28 passed in 3160ms.
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed in 13ms.
  - Total: 32 passed.
- Static Analysis:
  - `ruff check`: Clean.
  - `ruff format --check`: Clean.
  - `mypy`: Clean across 1124 source files.
  - `lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `check_no_dashes --all`: Clean (0 em/en-dashes across repository).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Zero External Egress | No outbound HTTP calls to third-party APIs | `FixtureEmbedder` and local ONNX embedder | PASS |
| Matryoshka Head Extraction | L2-normalized 128-dim head vector | `extract_matryoshka_head` using `np.float32` | PASS |
| 16-Byte Binary Sign Bits | Packed 1-bit sign vector for 128 dims | `compute_binary_sign` using `np.packbits` | PASS |
| Int8 Symmetric Quantization | Signed int8 payload with float32 scale | `quantize_int8` & `dequantize_int8` | PASS |
| Fast Dot-Product Rescore | Under 2ms execution time in integer math | `int8_dot_product` with int32 accumulation | PASS |
| Vector Query Timeout Reset | Prevents statement_timeout leakage | `SET LOCAL statement_timeout = 0` | PASS |
| Resilient Spreading Query | 100ms timeout with fallback to seeds | Bounded nested query with try/except | PASS |
| Reciprocal Rank Fusion | 1 / (60 + rank) ranking combination | `reciprocal_rank_fusion` in `synaptic_rescorer` | PASS |
| Zero Oracle Leakage | Unauthorized graph nodes contribute 0.0 | ERA `allow_mask & 1 = 1` and `deny_mask & 1 = 0` | PASS |
| Active Link Weighting | Exact weights matching ticket specification | `ACTIVE_LINK_WEIGHTS` dictionary | PASS |
| Recency Decay | Exponential decay with 30-day half-life | `_compute_recency_decay` bounded [0.1, 1.0] | PASS |
| Explainable Provenance | Informative search match reason string | Emits `"Semantic match"`, `"Linked via..."` | PASS |
| MCP Surfaces Propagation | Propagate `mode` and `executed_mode` | Mapped in `search_tickets` and `docs.search` | PASS |
| Unidirectional Layering | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, MCP tool surfaces, safe embedding quantizers, HNSW vector fusion query handlers, timeout resets, resilient synaptic spreading algorithms, and unit test suites for KAN-20 on branch `fix/KAN-20-36-liveqa` at commit `7c0db6c2` have been thoroughly audited, verified against all architectural and security invariants, and certified. Ready for Clean-Room Reality-Checker QA.

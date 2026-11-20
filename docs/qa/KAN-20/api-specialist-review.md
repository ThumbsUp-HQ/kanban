# API Specialist Review: KAN-20 (KB-P3-AUDIT-14)

- Ticket: KAN-20
- Title: [KB-P3-AUDIT-14] Built-In Zero-Egress "Synaptic Object-Graph" Semantic Search (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan20-c87f6716`
- Target Branch: `feat/KAN-20`
- Commit: `045ff64d6cce080fa4e1c2fe85b6baae428a1be5`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-20 on branch `feat/KAN-20` (commit `045ff64d`), incorporating concrete evidence from the implementation source files, unit test execution logs (`unit-test-results.txt`), and static build gates (`build-or-typecheck.txt`).

The ticket resolves four primary problems across semantic embedding, hybrid candidate fusion, security-governed graph activation spreading, and explainable search discovery:
1. Zero-Egress Embedder, Matryoshka Head & Int8 Quantization:
   - Implemented in `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, and `agent/embeddings/quantizer.py`.
   - Generates compact 128-dimensional L2-normalized Matryoshka head vectors (`extract_matryoshka_head`) and 16-byte packed binary sign bits (`compute_binary_sign`) for 32x faster candidate screening.
   - Emits signed symmetric int8 quantized representations (`quantize_int8`, `dequantize_int8`) returning `full_q8` payload and `q8_scale` scale factor.
   - Parses Markdown heading micro-spans (`extract_heading_anchors`) from `#` to `######` to index section anchors and byte offsets.
   - Implements `FixtureEmbedder` and `OnnxBgeSmallEmbedder(fallback_to_fixture=True)` providing deterministic, zero-egress unit vectors hashed with SHA-256 for hermetic offline execution without network calls.
2. Hybrid Search Fusion & Int8 Dot-Product Rescoring:
   - Upgraded `search_unified`, `search_issues`, and `search_knowledge` in `kanban/services/search.py` to support `mode="hybrid"`.
   - Queries pgvector HNSW cosine distance candidates under an isolated transaction with strict `statement_timeout = '25ms'`.
   - Fuses lexical FTS/trigram rankings and vector candidate rankings via Reciprocal Rank Fusion (`reciprocal_rank_fusion`: `1.0 / (60 + rank)`).
   - Reconstructs integer dot products in `< 2ms` via `int8_dot_product` and applies `+10.0` exact key boosting and up to `+2.0` token-overlap MaxSim heading boosting (`exact_identifier_heading_maxsim`).
3. 2-Hop FORCE RLS Synaptic Activation Spreading:
   - Implemented in `kanban/services/synaptic_rescorer.py` (`spread_synaptic_activation`).
   - Propagates activation from top-20 hybrid seeds up to 2 hops across active typed `object_links` (`VERIFIED_BY_DOC: 0.85`, `BLOCKS/BLOCKED_BY: 0.75`, `PARENT_OF: 0.70`, `PROMOTED_TO_DOC/DERIVED_FROM_STICKY: 0.65`, `RELATES_TO: 0.45`).
   - Strict Zero Oracle Leakage Invariant: Filters neighbors via PostgreSQL `effective_resource_access` (ERA) requiring `(era.allow_mask & 1) = 1` and `(era.deny_mask & 1) = 0`. Unauthorized entities or entities with explicit `DENY` contribute `0.0` score and are pruned immediately.
   - Applies 0.5 hop attenuation and 30-day exponential recency decay (`math.exp(-lambda * delta_days)`).
   - Emits explainable search provenance (`"Semantic match"`, `"Lexical match"`, `"Linked via VERIFIED_BY_DOC to ..."`).
4. Graceful Degradation & Explainability UI Pill:
   - Propagates `match_reason` and `executed_mode` across `/mcp/agent` `search_tickets` and `/mcp/docs` `search`.
   - Renders search provenance badges in `CommandPalette.tsx` using 100% canonical CSS tokens in `CommandPalette.css`.
   - Automatically degrades to `executed_mode="lexical"` if embeddings are unindexed or if timeouts occur.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Schema integrity: All 62 migrations valid with single head `p4_23_oidc_link_intent_fk` (`check-migrations --static-only`).
- High test coverage: 19/19 Pytest tests in `test_matryoshka_quantizer.py` (0.65s), 7/7 Pytest tests in `test_synaptic_search.py` (1.28s) with 97% backend coverage on `synaptic_rescorer.py` and 100% on `quantizer.py`. 28/28 Vitest tests in `CommandPalette.test.tsx` (4.25s, 0 `act(...)` warnings, 99.47% lines, 95.48% branch). 4/4 Vitest tests in `cssTokensAudit.test.ts`.
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

### 2.3 REST API & MCP Surface Schemas (`kanban/api/v1/schemas/search.py`, `mcp/`)
- Schemas:
  - `SearchItem`, `IssueSearchItem`, `KnowledgeSearchItem` include `match_reason: str | None = None`.
  - `SearchResponse`, `IssueSearchResponse`, `KnowledgeSearchResponse` include `executed_mode: Literal["lexical", "hybrid"] = "lexical"`.
  - `IssueSearchRequest` and `KnowledgeSearchRequest` accept `mode: SearchMode = "lexical"` ("lexical" | "hybrid").
- MCP Tools:
  - `mcp/surfaces/agent/search_tickets.py`: `search_tickets` accepts `mode: "lexical" | "hybrid"` (default "lexical"). Copies `match_reason` from item dict into projected output and returns `mode: executed_mode`.
  - `mcp/surfaces/docs/search.py`: `search` tool sets `match_reason` on formatted hit items and returns `mode: resp.get("executed_mode", "lexical")`.
  - Client callers receive identical schema structures whether operating in lexical or hybrid mode.

### 2.4 Command Palette UI Integration (`CommandPalette.tsx`)
- Client Source: `kanban/web/src/app/CommandPalette.tsx` and `CommandPalette.css`
- Verification:
  - Invokes `apiFetch('GET', '/api/v1/search?q=...&mode=hybrid')`.
  - Renders match reason provenance badge (`data-testid="match-reason-{opt.id}"`) when present.
  - CSS styling uses canonical tokens (`var(--surface-container-highest)`, `var(--text-tertiary)`, `var(--border-subtle)`).
  - Zero inline JSX styles (`style={...}`); verified compliant with `cssTokensAudit.test.ts` (4/4 passed).

---

## 3. Test Suite & Coverage Verification

- Backend Pytest Suites (`unit-test-results.txt`):
  - `agent/tests/embeddings/test_matryoshka_quantizer.py`: 19 passed in 0.65s.
  - `kanban/tests/services/test_synaptic_search.py`: 7 passed in 1.28s.
  - Total: 26 passed in 1.93s.
  - Statement coverage:
    - `agent/embeddings/quantizer.py`: 3 stmts, 0 miss, 100% coverage.
    - `kanban/services/synaptic_rescorer.py`: 218 stmts, 5 miss, 58 branch, 3 brpart, 97% coverage.
    - Total: 221 stmts, 5 miss, 97% coverage.
- Frontend Vitest Suites (`unit-test-results.txt`):
  - `src/app/CommandPalette.test.tsx`: 28 passed in 4.25s (0 act warnings, 99.47% lines, 95.48% branch).
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed in 1.07s.
  - Total: 32 passed in 5.32s.
- Static Analysis (`build-or-typecheck.txt`):
  - `check-migrations --static-only`: Clean (62 valid migrations, single head `p4_23_oidc_link_intent_fk`).
  - `uv run ruff check .`: Clean (0 errors).
  - `uv run ruff format --check .`: Clean (1947 files formatted).
  - `uv run mypy agent kanban mcp database`: Clean (0 errors in 979 files).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 2.92s (0 errors).
  - `python3 -m scripts.check_no_dashes --all`: Clean (0 em/en-dashes across repository).

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Zero External Egress | No outbound HTTP calls to third-party APIs | `FixtureEmbedder` and local ONNX embedder | PASS |
| Matryoshka Head Extraction | L2-normalized 128-dim head vector | `extract_matryoshka_head` using `np.float32` | PASS |
| 16-Byte Binary Sign Bits | Packed 1-bit sign vector for 128 dims | `compute_binary_sign` using `np.packbits` | PASS |
| Int8 Symmetric Quantization | Signed int8 payload with float32 scale | `quantize_int8` & `dequantize_int8` | PASS |
| Fast Dot-Product Rescore | Under 2ms execution time in integer math | `int8_dot_product` with int32 accumulation | PASS |
| Vector Query Timeout | Safe bounded statement timeout <= 25ms | `SET LOCAL statement_timeout = '25ms'` | PASS |
| Reciprocal Rank Fusion | 1 / (60 + rank) ranking combination | `reciprocal_rank_fusion` in `synaptic_rescorer` | PASS |
| Zero Oracle Leakage | Unauthorized graph nodes contribute 0.0 | ERA `allow_mask & 1 = 1` and `deny_mask & 1 = 0` | PASS |
| Active Link Weighting | Exact weights matching ticket specification | `ACTIVE_LINK_WEIGHTS` dictionary | PASS |
| Recency Decay | Exponential decay with 30-day half-life | `_compute_recency_decay` bounded [0.1, 1.0] | PASS |
| Explainable Provenance | Informative search match reason string | Emits `"Semantic match"`, `"Linked via..."` | PASS |
| MCP Surfaces Propagation | Propagate `match_reason` and `executed_mode` | Mapped in `search_tickets` and `docs.search` | PASS |
| Unidirectional Layering | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

All API endpoints, MCP tool surfaces, safe embedding quantizers, HNSW vector fusion query handlers, RLS-governed synaptic spreading algorithms, and unit test suites for KAN-20 on branch `feat/KAN-20` at commit `045ff64d` have been thoroughly audited, verified against all architectural and security invariants, and certified. Ready for Reality-Checker QA and merge into `main`.

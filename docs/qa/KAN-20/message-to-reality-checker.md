# Forensic QA Packet: KAN-20 Zero-Egress Synaptic Object-Graph Semantic Search

## Ticket Summary
- **Ticket ID:** KAN-20 (`[KB-P3-AUDIT-14] Built-In Zero-Egress "Synaptic Object-Graph" Semantic Search`)
- **Base Commit:** `b3b0f4ba` (main)
- **Branch:** `feat/KAN-20`
- **Architectural Scope:** Zero runtime network calls, zero external SaaS dependencies (Apache-2.0 native stack only), unidirectional architecture layering (`agent -> mcp -> kanban -> database`), hermetic deterministic testability, strict Row-Level Security (FORCE RLS / ERA), and explainable search provenance.

---

## 1. Problem 1: Zero-Egress Embedder, Matryoshka Head & Int8 Quantization
- **Modules Modified / Introduced:**
  - `agent/embeddings/onnx_embedder.py`
  - `agent/embeddings/indexer.py`
  - `agent/embeddings/quantizer.py`
  - `kanban/services/synaptic_rescorer.py`
- **Key Implementation Details:**
  - `extract_matryoshka_head(vec, dim=128)`: Truncates embedding vector to the first 128 dimensions and applies L2 normalization (`np.float32`), preserving high directional cosine fidelity for fast candidate screening.
  - `compute_binary_sign(vec, dim=128)`: Packs the signs of the first 128 dimensions into 16 bytes (1 bit per dimension) using `np.packbits` for 32x compact index filtering.
  - `quantize_int8(vec)` & `dequantize_int8(payload, scale)`: Performs signed symmetric int8 quantization (`max_abs / 127.0`) returning `full_q8` bytes and `q8_scale` float factor.
  - `extract_heading_anchors(markdown)`: Parses `#` to `######` Markdown headings and emits structured micro-span metadata (`title`, `slug`, `level`, `offset`).
  - `EmbeddedChunkPayload`: Data structure holding `embedding`, `head_128`, `binary_sign`, `full_q8`, `q8_scale`, and `heading_anchors`.
  - `FixtureEmbedder`: Zero-egress deterministic offline embedding fixture hashing input text into unit vectors with SHA-256 for hermetic offline execution.
  - `OnnxBgeSmallEmbedder(fallback_to_fixture=True)`: Safe local fallback to `FixtureEmbedder` when ONNX runtime weights are omitted in offline environments.

---

## 2. Problem 2: Hybrid Search Fusion & Int8 Dot-Product Rescoring
- **Modules Modified / Introduced:**
  - `kanban/services/search.py`
  - `kanban/services/synaptic_rescorer.py`
- **Key Implementation Details:**
  - Query Vector Acquisition (`_get_query_embedding`): Dynamically resolves embedding vectors via `agent.embeddings.onnx_embedder` at runtime without violating unidirectional import layers (`agent -> mcp -> kanban -> database`).
  - HNSW Vector Candidate Query (`_query_vector_candidates`): Runs inside an isolated nested transaction with `SET LOCAL statement_timeout = '25ms'` executing `<=>` cosine distance on `object_embeddings`.
  - Reciprocal Rank Fusion (`reciprocal_rank_fusion`): Combines rankings from lexical FTS/trigram searches and vector candidate hits using formula `1.0 / (60 + rank)`.
  - Int8 Rescoring (`int8_dot_product`): Reconstructs integer dot-products in `< 2ms` execution time and adds `0.5 * int8_sim` to the candidate fusion score.
  - Exact Identifier and Heading MaxSim Boosting (`exact_identifier_heading_maxsim`): Grants `+10.0` boost for exact identifier matches (such as `KAN-20`) and up to `+2.0` token-overlap MaxSim boost for section titles.

---

## 3. Problem 3: 2-Hop FORCE RLS Synaptic Activation Spreading
- **Modules Modified / Introduced:**
  - `kanban/services/synaptic_rescorer.py`
  - `kanban/services/search.py`
- **Key Implementation Details:**
  - Activation Spreading (`spread_synaptic_activation`): Spreads activation outward from the top 20 hybrid seeds up to 2 hops across active typed `object_links`.
  - Active Link Weights:
    - `VERIFIED_BY_DOC`: 0.85
    - `BLOCKS` / `BLOCKED_BY`: 0.75
    - `PARENT_OF`: 0.70
    - `PROMOTED_TO_DOC` / `DERIVED_FROM_STICKY`: 0.65
    - `RELATES_TO`: 0.45
  - Hop Attenuation & Recency Decay: Attenuates activation by factor `0.5` per hop and weights neighbor nodes with exponential recency decay (`math.exp(-lambda * delta_days)` with a 30-day half-life).
  - Zero Oracle Leakage Invariant: Neighbors are filtered via PostgreSQL `effective_resource_access` (ERA) matching `(allow_mask & 1) = 1` and `(deny_mask & 1) = 0`. Unauthorized objects or objects with an explicit `DENY` contribute `0.0` activation and are pruned immediately.
  - Explainable Provenance: Nodes record informative provenance strings (e.g. `"Semantic match"`, `"Lexical match"`, `"Linked via VERIFIED_BY_DOC to ..."`).

---

## 4. Problem 4: Graceful Degradation & Search Explainability UI Pill
- **Modules Modified:**
  - `kanban/web/src/app/CommandPalette.tsx`
  - `kanban/web/src/app/CommandPalette.css`
  - `kanban/api/v1/schemas/search.py`
  - `kanban/api/v1/search.py`
  - `mcp/surfaces/agent/search_tickets.py`
  - `mcp/surfaces/docs/search.py`
- **Key Implementation Details:**
  - Provenance Pill Badge: Rendered in `CommandPalette.tsx` via `data-testid="match-reason-{item.id}"` styled with 100% canonical CSS tokens (`var(--surface-container-highest)`, `var(--text-tertiary)`, `var(--border-subtle)`, `var(--font-mono)`, `var(--font-xs)`).
  - Mode Dispatch: `CommandPalette.tsx` issues live search with `mode: 'hybrid'`.
  - Graceful Degradation: If vector search hits zero rows or times out, the service falls back cleanly to `executed_mode="lexical"`, labeling matches as `"Lexical match"`.
  - MCP Surfaces: `/mcp/agent` `search_tickets` and `/mcp/docs` `search` propagate `match_reason` and `executed_mode` in output JSON envelopes.

---

## 5. Verification Results & Quality Gates
- **Pytest Suite:**
  - `agent/tests/embeddings/test_matryoshka_quantizer.py`: 19 passed in 0.65s (100% pass rate)
  - `kanban/tests/services/test_synaptic_search.py`: 7 passed in 1.28s (100% pass rate)
  - Backend Coverage: `synaptic_rescorer.py` 97% coverage, `quantizer.py` 100% coverage
- **Vitest Suite:**
  - `src/app/CommandPalette.test.tsx`: 28 passed in 4.25s (100% pass rate, 0 act warnings)
  - `src/app/CommandPalette.tsx` coverage: 99.47% lines, 95.48% branches
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (100% canonical CSS tokens)
- **Static Analysis & Builds:**
  - `check-migrations --static-only`: All 62 migrations valid, single head (`p4_23_oidc_link_intent_fk`)
  - `ruff check .`: Passed (0 errors, 0 warnings)
  - `ruff format --check .`: Passed (1947 files formatted)
  - `mypy agent kanban mcp database`: Passed (0 errors in 979 source files)
  - `lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`)
  - `tsc -b --noEmit`: Passed (0 type errors)
  - `eslint . --max-warnings 0`: Passed (0 errors, 0 warnings)
  - `vite build`: Passed (1.28s, 0 build errors)
  - `check_no_dashes --all`: Passed (0 forbidden unicode em/en-dashes across repository)

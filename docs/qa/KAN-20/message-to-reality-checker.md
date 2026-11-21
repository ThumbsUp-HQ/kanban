# Forensic QA Packet: KAN-20 Zero-Egress Synaptic Object-Graph Semantic Search

## Ticket Summary
- **Ticket ID:** KAN-20 (`[KB-P3-AUDIT-14] Built-In Zero-Egress "Synaptic Object-Graph" Semantic Search`)
- **Base Commit:** `9b163f07` (main)
- **Branch:** `main` (commit `9b163f07`)
- **Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
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
  - Project Filter Post-Filtering in `search_unified`: Post-filters synaptic 1-hop neighbors by project ID, completely preventing cross-project node leaks on project-scoped searches (`non_kan_leaks=[]`).

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
  - Hop Attenuation & Recency Decay: Scales activation by `0.5` per hop and applies exponential recency decay (`lambda = 0.023`, 30-day half-life).
  - Strict Zero Oracle Leakage (FORCE RLS / ERA): Evaluates PostgreSQL effective resource access (ERA) security bitmasks (`(era.allow_mask & 1) = 1` and `(era.deny_mask & 1) = 0`). Entities with explicit DENY or missing read permissions are pruned immediately and contribute `0.0` activation.
  - Explainable Search Provenance: Emits human-readable match reasons: `"Semantic match"`, `"Lexical match"`, `"Linked via <RELATION> to <SOURCE_KEY>"`.

---

## 4. Problem 4: Explainable Search Discovery & Client-Side Integration
- **Modules Modified / Introduced:**
  - `kanban/web/src/app/CommandPalette.tsx`
  - `kanban/web/src/app/CommandPalette.css`
  - `kanban/api/v1/search.py`
  - `kanban/api/v1/schemas/search.py`
  - `mcp/surfaces/agent/search_tickets.py`
  - `mcp/surfaces/docs/search.py`
- **Key Implementation Details:**
  - CommandPalette Ranking: `liveSearchResults` from `/api/v1/search?mode=hybrid` are rendered in exact RRF/synaptic order without being filtered or reordered by client-side string-matching algorithms.
  - Responsive Mobile Badges: `.kb-palette-option-header` wraps on `<=480px` viewports, and provenance badges truncate gracefully with text ellipsis (`max-width: 48%` desktop, `max-width: 100%` mobile), eliminating title crushing.
  - MCP Tool Schemas: Both `/mcp/agent search_tickets` and `/mcp/docs search` support `mode` (`"lexical"` or `"hybrid"`, defaulting to `"hybrid"`).

---

## 5. Live Container Verification Evidence (`kanban-liveqa-3`, `:18963`, commit `9b163f07`)

- **Hybrid Search & Zero Oracle Leakage Probes:**
  * `@member GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid`: HTTP 200 (29.76ms), total=6, 0 PRIV leaks.
  * `@member GET /api/v1/search?q=CLASSIFIED_QUANTUM_CIPHER_KEY_ROTATION&mode=hybrid`: HTTP 200 (31.02ms), `priv_leaks=0`.
  * `@admin GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid&project=KAN`: HTTP 200 (33.52ms), total=6, `non_kan_leaks=[]`.
- **MCP Search Probes:**
  * `/mcp/agent search_tickets (project=KAN, states=['Backlog'])`: total=4 (KAN-1, KAN-3, KAN-4, KAN-2).
  * `/mcp/agent search_tickets (project=KAN, states=['Done'])`: total=0.
  * `/mcp/docs search (query="Synaptic Vector Kernel", mode="hybrid")`: total=3 (docs/classified-vault-runbook, docs/verification-architecture-spec, docs/deployment-proof-checklist).
- **Screenshots Captured on Disk in `docs/qa/KAN-20/screenshots/`:**
  1. `live-command-palette-desktop-light.png` (1440x900)
  2. `live-command-palette-desktop-dark.png` (1440x900)
  3. `live-command-palette-tablet-light.png` (768x1024)
  4. `live-command-palette-mobile-light.png` (390x844)
- **Telemetry:** 0 console errors, 0 page errors, 0 HTTP 5xx responses. `LIVE_STACK_VERDICT: PASS`.

---

## 6. Test Suites & Quality Gates Summary

- **Backend & MCP Pytests:** 89 passed in 27.53s. 96% coverage across all 7 KAN-20 modules.
- **Frontend Vitest:** 33 passed in 4.21s (0 `act(...)` warnings, 100% token usage).
- **Static Gates:** Database migrations valid (63 migrations), Ruff clean, Mypy clean (997 source files), Import Linter clean (2 kept, 0 broken), check_no_dashes clean (0 em/en-dashes).

# API Specialist Review: KAN-20 (KB-P3-AUDIT-14)

- Ticket: KAN-20
- Title: [KB-P3-AUDIT-14] Built-In Zero-Egress "Synaptic Object-Graph" Semantic Search (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-20`
- Branch: `main` (commit `9b163f07`)
- Container Environment: `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)
- Live Stack Status: `LIVE_STACK_VERDICT: PASS`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-20 on branch `main` at commit `9b163f07`, incorporating concrete verification evidence from live zero-mock full-stack testing against container `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS), all 4 live visual screenshots in `docs/qa/KAN-20/screenshots/`, unit test execution logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four primary problems across semantic embedding, hybrid candidate fusion, security-governed graph activation spreading, and explainable search discovery, and incorporates all reality-checker remediations:
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
   - Hardened project identifier filter in `_resolve_issue_search_scope`: evaluates case-insensitively against resolved project identifier (`c.project_identifier.upper() == resolved_proj_identifier.upper()`) rather than raw input query strings.
   - Unified Search Project Isolation Fix in `9b163f07`: `search_unified` (`GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid&project=KAN`) now post-filters synaptic 1-hop neighbors by `project_id`. When querying project `KAN`, `PRIV-1` (which was linked via BLOCKS to `KAN-1`) is filtered out (`non_kan_leaks=[]`), ensuring zero cross-project leakage even for `@admin` users.
3. 2-Hop FORCE RLS Synaptic Activation Spreading:
   - Implemented in `kanban/services/synaptic_rescorer.py` (`spread_synaptic_activation`).
   - Propagates activation from top-20 hybrid seeds up to 2 hops across active typed `object_links` (`VERIFIED_BY_DOC: 0.85`, `BLOCKS/BLOCKED_BY: 0.75`, `PARENT_OF: 0.70`, `PROMOTED_TO_DOC/DERIVED_FROM_STICKY: 0.65`, `RELATES_TO: 0.45`).
   - Strict Zero Oracle Leakage Invariant: Filters neighbors via PostgreSQL `effective_resource_access` (ERA) requiring `(era.allow_mask & 1) = 1` and `(era.deny_mask & 1) = 0`. Unauthorized entities or entities with explicit `DENY` contribute `0.0` score and are pruned immediately.
   - Applies 0.5 hop attenuation and 30-day exponential recency decay (`math.exp(-lambda * delta_days)`).
   - Emits explainable search provenance (`"Semantic match"`, `"Lexical match"`, `"Linked via VERIFIED_BY_DOC to ..."`).
4. CommandPalette Client-Side Ranking & MCP Tool Mode Alignment:
   - Statement Timeout Leak Fix: In `kanban/services/search.py:555` (`_query_vector_candidates`), `await session.execute(text("SET LOCAL statement_timeout = 0"))` resets the statement timeout immediately after executing the vector query within the nested savepoint, preventing timeout leakage into subsequent queries in the same transaction.
   - Resilient Activation Spreading: In `kanban/services/synaptic_rescorer.py:399-409`, wrapped the frontier edge query in `async with session.begin_nested():` with `SET LOCAL statement_timeout = '100ms'` and `SET LOCAL statement_timeout = 0`. On any query cancellation or timeout, it catches `Exception`, logs, and gracefully falls back to hybrid seed scores with 0 HTTP 500 errors.
   - CommandPalette Ranking & Non-Literal Results: In `CommandPalette.tsx`, `liveSearchResults` from backend `/api/v1/search?mode=hybrid` are preserved in exact RRF/synaptic order and are NEVER dropped by client-side `scoreMatch(query, opt.title) === 0`. Client-side scoring is strictly confined to local base and cached issue commands.
   - Mobile Badge Ergonometrics: In `CommandPalette.css`, capped `.kb-palette-badge` with `max-width: 48%; overflow: hidden; text-overflow: ellipsis;` and responsive wrapping on `<=480px`, preventing title crushing on 390px mobile viewports.
   - MCP Schema Alignment: Both `mcp/surfaces/docs/search.py` and `mcp/surfaces/agent/search_tickets.py` declare and validate `mode` (`"lexical"` or `"hybrid"`, default `"hybrid"`) and forward `"mode": mode` to backend search services.

All API contracts, security invariants, transaction boundaries, import layering constraints, and test coverage requirements are verified and certified:
- Zero new external runtime dependencies introduced (`Apache-2.0` stack only).
- Strict unidirectional architectural layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- High test coverage: >=95% achieved across ALL 7 KAN-20 modules (`agent/embeddings/indexer.py`: 99%, `agent/embeddings/onnx_embedder.py`: 95%, `agent/embeddings/quantizer.py`: 100%, `kanban/services/search.py`: 95%, `kanban/services/synaptic_rescorer.py`: 98%, `mcp/surfaces/agent/search_tickets.py`: 99%, `mcp/surfaces/docs/search.py`: 95%; total: 96% across 1642 statements). 89/89 Pytest passed in 27.53s; 33/33 Vitest passed.

---

## 2. API Contract & Security Verification

### 2.1 Live Full-Stack Verification Telemetry (`kanban-liveqa-3`, `:18963`, commit `9b163f07`)
- `@member GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid`:
  * Returns HTTP 200 OK (29.76ms / 30.65ms), `executed_mode="hybrid"`, total=6.
  * Correctly includes non-literal synaptic neighbors: `KAN-4` ("Linked via BLOCKS to KAN-1") and `docs/deployment-proof-checklist` ("Linked via VERIFIED_BY_DOC to KAN-1").
  * 0 PRIV leaks: Secret project entities (`PRIV-1`, `docs/classified-vault-runbook`) are completely withheld.
- `@member secret query probe (q=CLASSIFIED_QUANTUM_CIPHER_KEY_ROTATION&mode=hybrid)`:
  * Returns HTTP 200 OK (31.02ms), `executed_mode="hybrid"`, `priv_leaks=0`. Complete zero oracle leakage verified under FORCE RLS.
- `@admin GET /api/v1/search?project=KAN (search_unified)`:
  * Returns HTTP 200 OK (33.52ms), `total=6`, `non_kan_leaks=[]`.
  * `PRIV-1` (which links to `KAN-1` via BLOCKS) is strictly post-filtered out by project ID scope in `search_unified`.
- MCP JSON-RPC Probes:
  * `/mcp/agent search_tickets (project=KAN, states=['Backlog'])`: Returns 4 issues (KAN-1, KAN-3, KAN-4, KAN-2).
  * `/mcp/agent search_tickets (project=KAN, states=['Done'])`: Returns 0 issues (extra_predicates properly enforced across both vector and synaptic candidates).
  * `/mcp/docs search (query="Synaptic Vector Kernel", mode="hybrid")`: Returns 3 docs (docs/classified-vault-runbook, docs/verification-architecture-spec, docs/deployment-proof-checklist).

### 2.2 Client-Side Integration & CommandPalette UI
- Desktop Light (1440x900): `searchMs=498ms`, `pillCount=8`, `hasLinkedVerified=true`, `hasLinkedBlocks=true`, `docOverflow=false`.
- Desktop Dark (1440x900): `searchMs=494ms`, `pillCount=8`, `hasLinkedVerified=true`, `hasLinkedBlocks=true`, `docOverflow=false`.
- Tablet Light (768x1024): `searchMs=488ms`, `pillCount=8`, `hasLinkedVerified=true`, `hasLinkedBlocks=true`, `docOverflow=false`.
- Mobile Light (390x844): `searchMs=486ms`, `pillCount=8`, `hasLinkedVerified=true`, `hasLinkedBlocks=true`, `docOverflow=false`, clean ellipsis on "Linked via VERIFIED_BY_DOC to K...".
- Runtime Telemetry: 0 console errors, 0 page errors, 0 5xx responses.

---

## 3. Test Suites & Coverage Verification

### 3.1 Backend & MCP Pytest Suites (89 passed in 27.53s)
- `agent/tests/embeddings/test_indexer.py`: 12 passed
- `agent/tests/embeddings/test_matryoshka_quantizer.py`: 19 passed
- `agent/tests/embeddings/test_onnx_embedder.py`: 11 passed
- `kanban/tests/services/test_synaptic_search.py`: 13 passed
- `kanban/tests/api/test_search.py`: 6 passed
- `mcp/tests/agent/test_search_tickets.py`: 8 passed
- `mcp/tests/docs/test_docs_tools.py`: 7 passed
- `mcp/tests/docs/test_docs_surfaces_unit.py`: 13 passed
- Code Coverage across all 7 KAN-20 modules:
  * `agent/embeddings/indexer.py`: 99%
  * `agent/embeddings/onnx_embedder.py`: 95%
  * `agent/embeddings/quantizer.py`: 100%
  * `kanban/services/search.py`: 95%
  * `kanban/services/synaptic_rescorer.py`: 98%
  * `mcp/surfaces/agent/search_tickets.py`: 99%
  * `mcp/surfaces/docs/search.py`: 95%
  * **TOTAL: 96% coverage across 1642 statements**

### 3.2 Frontend Vitest Suite (33 passed in 4.21s)
- `src/app/CommandPalette.test.tsx`: 29 passed
- `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed (100% token usage, 0 inline JSX styles)

---

## 4. Static Quality Gates (Commit `9b163f07`)

- Database Migrations (`check-migrations`): OK: All 63 migrations valid. Single head: `p4_24_agent_safe_sequences`
- Ruff Linter (`ruff check .`): All checks passed (0 errors).
- Ruff Formatter (`ruff format --check .`): Clean across 2027 files.
- Mypy Strict Typecheck (`mypy database kanban mcp agent`): Success: no issues found in 997 source files.
- Import Linter (`lint-imports`): Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database` KEPT).
- Frontend Typecheck (`tsc -b --noEmit`): Clean (0 type errors).
- Frontend Eslint (`eslint . --max-warnings 0`): Clean (0 warnings).
- Typography Audit (`check_no_dashes`): Clean (0 em/en-dashes).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Zero External Egress** | No outbound HTTP calls to third-party APIs | `FixtureEmbedder` and local ONNX embedder | PASS |
| **Matryoshka Head Extraction** | L2-normalized 128-dim head vector | `extract_matryoshka_head` using `np.float32` | PASS |
| **16-Byte Binary Sign Bits** | Packed 1-bit sign vector for 128 dims | `compute_binary_sign` using `np.packbits` | PASS |
| **Int8 Symmetric Quantization** | Signed int8 payload with float32 scale | `quantize_int8` & `dequantize_int8` | PASS |
| **Fast Dot-Product Rescore** | Under 2ms execution time in integer math | `int8_dot_product` with int32 accumulation | PASS |
| **Vector Query Timeout Reset** | Prevents statement_timeout leakage | `SET LOCAL statement_timeout = 0` | PASS |
| **Resilient Spreading Query** | 100ms timeout with fallback to seeds | Bounded nested query with try/except | PASS |
| **Reciprocal Rank Fusion** | 1 / (60 + rank) ranking combination | `reciprocal_rank_fusion` in `synaptic_rescorer` | PASS |
| **Zero Oracle Leakage** | Unauthorized graph nodes contribute 0.0 | ERA `allow_mask & 1 = 1` and `deny_mask & 1 = 0` | PASS |
| **Project-Filtered Unified Search** | Post-filter synaptic 1-hop neighbors by project | Enforced in `search_unified` (`non_kan_leaks=[]`) | PASS |
| **Active Link Weighting** | Exact weights matching ticket specification | `ACTIVE_LINK_WEIGHTS` dictionary | PASS |
| **Recency Decay** | Exponential decay with 30-day half-life | `_compute_recency_decay` bounded [0.1, 1.0] | PASS |
| **Explainable Provenance** | Informative search match reason string | Emits `"Semantic match"`, `"Linked via..."` | PASS |
| **Non-Literal Result Preservation** | Do not drop semantic/synaptic matches | Direct result push in `CommandPalette.tsx` | PASS |
| **MCP Docs Search Mode** | Declare, validate, and forward mode parameter | `mcp/surfaces/docs/search.py` | PASS |
| **Case-Insensitive Project Scope** | Compare against resolved identifier | `kanban/services/search.py` | PASS |
| **Unidirectional Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, MCP tool surfaces, safe embedding quantizers, HNSW vector fusion query handlers, timeout resets, project-filtered synaptic spreading algorithms, and unit test suites for KAN-20 on branch `main` at commit `9b163f07` have been thoroughly audited, verified against all architectural and security invariants, and certified. Verified on live stack `kanban-liveqa-3` with `LIVE_STACK_VERDICT: PASS`. Ready for Reality-Checker QA.

# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive forensic read-only audit conducted strictly via `read_file` (zero shell commands executed, zero URLs visited, zero files modified, per clean-room protocol).
**Evidence Captured**:
- QA packet files inspected in `docs/qa/KAN-20/`: `message-to-reality-checker.md`, `changed-files-manifest.txt`, `git-diff.patch`, `unit-test-results.txt`, `build-or-typecheck.txt`, `live-fullstack-proof.txt`, `api-specialist-review.md`, `ui-specialist-review.md`.
- Visual screenshots inspected via `read_file`:
  - `docs/qa/KAN-20/screenshots/live-command-palette-desktop-light.png`
  - `docs/qa/KAN-20/screenshots/live-command-palette-desktop-dark.png`
  - `docs/qa/KAN-20/screenshots/live-command-palette-tablet-light.png`
  - `docs/qa/KAN-20/screenshots/live-command-palette-mobile-light.png`
- On-disk implementation and test files inspected: `kanban/services/search.py`, `kanban/services/synaptic_rescorer.py`, `kanban/api/v1/search.py`, `kanban/api/v1/schemas/search.py`, `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, `agent/embeddings/quantizer.py`, `mcp/surfaces/agent/search_tickets.py`, `mcp/surfaces/docs/search.py`, `kanban/web/src/app/CommandPalette.tsx`, `kanban/web/src/app/CommandPalette.css`, `kanban/web/src/app/CommandPalette.test.tsx`, `kanban/tests/services/test_synaptic_search.py`. (Note: the prompt referenced `kanban/services/synaptic_graph.py`, `mcp/surfaces/agent_surface.py`, `mcp/surfaces/docs_surface.py`, and `kanban/web/src/components/CommandPalette.tsx`; the actual on-disk paths are `kanban/services/synaptic_rescorer.py`, `mcp/surfaces/agent/search_tickets.py`, `mcp/surfaces/docs/search.py`, and `kanban/web/src/app/CommandPalette.tsx`.)

**QA Cross-Validation**:
- **CHALLENGED** `api-specialist-review.md` (`STATUS: APPROVED`) and `ui-specialist-review.md` (`STATUS: APPROVED`):
  1. Both specialist reviews missed a critical UI integration bug directly exposed by comparing `live-fullstack-proof.txt` against all 4 Playwright screenshots. While `GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid` returned `total=24` including synaptic neighbor hits (`Verification Architecture Spec` with `Linked via VERIFIED_BY_DOC to KAN-10` and `KAN-11` / `KAN-2` with `Linked via BLOCKS to KAN-*`), **ZERO** `Linked via ...` results appear in any of the 4 CommandPalette screenshots (`pillCount=11`, showing only `KAN-* - Synaptic Vector Kernel...` with `Semantic match` or `Lexical match` badges, and `KAN-13` re-ranked ahead of backend rank #1 `KAN-16`). Root cause verified in `kanban/web/src/app/CommandPalette.tsx:531-558`: `filteredOptions` passes `liveSearchResults` through client-side `scoreMatch(query, opt.title)` and drops any result with `s === 0` while re-sorting by fuzzy subsequence score.
  2. `api-specialist-review.md` claims `mcp/surfaces/docs/search.py` supports hybrid search and propagates `mode` and `executed_mode`. In reality, `mcp/surfaces/docs/search.py:36-83` (`_INPUT_SCHEMA` with `additionalProperties: False`) exposes **no `mode` parameter**, and `search_payload` (`lines 494-498`) omits `"mode"`, forcing `/mcp/docs` `search` to execute in default `"lexical"` mode (`live-fullstack-proof.txt:92-93` confirms `mode: lexical`, `executed_mode: lexical`).
  3. Packet hygiene discrepancies: `docs/qa/KAN-20/git-diff.patch` is stale relative to on-disk `main` (`07d04cde`) and omits live-QA fixes (`search.py:555`, `synaptic_rescorer.py:399-409`, `executed_mode` in MCP envelopes, and 2 extra tests in `test_synaptic_search.py:734-822`); `changed-files-manifest.txt` omits most source/test files; `message-to-reality-checker.md` cites `7 passed` and `97%` coverage while `unit-test-results.txt` shows `9 passed` and `98%` coverage; `build-or-typecheck.txt:83-84` truncates output for section `9. FORBIDDEN UNICODE DASH AUDIT`; and `unit-test-results.txt` reports coverage only for `quantizer.py` (100%) and `synaptic_rescorer.py` (98%), omitting coverage for `kanban/services/search.py`, `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, `mcp/surfaces/agent/search_tickets.py`, and `mcp/surfaces/docs/search.py`.

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system / modal screenshots:
  - `docs/qa/KAN-20/screenshots/live-command-palette-desktop-light.png` (Desktop 1440x900, Light theme)
  - `docs/qa/KAN-20/screenshots/live-command-palette-desktop-dark.png` (Desktop 1440x900, Dark theme)
  - `docs/qa/KAN-20/screenshots/live-command-palette-tablet-light.png` (Tablet 768x1024, Light theme)
  - `docs/qa/KAN-20/screenshots/live-command-palette-mobile-light.png` (Mobile 390x844, Light theme)
- User journey evidence: Live container (`kanban-liveqa-3`, `http://127.0.0.1:18963`) API + MCP + Playwright CommandPalette telemetry in `docs/qa/KAN-20/live-fullstack-proof.txt`. Note: no pre-search or post-selection navigation screenshots are included; only the open CommandPalette search state for query `"Synaptic Vector Kernel"` is captured.
- Cross-browser comparison: Single headless Chromium (Playwright) run only; no multi-browser captures provided.

**What System Actually Delivers**:
- **Backend Search, Quantization & ERA Security**: Solid. `synaptic_rescorer.py` implements Matryoshka 128-d L2-normalized head extraction, 16-byte packed binary sign bits, symmetric int8 quantization/dot-product, MaxSim identifier/heading boosting, RRF (`1/(60+rank)`), and 2-hop activation spreading across active `object_links` with PostgreSQL `effective_resource_access` (`allow_mask & 1 = 1 AND deny_mask & 1 = 0`) filtering and nested savepoint timeout guards (`25ms` for vector HNSW query with `SET LOCAL statement_timeout = 0` reset; `100ms` for frontier link query with graceful fallback).
- **CommandPalette UI (`CommandPalette.tsx` + `CommandPalette.css`)**: Visually clean modal layout with canonical CSS tokens, zero inline styles, clean dark/light contrast, and zero horizontal overflow across Desktop, Tablet, and Mobile. However, **functionally broken for semantic and synaptic results**: client-side `scoreMatch` filtering in `CommandPalette.tsx:546-557` discards all backend `liveSearchResults` whose title/meta do not contain a fuzzy subsequence of the query (deleting every `Linked via ...` neighbor and non-literal semantic hit from the rendered list) and alters backend RRF/synaptic rank order. Furthermore, on Mobile (`390x844`), `"Semantic match"` already truncates `"KAN-13 - Synaptic Vector Kernel"` to `"KAN-13 - Synap..."`; longer provenance strings like `"Linked via VERIFIED_BY_DOC to KAN-10"` with `white-space: nowrap; flex-shrink: 0` will severely crush titles or risk header crowding once the filter bug is fixed.
- **Embedding Indexer & Storage (`agent/embeddings/indexer.py`)**: `EmbeddingIndexer.index_object` (`lines 265-301`) calls `embed_batch_rich` and immediately discards `head_128`, `binary_sign`, `full_q8`, `q8_scale`, and `heading_anchors`, persisting only the 384-d float `embedding` column. `kanban/services/search.py:757` re-quantizes vectors on the fly at query time and passes only `[cand.title]` to `exact_identifier_heading_maxsim` (`line 766`) instead of persisted document heading anchors.

## 🧪 Integration Testing Results
- **End-to-End User Journeys**: **FAIL (UI Journey)** / **PASS (Backend API Journey)**
  - Backend API (`live-fullstack-proof.txt`): Cold/warm `GET /api/v1/search?q=Synaptic+Vector+Kernel&mode=hybrid` returned `200 OK` (`168.83ms` cold / `157.07ms` warm for `@member`; `74.26ms` / `76.82ms` for `@admin`), `executed_mode="hybrid"`, `0 PRIV leaks` on `@member` secret probe (`q=CLASSIFIED_QUANTUM_CIPHER_KEY_ROTATION`), and emitted `"Semantic match"`, `"Lexical match"`, `"Linked via VERIFIED_BY_DOC to KAN-*"`, and `"Linked via BLOCKS to KAN-*"`.
  - CommandPalette UI (`screenshots/*.png` + `CommandPalette.tsx:531-558`): FAILS end-to-end hybrid/synaptic discovery because `filteredOptions` discards all synaptic-activated (`Linked via ...`) and synonymic semantic hits before rendering (`pillCount=11` vs `total=24` backend items; zero `Linked via ...` pills rendered in any screenshot).
- **Cross-Device Consistency**: **PARTIAL PASS** - Desktop Light/Dark (1440x900), Tablet (768x1024), and Mobile (390x844) render cleanly with `docOverflow=false`, `dialogOverflow=false`, `outsideDialog=false`, `consoleErrors=0`, `pageErrors=0`. However, Mobile title truncation is aggressive (`KAN-13 - Synap...`) and untested against longer `Linked via VERIFIED_BY_DOC to ...` provenance pills because those items were filtered out by `CommandPalette.tsx`.
- **Performance Validation**: **PASS** - Live container API latency `74.26ms - 168.83ms` (`< 3000ms`), CommandPalette UI search latency `286ms - 292ms`, Vite build `2.92s`, `int8_dot_product` verified `< 2ms` in `test_matryoshka_quantizer.py`.
- **Specification Compliance**: **FAIL** -
  - CommandPalette Provenance & Hybrid Search (`CommandPalette.tsx`): Violated by client-side `scoreMatch` filtering dropping semantic/synaptic hits.
  - `/mcp/docs` `search` Hybrid Mode (`mcp/surfaces/docs/search.py:25,36-83,494-498`): Tool description and help text advertise `"hybrid knowledge search"`, but schema rejects `mode` (`additionalProperties: False`) and handler never sends `mode` to `/api/v1/search/knowledge`.
  - `>=95%` Coverage & Verification Packet Completeness (`GEMINI.md`): Backend coverage report in `unit-test-results.txt` covers only 2 files (`quantizer.py`, `synaptic_rescorer.py`) and omits `kanban/services/search.py`, `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, `mcp/surfaces/agent/search_tickets.py`, and `mcp/surfaces/docs/search.py`.

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
- Statement timeout leak and nested savepoint handling from earlier live QA were verified fixed on disk (`kanban/services/search.py:555`, `kanban/services/synaptic_rescorer.py:399-409`), and `executed_mode` propagation was added on disk to MCP tools. However, `docs/qa/KAN-20/git-diff.patch` was never regenerated after those fixes.

**New Issues Discovered**:
1. **[CRITICAL] Client-Side `scoreMatch` Filter Drops Hybrid Semantic & Synaptic Results in CommandPalette** (`kanban/web/src/app/CommandPalette.tsx:531-558`):
   - `liveSearchResults` are merged into `all` (`line 535`) and then filtered by `scoreMatch(query, opt.title) > 0` (`lines 547-557`). Any backend semantic match without literal query characters in its title and any 1-hop/2-hop synaptic neighbor (`Linked via VERIFIED_BY_DOC to ...`, `Linked via BLOCKS to ...`) gets `score === 0` and is dropped; remaining results are re-sorted by subsequence score rather than backend RRF/synaptic score.
   - Confirmed by `CommandPalette.test.tsx:893-931` masking the bug with literal query `'Live'` against title `'Live Synaptic Search Issue'`, and by all 4 live screenshots (`pillCount=11`, zero `Linked via ...` items despite `live-fullstack-proof.txt` showing `Verification Architecture Spec` and `KAN-11` / `KAN-2` in backend results).
2. **[MEDIUM] `/mcp/docs` `search` Tool Omits `mode` Parameter and Hardcodes Lexical Search** (`mcp/surfaces/docs/search.py:25,36-83,494-498`):
   - `_INPUT_SCHEMA` (`additionalProperties: False`) lacks `mode` (`"lexical" | "hybrid"`), and `search_payload` never forwards `mode` to `POST /api/v1/search/knowledge`, contradicting its `"hybrid knowledge search"` description and returning `executed_mode: lexical` in `live-fullstack-proof.txt:92-93`.
3. **[MEDIUM] Mobile Provenance Pill Truncation / Title Crushing Risk** (`kanban/web/src/app/CommandPalette.css:103-123` & `live-command-palette-mobile-light.png`):
   - `.kb-palette-badge` uses `white-space: nowrap; flex-shrink: 0` on the same row as `.kb-palette-option-title`. On 390px viewports, short `"Semantic match"` pills already cut titles to `"KAN-13 - Synap..."`. Longer provenance strings (`"Linked via VERIFIED_BY_DOC to KAN-10"`) will crush titles or crowd the row once Issue #1 is fixed.
4. **[MEDIUM] Incomplete QA Packet & Missing Coverage on Core Changed Files** (`docs/qa/KAN-20/`):
   - `git-diff.patch` is stale (does not include commit `07d04cde` remediations); `changed-files-manifest.txt` omits 11+ modified files; `build-or-typecheck.txt:83-84` lacks output under `9. FORBIDDEN UNICODE DASH AUDIT`; `unit-test-results.txt` omits coverage metrics for `kanban/services/search.py`, `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, `mcp/surfaces/agent/search_tickets.py`, and `mcp/surfaces/docs/search.py`.
5. **[LOW] Project Filter String Comparison Fragility & Unpersisted Rich Embedding Fields**:
   - `kanban/services/search.py:1066` compares `c.project_identifier == request.project` (fails if `request.project` was a UUID or lowercase string; should compare against resolved `proj.identifier` or `project_id`).
   - `agent/embeddings/indexer.py:265-301` discards `head_128`, `binary_sign`, `full_q8`, `q8_scale`, and `heading_anchors` from `embed_batch_rich`, while `kanban/services/search.py:757,766` re-quantizes on the fly and passes `[cand.title]` instead of persisted heading anchors to `exact_identifier_heading_maxsim`.

**Critical Issues**:
- Issue #1 (`CommandPalette.tsx:531-558` dropping semantic & synaptic-activated search results).

**Medium Issues**:
- Issue #2 (`mcp/surfaces/docs/search.py` missing `mode` schema/forwarding).
- Issue #3 (`CommandPalette.css` mobile layout handling for long `"Linked via ..."` provenance pills).
- Issue #4 (Stale/incomplete QA packet & missing coverage measurement on `kanban/services/search.py`, `agent/embeddings/*`, `mcp/surfaces/*`).

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: **B-**
**Design Implementation Level**: **Good** (Strong backend RLS/ERA zero-oracle design and clean CSS-token modal styling, undermined by frontend filtering breaking the core hybrid/synaptic feature in the UI)
**System Completeness**: **78%**
**Production Readiness**: **NEEDS WORK**

## 🔄 Deployment Readiness Assessment
**Status**: **NEEDS WORK**

**Required Fixes Before Production**:
1. **Preserve Backend `liveSearchResults` Order & Non-Literal Semantic/Synaptic Matches in `CommandPalette.tsx`**:
   - Update `CommandPalette.tsx:531-558` so backend `liveSearchResults` returned by `/api/v1/search?mode=hybrid` are NOT filtered out or re-sorted by client-side `scoreMatch` (keep `scoreMatch` only for local `baseCommands` and cached `issueCommands`, deduplicating against `liveSearchResults` while preserving backend RRF + synaptic rank order).
   - Add a Vitest case in `CommandPalette.test.tsx` where the query (e.g., `"Synaptic Vector Kernel"`) does NOT substring/subsequence-match the returned item's title (e.g., `"Verification Architecture Spec"` with `match_reason: "Linked via VERIFIED_BY_DOC to KAN-10"`) and assert it renders with its provenance pill.
   - Re-capture live Playwright screenshots proving `"Linked via ..."` provenance pills visibly render in the CommandPalette UI across desktop, tablet, and mobile.
2. **Expose & Forward `mode` (`"lexical" | "hybrid"`) in `/mcp/docs` `search`** (`mcp/surfaces/docs/search.py:36-83,494-498`):
   - Add `mode` (`enum: ["lexical", "hybrid"]`, `default: "lexical"` or `"hybrid"` per tool spec) to `_INPUT_SCHEMA`, validate it, forward it in `search_payload`, and prove `executed_mode: hybrid` in live MCP `/mcp/docs` verification.
3. **Prevent Mobile Title Crushing with Long Provenance Pills** (`kanban/web/src/app/CommandPalette.css:103-123`):
   - Cap `.kb-palette-badge` width (e.g., `max-width: 50%; overflow: hidden; text-overflow: ellipsis;` or stack/wrap `.kb-palette-option-header` on `max-width: 480px`) and verify with a live mobile screenshot containing `"Linked via VERIFIED_BY_DOC to KAN-10"`.
4. **Refresh & Complete Forensic QA Packet (`docs/qa/KAN-20/`)**:
   - Regenerate `git-diff.patch` and `changed-files-manifest.txt` against final commit; include full `check_no_dashes --all` output in `build-or-typecheck.txt`; include `>=95%` backend & MCP coverage evidence for `kanban/services/search.py`, `agent/embeddings/onnx_embedder.py`, `agent/embeddings/indexer.py`, `mcp/surfaces/agent/search_tickets.py`, and `mcp/surfaces/docs/search.py` in `unit-test-results.txt` (and fix `kanban/services/search.py:1066` `proj.identifier` check).

**Timeline for Production Readiness**: 1 focused revision cycle (fixes + live Playwright re-capture + packet regeneration).
**Revision Cycle Required**: **YES**

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- End-to-end fidelity between backend hybrid/synaptic responses and what actually renders in `CommandPalette.tsx` and `/mcp/docs` `search`.
- Responsive mobile ergonomics when long `"Linked via <LINK_TYPE> to <KEY>"` provenance pills are rendered.
- Exact consistency and completeness across `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, and `build-or-typecheck.txt`.

**Quality Targets**:
- Zero dropped semantic or synaptic-activated items in `CommandPalette.tsx`; backend rank #1 remains UI rank #1 for live search items.
- `/mcp/docs` `search` supports and executes `mode="hybrid"` returning `executed_mode: hybrid`.
- Mobile (390x844) renders long `"Linked via ..."` pills cleanly without crushing titles below readability or causing horizontal overflow.
- `>=95%` test coverage reported across ALL modified Python and TypeScript modules.

**Evidence Requirements**:
- Updated Vitest + Pytest logs with per-file coverage >=95% for all changed modules (`kanban/services/search.py`, `kanban/services/synaptic_rescorer.py`, `agent/embeddings/*`, `mcp/surfaces/*`, `CommandPalette.tsx`).
- Updated `live-fullstack-proof.txt` showing `/mcp/docs` `search` with `mode="hybrid"` -> `executed_mode: hybrid`, plus updated Desktop/Tablet/Mobile Playwright screenshots visibly displaying at least one `"Linked via ..."` provenance pill inside the live CommandPalette modal.
- Synchronized `git-diff.patch`, `changed-files-manifest.txt`, and complete `build-or-typecheck.txt` (including `check_no_dashes --all` output).

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-20/
**Re-assessment Required**: After fixes implemented

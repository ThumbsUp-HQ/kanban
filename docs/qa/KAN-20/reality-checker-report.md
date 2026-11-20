# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Passive forensic audit mode (`read_file` only; zero shell commands executed, zero URLs visited, zero files modified, per `.agents/agents/reality-checker.md` passive protocol).
**Evidence Captured**:
- QA packet manifests and logs in `/home/adamoutler/kanban/docs/qa/KAN-20/`: `message-to-reality-checker.md`, `changed-files-manifest.txt`, `git-diff.patch`, `unit-test-results.txt`, `build-or-typecheck.txt`, `live-fullstack-proof.txt`, `api-specialist-review.md`, `ui-specialist-review.md`.
- Four live Playwright screenshots in `/home/adamoutler/kanban/docs/qa/KAN-20/screenshots/`: `live-command-palette-desktop-light.png`, `live-command-palette-desktop-dark.png`, `live-command-palette-tablet-light.png`, `live-command-palette-mobile-light.png`.
- On-disk source and test files: `kanban/services/search.py`, `kanban/services/synaptic_rescorer.py`, `mcp/surfaces/agent/search_tickets.py`, `mcp/surfaces/docs/search.py`, `kanban/web/src/app/CommandPalette.tsx`, `kanban/web/src/app/CommandPalette.css`, `kanban/web/src/app/CommandPalette.test.tsx`.

**QA Cross-Validation**:
- Round-1 remediations are confirmed in the on-disk code, `git-diff.patch`, unit tests, live container log, and screenshots:
  1. `kanban/web/src/app/CommandPalette.tsx` (lines 539-573) preserves `liveSearchResults` from `/api/v1/search?mode=hybrid` in exact backend order without dropping non-literal synaptic results via `scoreMatch`.
  2. `kanban/web/src/app/CommandPalette.css` (lines 111-149) caps `.kb-palette-badge` (`max-width: 48%`) and adds `@media (max-width: 480px)` wrapping rules (`flex-wrap: wrap; gap: 4px;` and `max-width: 100%`).
  3. `mcp/surfaces/docs/search.py` (lines 59-64, 404-408, 511) declares, validates, and forwards `mode` (`"lexical"` | `"hybrid"`, default `"hybrid"`), confirmed in `live-fullstack-proof.txt` lines 104-124 (`mode: hybrid`, `executed_mode: hybrid`).
  4. `kanban/services/search.py` (line 1070) compares `c.project_identifier.upper() == resolved_proj_identifier.upper()` using the resolved project identifier.
- **Challenged QA Packet Consistency**: `docs/qa/KAN-20/api-specialist-review.md` Section 3 (lines 120-150) embeds stale Round-1 telemetry from commit `07d04cde` (`latency=168.83ms`, `total=24`, `pillCount=11`, `/mcp/docs` `mode: lexical`, `KAN-16`/`PRIV-6`), which contradicts the actual Round-2 `docs/qa/KAN-20/live-fullstack-proof.txt` at commit `7913c2c8` (`latency=30.35ms`, `total=4`/`8`, `pillCount=8`, `/mcp/docs` `mode: hybrid`, `KAN-1`/`PRIV-1`). Similarly, `message-to-reality-checker.md` (lines 102, 106) and `api-specialist-review.md` (lines 180-185) cite older static counts (`989` mypy files, `1947` ruff files, `1.24s` vite build) compared to `build-or-typecheck.txt` at HEAD `7913c2c8` (`995` mypy files, `2018` ruff files, `1.22s` vite build).

## 📸 Complete System Evidence
**Visual Documentation**:
- Desktop Light: `docs/qa/KAN-20/screenshots/live-command-palette-desktop-light.png` (1440x900)
- Desktop Dark: `docs/qa/KAN-20/screenshots/live-command-palette-desktop-dark.png` (1440x900)
- Tablet Light: `docs/qa/KAN-20/screenshots/live-command-palette-tablet-light.png` (768x1024)
- Mobile Light: `docs/qa/KAN-20/screenshots/live-command-palette-mobile-light.png` (390x844)

**What System Actually Delivers**:
- Desktop Light & Dark (`1440x900`) and Tablet Light (`768x1024`) render the Command Palette cleanly centered over `/w/kanban/p/KAN/issues` for query `"Synaptic Vector Kernel"`, displaying all 8 backend hybrid results in exact rank order, including non-literal 1-hop synaptic neighbors (`Deployment Proof Checklist` with `"Linked via VERIFIED_BY_DOC to KAN-1"` and `KAN-4 - Release Verification Gate` with `"Linked via BLOCKS to KAN-1"`). Contrast in both light and dark modes is legible and crisp.
- Mobile Light (`390x844`) successfully wraps `.kb-palette-option-header` onto two lines so item titles are no longer crushed horizontally (`KAN-3 - Synaptic Vector Kernel T...`, `KAN-2 - Release Gate Readiness...`, `PRIV-1 - CLASSIFIED_QUANTUM_CI...` truncate cleanly with `...`). However, visual inspection of the 3rd item's provenance badge (`Linked via VERIFIED_BY_DOC to KAN-`) shows hard character clipping at the right border of the pill without an ellipsis (`...`) because `display: inline-flex` prevents `text-overflow: ellipsis` from taking effect. The 8th item (`Verification Architecture Spec`) is partially below the scrollable fold of `.kb-palette-list`, which is expected inside `max-height: 70vh`.
- Live full-stack proof (`kanban-liveqa-3`, `http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) demonstrates hybrid search returning `200 OK` in `30.10ms`-`30.44ms`, zero PRIV leakage under `@member` ERA/DENY probes, and both `/mcp/agent` `search_tickets` and `/mcp/docs` `search` emitting `executed_mode: hybrid` and `match_reason`.

## 🧪 Integration Testing Results
- **End-to-End User Journeys**: CONDITIONAL PASS (CommandPalette live search + synaptic provenance + MCP JSON-RPC surfaces verified in `live-fullstack-proof.txt` and 4 screenshots; filtered `search_issues` hybrid queries with `FilterSpec` predicates remain unverified and have a logic gap on disk).
- **Cross-Device Consistency**: PARTIAL PASS (`docOverflow=false`, `dialogOverflow=false`, `outsideDialog=false` across 1440x900, 768x1024, and 390x844, but mobile provenance badge hard-clips at `Linked via VERIFIED_BY_DOC to KAN-` without ellipsis in `live-command-palette-mobile-light.png`).
- **Performance Validation**: PASS (Backend API cold/warm hybrid search `30.10ms`-`30.44ms`; Playwright UI end-to-end search render `285ms`-`288ms`, well under 3s; `vite build` `1.22s`).
- **Specification Compliance**: PARTIAL PASS (Zero-egress Matryoshka/int8 quantization, RRF fusion, 2-hop ERA-filtered synaptic spreading, graceful lexical fallback, and CommandPalette provenance pills are implemented and verified, but `search_issues` hybrid mode omits `extra_predicates` filtering on vector/synaptic candidates).

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
- None of the 4 specific Round-1 blockers (`scoreMatch` dropping non-literal results, mobile title crushing, `mcp/surfaces/docs/search.py` missing `mode`, raw project string comparison) remain unfixed in code.

**New Issues Discovered**:
1. **[Medium - Functional/Filter Bypass] `kanban/services/search.py` (`search_issues`, lines 1047-1073) ignores `FilterSpec` and `workspace` predicates for vector and synaptic candidates in `mode="hybrid"`**: `issue_query` applies `extra_predicates` (`Workspace.slug == workspace_ref` and `compile_issue_filter_predicates(...)`) to `lex_rows`, but `_execute_hybrid_search_core` queries `object_embeddings` and `spread_synaptic_activation` without `extra_predicates`, and `filtered_cands` (lines 1062-1073) only filters by `c.kind == "issue"` and `resolved_proj_identifier`. Calling `search_issues` or MCP `search_tickets` with `mode="hybrid"` and `states`/`assignees`/`blocked`/`labels`/`cycle`/`modules`/`workspace` filters can return issues that violate those filters.
2. **[Medium - Visual/CSS] `kanban/web/src/app/CommandPalette.css` (lines 111-126) uses `display: inline-flex` with `text-overflow: ellipsis`, causing hard clipping on mobile**: CSS `text-overflow: ellipsis` does not apply to flex containers (`inline-flex`), so in `live-command-palette-mobile-light.png` item 3's badge clips mid-token as `Linked via VERIFIED_BY_DOC to KAN-` instead of rendering `...`.
3. **[Medium - Evidence Integrity] Stale Round-1 telemetry in `docs/qa/KAN-20/api-specialist-review.md` (lines 120-150) and outdated file counts in `message-to-reality-checker.md` (lines 102, 106)**: `api-specialist-review.md` Section 3 quotes commit `07d04cde` (`total=24`, `latency=168.83ms`, `pillCount=11`, `/mcp/docs` `mode: lexical`), contradicting `live-fullstack-proof.txt` at commit `7913c2c8`. `build-or-typecheck.txt` reports `995` mypy source files and `2018` ruff files (`1.22s` build), whereas `message-to-reality-checker.md` and `api-specialist-review.md` report `989` / `1947` / `1.24s`.
4. **[Low - UI Polish] `kanban/web/src/app/CommandPalette.tsx` (lines 430-434) does not clear `liveSearchResults` when `query.trim()` becomes empty**: Clearing the input leaves prior `liveSearchResults` in state, which can briefly flash during the 150ms debounce when a new non-empty query is typed.

**Critical Issues**:
- None observed in ERA/FORCE RLS isolation (`test_synaptic_zero_oracle_leakage` and live `@member` secret probe both confirm 0 PRIV leaks) or statement-timeout handling (`SET LOCAL statement_timeout = 0` reset and nested savepoint fallback verified).

**Medium Issues**:
- Unfiltered vector/synaptic candidates in `search_issues(..., mode="hybrid")` when `filters` or `workspace` are provided (`kanban/services/search.py:1047-1073`).
- Mobile badge hard-clipping without ellipsis due to `display: inline-flex` + `text-overflow: ellipsis` (`kanban/web/src/app/CommandPalette.css:112`, visible in `live-command-palette-mobile-light.png`).
- Stale Round-1 live-proof section in `docs/qa/KAN-20/api-specialist-review.md` and stale static counts in `message-to-reality-checker.md`.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B+
**Design Implementation Level**: Good
**System Completeness**: 92%
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. Fix `search_issues` in `kanban/services/search.py` (lines 1047-1073) so that when `request.filters` or `request.workspace` is present in `mode="hybrid"`, any vector-hydrated or synaptic-spread issue candidates are constrained against the same `extra_predicates` (or matching issue IDs from the filtered scope) before returning `IssueSearchResponse`, and add a regression test in `kanban/tests/services/test_synaptic_search.py` verifying `search_issues(..., mode="hybrid", filters=...)` does not leak non-matching states/assignees.
2. Fix `.kb-palette-badge` truncation in `kanban/web/src/app/CommandPalette.css` (lines 111-126) by changing `display: inline-flex` to `display: inline-block` (with `vertical-align: middle; line-height: 1.4;`) or wrapping the inner label in a `block`/`inline-block` span so `text-overflow: ellipsis` renders a clean `...` on `390x844` mobile viewports (and consider clearing `liveSearchResults` when `!trimmed` in `CommandPalette.tsx:432`).
3. Refresh `docs/qa/KAN-20/api-specialist-review.md` Section 3 and `docs/qa/KAN-20/message-to-reality-checker.md` so all cited commit hashes (`7913c2c8`), live-proof counts (`total=4`/`8`, `pillCount=8`, `/mcp/docs` `mode: hybrid`), and static gate counts (`995` mypy files, `2018` ruff files, `1.22s` vite build) match `live-fullstack-proof.txt` and `build-or-typecheck.txt` verbatim.

**Timeline for Production Readiness**: 1 short revision cycle (targeted backend filter fix + 1 CSS/UI fix + packet refresh + re-capture mobile screenshot).
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Strict parity between `IssueSearchRequest.filters` / `workspace` and `mode="hybrid"` results.
- Clean CSS ellipsis rendering on long provenance pills in narrow mobile viewports (`390x844`).
- 100% factual alignment across all specialist review documents and attached proof logs in `docs/qa/KAN-20/`.

**Quality Targets**:
- Maintain `>=95%` test coverage across all 7 KAN-20 modules and `0` warnings across Ruff, Mypy, ESLint, TypeScript, Vitest, and `check_no_dashes`.
- Zero stale Round-1 numbers in `docs/qa/KAN-20/*.md`.

**Evidence Requirements**:
- Updated `kanban/tests/services/test_synaptic_search.py` output proving `search_issues(..., mode="hybrid", filters=...)` excludes non-matching filtered issues even when embeddings/links exist.
- Re-captured `docs/qa/KAN-20/screenshots/live-command-palette-mobile-light.png` showing `...` ellipsis (not hard clipping at `KAN-`) on `Linked via VERIFIED_BY_DOC to KAN-...`.
- Updated `api-specialist-review.md` and `message-to-reality-checker.md` consistent with `7913c2c8` logs.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-20/
**Re-assessment Required**: After fixes implemented

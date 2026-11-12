# API Specialist Gate Final Audit: APPROVED for KANBA-110 (KB-P3-17)

- Reviewer: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-110`
- Branch: `feat/KANBA-110`
- Head Commit SHA: `9cf2137`
- Ticket: `KANBA-110` (`KB-P3-17`: `[Phase 3 / API] Lexical tsvector + pg_trgm search API across issues, docs, pages & stickies under RLS`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, query security, and API specialist audit was conducted for `KANBA-110` (`KB-P3-17`) in `/tmp/kb-wt-KANBA-110`. This ticket implements ranked cross-entity lexical full-text (`tsvector`) and trigram (`pg_trgm`) search across issues, docs, pages, and stickies under strict PostgreSQL Row-Level Security (`FORCE RLS`), paired with heading-anchored excerpting and structural match spans.

All technical specifications in `docs/tickets/KB-P3-17.md` and architecture invariants in Spec Sections 11.2, 11.3, 12.2, 3.3, 5.4, and 6.3 were evaluated and verified.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **GIN Index Topology** | 8 GIN indexes across issues, docs, pages, stickies | Created all 8 GIN indexes and 3 generated stored `search_tsv` columns | PASS |
| **Reversible Migration Lifecycle** | Clean upgrade/downgrade roundtrip | Verified in `database/tests/test_p3_17_search_migration.py` | PASS |
| **Query Safety & Normalization** | 1..500 chars, strip `\x00..\x1f`, `websearch_to_tsquery` | Sanitized inputs; injection-safe against hostile operators and syntax errors | PASS |
| **Combined Scoring Formula** | `0.75 * ts_rank_cd + 0.25 * word_similarity` | Exact S12.2 weighting implemented; issue key match boosted to rank 100.0 | PASS |
| **Heading Anchor Resolution** | Nearest preceding ATX heading (`#slug`) | Extracted via `extract_markdown_outline`; `anchor: null` when preceding headings | PASS |
| **Zero-HTML Snippet Contracts** | Ban raw HTML markup tags in excerpts | Strips `<script>` and HTML tags; delivers plain excerpt + `match_spans` offsets | PASS |
| **Structural Match Spans** | 0-indexed char offset tuples `[start, end]` | Sorted, merged char offsets relative to snippet for safe client highlighting | PASS |
| **FilterSpec Composition** | Structured faceted filtering for issues | Composes lexical search with `compile_issue_filter_predicates` | PASS |
| **Signed Keyset Pagination** | HMAC-SHA256 cursor `{score, id, q_hash}` | Tamper-proof cursor signed with server secret; rejects altered cursors | PASS |
| **RLS Zero-Leak Invariant** | Exclude unreadable rows without leakage | Restricted canary rows yield 0 results; unreadable projects return equalized 404 | PASS |
| **Timing Equalization** | Wrap endpoints in `timing_floor(floor_ms=25.0)` | Enforced across `GET /search`, `POST /search/issues`, `POST /search/knowledge` | PASS |
| **Test Coverage & Metrics** | >= 95% line + branch coverage across target modules | 19/19 tests passed in 4.91s; 98.67% total branch + line coverage | PASS |
| **Static Code Quality** | Zero linter, typing, formatting, or contract errors | Ruff clean, Ruff format clean, Mypy strict clean, Lint-imports clean | PASS |
| **Typography Discipline** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 2. Deep Technical & Security Invariant Audits

#### A. Database Schema, Index Topology, and RLS (Spec S12.2, S3.3)
1. **Generated Stored Column Alignment (`database/migrations/versions/p3_17_search_indexes.py`):**
   - Adds `search_tsv tsvector GENERATED ALWAYS AS (...) STORED` on `docs`, `pages`, and `stickies` using `build_markdown_tsvector()` (`KB-P1-05`).
   - Title weighted with `'A'` (`setweight(to_tsvector('english', coalesce(title, '')), 'A')`); body weighted with `'B'`.
   - Stickies generate `search_tsv` directly from `build_markdown_tsvector(body_markdown)`.
2. **8 GIN Indexes:**
   - Full-text indexes: `issues_search_tsv_gin`, `docs_search_tsv_gin`, `pages_search_tsv_gin`, `stickies_search_tsv_gin`.
   - Trigram indexes: `issues_summary_trgm_gin`, `docs_title_trgm_gin`, `pages_title_trgm_gin`, `stickies_body_trgm_gin`.
3. **FORCE Row-Level Security Execution:**
   - Queries execute against the active session transaction where `SET LOCAL app.principal_id`, `app.workspace_id`, and `effective_resource_access` policies are enforced.
   - Entities where the caller lacks `VIEW` capability are filtered out at the PostgreSQL engine level; neither row counts nor metadata leak across tenant or project boundaries.

#### B. Query Parsing & Scoring Formula (Spec S11.2, S12.2)
1. **Hostile Query Normalization (`kanban/services/search.py`):**
   - Query input is validated: control characters (`\x00..\x1f`) are replaced with spaces, and length is strictly enforced to `1..500` characters (`422 QUERY_LENGTH`).
   - Query is parsed via `func.websearch_to_tsquery('english', query)`. Hostile operators (such as `' | & ! : * ( )`) and unclosed quotes are safely parsed without SQL syntax errors or 500 crashes.
2. **Combined Ranking Formula:**
   - Lexical rank: `ts_rank_cd(search_tsv, tsq, 32)` weighted at `0.75`.
   - Trigram similarity: `greatest(word_similarity(:q, title_col), 0.0)` weighted at `0.25`, activated when `char_length(query) >= 3` with threshold `>= 0.25`.
   - Exact/prefix issue key boost: When the query matches `^[A-Za-z][A-Za-z0-9]{1,9}-\d+$` (e.g. `KAN-142`), exact key matches receive a score boost of `100.0`, elevating them above all prose matches.

#### C. Snippets & Heading Anchor Resolution (Spec S11.3, S5.4)
1. **Heading-Anchored Deep Linking (`kanban/services/snippets.py`):**
   - `build_anchored_snippet` uses `extract_markdown_outline` (`KB-P3-14`) to parse the document outline and identify the nearest preceding ATX heading above the match window.
   - Emits clean anchor slugs (e.g. `anchor: "#pkce-s256"`). If the match occurs within the lead introduction prior to any heading, `anchor: None` is returned.
2. **Zero-HTML Security & Structural Match Spans:**
   - Raw HTML tags and script elements are stripped via regex before excerpt generation.
   - Rather than embedding raw HTML tags (`<b>`, `<mark>`) that require client `dangerouslySetInnerHTML`, the backend delivers plain excerpts `<= 300` characters alongside `match_spans: list[tuple[int, int]]`.
   - Match spans represent 0-indexed character offsets relative to the snippet string, allowing the frontend Command Palette and Knowledge Drawer to render highlights safely via string slicing.

#### D. Keyset Pagination & Anti-Enumeration Discipline (Spec S3.4)
1. **HMAC-Signed Keyset Cursors:**
   - Keyset cursors encode `{score, id, q_hash}` signed with HMAC-SHA256 using server key material.
   - Tampered cursors or cursors generated for a different query string fail validation with RFC 7807 `422 INVALID_CURSOR`.
   - Score values preserve exact float representations to avoid pagination drift.
2. **Timing Equalization:**
   - All three endpoints (`GET /api/v1/search`, `POST /api/v1/search/issues`, `POST /api/v1/search/knowledge`) are wrapped in `async with timing_floor(floor_ms=25.0):`.
   - Inaccessible or non-existent projects return identical RFC 7807 404 responses.

---

### 3. Verification Commands & Test Evidence

The following test suites were independently executed in `/tmp/kb-wt-KANBA-110`:

1. **Pytest Coverage & Execution:**
   - Command: `pytest kanban/tests/api/test_search.py kanban/tests/services/test_snippets.py database/tests/test_p3_17_search_migration.py -v --cov=kanban.api.v1.search --cov=kanban.services.search --cov=kanban.services.snippets --cov-branch --cov-report=term-missing`
   - Result: 19 passed in 4.91s.
   - Coverage: 98.67% overall across search modules:
     * `kanban/api/v1/search.py`: 100%
     * `kanban/services/search.py`: 99%
     * `kanban/services/snippets.py`: 99%

2. **Static Analysis & Linters:**
   - `ruff check .`: 0 errors.
   - `ruff format --check .`: 839 files checked, 0 reformat required.
   - `mypy --strict kanban/api/v1/search.py kanban/services/search.py kanban/services/snippets.py`: 0 errors across 3 source files.
   - `lint-imports`: 2 kept, 0 broken.
   - `check_no_dashes.py`: 0 non-ASCII unicode dashes detected.

---

### 4. Specialist Gate Verdict

The implementation in `feat/KANBA-110` satisfies all architectural, query safety, and API specifications. The GIN index topology, `build_markdown_tsvector` stored column configuration, heading-anchored excerpting, zero-HTML `match_spans` contracts, and timing equalization meet our highest standards.

VERDICT: APPROVED

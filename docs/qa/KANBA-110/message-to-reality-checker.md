# Reality-Checker Verification Packet: KANBA-110 (KB-P3-17)

## Ticket Overview
- **Ticket ID**: `KANBA-110`
- **Spec Section**: `KB-P3-17` (S11.1, S15.1, S15.4, S3.4)
- **Title**: `[Phase 3 / API] Lexical tsvector + pg_trgm search API across issues, docs, pages & stickies under RLS`
- **Wave**: `W17`
- **Git Branch**: `feat/KANBA-110` in isolated worktree `/tmp/kb-wt-KANBA-110`

---

## Technical Actions & File Manifest

1. **Database Migration & DDL**:
   - `database/migrations/versions/p3_17_search_indexes.py` (`down_revision = "p3_14_markdown_toc_ast"`)
   - `database/migrations/sql/p3_17_search_indexes.up.sql`
   - `database/migrations/sql/p3_17_search_indexes.down.sql`
   - Added `search_tsv` generated stored columns on `docs`, `pages`, and `stickies` using `build_markdown_tsvector()`.
   - Created all 8 required GIN indexes:
     * `issues_search_tsv_gin` ON `issues` USING gin (`search_tsv`)
     * `issues_summary_trgm_gin` ON `issues` USING gin (`summary` gin_trgm_ops)
     * `docs_search_tsv_gin` ON `docs` USING gin (`search_tsv`)
     * `docs_title_trgm_gin` ON `docs` USING gin (`title` gin_trgm_ops)
     * `pages_search_tsv_gin` ON `pages` USING gin (`search_tsv`)
     * `pages_title_trgm_gin` ON `pages` USING gin (`title` gin_trgm_ops)
     * `stickies_search_tsv_gin` ON `stickies` USING gin (`search_tsv`)
     * `stickies_body_trgm_gin` ON `stickies` USING gin (`body_markdown` gin_trgm_ops)
   - Updated ORM mappings in `database/models/knowledge.py` (`Doc.search_tsv`, `Page.search_tsv`, `Sticky.search_tsv` mapped to `TSVECTOR`).
   - Verified migration reversibility: `database/tests/test_p3_17_search_migration.py` tests upgrade -> downgrade -> upgrade cleanly.

2. **Snippets & Anchor Resolution Service**:
   - `kanban/services/snippets.py`:
     * `build_anchored_snippet(markdown: str, query: str, max_chars: int = 300) -> AnchoredSnippet`.
     * Zero raw HTML tags emitted (`<b>`, `<mark>`) preserving strict Content-Security-Policy compliance.
     * Structural `match_spans: list[tuple[int, int]]` offsets returned for safe client-side highlight rendering.
     * Resolves nearest preceding ATX heading using `extract_markdown_outline()` (`KB-P3-14`) to anchor snippets `#<slug>`.
     * Clean window slicing bounded by `max_chars`.
   - Unit tests: `kanban/tests/services/test_snippets.py` (12 tests, 99% coverage).

3. **Search Schemas & Domain Models**:
   - `kanban/api/v1/schemas/search.py`:
     * `SearchItem`, `SearchResponse` for unified cross-entity search (`GET /api/v1/search`).
     * `IssueSearchRequest`, `IssueSearchItem`, `IssueSearchResponse` for structured issue search (`POST /api/v1/search/issues`).
     * `KnowledgeSearchRequest`, `KnowledgeSearchItem`, `KnowledgeSearchResponse` for knowledge search (`POST /api/v1/search/knowledge`).
     * All schemas enforce safe input validation (query 1..500 chars, limit 1..50, valid entity kinds).

4. **Search Service Layer**:
   - `kanban/services/search.py`:
     * Query normalization stripping control characters `\x00..\x1f`.
     * Full-text search via `websearch_to_tsquery('english', :q)` paired with `word_similarity(:q, title_col)` (`pg_trgm`) when query length >= 3.
     * Exact/prefix issue key boost (`100.0` score) for queries matching `^[A-Za-z][A-Za-z0-9]{1,9}-\d+$`.
     * Combined ranking: `(0.75 * ts_rank_cd(search_tsv, tsq, 32)) + (0.25 * greatest(word_similarity(:q, title_col), 0.0))`.
     * Deterministic HMAC-SHA256 signed keyset pagination cursor encoding `{score, id, q_hash}` with bit-level IEEE-754 float precision.
     * Composes FilterSpec predicates via `compile_issue_filter_predicates` (`KB-P3-11`).
     * Cross-entity search executed under PostgreSQL RLS on `issues`, `docs`, `pages`, and `stickies`.

5. **Search API Endpoints**:
   - `kanban/api/v1/search.py` mounted at `/api/v1/search`:
     * `GET /api/v1/search`
     * `POST /api/v1/search/issues`
     * `POST /api/v1/search/knowledge`
     * Wrapped in `timing_floor(floor_ms=25.0)`.
     * Canonical 404 response for unreadable/non-existent projects eliminating enumeration side-channels.

---

## Verification & Quality Metrics

1. **Unit Test Suite & Coverage**:
   - Test files:
     * `kanban/tests/api/test_search.py`
     * `kanban/tests/services/test_snippets.py`
     * `database/tests/test_p3_17_search_migration.py`
   - Results: **19/19 tests passed** in 5.41s.
   - Combined coverage across touched modules: **98.67% branch + line** (mandate >= 95%).
     * `kanban.api.v1.search`: 100%
     * `kanban.services.search`: 99%
     * `kanban.services.snippets`: 99%
   - Migration lifecycle: Reversible test passed (upgrade -> downgrade -> upgrade).

2. **Zero New Third-Party Dependencies**:
   - `pyproject.toml` and `uv.lock` are 100% untouched.
   - Stdlib `hashlib`, `hmac`, `json`, `base64`, `re`, and existing `pg_trgm` / `tsvector` PostgreSQL extensions.

3. **Build & Static Analysis**:
   - `uv run ruff check kanban database`: Clean (All checks passed).
   - `uv run ruff format --check kanban database`: Clean (383 files formatted).
   - `uv run mypy --strict kanban database`: Clean (Success: no issues found in 379 source files).
   - `uv run lint-imports`: Contracts: 2 kept, 0 broken.
   - Dash character check: Clean (0 non-ASCII dashes repo-wide).

4. **Proof Artifacts**:
   - `docs/qa/KANBA-110/git-diff.patch`
   - `docs/qa/KANBA-110/unit-test-results.txt`
   - `docs/qa/KANBA-110/build-check.txt`
   - `docs/qa/KANBA-110/schema-dump.sql`
   - `docs/qa/KANBA-110/contract-sample.json`
   - `docs/qa/KANBA-110/message-to-reality-checker.md`

# Forensic QA Verification Packet: KAN-78

## Executive Summary
Ticket: `KAN-78` (`[KB-SEARCH-01] Build Server-Side Filter Predicate Compiler, Fix 'english' FTS Stemming Mismatch, & Enable hnsw.iterative_scan for RLS Vector Recall`)
Branch: `main` (merged from `feat/KAN-78-predicate-compiler-fts-hnsw`)
Merged Commit (`HEAD`): `68782e871112a1b8794e98ad74af933a4a1ced00` (`68782e87`)
Pre-Ticket Base Commit (`main`): `99c2c06586b4715cd5d0ee1257120d6b0be668fc` (`99c2c065`)
Visual Browser Screenshots: `N/A - Non-UI Ticket`
Status: READY FOR SPECIALIST AND REALITY-CHECKER AUDIT

All three core technical problems outlined in ticket KAN-78 have been solved, verified, and backed by automated unit and integration tests.

---

## 1. Problem 1: Bounded Filter Predicate Compiler
### Implementation
- Created `kanban/services/predicate_compiler.py`:
  - Enforces strict complexity budgets:
    - `MAX_QUERY_LENGTH = 512` characters
    - `MAX_CLAUSES = 32` clauses
    - `MAX_TOKENS = 32` tokens
    - Disallows complex nested ASTs or ReDoS backtracking via a linear O(n) tokenizer and clause splitter.
    - Rejects lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`) and non-printable ASCII control characters.
  - Translates DSL expressions into parameterized SQLAlchemy binary expressions and subqueries:
    - `state:actionable` -> `state_group NOT IN ('completed', 'cancelled')`
    - `state:closed` / `state:terminal` -> `state_group IN ('completed', 'cancelled')`
    - `state!=done` / `-state:cancelled` / `!status:closed` -> boolean inversion (`~cond`)
    - `priority:high,urgent` -> `lower(slug) IN ('high', 'urgent') OR lower(label) IN ('high', 'urgent')`
    - `assignee:@me` -> `EXISTS(IssueAssignee where principal_id = :caller_id)`
    - `assignee:unassigned` / `none` -> `NOT EXISTS(IssueAssignee where issue_id = Issue.id)`
    - `label:security` -> `EXISTS(IssueLabel join ProjectLabel where name = 'security')`
    - `cycle:current` / `active` -> `cycle_id IN (SELECT id FROM cycles WHERE status = 'active')`
    - `module:backend` -> `EXISTS(IssueModule join Module where name = 'backend')`
    - `project:KEY` / `-project:KEY` -> `EXISTS(Project where identifier = 'KEY')`
    - `key:FLTR-10` -> `sequence_id = 10 AND Project.identifier = 'FLTR'`
    - Free-text terms (e.g., `"mars telemetry"`) -> `Issue.search_tsv @@ websearch_to_tsquery('english', :q)`
- Integrated with `kanban/services/view_dsl.py`:
  - Exported `compile_predicate_string`, `MAX_QUERY_LENGTH`, `MAX_CLAUSES`, `MAX_TOKENS`.
  - Added support for compiling raw filter DSL strings alongside structured `FilterSpec`.

---

## 2. Problem 2: Full-Text Search English Stemming Dictionary Mismatch
### Implementation
- Root Cause Identified:
  - Database schema (`database/migrations/versions/p1_05_issues.py`) creates `search_tsv` using `'english'` stemming via trigger function `build_markdown_tsvector('english', ...)`.
  - Query compilation in `kanban/services/view_dsl.py` previously executed `websearch_to_tsquery('simple', :q)`, resulting in dictionary mismatch where inflected, plural, or conjugated English terms failed to match indexed documents.
- Fix:
  - Updated `kanban/services/view_dsl.py` line 315 to use `websearch_to_tsquery('english', :q)`.
  - Updated `kanban/services/search.py` lines 145 and 488 to use `plainto_tsquery('english', :q)` and `websearch_to_tsquery('english', :q)`.
  - Added integration test `test_english_fts_stemming_consistency_vs_simple` in `kanban/tests/services/test_predicate_compiler_fts_hnsw.py` verifying that inflected terms (e.g. "retrying" matching "retry", "telemetries" matching "telemetry") match under `'english'` stemming while failing under `'simple'`.

---

## 3. Problem 3: pgvector HNSW Iterative Scan under RLS
### Implementation
- Root Cause Identified:
  - Under PostgreSQL `FORCE ROW LEVEL SECURITY`, standard pgvector HNSW vector similarity search stops exploring index graph nodes after top-K candidates without accounting for rows filtered out by tenant RLS policies, leading to truncated recall (or 0 results) for non-admin users.
- Fix:
  - In `kanban/services/search.py` (`_query_vector_candidates`):
    - Executed `SET LOCAL hnsw.iterative_scan = 'relaxed_order'` inside a nested savepoint (`async with session.begin_nested():`).
    - Handled fallback gracefully if the GUC is unsupported by the runtime PostgreSQL engine.
  - In `agent/sparkle/retrieval.py` (`retrieve_context`):
    - Executed `SET LOCAL hnsw.iterative_scan = 'relaxed_order'` inside a nested savepoint (`async with session.begin_nested():`).
    - Handled fallback gracefully if the GUC is unsupported by the runtime PostgreSQL engine.
  - Added integration test `test_hnsw_iterative_scan_and_fallback` and unit tests in `kanban/tests/services/test_predicate_compiler_fts_hnsw.py`.

---

## 4. Verification Evidence & Quality Gates
### Test Coverage
- `kanban/services/predicate_compiler.py`: 95% statement coverage (404/427 stmts, 214/224 branches)
- `kanban/services/view_dsl.py`: 98% statement coverage (156/156 stmts, 76/80 branches)
- `agent/sparkle/retrieval.py`: 99% statement coverage (98/98 stmts, 31/32 branches)

### Build Checks (`make check`)
- `uv run ruff check .` -> PASSED (0 errors)
- `uv run ruff format --check .` -> PASSED (2150 files formatted)
- `uv run mypy` -> PASSED (0 errors in 1190 source files)
- `uv run lint-imports` -> PASSED (2 contracts kept, 0 broken)
- `uv run python -m scripts.check_no_dashes --all` -> PASSED (0 violations)
- `uv run python -m database.migrations.cli check-migrations --static-only` -> PASSED (65 migrations valid, single head)

---

## 5. Artifacts Checklist
- `docs/qa/KAN-78/git-diff.patch`: Complete git diff against main
- `docs/qa/KAN-78/unit-test-results.txt`: Test run output of all relevant test modules
- `docs/qa/KAN-78/build-check.txt`: Complete log output of `make check`
- `docs/qa/KAN-78/contract-sample.json`: Concrete schema sample of DSL clauses, AST, and SQL output
- `docs/qa/KAN-78/message-to-reality-checker.md`: This forensic QA summary

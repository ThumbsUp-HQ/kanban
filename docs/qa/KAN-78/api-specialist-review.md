# API and Security Specialist Review: KAN-78

- **Ticket:** KAN-78 ([KB-SEARCH-01]) - Build Server-Side Filter Predicate Compiler, Fix 'english' FTS Stemming Mismatch, & Enable hnsw.iterative_scan for RLS Vector Recall
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `main` (merged from `feat/KAN-78-predicate-compiler-fts-hnsw`)
- **Commit Under Audit (`HEAD`):** `68782e871112a1b8794e98ad74af933a4a1ced00` (`68782e87`)
- **Base Commit (`main`):** `99c2c06586b4715cd5d0ee1257120d6b0be668fc` (`99c2c065`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan78-884371fc`
- **Status:** APPROVED

---

## 1. Executive API & Security Architecture Evaluation

Ticket KAN-78 addresses three fundamental backend data-retrieval and search integrity challenges:
1. **Bounded Server-Side Filter Predicate Compiler (`kanban/services/predicate_compiler.py`):**
   - Implements a linear tokenizer and parser for human-typed and MCP DSL filter strings.
   - Strictly enforces complexity bounds: maximum 512 characters, 32 clauses, and 32 tokens, completely preventing algorithmic complexity and ReDoS attacks.
   - Enforces UTF-16 lone-surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF`) and rejects ASCII control characters.
   - Compiles parsed clauses to parameterized SQLAlchemy binary expressions and subqueries against project-scoped tables (`workflow_states`, `project_priorities`, `issue_assignees`, `cycles`, `modules`, `project_labels`).
   - Supports intuitive semantic shorthands (`state:actionable`, `state:closed`, `priority:high,urgent`, `assignee:@me`, `assignee:unassigned`, `cycle:current`, `-project:KEY`, etc.).
2. **Full-Text Search English Stemming Dictionary Synchronization:**
   - Corrected dictionary mismatch between PostgreSQL tsvector generation (`build_markdown_tsvector('english', ...)`) and query parsing.
   - Updated `kanban/services/view_dsl.py` and `kanban/services/search.py` to use `websearch_to_tsquery('english', :q)` and `plainto_tsquery('english', :q)` instead of `'simple'`.
   - Verified that inflected forms (e.g., "telemetries" matching "telemetry") resolve correctly under English stemming.
3. **pgvector HNSW Iterative Scan Under RLS:**
   - Resolved vector recall loss under PostgreSQL `FORCE ROW LEVEL SECURITY`.
   - Configured `SET LOCAL hnsw.iterative_scan = 'relaxed_order'` inside nested savepoints (`async with session.begin_nested():`) in both `kanban/services/search.py` and `agent/sparkle/retrieval.py`.
   - Guaranteed graceful fallback when running on environments or Postgres versions where the GUC is unrecognized.

---

## 2. Wire Contracts & Security Invariants

### A. SQL Injection & ReDoS Defense
- All filter values are converted to bound query parameters or verified against strict allowlists (e.g. integer sequence IDs, static state group names).
- Zero raw string concatenation is used in SQL generation.
- Complexity limits and regex-free linear tokenization protect the server against parser exhaustion.

### B. Tenancy & RLS Invariants
- `assignee:@me` securely resolves to the verified `caller_principal_id` without client forgery risks.
- Subqueries for states, priorities, cycles, and labels enforce explicit project-level scoping (`project_id = :project_id`).
- Vector queries maintain tenant isolation through RLS policies while restoring candidate recall via `relaxed_order` traversal.

---

## 3. Unit Test Coverage & Verification Metrics

- **Pytest Results:** 23 tests passed in 1.54s across `test_predicate_compiler_fts_hnsw.py`, `test_query_engine.py`, and `test_retrieval.py`.
- **Statement & Branch Coverage:**
  - `kanban/services/predicate_compiler.py`: 95% statement coverage (404/427 stmts, 214/224 branches).
  - `kanban/services/view_dsl.py`: 98% statement coverage (156/156 stmts, 76/80 branches).
  - `agent/sparkle/retrieval.py`: 99% statement coverage (98/98 stmts, 31/32 branches).
- **Static Quality Checks:**
  - `ruff check`: All checks passed.
  - `ruff format`: Clean.
  - `mypy`: 0 issues found in 1190 source files.
  - `lint-imports`: 2 kept, 0 broken.
  - `check-migrations`: Valid single head.
  - `check_no_dashes`: Clean across all files.

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.

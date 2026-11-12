# Audit Manifest: KANBA-41 (KB-P1-05)

- **Ticket ID**: `KANBA-41` (`KB-P1-05`)
- **Title**: `[Phase 1 / Database] issues table, atomic sequence allocation & build_markdown_tsvector()`
- **Epic**: `KB-E1`
- **Branch**: `feat/KANBA-41` (isolated worktree at `/tmp/kb-wt-KANBA-41`)
- **Spec Sections**: Section 12.2, Section 7.2 (8a, 8e), Section 5.1

---

## 1. Executive Summary

This ticket implements the core `issues` graph entity table, atomic per-project sequence allocation, and Markdown-aware full-text search indexing:
1. `build_markdown_tsvector(md text)` Function:
   - Defined as `LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE`.
   - Strips fence delimiter lines and info strings (`(?m)^\s{0,3}(```|~~~).*$`).
   - Normalizes markdown links and images to anchor text (`[text](url)` -> `text`).
   - Strips markdown link reference definitions, autolinks, and bare URLs.
   - Replaces markdown structural punctuation with spaces while preserving code identifiers.
2. `issues` Entity Table:
   - DDL verbatim matching Section 12.2 specification.
   - Pinned `object_type = 'issue'` with composite foreign key to `objects(id, object_type) ON DELETE RESTRICT`.
   - Generated stored `description_sha256 BYTEA GENERATED ALWAYS AS (digest(description_markdown, 'sha256')) STORED`.
   - Generated stored `search_tsv` tsvector combining summary (weight 'A') and `build_markdown_tsvector(description_markdown)` (weight 'B').
   - Supporting GIN index on `search_tsv`, B-tree composite index on `(project_id, state_id, board_rank COLLATE "C")`, and partial B-tree index on `parent_issue_id`.
   - Temporary plain UUID for `cycle_id` pending KB-P1-08 cycles implementation.
3. Atomic Sequence Allocation (`allocate_issue_sequence(p_project_id uuid)`):
   - Defined as `LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public', 'pg_temp'`.
   - Atomic counter increment on `projects.issue_seq_counter` with row lock.
   - Raises `PROJECT_NOT_FOUND` (P0001) if project does not exist.
   - Granted execution rights to `kanban_app`.
4. Integrity Trigger (`issues_validate_biu`):
   - Enforces workspace consistency between issue and parent project (`ISSUE_WORKSPACE_MISMATCH`).
   - Enforces spine registration and canonical key alignment (`ISSUE_SPINE_MISMATCH`).
   - Enforces sequence number allocation bounds (`ISSUE_SEQUENCE_NOT_ALLOCATED`).
   - Enforces project scope for workflow state and priority (`ISSUE_STATE_PROJECT_MISMATCH`, `ISSUE_PRIORITY_PROJECT_MISMATCH`).
   - Enforces immutability of `sequence_id` and `project_id` on update (`ISSUE_KEY_IMMUTABLE`).
   - Automatically computes and sets `ancestry_path` ltree on insert, overwriting client input.
5. Migration & Lineage:
   - Strict linear Alembic migration `p1_05_issues.py` chained from `p1_11_object_links`.
   - Fully reversible with reverse drop order in `p1_05_issues.down.sql`.

---

## 2. Requirement Traceability Matrix

| Requirement | Implementation Artifact | Verification Method |
| :--- | :--- | :--- |
| Section 12.2: `issues` table DDL verbatim | `p1_05_issues.up.sql` | `test_01_create_issue_app_flow_and_hash` |
| Section 12.2: Generated `description_sha256` | `p1_05_issues.up.sql` | `test_01_create_issue_app_flow_and_hash` |
| Section 12.2: `build_markdown_tsvector` FTS | `p1_05_issues.up.sql` | `test_02_tsvector_markdown_filtering` |
| Section 7.2 8a: Summary length 1 to 500 chars | `p1_05_issues.up.sql` | `test_03_negative_checks` (SQLSTATE 23514) |
| Section 7.2 8e: Date order `due_date >= start_date` | `p1_05_issues.up.sql` | `test_03_negative_checks` (SQLSTATE 23514) |
| Section 5.1: Description size <= 1048576 bytes | `p1_05_issues.up.sql` | `test_03_negative_checks` (SQLSTATE 23514) |
| Section 12.2: Generated column write rejection | PostgreSQL Engine | `test_04_negative_security_and_spine` (SQLSTATE 428C9) |
| Section 12.2: Cross-project state validation | `issues_validate_biu()` | `test_04_negative_security_and_spine` (`ISSUE_STATE_PROJECT_MISMATCH`) |
| Section 12.2: Sequence counter bounds validation | `issues_validate_biu()` | `test_04_negative_security_and_spine` (`ISSUE_SEQUENCE_NOT_ALLOCATED`) |
| Section 12.2: Ancestry path client overwrite | `issues_validate_biu()` | `test_04_negative_security_and_spine` |
| Section 12.2: Sequence and project key immutability | `issues_validate_biu()` | `test_05_negative_immutability_and_missing_project` (`ISSUE_KEY_IMMUTABLE`) |
| Section 12.2: Non-existent project sequence allocation | `allocate_issue_sequence()` | `test_05_negative_immutability_and_missing_project` (`PROJECT_NOT_FOUND`) |
| Concurrency: 20 concurrent connections allocation | `allocate_issue_sequence()` | `test_06_concurrent_sequence_allocation` |
| Boundary: `build_markdown_tsvector` volatility | `p1_05_issues.up.sql` | `test_07_boundary_and_volatility` (`provolatile = 'i'`) |
| Migration: Up/Down/Up reversibility | `p1_05_issues.py` | `test_p1_05_migration.py` (`test_p1_05_migration_lifecycle`) |

---

## 3. Passive Forensic Proof Artifacts

All verification artifacts are stored under `docs/qa/KANBA-41/`:
1. `docs/qa/KANBA-41/unit-test-results.txt`:
   - Command: `uv run pytest database/tests/test_p1_05_issues.py database/tests/test_p1_05_sequence_concurrency.py database/tests/migrations/test_p1_05_migration.py -q --cov=database --cov-branch --cov-report=term-missing`
   - Result: 8 passed in 0.90s, 100% statement and branch coverage on touched modules, exit code 0.
2. `docs/qa/KANBA-41/build-check.txt`:
   - Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
   - Result: ruff check clean, ruff format clean (37 files), mypy strict clean (35 source files), exit code 0.
3. `docs/qa/KANBA-41/alembic-heads.txt`:
   - Command: `uv run alembic -c database/alembic.ini heads`
   - Result: Single linear head `p1_05_issues (head)`, exit code 0.
4. `docs/qa/KANBA-41/schema-dump.sql`:
   - Raw PostgreSQL schema dump of `issues` table and definitions of `build_markdown_tsvector` and `allocate_issue_sequence`.
5. `docs/qa/KANBA-41/tsvector-sample.txt`:
   - Query output of `build_markdown_tsvector` on the test case 2 input verifying fence markers, info strings, and URLs are stripped while content is indexed.
6. `docs/qa/KANBA-41/git-diff.patch`:
   - Complete unified git diff against `main`.

---

## 4. Unicode Character Verification

Zero Unicode dash characters (`U+2014` em-dash or `U+2013` en-dash) repository-wide. Checked and enforced across all source, migration, test, and documentation files.

# Reality-Checker Verification Packet: KANBA-49 (KB-P1-09)

**Ticket:** KANBA-49 (`KB-P1-09`)
**Title:** [Phase 1 / Database] issue_comments, stickies, docs, pages & page_versions (Markdown-only + STORED sha256)
**Epic:** KB-E1
**Branch:** `feat/KANBA-49` (Worktree: `/tmp/kb-wt-KANBA-49`)
**Author:** `builder-20`
**Spec Traceability:** `S5.1` (zero `*_html` / `*_ast` columns), `S8.1` (`ltree` pages `max_depth <= 10`, 6-color palette), `S8.2` (`promotion_recommended`, `promotion_snoozed_at_length`), `S12.2` (prose contract lines for `issue_comments`, `stickies`, `docs`, `pages`), Requirements #5, #10, #11, #8k, #13b, #13c, #13i

---

## 1. Executive Summary

This ticket delivers the canonical Markdown-only database schema, size caps, and triggers for all prose entities across the platform:
- **Canonical Markdown & Generated Hash Invariant:**
  - `100%` of prose is stored as canonical UTF-8 GitHub-Flavored Markdown.
  - Zero `*_html`, `*_ast`, or prose-bearing `jsonb` columns exist repository-wide (verified via catalog audit returning 0 rows).
  - Every prose table implements `body_sha256 BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED` providing an automatic tamper-evident ETag.
- **Five Prose Tables:**
  1. `issue_comments`: Threaded comments with `body_markdown` (1..262144 bytes), `parent_comment_id` self-FK (`ON DELETE RESTRICT`), and `issue_comments_workspace_biu` trigger enforcing issue workspace inheritance and parent comment issue alignment (`COMMENT_PARENT_MISMATCH`).
  2. `docs`: Top-level knowledge documents referencing `objects(id, object_type)` (`ON DELETE RESTRICT`), project assignment, title (1..500 chars), `body_markdown` (<= 1048576 bytes), `docs_hierarchy_bi` trigger generating root `d<hex>` ltree path, and `docs_versioning_bu` trigger auto-incrementing `version_seq` on edits while rejecting manual mutations (`VERSION_SEQ_MANAGED`).
  3. `pages`: Hierarchical subpages organized in an `ltree` tree under parent doc, referencing `objects(id, object_type)` (`ON DELETE RESTRICT`), with `sort_rank`, title (1..500 chars), `body_markdown` (<= 1048576 bytes), check constraint `nlevel(hierarchy_path) BETWEEN 2 AND 11` (enforcing max page depth <= 10), `pages_hierarchy_biu` trigger preventing cycles (`PAGE_CYCLE`), locking ancestors `FOR UPDATE`, enforcing same-doc parentage (`PAGE_PARENT_DOC_MISMATCH`), enforcing max depth (`PAGE_MAX_DEPTH_EXCEEDED`), and `pages_hierarchy_au` trigger cascading path rebase across descendants upon reparenting.
  4. `page_versions`: Append-only immutable snapshot ledger storing previous page versions upon title or body mutations, with `page_versions_immutable_bud` trigger preventing direct updates or deletions (`PAGE_VERSION_IMMUTABLE`) while allowing parent page cascade deletions (`pg_trigger_depth() > 1`).
  5. `stickies`: Lightweight project/workspace notes with `body_markdown` (<= 65536 bytes), 6-palette `color_token` check (`amber`, `mint`, `sky`, `lavender`, `coral`, `slate`), `promotion_recommended`, `promotion_snoozed_at_length`, `promoted_to_doc_id` FK (`ON DELETE SET NULL`), and `stickies_promotion_guard_bu` trigger ensuring promotion can transition only from NULL to a doc in the same workspace (`STICKY_PROMOTION_INVALID`).
- **Objects Spine Match Triggers:**
  - `docs_spine_match_biu`, `pages_spine_match_biu`, and `stickies_spine_match_biu` verify `objects` registration and enforce matching `workspace_id` and `project_id` (`PROSE_SPINE_MISMATCH`).

---

## 2. Definition of Done Compliance Matrix

| DoD Requirement | Status | Evidence File / Proof |
| :--- | :---: | :--- |
| **File Existence & Implementation:** `p1_09_prose_tables.py`, `p1_09_prose_tables.up.sql`, `p1_09_prose_tables.down.sql` exist and define all 5 tables with `STORED sha256` and 6-value `color_token` check | PASS | `database/migrations/versions/p1_09_prose_tables.py`<br>`database/migrations/sql/p1_09_prose_tables.up.sql`<br>`database/migrations/sql/p1_09_prose_tables.down.sql` |
| **Single Head:** `alembic heads` prints exactly one head: `p1_09_prose_tables (head)` | PASS | `docs/qa/KANBA-49/alembic-heads.txt` |
| **Unit Tests Implemented & Passing:** 8/8 tests passing in 1.14s with 100% statement and branch coverage on touched modules | PASS | `docs/qa/KANBA-49/unit-test-results.txt` (8 passed in 1.14s, 100% coverage on `p1_09_prose_tables.py`, `test_p1_09_prose.py`, `test_p1_09_markdown_only_schema.py`, `test_p1_09_migration.py`) |
| **Build / Type / Lint Clean:** `ruff check`, `ruff format --check`, `mypy --strict`, `check_no_dashes --all` exit 0 | PASS | `docs/qa/KANBA-49/build-check.txt` |
| **Forensic Proof Packet Complete:** All artifacts populated under `docs/qa/KANBA-49/` | PASS | `git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, `alembic-heads.txt`, `schema-dump.sql`, `markdown-only-catalog.txt`, `message-to-reality-checker.md` |

---

## 3. Test Traceability Matrix

| Test Function | Scoped Requirement | Verifications |
| :--- | :--- | :--- |
| `test_01_prose_sha256_hash_verification` | S12.2, S5.1 | Comment, sticky, doc, and page insert; each `body_sha256` matches Python `hashlib.sha256(body.encode()).digest()` byte-for-byte. Verified root doc path format `d<hex>` and page path format `d<hex>.p<hex>`. |
| `test_02_page_versioning_and_snapshots` | S8.1, S12.2 | Updating page body twice increments `version_seq` from 1 to 2 to 3, automatically archiving v1 and v2 snapshots in `page_versions` with exact bodies and hashes. Verified doc body update increments `docs.version_seq` without snapshot rows. |
| `test_03_pages_hierarchy_tree_and_rebase` | S8.1 | Three-level page tree `P1 <- P2 <- P3` under doc `D`. Moving `P2` to doc root (`parent_page_id = NULL`) automatically rebases `P3` descendant path via `pages_hierarchy_au` trigger. |
| `test_04_markdown_only_schema_catalog` | S5.1 | Schema-wide catalog query asserting 0 columns matching `_html$`, `_ast$`, `^html_`, or prose `jsonb` types. Verifies every `*_markdown` column across `issues, issue_comments, docs, pages, page_versions, stickies` has a sibling `*_sha256` column with `is_generated = 'ALWAYS'`. |
| `test_05a_negative_color_cycle_and_hierarchy` | S8.1, S12.2 | `color_token='red'` raises check violation `23514`. Self-parent and indirect page cycles raise `PAGE_CYCLE`. Reparenting across different docs raises `PAGE_PARENT_DOC_MISMATCH`. |
| `test_05b_negative_immutability_and_promotions` | S8.1, S8.2, S12.2 | Direct `UPDATE` or `DELETE` on `page_versions` raises `PAGE_VERSION_IMMUTABLE`. Explicit insert to `body_sha256` raises `428C9`. Cross-issue comment reply raises `COMMENT_PARENT_MISMATCH`. Cross-workspace sticky promotion and re-promotion raise `STICKY_PROMOTION_INVALID`. |
| `test_06_boundary_lengths_and_depth` | S8.1, S12.2 | Page nesting at depth 10 accepted; depth 11 raises `PAGE_MAX_DEPTH_EXCEEDED`. Sticky body at 65536 bytes accepted; 65537 bytes raises `23514`. Empty comment body rejected (`23514`), 262144 bytes accepted, 262145 rejected. Doc body at 1048576 bytes accepted, 1048577 rejected. |
| `test_07_prose_tables_migration_lifecycle` | Migration | `MigrationHarness` upgrade `p1_09_prose_tables` -> 5 tables exist; downgrade to `p1_13_access_control` -> absent; re-upgrade succeeds. |

---

## 4. Verification Proof Artifacts

- `docs/qa/KANBA-49/git-diff.patch`: Clean unified diff against base branch `main`.
- `docs/qa/KANBA-49/unit-test-results.txt`: Output of `uv run pytest database/tests/test_p1_09_prose.py database/tests/test_p1_09_markdown_only_schema.py database/tests/migrations/test_p1_09_migration.py -q --cov=database --cov-branch --cov-report=term-missing` (8 passed in 1.14s, exit code 0).
- `docs/qa/KANBA-49/build-check.txt`: Output of `ruff check`, `ruff format --check`, `mypy --strict`, and `check_no_dashes --all` (exit code 0).
- `docs/qa/KANBA-49/alembic-heads.txt`: Single linear head `p1_09_prose_tables (head)`.
- `docs/qa/KANBA-49/schema-dump.sql`: Complete pg_dump schema for `issue_comments`, `docs`, `pages`, `page_versions`, `stickies`.
- `docs/qa/KANBA-49/markdown-only-catalog.txt`: Raw query output showing `(0 rows)` for disallowed prose columns.
- Screenshots: N/A (Backend Database & Migration Ticket).

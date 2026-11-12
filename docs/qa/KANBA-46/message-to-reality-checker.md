# Audit Manifest: KANBA-46 (KB-P1-06)

- **Ticket ID**: `KANBA-46` (`KB-P1-06`)
- **Title**: `[Phase 1 / Database] Parent DAG trigger with FOR UPDATE ancestor locks & ltree ancestry`
- **Epic**: `KB-E1`
- **Branch**: `feat/KANBA-46` (isolated worktree at `/tmp/kb-wt-KANBA-46`)
- **Spec Sections**: Section 7.2 (8h)
- **Dependencies**: `KB-P1-05` (KANBA-41)

---

## 1. Executive Summary

This ticket delivers the hierarchical parent-child DAG enforcement engine for issues, securing the acyclic tree invariant and materialized `ancestry_path` ltree under concurrent reparenting:
1. Schema Additions:
   - GiST index `issues_ancestry_gist` on `issues(ancestry_path)` for accelerated `@>`, `<@`, and `~` hierarchical operations.
   - Depth check constraint `issues_ancestry_depth_chk CHECK (nlevel(ancestry_path) BETWEEN 1 AND 6)`.
   - Helper function `issue_ltree_label(p_id uuid) RETURNS ltree` declared `LANGUAGE sql IMMUTABLE PARALLEL SAFE`.
2. Validation Trigger (`issues_validate_biu`):
   - Replaced KB-P1-05 simple path logic, establishing precedence for `issues_parent_dag_biu`.
   - Immutable keys (`sequence_id`, `project_id`) enforced as the first step on UPDATE (`ISSUE_KEY_IMMUTABLE`).
   - Project existence, workspace matching, sequence bounds, and state/priority project validation maintained.
3. Parent DAG Validation Trigger (`issues_parent_dag_biu`):
   - Defined as `BEFORE INSERT OR UPDATE OF parent_issue_id ON issues FOR EACH ROW`.
   - Root handling: `NEW.parent_issue_id IS NULL` sets `NEW.ancestry_path := issue_ltree_label(NEW.id)`.
   - Self-reference rejection: `NEW.parent_issue_id = NEW.id` raises `PARENT_SELF_REFERENCE` (P0001).
   - Top-down ancestor locking: executes `PERFORM 1 FROM issues WHERE ancestry_path @> v_parent_path ORDER BY nlevel(ancestry_path) FOR UPDATE` to prevent lock-order inversions.
   - Cross-project rejection: parent project must match `NEW.project_id`, else raises `PARENT_CROSS_PROJECT` (P0001).
   - Cycle detection: checks `v_parent_path ~ ('*.' || replace(NEW.id::text, '-', '') || '.*')::lquery`, raising `PARENT_CYCLE` (P0001).
   - Subtree depth capping: checks `nlevel(v_parent_path) + 1 + v_subtree_height > 6`, raising `PARENT_MAX_DEPTH_EXCEEDED` (P0001).
   - Authoritative path assignment: `NEW.ancestry_path := v_parent_path || issue_ltree_label(NEW.id)`.
4. Descendant Rebasing Trigger (`issues_parent_dag_au`):
   - Defined as `AFTER UPDATE OF parent_issue_id ON issues FOR EACH ROW WHEN (OLD.ancestry_path IS DISTINCT FROM NEW.ancestry_path)`.
   - Automatically rebases all descendants:
     `UPDATE issues SET ancestry_path = NEW.ancestry_path || subpath(ancestry_path, nlevel(OLD.ancestry_path)) WHERE ancestry_path <@ OLD.ancestry_path AND id <> NEW.id`.
   - Updates only `ancestry_path`, ensuring no recursive re-triggering of `BEFORE ... OF parent_issue_id`.
   - Naturally handles parent deletion (`ON DELETE SET NULL`), promoting orphans to roots and rebasing subtrees.
5. Migration & Reversibility:
   - Linear Alembic migration `p1_06_parent_dag.py` chained from `p1_05_issues`.
   - Clean, verified rollback in `p1_06_parent_dag.down.sql` restoring KB-P1-05 path logic.

---

## 2. Requirement Traceability Matrix

| Requirement | Implementation Artifact | Verification Method |
| :--- | :--- | :--- |
| Section 7.2 8h: Materialized `ancestry_path ltree` | `p1_06_parent_dag.up.sql` | `test_01_positive_hierarchy_path_and_depth` |
| Section 7.2 8h: Max depth <= 6 constraint | `issues_ancestry_depth_chk` | `test_04_negative_depth_limits` |
| Section 7.2 8h: `FOR UPDATE` ancestor locking | `issues_parent_dag_biu()` | `test_07_concurrent_opposite_reparenting` |
| Section 7.2 8h: Reject cycles (`A -> B -> A`) | `issues_parent_dag_biu()` | `test_03_negative_cycles_and_self_reference` (`PARENT_CYCLE`) |
| Section 7.2 8h: Reject self-parent reference | `issues_parent_dag_biu()` | `test_03_negative_cycles_and_self_reference` (`PARENT_SELF_REFERENCE`) |
| Section 7.2 8h: Cross-project parent prevention | `issues_parent_dag_biu()` | `test_05_negative_cross_project_and_nonexistent_parent` (`PARENT_CROSS_PROJECT`) |
| Section 7.2 8h: Subtree reparenting rebase | `issues_parent_dag_au()` | `test_02_positive_subtree_move_and_rebase` |
| Section 7.2 8h: Parent delete / unparent rebase | `issues_parent_dag_au()` | `test_06_boundary_parent_delete_and_unparent` |
| Concurrency: Opposite moves serialization / deadlock | `issues_parent_dag_biu()` | `test_07_concurrent_opposite_reparenting` |
| Migration: Up/Down/Up reversibility | `p1_06_parent_dag.py` | `test_08_parent_dag_migration_lifecycle` |

---

## 3. Passive Forensic Proof Artifacts

All verification artifacts are stored under `docs/qa/KANBA-46/`:
1. `docs/qa/KANBA-46/unit-test-results.txt`:
   - Command: `uv run pytest database/tests/test_p1_06_parent_dag.py database/tests/test_p1_06_parent_concurrency.py database/tests/migrations/test_p1_06_migration.py -q --cov=database --cov-branch --cov-report=term-missing`
   - Result: 8 passed in 1.91s, 100% statement and branch coverage on touched modules, exit code 0.
2. `docs/qa/KANBA-46/build-check.txt`:
   - Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
   - Result: ruff check clean, ruff format clean (41 files), mypy strict clean (39 source files), exit code 0.
3. `docs/qa/KANBA-46/alembic-heads.txt`:
   - Command: `uv run alembic -c database/alembic.ini heads`
   - Result: Single linear head `p1_06_parent_dag (head)`, exit code 0.
4. `docs/qa/KANBA-46/schema-dump.sql`:
   - PostgreSQL schema dump of `issues` table and function definitions (`issue_ltree_label`, `issues_parent_dag_biu`, `issues_parent_dag_au`, `issues_validate_biu`).
5. `docs/qa/KANBA-46/subtree-move-sample.txt`:
   - Output of `SELECT summary, id, parent_issue_id, ancestry_path FROM issues ORDER BY ancestry_path` before and after test case 2.
6. `docs/qa/KANBA-46/git-diff.patch`:
   - Complete unified git diff against base commit `f38fbc2`.

---

## 4. Unicode Character Verification

Zero Unicode dash characters (`U+2014` em-dash or `U+2013` en-dash) repository-wide. Checked and enforced across all source, migration, test, and documentation files.

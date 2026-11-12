# Audit Manifest: KANBA-37 (KB-P1-11)

- **Ticket ID**: `KANBA-37` (`KB-P1-11`)
- **Title**: `[Phase 1 / Database] object_links, link_kind enum & seeded link_type_matrix allowlist`
- **Epic**: `KB-E1`
- **Branch**: `feat/KANBA-37` (isolated worktree at `/tmp/kb-wt-KANBA-37`)
- **Spec Sections**: Section 12.1, Section 7.2 (8m), Section 12.3 (item 4)

---

## 1. Executive Summary

This ticket delivers the typed relationship layer of the Universal Object Graph for the Kanban platform:
1. `link_kind` Enum: Creates the 13-label PostgreSQL enum in the exact specification order defined in Section 12.1 (`BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `PARENT_OF`, `ASSIGNED_TO`, `IN_CYCLE`, `IN_MODULE`, `PROMOTED_TO_DOC`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`, `EMBEDS_OBJECT`, `GOVERNED_BY_VIEW`).
2. `object_links` Table: Implements the graph edge table with composite type-pinned foreign keys (`FOREIGN KEY (source_id, source_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT`), self-link prevention (`CHECK (source_id <> target_id)`), duplicate edge prevention (`UNIQUE (source_id, target_id, link_type)`), and three query-optimizing B-tree indexes (`source_idx`, `target_idx`, `ws_state_idx`).
3. `link_type_matrix` Catalog: Defines the baseline relationship allowlist table with `kanban_app` write permissions revoked (`REVOKE INSERT, UPDATE, DELETE ON link_type_matrix FROM kanban_app`). Seeded with exactly 96 tuples partitioning user-creatable relationships (57 tuples across the 6 Section 7.2 8m user kinds) from system-managed graph edges (39 tuples across the 7 system kinds).
4. Validation & Immutability Triggers:
   - `object_links_validate_bi`: Enforces allowlist validation (`LINK_TYPE_NOT_ALLOWED`), validates endpoint object existence (`LINK_ENDPOINT_NOT_FOUND`), enforces workspace boundary integrity (`LINK_CROSS_WORKSPACE_FORBIDDEN`), and overwrites caller parameters with authoritative `canonical_key` snapshots and `link_state = 'ACTIVE'`.
   - `object_links_guard_bu`: Strictly forbids mutation of any column other than `link_state` (`OBJECT_LINK_IMMUTABLE`).
5. Migration & Reversibility: Fully reversible migration lifecycle (`p1_11_object_links.py`, `p1_11_object_links.up.sql`, `p1_11_object_links.down.sql`) maintaining a single linear head on Alembic.

---

## 2. Requirement Traceability Matrix

| Requirement | Implementation Artifact | Verification Method |
| :--- | :--- | :--- |
| Section 12.1: 13-value `link_kind` enum | `p1_11_object_links.up.sql` | `test_06_boundary_enum_order_and_link_type_matrix` + `test_07_object_links_migration_lifecycle` |
| Section 12.1: `object_links` DDL verbatim | `p1_11_object_links.up.sql` | `test_01_link_objects_positive_snapshots_and_active_state` |
| Section 12.1: Composite `ON DELETE RESTRICT` FKs | `p1_11_object_links.up.sql` | `test_04_negative_cross_workspace_and_foreign_key_guards` |
| Section 12.1: Self-link check (`source_id <> target_id`) | `p1_11_object_links.up.sql` | `test_03_negative_matrix_and_self_link_guards` (SQLSTATE 23514) |
| Section 12.1: Edge uniqueness | `p1_11_object_links.up.sql` | `test_03_negative_matrix_and_self_link_guards` (SQLSTATE 23505) |
| Section 7.2 8m: User vs system link partition | `p1_11_object_links.up.sql` | `test_06_boundary_enum_order_and_link_type_matrix` |
| Section 12.3: Type matrix enforcement on insert | `object_links_validate_bi()` | `test_03_negative_matrix_and_self_link_guards` (`LINK_TYPE_NOT_ALLOWED`) |
| Section 12.1: Cross-workspace link prevention | `object_links_validate_bi()` | `test_04_negative_cross_workspace_and_foreign_key_guards` (`LINK_CROSS_WORKSPACE_FORBIDDEN`) |
| Section 12.1: Authoritative key snapshot capture | `object_links_validate_bi()` | `test_01_link_objects_positive_snapshots_and_active_state` |
| Section 12.1: Edge attribute immutability | `object_links_guard_bu()` | `test_05_negative_immutability_and_invalid_state` (`OBJECT_LINK_IMMUTABLE`) |
| Section 12.1: Least-privilege matrix table | `REVOKE ... FROM kanban_app` | `test_04_negative_cross_workspace_and_foreign_key_guards` (SQLSTATE 42501) |

---

## 3. Passive Forensic Proof Artifacts

All verification artifacts are stored under `docs/qa/KANBA-37/`:
1. `docs/qa/KANBA-37/unit-test-results.txt`:
   - Command: `uv run pytest database/tests/test_p1_11_object_links.py database/tests/migrations/test_p1_11_migration.py -q --cov=database --cov-branch --cov-report=term-missing`
   - Result: 7 passed in 0.58s, 100% coverage on touched migration and test modules, exit code 0.
2. `docs/qa/KANBA-37/build-check.txt`:
   - Command: `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database`
   - Result: ruff check clean, ruff format clean (27 files), mypy strict clean (25 source files), exit code 0.
3. `docs/qa/KANBA-37/alembic-heads.txt`:
   - Command: `uv run alembic -c database/alembic.ini heads`
   - Result: Single linear head `p1_11_object_links (head)`, exit code 0.
4. `docs/qa/KANBA-37/schema-dump.sql`:
   - Raw PostgreSQL schema dump of `object_links`, `link_type_matrix`, and `\dT+ link_kind`.
5. `docs/qa/KANBA-37/matrix-seed.txt`:
   - Query output of all 96 seeded tuples in `link_type_matrix`.
6. `docs/qa/KANBA-37/git-diff.patch`:
   - Complete unified git diff against `main`.

---

## 4. Unicode Character Verification

Verified zero Unicode dash characters (`U+2014` em-dash or `U+2013` en-dash) repository-wide via `uv run python -m scripts.check_no_dashes --all`.

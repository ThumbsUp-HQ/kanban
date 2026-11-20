# API Specialist Clean-Room Audit & Signoff: KAN-49

- Ticket: KAN-49 (`[KB-AGENT-SEQ-01]`)
- Title: Add DB Migration, Swarm Batch Sequence Allocator & SEQUENCE_SKIPPED Audit Event
- Branch: `feat/KAN-49`
- Base Commit: `837f657d079ebcb8ee88eec86ad2f6df41c1eb33`
- Commit SHA: `c0e4a2b54ca0b933777c11bec8ee80963b5268d9` (parent of UI review `271dbe5f`)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan49-43e0a58b/docs/qa/KAN-49`
- Status: STATUS: APPROVED

---

## 1. Executive Summary & Audit Scope

This clean-room API, Security, and Database Architecture audit inspects ticket KAN-49 on branch `feat/KAN-49` (commit `c0e4a2b5`). KAN-49 establishes agent-safe sequence allocation across the universal object graph, preventing collision with culturally sensitive or agent-triggering loaded numbers while maintaining strict relational integrity, linear migration history, high-concurrency throughput, and cryptographic audit accountability.

The implementation addresses four architectural requirements:
1. Linear Single-Head Database Migration (`p4_24_agent_safe_sequences`):
   - Adds `skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `projects`.
   - Adds `default_skip_loaded_sequence_numbers BOOLEAN NOT NULL DEFAULT FALSE` to `workspace_settings`.
   - Synchronizes SQLAlchemy ORM models with 100% column-level parity (`database/models/projects.py` and `database/models/workspace_settings.py`).
   - Clean linear migration chaining off `p4_23_oidc_link_intent_fk` verified by `kanban-ctl db check-migrations` (63 valid migrations).
2. Pure Sequence Mathematics & Atomic Locking:
   - Pure function `compute_agent_safe_sequence_batch(p_current_seq BIGINT, p_count INTEGER, p_skip_loaded BOOLEAN)` declared `IMMUTABLE PARALLEL SAFE`.
   - Skips only exact integers `ARRAY[13, 69, 88, 404, 420, 666, 1337, 1488]`.
   - Preserves substrings (e.g. `113`, `4040`, `6660`) without false positive filtering.
   - Enforces bounds checking (`1 <= p_count <= 1000`, raising `INVALID_SEQUENCE_COUNT`) and safety loop ceiling (`c_max_skip_iterations = 16`, raising `SEQUENCE_SKIP_CEILING_EXCEEDED`).
   - State-modifying function `allocate_issue_sequences(p_project_id UUID, p_count INTEGER, p_emit_activity BOOLEAN)` declared `SECURITY DEFINER SET search_path = pg_catalog, public`.
   - Acquires `FOR UPDATE` lock once per batch on the target `projects` row, eliminating lock thrashing.
   - Preserves backward compatibility via legacy delegate `allocate_issue_sequence(p_project_id UUID)`.
3. Service Integration & Batch Optimization:
   - Registered `ActivityEventType.SEQUENCE_SKIPPED = "SEQUENCE_SKIPPED"` mapped to `ActivityCategory.SYSTEM` in `kanban/services/activity.py`.
   - Refactored `create_issue` (`kanban/services/issues.py`): allocates sequence via `allocate_issue_sequences(:proj, 1, false)` and records `SEQUENCE_SKIPPED` via Python's `record_activity`, maintaining strict boundary discipline (zero modifications to `serialize_issue`).
   - Refactored `create_issue_tree` (`kanban/issues/tree_service.py`): computes total node count N, executes single batch allocation, assigns sequence IDs in preorder traversal, and emits a single consolidated `SEQUENCE_SKIPPED` event.
   - Refactored `copy_issue` (`kanban/services/issue_copy.py`): computes total count `1 + len(readable_rows)`, executes single batch allocation, assigns sequence IDs across parent and sub-issues, and emits a single consolidated `SEQUENCE_SKIPPED` event.
4. Cryptographic Audit Chain & Concurrency Quality:
   - All `SEQUENCE_SKIPPED` audit events preserve ledger continuity, verified by `verify_activity_chain(workspace_id)`.
   - High-concurrency stress test with 150 concurrent workers allocating 300 total sequences confirms 0 duplicates, 0 sequence leaks, and monotonic ordering.
   - 100% clean static analysis and 0 em/en-dashes.

---

## 2. Detailed Contract & Security Verification

### 2.1 Database Schema & Migration Parity
- Files Audited:
  - `database/migrations/versions/p4_24_agent_safe_sequences.py`
  - `database/migrations/sql/p4_24_agent_safe_sequences.up.sql`
  - `database/migrations/sql/p4_24_agent_safe_sequences.down.sql`
  - `database/models/projects.py`
  - `database/models/workspace_settings.py`
- Schema Invariants:
  - Migration cleanly downgrades back to `p4_23_oidc_link_intent_fk` by dropping batch functions, dropping columns, and restoring the original `allocate_issue_sequence(uuid)` definition.
  - Full lifecycle upgrade -> downgrade -> upgrade tested and verified in `database/tests/migrations/test_p4_24_agent_safe_sequences_migration.py`.
  - Column parity:
    * `projects.skip_loaded_sequence_numbers`: mapped in `Project` as `Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))`.
    * `workspace_settings.default_skip_loaded_sequence_numbers`: mapped in `WorkspaceSettings` as `Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")`.
  - Ownership & Grants:
    * `compute_agent_safe_sequence_batch`: Owner `kanban_migrator`, granted to `kanban_app, app_rls_reader`.
    * `allocate_issue_sequences`: Owner `kanban_migrator`, granted to `kanban_app`.
    * `allocate_issue_sequence`: Owner `kanban_migrator`, granted to `kanban_app`.

### 2.2 PL/pgSQL Function Contracts & Boundary Safety
- Pure Sequence Calculation:
  - `compute_agent_safe_sequence_batch(p_current_seq BIGINT, p_count INTEGER, p_skip_loaded BOOLEAN)`
  - Parameter `p_count`: Enforces `1 <= p_count <= 1000`. Test `test_09_invalid_sequence_count_bounds` confirms that `p_count = 0`, `p_count = -1`, `p_count = 1001`, and `p_count = NULL` all raise exception `INVALID_SEQUENCE_COUNT` (SQLSTATE `P0001`).
  - Loaded sequence array: `ARRAY[13, 69, 88, 404, 420, 666, 1337, 1488]`.
  - Substring preservation: Tested in `test_08_compute_agent_safe_sequence_batch_exact_skipping_1_to_1500`. Integer `113` and `4040` are kept. Exact integer `404` is skipped.
  - Skip iterations ceiling: Maximum of 16 skips prevents infinite loops under catastrophic configuration.
- Concurrency & Lock Isolation:
  - `allocate_issue_sequences` uses `SELECT ... FROM public.projects WHERE id = p_project_id FOR UPDATE`.
  - This ensures serialization of concurrent allocations for the same project without deadlocks or counter races.
  - Verified by `test_06_sequence_concurrency_20_connections` (20 concurrent workers) and `test_07_sequence_concurrency_150_connections_batches` (150 workers allocating batches of 2 = 300 total sequences). Zero collisions or gaps occurred.

### 2.3 Service Caller Refactoring & Audit Event Integrity
- Event Registration (`kanban/services/activity.py`):
  - `ActivityEventType.SEQUENCE_SKIPPED = "SEQUENCE_SKIPPED"` added to `ActivityEventType` enum.
  - Mapped to `ActivityCategory.SYSTEM` in `EVENT_CATEGORY` dictionary.
  - Tested in `test_activity_event_type_registration`.
- Service Callers:
  - `create_issue` (`kanban/services/issues.py`):
    * Invokes `allocate_issue_sequences(:proj, 1, false)`.
    * If `skipped_sequences` is non-empty, calls `record_activity` with `workspace_id`, `project.id`, `caller.principal_id`, `ActivityEventType.SEQUENCE_SKIPPED`, and payload containing `project_key`, `skipped_sequences`, `allocated_sequence`, and `reason: "agent_safe_sequence_numbering"`.
    * Scope Boundary Audit: Confirmed 0 modifications to `serialize_issue` or unrelated issue endpoints.
  - `create_issue_tree` (`kanban/issues/tree_service.py`):
    * Replaced per-node serial `allocate_issue_sequence` with a single batch allocation for `len(resolved_nodes_data)`.
    * Sequences assigned sequentially via preorder queue traversal.
    * Single `SEQUENCE_SKIPPED` event emitted if any sequence in the tree was skipped.
  - `copy_issue` (`kanban/services/issue_copy.py`):
    * Replaced per-issue serial `allocate_issue_sequence` with a single batch allocation for `1 + len(readable_rows)`.
    * First sequence allocated to the root cloned issue; subsequent sequences allocated to cloned sub-issues.
    * Single `SEQUENCE_SKIPPED` event emitted if any sequence was skipped.
- Audit Ledger Continuity:
  - Tested via `test_10_allocate_issue_sequences_and_verify_activity_chain` and `test_create_issue_skips_loaded_and_records_activity`.
  - Cryptographic verification function `verify_activity_chain(:ws)` confirms hash chain validity (`is_valid = True`).

---

## 3. Test Suite & Coverage Verification

- Migration Test Suite (`unit-test-results.txt`):
  - `database/tests/migrations/test_p4_24_agent_safe_sequences_migration.py::test_p4_24_agent_safe_sequences_migration_lifecycle`: PASSED (0.63s).
- Database Concurrency & Batch Suite (`unit-test-results.txt`):
  - `database/tests/test_p1_05_sequence_concurrency.py`: 5 passed in 0.72s.
    * `test_06_sequence_concurrency_20_connections`: PASSED
    * `test_07_sequence_concurrency_150_connections_batches`: PASSED
    * `test_08_compute_agent_safe_sequence_batch_exact_skipping_1_to_1500`: PASSED
    * `test_09_invalid_sequence_count_bounds`: PASSED
    * `test_10_allocate_issue_sequences_and_verify_activity_chain`: PASSED
- Service Audit Suite (`unit-test-results.txt`):
  - `kanban/tests/services/test_agent_safe_sequences.py`: 5 passed in 0.88s.
    * `test_activity_event_type_registration`: PASSED
    * `test_create_issue_skips_loaded_and_records_activity`: PASSED
    * `test_create_issue_does_not_skip_when_disabled`: PASSED
    * `test_create_issue_tree_batch_sequence_and_skip_activity`: PASSED
    * `test_copy_issue_batch_sequence_and_skip_activity`: PASSED
- Existing Regression Suite (`unit-test-results.txt`):
  - `test_issue_trees.py`, `test_issue_copy.py`, `test_issues.py`: 34 passed in 17.27s.
  - ORM Models statement coverage: `database/models/projects.py` (98%), `database/models/workspace_settings.py` (100%), `kanban/services/activity.py` (95%).
- Static Analysis Gates (`build-or-typecheck.txt`):
  - `kanban-ctl db check-migrations`: PASS (All 63 migrations valid. Single head: `p4_24_agent_safe_sequences`).
  - `ruff check database kanban`: PASS (0 errors, all checks passed).
  - `mypy database kanban`: PASS (Success: no issues found in 748 source files).
  - `lint-imports`: PASS (Unidirectional module layers `agent -> mcp -> kanban -> database` KEPT, `mcp` forbidden from importing `database` KEPT; Contracts: 2 kept, 0 broken).
  - `check_no_dashes`: PASS (0 em/en-dashes across codebase).

---

## 4. Security & Isolation Matrix

| Capability / Invariant | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Single Head Migration Chain | Linear chain off `p4_23_oidc_link_intent_fk` | Validated by `check-migrations` (63 valid) | PASS |
| Clean Migration Downgrade | Drops new functions/columns, restores legacy | Validated by migration lifecycle test | PASS |
| Column-Level ORM Parity | Exact match on `projects` and `workspace_settings` | Models updated with server_default | PASS |
| Pure Sequence Function | `IMMUTABLE PARALLEL SAFE`, no side-effects | `compute_agent_safe_sequence_batch` | PASS |
| Bound Checks Enforcement | `1 <= count <= 1000`, max 16 skip iterations | Validated by `test_09` with `INVALID_SEQUENCE_COUNT` | PASS |
| Substring Preservation | Preserves `113`, `4040`, skips exact integers | Validated by `test_08` across 1..1500 | PASS |
| Atomic Project Locking | `FOR UPDATE` lock on `projects` row | Single lock per batch, 0 counter races | PASS |
| Concurrency Throughput | Clean allocation under high concurrency | Tested with 150 concurrent connection workers | PASS |
| Hash-Chained Audit Event | `SEQUENCE_SKIPPED` in `SYSTEM` category | Validated with `verify_activity_chain` | PASS |
| Boundary Isolation | Do not touch `serialize_issue` in `issues.py` | Strictly verified in git diff | PASS |
| Unidirectional Layering | Layer hierarchy preserved | `lint-imports` confirms 2 kept, 0 broken | PASS |
| Dash Character Policy | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Verdict & Signoff

STATUS: APPROVED

The database migration `p4_24_agent_safe_sequences`, ORM model parity, PL/pgSQL batch sequence allocation functions, service layer refactoring (`create_issue`, `create_issue_tree`, `copy_issue`), and `SEQUENCE_SKIPPED` cryptographic audit records for KAN-49 on branch `feat/KAN-49` (commit `c0e4a2b5`) have been thoroughly audited, verified against strict concurrency and migration fixtures, and certified. Dual specialist gate (API Specialist + UI Specialist) is complete. Ready for Clean-Room Reality-Checker QA.
